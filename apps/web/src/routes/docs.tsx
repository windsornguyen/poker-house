import {type JSX, Suspense, lazy} from 'react';

import {ThemeProvider} from '../theme/theme-provider.tsx';

// Loaded only on this page, and only in the browser: Scalar is large and reads the window.
const Reference = lazy(() =>
  import('../docs/reference.tsx').then(module => ({default: module.Reference})),
);

/** The docs page's title. */
export function meta(): Array<{title: string}> {
  return [{title: 'Docs · Doggybank'}];
}

/** Renders the page in the browser only, after the prerendered fallback. */
export function clientLoader(): null {
  return null;
}

/** The empty page shown until the reference loads. */
export function HydrateFallback(): JSX.Element {
  return <main className="min-h-svh" />;
}

/** The quickstart and every API call, for people and agents. */
export default function Docs(): JSX.Element {
  return (
    <ThemeProvider>
      <Suspense fallback={<HydrateFallback />}>
        <Reference />
      </Suspense>
    </ThemeProvider>
  );
}
