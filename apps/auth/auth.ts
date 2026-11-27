import {type BetterAuthOptions, betterAuth} from 'better-auth';
import {Pool} from 'pg';
import * as z from 'zod';

const WEEK_SECONDS = 7 * 24 * 60 * 60;
// How long the Worker trusts a session without asking this service, so a
// removed player or a revoked session loses access within this time.
const COOKIE_CACHE_SECONDS = 5 * 60;

const Env = z.object({
  BETTER_AUTH_URL: z.url(),
  BETTER_AUTH_SECRET: z.string().min(32),
  DATABASE_URL: z.url(),
  MAIL_KEY: z.string().min(32),
});
const env = Env.parse(process.env);
/** The connection pool Better Auth and the readiness probe share. */
export const pool = new Pool({
  connectionString: env.DATABASE_URL,
  options: '-c search_path=auth',
});

/** The emails the Worker sends: to confirm an address, and to reset a password. */
type Mail = 'verify' | 'reset';

/** Asks the Worker to email `to` the link `url`, for `mail`. */
async function sendMail(mail: Mail, to: string, url: string): Promise<void> {
  const sent = await fetch(new URL(`/mail/${mail}`, env.BETTER_AUTH_URL), {
    method: 'POST',
    headers: {
      Authorization: `Bearer ${env.MAIL_KEY}`,
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({to, url}),
  });
  if (!sent.ok) {
    throw new Error(
      `The ${mail} email to ${to} failed: ${String(sent.status)} ${await sent.text()}`,
    );
  }
}

/** Better Auth's configuration, shared by the server and the migration. */
export const options = {
  baseURL: env.BETTER_AUTH_URL,
  secret: env.BETTER_AUTH_SECRET,
  database: pool,
  emailAndPassword: {
    enabled: true,
    requireEmailVerification: true,
    sendResetPassword: async ({user, url}) =>
      sendMail('reset', user.email, url),
  },
  emailVerification: {
    sendOnSignUp: true,
    autoSignInAfterVerification: true,
    sendVerificationEmail: async ({user, url}) =>
      sendMail('verify', user.email, url),
  },
  session: {
    expiresIn: WEEK_SECONDS,
    cookieCache: {enabled: true, maxAge: COOKIE_CACHE_SECONDS},
  },
} satisfies BetterAuthOptions;

/** The Better Auth instance the server mounts. */
export const auth = betterAuth(options);
