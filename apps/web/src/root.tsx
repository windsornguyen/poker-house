import type {JSX, ReactNode} from 'react';
import {Links, Meta, Outlet, Scripts, ScrollRestoration} from 'react-router';

import './styles/theme.css';
import './styles/tokens.css';
import './styles/base.css';
import './styles/dock.css';

/** Applies the stored theme before the first paint, as ThemeProvider resolves it. */
export const FIRST_PAINT_THEME = `      (() => {
        let preference = null;
        try {
          preference = localStorage.getItem('poker_house.theme');
        } catch {
        }
        const dark =
          preference === 'dark' ||
          (preference !== 'light' &&
            matchMedia('(prefers-color-scheme: dark)').matches);
        const theme = dark ? 'dark' : 'light';
        document.documentElement.dataset.theme = theme;
        document.documentElement.style.colorScheme = theme;
      })();`;

/** The document every page renders into. */
export function Layout({
  children,
}: {
  readonly children: ReactNode;
}): JSX.Element {
  return (
    <html lang="en">
      <head>
        <meta charSet="utf-8" />
        <meta name="viewport" content="width=device-width, initial-scale=1" />
        <link rel="icon" href="data:," />
        <script dangerouslySetInnerHTML={{__html: FIRST_PAINT_THEME}} />
        <Meta />
        <Links />
      </head>
      <body>
        {children}
        <ScrollRestoration />
        <Scripts />
      </body>
    </html>
  );
}

/** The root route. */
export default function Root(): JSX.Element {
  return <Outlet />;
}
