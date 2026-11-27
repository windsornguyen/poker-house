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

// Modified for Poker House: poker-only application integration.

import process from 'node:process';

import {reactRouter} from '@react-router/dev/vite';
import babel from '@rolldown/plugin-babel';
import react, {reactCompilerPreset} from '@vitejs/plugin-react';
import {defineConfig} from 'vitest/config';

import {thirdPartyNotices} from './scripts/third_party_notices.ts';

// The server `npm run dev` sends the client's API requests to:
// `python -m poker_house_server`, on its default port unless
// POKER_HOUSE_SERVER names another. The request keeps its own Host and
// Origin, the dev server's, so the server's same-origin check passes.
const API_SERVER = process.env['POKER_HOUSE_SERVER'] ?? 'http://127.0.0.1:8787';

export default defineConfig({
  plugins: [
    process.env['VITEST'] ? react() : reactRouter(),
    babel({presets: [reactCompilerPreset()]}),
    thirdPartyNotices(),
  ],
  server: {proxy: {'/api': {target: API_SERVER, changeOrigin: false}}},
  test: {
    environment: 'jsdom',
    // Browser tests use jsdom's origin-scoped storage, not Node's file store.
    execArgv: ['--no-experimental-webstorage'],
    include: ['{scripts,src}/**/*_test.{ts,tsx}'],
    setupFiles: ['src/testing/setup.ts'],
    // Twice app_test's 5 s `until`, so a slow wait reports its failing
    // check rather than the test timeout, and two waits fit in one test.
    testTimeout: 10000,
  },
});
