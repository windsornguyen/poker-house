import {type BetterAuthOptions, betterAuth} from 'better-auth';
import {Pool} from 'pg';

const WEEK_SECONDS = 7 * 24 * 60 * 60;
// How long the Worker trusts a session without asking this service, so a
// removed player or a revoked session loses access within this time.
const COOKIE_CACHE_SECONDS = 5 * 60;

function required(name: string): string {
  const value = process.env[name];
  if (value === undefined || value === '') {
    throw new Error(`${name} must be set.`);
  }
  return value;
}

const allowed = new Set(required('POKER_HOUSE_PLAYERS').split(','));

/** Better Auth's configuration, shared by the server and the migration. */
export const options = {
  baseURL: required('BETTER_AUTH_URL'),
  secret: required('BETTER_AUTH_SECRET'),
  database: new Pool({
    connectionString: required('DATABASE_URL'),
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
