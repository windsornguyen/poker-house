// Copyright 2026 Poker House contributors
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

import {act} from 'react';
import {afterEach, describe, expect, it, vi} from 'vite-plus/test';

import type {CatalogueEntry} from './contract/contract.ts';
import {PokerLobby} from './lobby.tsx';
import {type Fetch, SessionClient} from './session/client.ts';
import {frame} from './testing/frames.ts';
import {enter, labelled} from './testing/input.ts';
import {type Rendered, render} from './testing/render.tsx';

const ENTRY = {
  name: 'poker_house',
  loadable: true,
  unavailable_reason: null,
} as CatalogueEntry;

let rendered: Rendered | undefined;

afterEach(() => {
  rendered?.unmount();
  rendered = undefined;
});

describe('the poker lobby', () => {
  it('connects both bot endpoints', async () => {
    const shown = frame();
    shown.session.game = 'poker_house';
    const fetch = vi.fn<Fetch>(() => Promise.resolve(Response.json(shown)));
    const client = new SessionClient({fetch});
    const open = vi.fn();
    rendered = render(
      <PokerLobby entry={ENTRY} client={client} onOpen={open} />,
    );
    const {container} = rendered;
    enter(labelled(container, 'Player 1 bot URL'), 'http://alice.local:9001');
    enter(labelled(container, 'Player 2 bot URL'), 'https://bob.example/bot');
    const form = container.querySelector('form');
    if (form === null) throw new Error('No match form.');
    await act(async () => {
      form.dispatchEvent(
        new Event('submit', {bubbles: true, cancelable: true}),
      );
      await Promise.resolve();
    });
    const sent = fetch.mock.calls[0];
    if (sent === undefined) throw new Error('No create request.');
    expect(sent[0]).toBe('/api/sessions?viewer=oracle');
    const init = sent[1];
    if (typeof init.body !== 'string') throw new Error('No JSON request body.');
    expect(JSON.parse(init.body)).toMatchObject({
      game: 'poker_house',
      parameters: {num_players: 2, blinds: '1 2', stack_sizes: '200 200'},
      chance_policy: 'auto',
      seed: null,
      seats: [
        {
          controller: 'remote',
          config: {url: 'http://alice.local:9001'},
          autoplay: true,
        },
        {
          controller: 'remote',
          config: {url: 'https://bob.example/bot'},
          autoplay: true,
        },
      ],
    });
    expect(open).toHaveBeenCalledWith(shown);
  });

  it('shows invalid stakes without sending a hand to the server', async () => {
    const fetch = vi.fn<Fetch>(() => Promise.resolve(Response.json(frame())));
    const client = new SessionClient({fetch});
    rendered = render(
      <PokerLobby entry={ENTRY} client={client} onOpen={vi.fn()} />,
    );
    enter(labelled(rendered.container, 'Starting stack'), '1');
    const form = rendered.container.querySelector('form');
    if (form === null) throw new Error('No match form.');
    await act(async () => {
      form.dispatchEvent(
        new Event('submit', {bubbles: true, cancelable: true}),
      );
      await Promise.resolve();
    });
    expect(fetch).not.toHaveBeenCalled();
    expect(
      rendered.container.querySelector('[role="alert"]')?.textContent,
    ).toContain('stack at least as large as the big blind');
  });
});
