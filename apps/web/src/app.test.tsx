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

import {act} from 'react';
import {afterEach, beforeEach, describe, expect, it, vi} from 'vite-plus/test';

import {App} from './app.tsx';
import {SessionClient} from './session/client.ts';
import {FakeServer} from './session/testing/fake-server.ts';
import {fakeColorScheme} from './testing/color-scheme.ts';
import {enter, labeled} from './testing/input.ts';
import {render, type Rendered} from './testing/render.tsx';
import {chooseTab} from './testing/tabs.ts';
import {ThemeProvider} from './theme/theme-provider.tsx';

let rendered: Rendered | undefined;
let server: FakeServer;

/** Renders the app at `path` against the fake server. */
function open(path: string): HTMLElement {
  const client = new SessionClient({fetch: server.fetch});
  const url = new URL(path, window.location.origin);
  rendered = render(
    <ThemeProvider>
      <App url={url} client={client} />
    </ThemeProvider>,
  );
  return rendered.container;
}

/**
 * Waits, letting the fake server answer, until `check` passes. Five seconds,
 * not vitest's one: a loaded CI runner timed this out at one second on a
 * passing build.
 */
async function until(check: () => void): Promise<void> {
  await vi.waitFor(
    async () => {
      await act(async () => {
        await Promise.resolve();
      });
      check();
    },
    {timeout: 5000},
  );
}

function click(element: HTMLElement): void {
  act(() => {
    element.click();
  });
}

/** Opens the panels sheet, if it is closed, at the tool titled `title`. */
function tool(title: string): void {
  if (document.querySelector('[role="dialog"]') === null) {
    const opener = document.querySelector<HTMLElement>(
      'button[aria-label="Panels"]',
    );
    if (opener === null) throw new Error('No Panels button.');
    click(opener);
  }
  openTab(title);
}

/** Opens the tab whose label starts with `title`, anywhere on the page. */
function openTab(title: string): void {
  const tab = [...document.querySelectorAll<HTMLElement>('[role="tab"]')].find(
    candidate => candidate.textContent.startsWith(title),
  );
  if (tab === undefined) throw new Error(`No ${title} tab.`);
  if (tab.getAttribute('aria-selected') !== 'true') chooseTab(tab);
}

/** The legal action labeled `label`, in Actions › Legal, which it opens. */
function legal(label: string): HTMLElement {
  tool('Actions');
  openTab('Legal');
  const row = [
    ...document.querySelectorAll<HTMLElement>('button.legal__row'),
  ].find(candidate => candidate.textContent.endsWith(label));
  if (row === undefined) throw new Error(`No legal action ${label}.`);
  return row;
}

/** The text of Actions › History, which it opens. */
function historyText(): string | undefined {
  tool('Actions');
  openTab('History');
  return document.querySelector('.history')?.textContent;
}

/** The Perspective list, in the View panel, which it brings forward. */
function perspective(): HTMLSelectElement {
  tool('View');
  return labeled(document.body, 'Perspective') as HTMLSelectElement;
}

/** Every viewer the page sent a session request as, once each. */
function sessionViewers(): Array<string | null> {
  return [
    ...new Set(
      server.received
        .filter(({path}) => path.startsWith('/api/sessions'))
        .map(({viewer}) => viewer),
    ),
  ];
}

/** A locked Perspective: the seat it shows, and why it is locked. */
function lockedPerspective(container: HTMLElement): Array<string | null> {
  return ['perspective-locked', 'perspective-lock-reason'].map(
    id => container.querySelector(`[data-testid="${id}"]`)?.textContent ?? null,
  );
}

beforeEach(() => {
  window.localStorage.clear();
  fakeColorScheme(false);
  server = new FakeServer();
});

afterEach(() => {
  rendered?.unmount();
  rendered = undefined;
  vi.unstubAllGlobals();
  window.history.replaceState(null, '', '/');
  window.localStorage.clear();
});

