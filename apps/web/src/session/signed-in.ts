import {fetchSession} from '@better-auth-ui/core';

import {authClient, queryClient} from './auth-client.ts';

/**
 * Resolves whether a session reader found a signed-in player, treating errors as signed out.
 * It lives outside the route module because React Router splits `clientLoader` into its own
 * chunk, which can import a module but cannot see the route's other exports.
 */
export async function loadSignedIn(
  readSession: () => Promise<unknown> = () =>
    fetchSession(queryClient, authClient),
): Promise<{signedIn: boolean}> {
  const session = await readSession().catch(() => null);
  return {signedIn: session !== null && session !== undefined};
}
