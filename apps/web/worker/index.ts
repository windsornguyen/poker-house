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

/** An email the Machine may ask for: the site page its link must open. */
interface MailKind {
  readonly page: string;
  readonly action: string;
}

const MAILS = new Map<string, MailKind>([
  [
    '/mail/verify',
    {page: '/api/auth/verify-email?', action: 'Confirm your email'},
  ],
  [
    '/mail/reset',
    {page: '/api/auth/reset-password/', action: 'Reset your password'},
  ],
]);

const SAFE_METHODS = new Set(['GET', 'HEAD']);
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

/** The recipient and link in `body`, or null unless the link opens `page`. */
function linkOf(body: unknown, page: string): {to: string; url: string} | null {
  if (typeof body !== 'object' || body === null) return null;
  const {to, url} = body as Record<string, unknown>;
  if (typeof to !== 'string' || typeof url !== 'string') return null;
  if (!url.startsWith(page)) return null;
  return {to, url};
}

/** Sends the email `kind` names: one link, to this site. */
async function sendMail(
  request: Request,
  env: Env,
  kind: MailKind,
): Promise<Response> {
  if (request.method !== 'POST' || !(await hasMailKey(request, env))) {
    return notFound();
  }
  const body: unknown = await request.json().catch(() => null);
  const link = linkOf(body, new URL(request.url).origin + kind.page);
  if (link === null) return notFound();
  const href = Object.entries(ENTITIES).reduce(
    (text, [char, entity]) => text.replaceAll(char, entity),
    link.url,
  );
  try {
    await env.EMAIL.send({
      from: {email: env.MAIL_FROM, name: 'Poker House'},
      to: link.to,
      subject: kind.action,
      text: `${kind.action}: ${link.url}`,
      html: `<p><a href="${href}">${kind.action}</a></p>`,
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
    const mail = MAILS.get(url.pathname);
    if (mail !== undefined) return sendMail(request, env, mail);
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
