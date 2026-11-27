import {QueryClientProvider} from '@tanstack/react-query';
import {
  type ComponentPropsWithoutRef,
  type JSX,
  type ReactNode,
  useEffect,
} from 'react';
import {
  Link,
  Links,
  Meta,
  Outlet,
  Scripts,
  ScrollRestoration,
  useNavigate,
} from 'react-router';

import {AuthProvider} from '@/components/auth/auth-provider';
import {Toaster} from '@/components/ui/sonner';

import {
  SESSION_REFRESH_MS,
  authClient,
  queryClient,
} from './session/auth_client.ts';

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
  const navigate = useNavigate();
  useEffect(() => {
    const timer = setInterval(() => {
      void authClient.getSession({query: {disableCookieCache: true}});
    }, SESSION_REFRESH_MS);
    return () => {
      clearInterval(timer);
    };
  }, []);
  return (
    <QueryClientProvider client={queryClient}>
      <AuthProvider
        authClient={authClient}
        queryClient={queryClient}
        navigate={({to, replace}) => {
          void navigate(to, {replace: replace ?? false});
        }}
        Link={RouterLink}
        emailAndPassword={{requireEmailVerification: true}}
      >
        <Outlet />
        <Toaster />
      </AuthProvider>
    </QueryClientProvider>
  );
}

type RouterLinkProps = {
  readonly href: string;
  readonly className?: string;
  readonly children?: ReactNode;
} & Pick<
  ComponentPropsWithoutRef<'a'>,
  'aria-disabled' | 'tabIndex' | 'onClick'
>;

function RouterLink({href, ...props}: RouterLinkProps): JSX.Element {
  return <Link to={href} {...props} />;
}
