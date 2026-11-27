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

import {act} from 'react';
import {type Root, createRoot} from 'react-dom/client';
import {afterEach, beforeEach, describe, expect, it, vi} from 'vitest';

import {playBlocker} from '../actions/play_blocker.ts';
import type {Frame, SeatConfig, SeatView} from '../contract/contract.ts';
import {controllerToMove, statusLine} from '../game/gameplay_state.ts';
import {stubResizeObserver} from '../testing/dom.ts';
import {only} from '../testing/render.tsx';
import {PlayersPanel} from './players_panel.tsx';
import {anyPreparing, preparingMover, preparingText} from './preparing.ts';
import {CONTROLLERS, RANDOM, frameWith, seatView} from './testing/seats.ts';

const MESSAGE = 'Building Random, for at most 120 seconds.';

// Seat 1, played by Random and to move, as `seat` says.
function seatOne(seat: Partial<SeatView>, fields: Partial<Frame> = {}): Frame {
  return frameWith([seatView(0), seatView(1, RANDOM, seat)], {
    to_move: {kind: 'seat', seat: 1},
    ...fields,
  });
}

const PREPARING = seatOne({status: 'preparing', message: MESSAGE});
const READY = seatOne({});
const UNAVAILABLE = seatOne(
  {
    status: 'unavailable',
    message: 'The checkpoint does not load.',
    failure: {error: 'UnavailableError', message: null},
  },
  {status: 'paused', to_move: {kind: 'seat', seat: 0}},
);

let container: HTMLElement;
let root: Root;

beforeEach(() => {
  stubResizeObserver();
  container = document.createElement('div');
  document.body.append(container);
  root = createRoot(container);
});

afterEach(() => {
  act(() => {
    root.unmount();
  });
  container.remove();
  vi.useRealTimers();
  vi.unstubAllGlobals();
});

describe('preparing', () => {
  it('names the controller a seat prepares', () => {
    expect(preparingText(CONTROLLERS, seatView(1, RANDOM))).toBe(
      'Preparing Random…',
    );
    expect(
      preparingText(CONTROLLERS, seatView(1, RANDOM, {controller: 'lost'})),
    ).toBe('Preparing lost…');
  });

  it('finds the seat play waits on, only live and in play', () => {
    expect(anyPreparing(PREPARING)).toBe(true);
    expect(anyPreparing(READY)).toBe(false);
    expect(preparingMover(PREPARING)?.seat).toBe(1);
    expect(preparingMover(READY)).toBeNull();
    expect(
      preparingMover({...PREPARING, to_move: {kind: 'seat', seat: 0}}),
    ).toBeNull();
    expect(preparingMover({...PREPARING, ply: 0, num_plies: 2})).toBeNull();
  });

  it('says so on the turn line and in place of the legal actions', () => {
    expect(statusLine(PREPARING)).toBe('Turn 0 · Player 1 · Preparing Random…');
    expect(controllerToMove(PREPARING)).toBeNull();
    expect(statusLine(READY)).toBe('Turn 0 · Player 1 · Waiting for bot step…');
    expect(playBlocker(PREPARING)).toBe('Preparing Random…');
  });
});

describe('PlayersPanel while a seat prepares', () => {
  const setSeat = vi.fn<(seat: number, config: SeatConfig) => void>();
  const advance = vi.fn<(maxPlies?: number | null) => void>();

  function show(frame: Frame): void {
    act(() => {
      root.render(
        <PlayersPanel
          frame={frame}
          busy={false}
          commands={{setSeat, advance}}
        />,
      );
    });
  }

  function row(): HTMLElement {
    const found = container.querySelectorAll<HTMLElement>('li.seat')[1];
    if (found === undefined) throw new Error('No seat 1.');
    return found;
  }

  function step(): HTMLButtonElement {
    const found = Array.from(row().querySelectorAll('button')).find(
      button => button.textContent === 'Step',
    );
    if (found === undefined) throw new Error('No Step.');
    return found;
  }

  beforeEach(() => {
    setSeat.mockClear();
    advance.mockClear();
  });

  it('shows the seat preparing in place of its controller, then ready', () => {
    show(PREPARING);
    const label = only(row(), '.seat__controller');
    expect(label.textContent).toBe('Preparing Random…');
    expect(label.title).toBe(MESSAGE);
    expect(label.getAttribute('aria-live')).toBe('polite');
    expect(step().disabled).toBe(true);
    expect(step().title).toBe('Preparing Random…');
    expect(row().querySelector('[role="alert"]')).toBeNull();
    show(READY);
    // The same element and the same Step, so nothing moves when it is ready.
    expect(only(row(), '.seat__controller')).toBe(label);
    expect(label.textContent).toBe('Random');
    expect(label.title).toBe('');
    expect(step().disabled).toBe(false);
  });

  it('says why a seat could not be prepared, and builds it again', () => {
    show(UNAVAILABLE);
    const alert = only(row(), '[role="alert"]');
    expect(alert.textContent).toContain(
      'Player 1’s controller could not be prepared (UnavailableError). Play is paused.',
    );
    expect(only(alert, 'pre').textContent).toBe(
      'The checkpoint does not load.',
    );
    expect(only(row(), '.seat__controller').textContent).toBe('Random');
    const retry = Array.from(row().querySelectorAll('button')).find(
      button => button.textContent === 'Retry',
    );
    if (retry === undefined) throw new Error('No Retry.');
    act(() => {
      retry.click();
    });
    expect(setSeat.mock.calls).toEqual([
      [1, {controller: 'random', config: {}, autoplay: false}],
    ]);
    expect(advance).not.toHaveBeenCalled();
  });
});
