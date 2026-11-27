import type {JSX} from 'react';

import {App} from '../app.tsx';
import {ThemeProvider} from '../theme/theme_provider.tsx';

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

/** Renders the table in the browser, where the session lives. */
export function clientLoader(): null {
  return null;
}

/** The prerendered page, shown until the table loads. */
export function HydrateFallback(): JSX.Element {
  return (
    <main className="landing">
      <h1>Poker House</h1>
      <p>
        Heads-up no-limit Texas hold’em against friends and your own bots, live
        in the browser.
      </p>
    </main>
  );
}

/** The lobby or a game's table. */
export default function Table(): JSX.Element {
  return (
    <ThemeProvider>
      <App />
    </ThemeProvider>
  );
}
