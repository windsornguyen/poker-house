// Copyright 2026 Doggybank contributors
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

import {MemoryRouter} from 'react-router';
import {afterEach, beforeEach, describe, expect, it} from 'vite-plus/test';

import {AGENT_TURN_SNIPPET, HomePage} from './home.tsx';
import Home, {loadSignedIn} from './routes/home.tsx';
import {fakeColorScheme} from './testing/color-scheme.ts';
import {type Rendered, render} from './testing/render.tsx';

let rendered: Rendered | undefined;

beforeEach(() => {
  fakeColorScheme(false);
});

afterEach(() => {
  rendered?.unmount();
  rendered = undefined;
});

describe('the public landing page', () => {
  it('links to sign-up, sign-in, and the docs, and shows the three steps and turn snippet', () => {
    rendered = render(
      <MemoryRouter>
        <HomePage />
      </MemoryRouter>,
    );
    const {container} = rendered;

    const links = [...container.querySelectorAll('a')].map(anchor => [
      anchor.textContent.trim(),
      anchor.getAttribute('href'),
    ]);
    expect(links).toEqual([
      ['Doggybank', '/'],
      ['Docs', 'https://docs.doggybank.io'],
      ['Sign in', '/auth/sign-in'],
      ['Create account', '/auth/sign-up'],
      ['Create an account', '/auth/sign-up'],
      ['Read the docs', 'https://docs.doggybank.io'],
      ['Read the agent guide', 'https://docs.doggybank.io/agents'],
      ['Create an account', '/auth/sign-up'],
      ['Read the docs', 'https://docs.doggybank.io'],
      ['Docs', 'https://docs.doggybank.io'],
      ['Sign in', '/auth/sign-in'],
    ]);

    const steps = [...container.querySelectorAll('.home__step h3')].map(
      heading => heading.textContent,
    );
    expect(steps).toEqual([
      'Sign up and get 1,000 chips',
      'Open a table and share the code',
      'Or connect an agent with an API key',
    ]);

    expect(container.querySelector('.home__code-pre')?.textContent).toBe(
      AGENT_TURN_SNIPPET,
    );
  });

  it('maps signed-out, offline, and signed-in session checks to the home route state', async () => {
    const cases: ReadonlyArray<[() => Promise<unknown>, boolean]> = [
      [() => Promise.resolve(null), false],
      [() => Promise.reject(new Error('offline')), false],
      [() => Promise.resolve({user: {id: 'u1'}}), true],
    ];
    for (const [readSession, expected] of cases) {
      expect(await loadSignedIn(readSession)).toEqual({signedIn: expected});
    }

    rendered = render(
      <MemoryRouter>
        <Home loaderData={{signedIn: false}} />
      </MemoryRouter>,
    );
    expect(rendered.container.querySelector('.home')).not.toBeNull();
  });
});
