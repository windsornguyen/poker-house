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
  // The emails that may make an account, comma-separated.
  POKER_HOUSE_PLAYERS: z
    .string()
    .transform(list => list.split(','))
    .pipe(z.array(z.email()).min(1)),
});
const env = Env.parse(process.env);
const allowed = new Set(env.POKER_HOUSE_PLAYERS);

/** Better Auth's configuration, shared by the server and the migration. */
export const options = {
  baseURL: env.BETTER_AUTH_URL,
  secret: env.BETTER_AUTH_SECRET,
  database: new Pool({
    connectionString: env.DATABASE_URL,
    options: '-c search_path=auth',
  }),
  emailAndPassword: {enabled: true},
  session: {
    expiresIn: WEEK_SECONDS,
    cookieCache: {enabled: true, maxAge: COOKIE_CACHE_SECONDS},
  },
  databaseHooks: {
    user: {
      create: {
        before: async user =>
          Promise.resolve(allowed.has(user.email) ? {data: user} : false),
      },
    },
  },
} satisfies BetterAuthOptions;

/** The Better Auth instance the server mounts. */
export const auth = betterAuth(options);