describe('App', () => {
  it('shows the poker lobby and refuses an unavailable engine', async () => {
    const container = open('/');
    await until(() => {
      expect(container.querySelector('.lobby')).not.toBeNull();
    });
    expect(container.querySelector('.lobby h1')?.textContent).toBe('doggybank');
    expect(container.querySelector('.lobby__tagline')?.textContent).toBe(
      'Heads-up no-limit Texas Hold’em for Bots',
    );
    expect(container.querySelector('header .app__brand')?.textContent).toBe('');
    expect(container.textContent).toContain('The poker engine is unavailable.');
    expect(
      container.querySelector<HTMLButtonElement>('button[type="submit"]')
        ?.disabled,
    ).toBe(true);
  });

  it('says why the catalogue could not be loaded', async () => {
    server.refuseNext('bad_request', 'No games today.');
    const container = open('/');
    await until(() => {
      expect(container.textContent).toContain(
        'The poker table could not be loaded. No games today.',
      );
    });
  });

  it.each([
    ['/game/nope', 'There is no game "nope".'],
    ['/nowhere', 'Nothing is at /nowhere.'],
  ])('says what is missing at %s', async (path, sentence) => {
    const container = open(path);
    await until(() => {
      expect(container.textContent).toContain(sentence);
    });
  });
});

describe('App, its header', () => {
  it('holds the title, then the panels button, then the settings', async () => {
    const container = open('/game/count');
    await until(() => {
      expect(
        container.querySelector(
          '.app__page-actions button[aria-label="Panels"]',
        ),
      ).not.toBeNull();
    });
    const header = container.querySelector('header');
    expect(header?.querySelector('h1')?.textContent).toBe('Count');
    const controls = [
      ...(header?.querySelectorAll('.app__actions button[aria-haspopup]') ??
        []),
    ].map(control => control.getAttribute('aria-label') ?? control.textContent);
    expect(controls).toEqual(['Panels', 'Settings']);
  });

  it('names Doggybank, then a bullet hidden from readers, then the title', () => {
    const brand = open('/game/count').querySelector('header .app__brand');
    const parts = [...(brand?.children ?? [])].map(part => [
      part.tagName,
      part.textContent,
      part.getAttribute('aria-hidden'),
    ]);
    expect(parts).toEqual([
      ['A', 'Doggybank', null],
      ['SPAN', '•', 'true'],
      ['H1', 'Heads-up Hold’em', null],
    ]);
    expect(
      brand
        ?.querySelector('.app__home svg.app__logo')
        ?.getAttribute('aria-hidden'),
    ).toBe('true');
  });
});

describe('App, on a game page', () => {
  it('starts a game at its first seat, plays it, and keeps its session in the address', async () => {
    open('/game/count');
    await until(() => {
      expect(legal('zero')).toBeDefined();
    });
    const create = server.received.find(({method}) => method === 'POST');
    expect(create?.body).toMatchObject({
      game: 'count',
      seats: [{controller: 'human'}, {controller: 'random', autoplay: true}],
    });
    click(legal('one'));
    await until(() => {
      expect(historyText()).toContain('#1one');
    });
    const url = new URL(window.location.href);
    expect(url.pathname).toBe('/game/count');
    expect(url.searchParams.get('viewer')).toBe('0');
    const id = url.searchParams.get('session');
    expect(id).not.toBeNull();
    expect(server.history(id ?? '')).toEqual([1]);
  });
});

describe('App, opening a table', () => {
  it('moves no chips when its address names no session', async () => {
    server = new FakeServer({game: 'doggybank'});
    open('/game/doggybank');
    await until(() => {
      expect(new URL(window.location.href).searchParams.get('session')).toBe(
        'session-1',
      );
    });
    const me = await new SessionClient({fetch: server.fetch}).me();
    expect(me.balance).toBe(1000);
  });
});

describe('App, at a table played for chips', () => {
  it('shows why the server refuses to let the player leave mid-hand', async () => {
    server = new FakeServer({staked: true});
    const container = open('/game/count');
    let leave: HTMLElement | undefined;
    await until(() => {
      leave = [...document.querySelectorAll<HTMLElement>('button')].find(
        button => button.textContent === 'Leave table',
      );
      expect(leave).toBeDefined();
    });
    server.refuseNext('table_not_ready', 'Finish the hand before you leave.');
    if (leave !== undefined) click(leave);
    await until(() => {
      expect(container.textContent).toContain(
        'Finish the hand before you leave.',
      );
    });
    expect(server.received.at(-1)).toMatchObject({
      method: 'POST',
      path: '/api/rooms/ROOM42/leave',
    });
  });
});

