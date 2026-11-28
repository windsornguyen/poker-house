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
import {enter} from './testing/input.ts';
import {type Rendered, render} from './testing/render.tsx';

const ENTRY = {
  name: 'doggybank',
  loadable: true,
  unavailable_reason: null,
  num_players: 2,
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

describe('opening a table', () => {
  it.each([
    ['Open a table · 200 chips', {controller: 'human', autoplay: false}],
    ['Practice against a bot', {controller: 'random', autoplay: true}],
  ])('opens %s at the first seat', async (label, opponent) => {
    const seated = frame();
    const fetch = server(seated);
    const open = vi.fn();
    rendered = render(
      <PokerLobby
        entry={ENTRY}
        client={new SessionClient({fetch})}
        onOpen={open}
      />,
    );
    const button = [...rendered.container.querySelectorAll('button')].find(
      candidate => candidate.textContent === label,
    );
    if (button === undefined) throw new Error(`No ${label} button.`);
    await act(async () => {
      button.click();
      await Promise.resolve();
    });

    const [url, init] = sent(fetch)[0] ?? [];
    expect(url).toBe('/api/sessions?viewer=0');
    if (typeof init?.body !== 'string') throw new Error('No JSON body.');
    expect(JSON.parse(init.body)).toMatchObject({
      game: 'doggybank',
      parameters: {stack_sizes: '200 200'},
      seats: [{controller: 'human'}, opponent],
    });
    expect(open).toHaveBeenCalledWith(seated);
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

describe('joining a room short of its buy-in', () => {
  it('links to the spectator view beside the refusal', async () => {
    const room: RoomView = {
      code: 'ROOM42',
      buy_in: 5000,
      session_id: 'hand-1',
      seat: null,
      stack: null,
      stacks: [5000],
    };
    const fetch = vi.fn<Fetch>(url => {
      if (url === '/api/me') return Promise.resolve(Response.json(ME));
      if (url.endsWith('/join')) {
        return Promise.resolve(
          Response.json(
            {
              code: 'insufficient_chips',
              message: 'You have 1000 chips, fewer than the 5000 this needs.',
              seat: null,
              ply: null,
            },
            {status: 402},
          ),
        );
      }
      return Promise.resolve(Response.json(room));
    });
    rendered = render(
      <PokerLobby
        entry={ENTRY}
        client={new SessionClient({fetch})}
        onOpen={vi.fn()}
      />,
    );
    const {container} = rendered;
    const input = container.querySelector<HTMLInputElement>(
      'input[aria-label="Room code"]',
    );
    if (input === null) throw new Error('No room code input.');
    enter(input, 'ROOM42');
    const forms = container.querySelectorAll('form');
    const join = forms[forms.length - 1];
    if (join === undefined) throw new Error('No join form.');
    await act(async () => {
      join.dispatchEvent(
        new Event('submit', {bubbles: true, cancelable: true}),
      );
      await Promise.resolve();
    });

    await vi.waitFor(() => {
      const link = container.querySelector('[role="alert"] a');
      expect(link?.getAttribute('href')).toBe(
        '/game/doggybank?session=hand-1&viewer=spectator',
      );
    });
  });
});
