import {getCookieCache} from 'better-auth/cookies';

interface Env {
  readonly API_ORIGIN: string;
  readonly AUTH_ORIGIN: string;
  readonly PORT_KEY: string;
  readonly AUTH_PORT_KEY: string;
  readonly BETTER_AUTH_SECRET: string;
}

const SAFE_METHODS = new Set(['GET', 'HEAD']);

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
    if (!url.pathname.startsWith('/api/')) {
      return new Response('Not found', {status: 404});
    }
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