describe('App, analysis and a game', () => {
  it('opens in analysis when its address names the oracle, offering every seat and nothing else', async () => {
    server = new FakeServer({hidesInformation: true});
    open('/game/count?viewer=oracle');
    await until(() => {
      expect(legal('zero')).toBeDefined();
    });
    const select = perspective();
    expect([...select.options].map(option => option.textContent)).toEqual([
      'Select a seat',
      'Seat 0',
      'Seat 1',
    ]);
    expect(select.value).toBe('0');
    expect(sessionViewers()).toEqual(['oracle']);
    expect(new URL(window.location.href).searchParams.get('viewer')).toBe(
      'oracle',
    );
  });

  it('sits at another seat without a request, and keeps it in the address', async () => {
    server = new FakeServer({hidesInformation: true});
    open('/game/count?viewer=oracle');
    await until(() => {
      expect(legal('zero')).toBeDefined();
    });
    const requests = server.received.length;
    enter(perspective(), '1');
    expect(perspective().value).toBe('1');
    await until(() => {
      expect(new URL(window.location.href).searchParams.get('viewSeat')).toBe(
        '1',
      );
    });
    expect(server.received).toHaveLength(requests);
  });

  it('opens analysis at the seat its address names', async () => {
    open('/game/count?viewer=oracle&viewSeat=1');
    await until(() => {
      expect(legal('zero')).toBeDefined();
    });
    expect(perspective().value).toBe('1');
  });

  it('plays every seat in analysis, with no hand-over', async () => {
    server = new FakeServer({hidesInformation: true});
    const container = open('/game/count?viewer=oracle');
    await until(() => {
      expect(legal('zero')).toBeDefined();
    });
    click(legal('zero'));
    await until(() => {
      expect(legal('one')).toBeDefined();
    });
    click(legal('one'));
    await until(() => {
      expect(historyText()).toContain('#2one');
    });
    expect(document.querySelector('[aria-modal]')).toBeNull();
    expect(container.textContent).not.toContain('Hand over');
  });
});

describe('App, a game at a seat or spectating', () => {
  it('opens a game at the seat its address names, its perspective locked', async () => {
    server = new FakeServer({hidesInformation: true});
    const container = open('/game/count?viewer=1');
    await until(() => {
      expect(container.querySelector('.gameplay__status')).not.toBeNull();
    });
    tool('View');
    expect(lockedPerspective(document.body)).toEqual([
      'Seat 1 (you)',
      'Locked to your seat during a game',
    ]);
    expect(container.querySelector('[data-testid="perspective-select"]')).toBe(
      null,
    );
    expect(sessionViewers()).toEqual(['1']);
  });

  it('opens a spectator, its perspective locked', async () => {
    const container = open('/game/count?viewer=spectator');
    await until(() => {
      expect(container.querySelector('.gameplay__status')?.textContent).toBe(
        'Turn 0 · Player 0 · Spectating',
      );
    });
    tool('View');
    expect(lockedPerspective(document.body)).toEqual([
      'Spectating',
      'Spectating: the perspective is fixed during a game',
    ]);
  });

  it.each(['7', '-1'])(
    'opens the spectator, never the oracle, for viewer=%s the game lacks',
    async parameter => {
      server = new FakeServer({hidesInformation: true});
      const container = open(`/game/count?viewer=${parameter}`);
      await until(() => {
        expect(container.querySelector('.gameplay__status')?.textContent).toBe(
          'Turn 0 · Player 0 · Spectating',
        );
      });
      tool('View');
      expect(lockedPerspective(document.body)).toEqual([
        'Spectating',
        'Spectating: the perspective is fixed during a game',
      ]);
      expect(sessionViewers()).toEqual(['spectator']);
      expect(new URL(window.location.href).searchParams.get('viewer')).toBe(
        'spectator',
      );
    },
  );
});
