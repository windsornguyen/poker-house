import {fetchSession} from '@better-auth-ui/core';
import {useAuthenticate} from '@better-auth-ui/react';
import type {JSX} from 'react';
import {redirect} from 'react-router';

import {App} from '../app.tsx';
import {authClient, queryClient} from '../session/auth-client.ts';
import {ThemeProvider} from '../theme/theme-provider.tsx';

/** The page's title and description, which search engines index. */
export function meta(): Array<{
  title?: string;
  name?: string;
  content?: string;
}> {
  return [
    {title: 'Poker House'},
    {
      name: 'description',
      content:
        'Heads-up no-limit Texas hold’em against friends and your own bots, live in the browser.',
    },
  ];
}

/** Sends a visitor without a session to sign in, and back here after. */
export async function clientLoader({
  request,
}: {
  request: Request;
}): Promise<null> {
  const session = await fetchSession(queryClient, authClient);
  if (session === null) {
    const {pathname, search} = new URL(request.url);
    throw redirect(
      `/auth/sign-in?redirectTo=${encodeURIComponent(pathname + search)}`,
    );
  }
  return null;
}

/** The prerendered page, shown until the table loads. */
export function HydrateFallback(): JSX.Element {
  return (
    <main className="flex min-h-svh flex-col items-center justify-center gap-2 p-6 text-center">
      <h1 className="text-2xl font-semibold tracking-tight">Poker House</h1>
      <p className="max-w-md text-sm text-muted-foreground">
        Heads-up no-limit Texas hold’em against friends and your own bots, live
        in the browser.
      </p>
    </main>
  );
}

/** The lobby or a game's table. */
export default function Table(): JSX.Element {
  const {data: session} = useAuthenticate(authClient);
  if (!session) return <HydrateFallback />;
  return (
    <ThemeProvider>
      <App />
    </ThemeProvider>
  );
}
