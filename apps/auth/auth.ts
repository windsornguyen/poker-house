import {type BetterAuthOptions, betterAuth} from 'better-auth';
import {Pool} from 'pg';

const WEEK_SECONDS = 7 * 24 * 60 * 60;

function required(name: string): string {
  const value = process.env[name];
  if (value === undefined || value === '') {
    throw new Error(`${name} must be set.`);
  }
  return value;
}

const allowed = new Set(required('POKER_HOUSE_PLAYERS').split(','));

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
    cookieCache: {enabled: true, maxAge: WEEK_SECONDS},
  },
  databaseHooks: {
    user: {
      create: {
        before: async (user) => Promise.resolve(allowed.has(user.email) ? {data: user} : false),
      },
    },
  },
} satisfies BetterAuthOptions;

export const auth = betterAuth(options);
