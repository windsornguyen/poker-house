import {viewPaths} from '@better-auth-ui/core';
import type {Config} from '@react-router/dev/config';

export default {
  appDirectory: 'src',
  buildDirectory: 'dist',
  ssr: false,
  prerender: [
    '/',
    '/game/poker_house',
    '/game/poker_house_acpc',
    ...Object.values(viewPaths.auth).map(path => `/auth/${path}`),
  ],
} satisfies Config;
