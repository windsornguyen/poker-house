import {QueryClient} from '@tanstack/react-query';
import {createAuthClient} from 'better-auth/react';

/** Better Auth's client. The API is this site's own, so it needs no base URL. */
export const authClient = createAuthClient();

/** The cache Better Auth UI keeps the session in, shared with route loaders. */
export const queryClient = new QueryClient();

/**
 * How often an open page re-reads the session. Each read re-issues the
 * five-minute cookie the Worker checks, before that cookie lapses.
 */
export const SESSION_REFRESH_MS = 4 * 60 * 1000;
