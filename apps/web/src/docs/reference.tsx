import {ApiReferenceReact} from '@scalar/api-reference-react';
import '@scalar/api-reference-react/style.css';
import type {JSX} from 'react';

import {useTheme} from '../theme/theme-provider.tsx';

// Scalar draws with its own variables. Pointing them at the site's tokens gives the docs
// the site's type, colors and radius in either theme, with no styles of their own.
const SITE_TOKENS = `
.light-mode, .dark-mode {
  --scalar-font: var(--font-sans);
  --scalar-background-1: var(--background);
  --scalar-background-2: var(--muted);
  --scalar-background-3: var(--accent);
  --scalar-color-1: var(--foreground);
  --scalar-color-2: var(--muted-foreground);
  --scalar-color-3: var(--muted-foreground);
  --scalar-color-accent: var(--primary);
  --scalar-border-color: var(--border);
  --scalar-radius: calc(var(--radius) - 2px);
  --scalar-radius-lg: var(--radius);
}`;

/** The API reference, drawn from the site's published OpenAPI document. */
export function Reference(): JSX.Element {
  const {theme} = useTheme();
  return (
    <ApiReferenceReact
      configuration={{
        url: '/openapi.json',
        theme: 'none',
        withDefaultFonts: false,
        hideClientButton: true,
        hideDarkModeToggle: true,
        forceDarkModeState: theme,
        customCss: SITE_TOKENS,
      }}
    />
  );
}
