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

import {act} from 'react';
import {afterEach, describe, expect, it, vi} from 'vite-plus/test';

import type {CatalogueEntry, Me, RoomView} from './contract/contract.ts';
import {PokerLobby} from './lobby.tsx';
import {type Fetch, SessionClient} from './session/client.ts';
import {frame} from './testing/frames.ts';
import {enter, labeled} from './testing/input.ts';
import {type Rendered, render} from './testing/render.tsx';

const ENTRY = {
  name: 'doggybank',
  loadable: true,
  unavailable_reason: null,
} as CatalogueEntry;

let rendered: Rendered | undefined;

// The lobby asks for the player's chips as it opens; every other request
// gets `body`.
function server(body: unknown, me: Me = ME): ReturnType<typeof vi.fn<Fetch>> {
  return vi.fn<Fetch>(url =>
    Promise.resolve(Response.json(url === '/api/me' ? me : body)),
  );
}

const ME: Me = {balance: 1000, kind: 'person', seats: []};

// The requests the lobby sent besides asking for the player's chips.
function sent(
  fetch: ReturnType<typeof vi.fn<Fetch>>,
): Array<Parameters<Fetch>> {
  return fetch.mock.calls.filter(([url]) => url !== '/api/me');
}

afterEach(() => {
  rendered?.unmount();
  rendered = undefined;
});

describe('the poker lobby', () => {
  it('connects both bot endpoints', async () => {
    const shown = frame();
    shown.session.game = 'doggybank';
    const fetch = server(shown);
    const client = new SessionClient({fetch});
    const open = vi.fn();
    rendered = render(
      <PokerLobby entry={ENTRY} client={client} onOpen={open} />,
    );
    const {container} = rendered;
    enter(labeled(container, 'Player 1 bot URL'), 'http://alice.local:9001');
    enter(labeled(container, 'Player 2 bot URL'), 'https://bob.example/bot');
    const form = container.querySelector('form');
    if (form === null) throw new Error('No match form.');
    await act(async () => {
      form.dispatchEvent(
        new Event('submit', {bubbles: true, cancelable: true}),
      );
      await Promise.resolve();
    });
    const [create] = sent(fetch);
    if (create === undefined) throw new Error('No create request.');
    expect(create[0]).toBe('/api/sessions?viewer=oracle');
    const init = create[1];
    if (typeof init.body !== 'string') throw new Error('No JSON request body.');
    expect(JSON.parse(init.body)).toMatchObject({
      game: 'doggybank',
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
    const fetch = server(frame());
    const client = new SessionClient({fetch});
    rendered = render(
      <PokerLobby entry={ENTRY} client={client} onOpen={vi.fn()} />,
    );
    enter(labeled(rendered.container, 'Starting stack'), '1');
    const form = rendered.container.querySelector('form');
    if (form === null) throw new Error('No match form.');
    await act(async () => {
      form.dispatchEvent(
        new Event('submit', {bubbles: true, cancelable: true}),
      );
      await Promise.resolve();
    });
    expect(sent(fetch)).toEqual([]);
    expect(
      rendered.container.querySelector('[role="alert"]')?.textContent,
    ).toContain('stack at least as large as the big blind');
  });
});

describe('joining a room', () => {
  it('joins a room by its code and opens the seat it answers with', async () => {
    const seated = frame();
    seated.viewer = {kind: 'seat', seat: 1};
    const fetch = server(seated);
    const open = vi.fn();
    rendered = render(
      <PokerLobby
        entry={ENTRY}
        client={new SessionClient({fetch})}
        onOpen={open}
      />,
    );
    const {container} = rendered;

    const input = container.querySelector<HTMLInputElement>(
      'input[aria-label="Room code"]',
    );
    if (input === null) throw new Error('No room code input.');
    enter(input, 'room42');
    const forms = container.querySelectorAll('form');
    const join = forms[forms.length - 1];
    if (join === undefined) throw new Error('No join form.');
    await act(async () => {
      join.dispatchEvent(
        new Event('submit', {bubbles: true, cancelable: true}),
      );
      await Promise.resolve();
    });

    const [url, init] = sent(fetch)[0] ?? [];
    expect(String(url)).toMatch(/\/api\/rooms\/ROOM42\/join$/);
    expect(init?.method).toBe('POST');
    expect(open).toHaveBeenCalledWith(seated);
  });
});

describe('the tables a player sits at', () => {
  it('lists each seat, and cashes one out', async () => {
    const left: RoomView = {
      code: 'ABC234',
      buy_in: 200,
      session_id: null,
      seat: null,
      stack: null,
      stacks: [],
    };
    const fetch = server(left, {
      ...ME,
      seats: [{code: 'ABC234', stack: 350}],
    });
    rendered = render(
      <PokerLobby
        entry={ENTRY}
        client={new SessionClient({fetch})}
        onOpen={vi.fn()}
      />,
    );
    await act(async () => {
      await Promise.resolve();
    });
    const {container} = rendered;
    expect(container.textContent).toContain('Table ABC234 · 350 chips');

    const cashOut = [...container.querySelectorAll('button')].find(
      button => button.textContent === 'Cash out',
    );
    if (cashOut === undefined) throw new Error('No Cash out button.');
    await act(async () => {
      cashOut.click();
      await Promise.resolve();
    });

    const [url, init] = sent(fetch)[0] ?? [];
    expect(url).toBe('/api/rooms/ABC234/leave');
    expect(init?.method).toBe('POST');
    await vi.waitFor(() => {
      expect(
        fetch.mock.calls.filter(([called]) => called === '/api/me'),
      ).toHaveLength(2);
    });
  });
});
