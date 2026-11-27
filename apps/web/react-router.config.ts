import {viewPaths} from '@better-auth-ui/core';
import type {Config} from '@react-router/dev/config';

export default {
  appDirectory: 'src',
  buildDirectory: 'dist',
  ssr: false,
  prerender: [
    '/',
    '/game/doggybank',
    '/game/doggybank_acpc',
    '/admin',
    '/docs',
    ...Object.values(viewPaths.auth).map(path => `/auth/${path}`),
  ],
} satisfies Config;
