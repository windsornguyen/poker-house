import type {JSX} from 'react';

import {App} from '../app.tsx';
import {HomePage} from '../home.tsx';
import {loadSignedIn} from '../session/signed-in.ts';
import {ThemeProvider} from '../theme/theme-provider.tsx';

/** The home page's title and description, which search engines index. */
export function meta(): Array<{
  title?: string;
  name?: string;
  content?: string;
}> {
  return [
    {title: 'Doggybank'},
    {
      name: 'description',
      content:
        'Heads-up no-limit Texas hold’em for people and agents, with 1,000 welcome chips and an HTTP API.',
    },
  ];
}

/** Checks whether the visitor holds a session before choosing the landing page or lobby. */
export function clientLoader(): Promise<{signedIn: boolean}> {
  return loadSignedIn();
}

/** The prerendered landing page, shown before hydration and kept when signed out. */
export function HydrateFallback(): JSX.Element {
  return <HomePage />;
}

/** Shows the public landing page to signed-out visitors and the lobby to signed-in players. */
export default function Home({
  loaderData,
}: {
  readonly loaderData: {readonly signedIn: boolean};
}): JSX.Element {
  return (
    <ThemeProvider>
      {loaderData.signedIn ? <App /> : <HomePage />}
    </ThemeProvider>
  );
}
