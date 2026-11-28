// Copyright 2026 DeepMind Technologies Limited
//
// Licensed under the Apache License, Version 2.0 (the "License");
// you may not use this file except in compliance with the License.
// You may obtain a copy of the License at
//
//      http://www.apache.org/licenses/LICENSE-2.0
//
// Unless required by applicable law or agreed to in writing, software
// distributed under the License is distributed on an "AS IS" BASIS,
// WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
// See the License for the specific language governing permissions and
// limitations under the License.

// Modified for Doggybank: poker-only application integration.

import process from 'node:process';

import {reactRouter} from '@react-router/dev/vite';
import babel from '@rolldown/plugin-babel';
import tailwindcss from '@tailwindcss/vite';
import {reactCompilerPreset} from '@vitejs/plugin-react';
import {defineConfig} from 'vite-plus';

import {thirdPartyNotices} from './scripts/third-party-notices.ts';

// `pnpm dev` sends /api to the Worker running under `wrangler dev`
// (DOGGYBANK_WORKER), which signs the player in and forwards to the local
// game server and sign-in service, as it does in production.
const WORKER = process.env['DOGGYBANK_WORKER'] ?? 'http://127.0.0.1:8789';

export default defineConfig({
  plugins: [
    tailwindcss(),
    reactRouter(),
    babel({presets: [reactCompilerPreset()]}),
    thirdPartyNotices(),
  ],
  resolve: {tsconfigPaths: true},
  optimizeDeps: {
    include: [
      '@better-auth-ui/core',
      '@tanstack/react-query',
      'better-auth/react',
      'react-router',
    ],
  },
  server: {
    proxy: {
      '/api': {target: WORKER, changeOrigin: false},
    },
  },
});
