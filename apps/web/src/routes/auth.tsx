import {viewPaths} from '@better-auth-ui/core';
import type {JSX} from 'react';
import {useParams} from 'react-router';

import {Auth} from '@/components/auth/auth';

const PATHS = new Set<string>(Object.values(viewPaths.auth));

/** The sign-in pages' title. */
export function meta(): Array<{title: string}> {
  return [{title: 'Sign in · Doggybank'}];
}

/** Refuses a path that names no sign-in view. */
export function clientLoader({params}: {params: {path?: string}}): null {
  if (!PATHS.has(params.path ?? '')) {
    throw new Response('Not found', {status: 404});
  }
  return null;
}

/** The empty page shown until the view loads. */
export function HydrateFallback(): JSX.Element {
  return <main className="flex min-h-svh items-center justify-center p-6" />;
}

/** Sign in, sign up, and the other account views, by path. */
export default function AuthPage(): JSX.Element {
  const {path = ''} = useParams();
  return (
    <main className="flex min-h-svh items-center justify-center p-6">
      <Auth path={path} />
    </main>
  );
}
