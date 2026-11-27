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

import type {JSX} from 'react';
import {useCallback, useRef, useState} from 'react';

import type {Frame, SeatConfig} from '../contract/contract.ts';
import {SeatRow} from './seat_row.tsx';

import './players.css';

/**
 * Below this height of the seat list's scroll, in pixels, a seat editor's two
 * save bars cannot both be shown with room to spare, so the one that sticks
 * moves from the top of the editor to its bottom.
 */
export const SHORT_SCROLL = 160;

/** What the Players panel may ask of the live game. */
export interface PlayersCommands {
  /** Hands `seat` to the controller and settings in `config`. */
  readonly setSeat: (seat: number, config: SeatConfig) => void;
  /** Lets controllers play at most `maxPlies` seat actions. */
  readonly advance: (maxPlies?: number | null) => void;
}

/** The properties of the Players panel. */
export interface PlayersPanelProps {
  /** The frame shown; its seats are the live game's. */
  readonly frame: Frame;
  /** Whether a request is in flight. */
  readonly busy: boolean;
  readonly commands: PlayersCommands;
}

/**
 * Who plays each seat. Every viewer but a spectator changes a seat; a
 * spectator sees every seat's settings read-only, open from the start.
 */
export function PlayersPanel({
  frame,
  busy,
  commands,
}: PlayersPanelProps): JSX.Element {
  const {session} = frame;
  const spectator = frame.viewer.kind === 'spectator';
  const {short, scrollRef} = useSeatList();
  return (
    <div className="players">
      <header className="players__header">
        <h2 className="players__title">Players</h2>
      </header>
      {spectator && (
        <p className="players__status" role="note">
          Spectating: the seats are read only during a game.
        </p>
      )}
      <div
        ref={scrollRef}
        className={`players__scroll${short ? ' players__scroll--short' : ''}`}
      >
        {/* Keyed by session, so no draft outlives the session it edits. */}
        <ul key={session.id} className="players__seats" aria-label="Seats">
          {frame.seats.map(seat => (
            <SeatRow
              key={seat.seat}
              seat={seat}
              frame={frame}
              editable={!spectator}
              busy={busy}
              onSave={config => {
                commands.setSeat(seat.seat, config);
              }}
              onStep={() => {
                commands.advance(1);
              }}
            />
          ))}
        </ul>
      </div>
    </div>
  );
}

// Watches whether the seat list's scroll is short.
function useSeatList(): {
  short: boolean;
  scrollRef: (element: HTMLDivElement | null) => void;
} {
  const [short, setShort] = useState(false);
  const observer = useRef<ResizeObserver | null>(null);
  const scrollRef = useCallback((element: HTMLDivElement | null) => {
    observer.current?.disconnect();
    observer.current = null;
    if (element === null) return;
    const measure = (): void => {
      setShort(element.clientHeight < SHORT_SCROLL);
    };
    const watching = new ResizeObserver(measure);
    watching.observe(element);
    const list = element.querySelector('.players__seats');
    if (list !== null) watching.observe(list);
    observer.current = watching;
  }, []);
  return {short, scrollRef};
}
