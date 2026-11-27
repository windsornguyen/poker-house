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

import {afterEach, describe, expect, it} from 'vitest';

import type {Frame} from '../../contract/contract.ts';
import {entries, frame} from '../../testing/frames.ts';
import {type Rendered, render} from '../../testing/render.tsx';
import {POKER_RENDERER} from './poker_renderer.tsx';
import {pokerSession} from './poker_session.ts';
import {derivePokerState} from './poker_state.ts';

let rendered: Rendered | null = null;

afterEach(() => {
  rendered?.unmount();
  rendered = null;
});

function holdem(terminal: boolean): Frame {
  return frame({
    status: terminal ? 'terminal' : 'playing',
    to_move: terminal
      ? {kind: 'terminal', seat: null}
      : {kind: 'seat', seat: 0},
    returns: terminal ? [2, -2] : null,
    legal_actions: [],
    presentation: {
      renderer: 'poker',
      actions: [],
      view: {
        pokerGame: {
          title: "No-limit Texas Hold'em",
          betting: 'nolimit',
          holeCards: 2,
          boardSizes: [0, 3, 1, 1],
          fixedSeats: 2,
        },
        historyActionStrings: [],
        struct: {
          player_hands: ['', ''],
          board_cards: '',
          starting_stacks: [200, 200],
          player_contributions: [2, 2],
          pot_size: terminal ? 0 : 4,
          current_player: terminal ? -4 : 0,
          betting_history: '',
          blinds: [2, 1],
        },
      },
    },
  });
}

describe('the PokerKit table', () => {
  it('keeps spectators from starting or resetting a hand', () => {
    const shown = holdem(true);
    shown.viewer = {kind: 'spectator', seat: null};
    shown.omniscient = false;
    if (shown.presentation === null) throw new Error('No poker view.');
    const Board = POKER_RENDERER.render;
    rendered = render(
      <Board frame={shown} presentation={shown.presentation} play={null} />,
    );
    const buttons = [...rendered.container.querySelectorAll('button')].filter(
      button => button.textContent === 'New hand',
    );
    expect(buttons).toHaveLength(2);
    expect(buttons.every(button => button.disabled)).toBe(true);
  });
  it('replays an earlier decision after the live hand has ended', () => {
    const shown = holdem(false);
    shown.status = 'terminal';
    shown.history = entries(['Deal', 'Call', 'Fold']);
    shown.num_plies = 3;
    shown.ply = 2;
    if (shown.presentation === null) throw new Error('No poker view.');
    const view = shown.presentation.view as Record<string, unknown>;
    view['historyActionStrings'] = ['Deal', 'Call'];
    const session = pokerSession(shown, shown.presentation);
    expect(session.state.historyActionStrings).toEqual(['Deal', 'Call']);
    expect(session.state.historyPlayers).toHaveLength(2);
    expect(session.state.isTerminal).toBe(false);
    expect(session.state.currentPlayer).toBe(0);
  });
  it('shows the settled stacks after the engine pays the pot', () => {
    const shown = holdem(true);
    if (shown.presentation === null) throw new Error('No poker view.');
    const state = derivePokerState(pokerSession(shown, shown.presentation));
    expect(state?.seats.map(seat => seat.stack)).toEqual([202, 198]);
  });

  it('subtracts committed chips while the hand is still live', () => {
    const shown = holdem(false);
    if (shown.presentation === null) throw new Error('No poker view.');
    const state = derivePokerState(pokerSession(shown, shown.presentation));
    expect(state?.seats.map(seat => seat.stack)).toEqual([198, 198]);
  });

  it('keeps the configured seats and their starting stacks together', () => {
    const shown = holdem(true);
    if (shown.presentation === null) throw new Error('No poker view.');
    const Board = POKER_RENDERER.render;
    rendered = render(
      <Board frame={shown} presentation={shown.presentation} play={null} />,
    );
    const select = rendered.container.querySelector('select');
    if (select === null) throw new Error('No seat control.');
    expect(select.disabled).toBe(true);
    expect([...select.options].map(option => option.value)).toEqual(['2']);
  });
});
