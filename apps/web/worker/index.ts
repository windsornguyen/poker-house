import {createRemoteJWKSet, jwtVerify} from 'jose';

interface Env {
  readonly API_ORIGIN: string;
  readonly PORT_KEY: string;
  readonly ACCESS_TEAM: string;
  readonly ACCESS_AUD: string;
}

const keys = new Map<string, ReturnType<typeof createRemoteJWKSet>>();

/** Whether Cloudflare Access signed this request for this application. */
async function signedIn(request: Request, env: Env): Promise<boolean> {
  const token = request.headers.get('Cf-Access-Jwt-Assertion');
  if (token === null) return false;
  const issuer = `https://${env.ACCESS_TEAM}.cloudflareaccess.com`;
  let jwks = keys.get(issuer);
  if (jwks === undefined) {
    jwks = createRemoteJWKSet(new URL(`${issuer}/cdn-cgi/access/certs`));
    keys.set(issuer, jwks);
  }
  try {
    await jwtVerify(token, jwks, {issuer, audience: env.ACCESS_AUD});
    return true;
  } catch {
    return false;
  }
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const url = new URL(request.url);
    if (!url.pathname.startsWith('/api/')) {
      return new Response('Not found', {status: 404});
    }
    if (!(await signedIn(request, env))) {
      return new Response('Sign in required', {status: 401});
    }
    const upstream = new Request(
      env.API_ORIGIN + url.pathname + url.search,
      request,
    );
    upstream.headers.set('X-Dedalus-Port-Key', env.PORT_KEY);
    upstream.headers.delete('Cookie');
    upstream.headers.delete('Cf-Access-Jwt-Assertion');
    return fetch(upstream);
  },
} satisfies ExportedHandler<Env>;
