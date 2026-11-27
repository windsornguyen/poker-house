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
});
const env = Env.parse(process.env);
const pool = new Pool({
  connectionString: env.DATABASE_URL,
  // public holds citext's operators; without it the player lookup compares as
  // case-sensitive text. auth stays first, where the auth tables live.
  options: '-c search_path=auth,public',
});

/** Whether `email` is on the player list, which decides who may sign up. */
async function isPlayer(email: string): Promise<boolean> {
  const found = await pool.query(
    'select 1 from poker.player where email = $1',
    [email],
  );
  return found.rowCount === 1;
}

/** Better Auth's configuration, shared by the server and the migration. */
export const options = {
  baseURL: env.BETTER_AUTH_URL,
  secret: env.BETTER_AUTH_SECRET,
  database: pool,
  emailAndPassword: {enabled: true},
  session: {
    expiresIn: WEEK_SECONDS,
    cookieCache: {enabled: true, maxAge: COOKIE_CACHE_SECONDS},
  },
  databaseHooks: {
    user: {
      create: {
        before: async user =>
          (await isPlayer(user.email)) ? {data: user} : false,
      },
    },
  },
} satisfies BetterAuthOptions;

/** The Better Auth instance the server mounts. */
export const auth = betterAuth(options);
