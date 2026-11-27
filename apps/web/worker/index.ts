import {getCookieCache} from 'better-auth/cookies';

interface Env {
  readonly API_ORIGIN: string;
  readonly AUTH_ORIGIN: string;
  readonly PORT_KEY: string;
  readonly AUTH_PORT_KEY: string;
  readonly BETTER_AUTH_SECRET: string;
  readonly EMAIL: SendEmail;
  readonly MAIL_KEY: string;
  readonly MAIL_FROM: string;
}

interface Verification {
  readonly to: string;
  readonly url: string;
}

const SAFE_METHODS = new Set(['GET', 'HEAD']);
const MAIL_PATH = '/mail/verify';
const ADDRESS = /^[^\s@,<>]+@[^\s@,<>]+$/;
const ENTITIES: Record<string, string> = {
  '&': '&amp;',
  '<': '&lt;',
  '>': '&gt;',
  '"': '&quot;',
};

function notFound(): Response {
  return new Response('Not found', {status: 404});
}

/** Whether `request` carries the Machine's mail key, compared in constant time. */
async function hasMailKey(request: Request, env: Env): Promise<boolean> {
  const encoder = new TextEncoder();
  const [given, expected] = await Promise.all(
    [request.headers.get('Authorization') ?? '', `Bearer ${env.MAIL_KEY}`].map(
      async text => crypto.subtle.digest('SHA-256', encoder.encode(text)),
    ),
  );
  if (given === undefined || expected === undefined) return false;
  return crypto.subtle.timingSafeEqual(given, expected);
}

/**
 * The address and link a verification email carries, or null. The link must
 * be this site's own verification page, so the route cannot relay other mail.
 */
function verificationOf(body: unknown, site: string): Verification | null {
  if (typeof body !== 'object' || body === null) return null;
  const {to, url} = body as Record<string, unknown>;
  if (typeof to !== 'string' || !ADDRESS.test(to)) return null;
  if (typeof url !== 'string') return null;
  if (!url.startsWith(`${site}/api/auth/verify-email?`)) return null;
  return {to, url};
}

/** Sends the email that confirms a player owns their address. */
async function sendVerification(request: Request, env: Env): Promise<Response> {
  if (request.method !== 'POST' || !(await hasMailKey(request, env))) {
    return notFound();
  }
  const body: unknown = await request.json().catch(() => null);
  const verification = verificationOf(body, new URL(request.url).origin);
  if (verification === null) return notFound();
  const {to, url} = verification;
  const link = url.replaceAll(
    /[&<>"]/g,
    character => ENTITIES[character] ?? character,
  );
  try {
    await env.EMAIL.send({
      from: {email: env.MAIL_FROM, name: 'Poker House'},
      to,
      subject: 'Confirm your email',
      text: `Confirm your email: ${url}`,
      html: `<p><a href="${link}">Confirm your email</a></p>`,
    });
  } catch (e) {
    return new Response(e instanceof Error ? e.message : String(e), {
      status: 502,
    });
  }
  return new Response(null, {status: 204});
}

/** Forwards `request` to `origin`, unlocking its Dedalus port with `key`. */
function forward(
  request: Request,
  origin: string,
  key: string,
): Promise<Response> {
  const url = new URL(request.url);
  const upstream = new Request(origin + url.pathname + url.search, request);
  upstream.headers.set('X-Dedalus-Port-Key', key);
  return fetch(upstream);
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const url = new URL(request.url);
    if (url.pathname === MAIL_PATH) return sendVerification(request, env);
    if (!url.pathname.startsWith('/api/')) return notFound();
    const origin = request.headers.get('Origin');
    if (
      !SAFE_METHODS.has(request.method) &&
      origin !== null &&
      origin !== url.origin
    ) {
      return new Response('Cross-origin request refused', {status: 403});
    }
    if (url.pathname.startsWith('/api/auth/')) {
      return forward(request, env.AUTH_ORIGIN, env.AUTH_PORT_KEY);
    }
    const session = await getCookieCache(request, {
      secret: env.BETTER_AUTH_SECRET,
      isSecure: url.protocol === 'https:',
    });
    if (session === null) {
      return new Response('Sign in required', {status: 401});
    }
    const game = new Request(request);
    game.headers.delete('Cookie');
    game.headers.delete('Origin');
    return forward(game, env.API_ORIGIN, env.PORT_KEY);
  },
} satisfies ExportedHandler<Env>;
