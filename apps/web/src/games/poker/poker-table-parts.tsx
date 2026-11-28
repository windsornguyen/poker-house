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

// The poker table's parts: a card, a seat's plate, a chip in flight, and the
// words the table writes (chips, blinds, stacks, the hand's result). Split
// from poker-gameplay-panel.tsx.

import {type CSSProperties, type JSX, useEffect, useRef} from 'react';

import {scaleMs} from '../../motion/index.ts';
import {
  type PokerCard,
  type PokerEnding,
  type PokerSeat,
  cardAriaLabel,
} from './poker-state.ts';
import type {ChipFlight, PokerMotion} from './use-poker-motion.ts';

/** `value` within [min, max]. */
export function clamp(value: number, min: number, max: number): number {
  return Math.min(max, Math.max(min, value));
}

/** Chips as the table writes them: "19,305". */
export function formatChips(value: number): string {
  if (!Number.isFinite(value)) {
    return '0';
  }
  return value.toLocaleString();
}

const suitSymbols: Record<PokerCard['suit'], string> = {
  c: '♣',
  d: '♦',
  h: '♥',
  s: '♠',
};

/** A signed chip count: "+18,201", "-18,201". */
export function formatSignedChips(value: number): string {
  if (value > 0) {
    return `+${formatChips(value)}`;
  }
  return formatChips(value);
}

/**
 * The hand's result line. A hand won by fold says so: nobody showed down.
 * The viewer's own seat is "You" ("You win +2"), as the reference clients
 * say it; `viewerSeat` is null for a spectator or the oracle.
 */
export function terminalSummary(
  seats: PokerSeat[],
  returns: number[] | null,
  ending: PokerEnding | null,
  viewerSeat: number | null = null,
): string {
  const byFold = ending === 'fold' ? ' by fold' : '';
  if (!returns || returns.length === 0) {
    return ending === 'fold' ? 'Won by fold' : 'Hand complete';
  }
  const maxReturn = Math.max(...returns);
  if (maxReturn <= 0) {
    return 'Hand complete: split pot';
  }
  const winners = seats.filter(seat => seat.returnValue === maxReturn);
  const names = winners
    .map(seat => (seat.slot === viewerSeat ? 'You' : seat.name))
    .join(', ');
  const verb =
    winners.length > 1
      ? 'split'
      : winners[0]?.slot === viewerSeat
        ? 'win'
        : 'wins';
  return `${names || 'Winner'} ${verb} ${formatSignedChips(
    maxReturn,
  )}${byFold}`;
}

/**
 * A card's motion: 'deal' (onto the board) or 'reveal' (turned face up on a
 * plate). Its delay and flight are base ms, scaled here to the viewer's
 * Animation speed (use-poker-motion.ts). `onLanded` runs at its own
 * animationend, so a motion carried into the next table state ends where it
 * ends, not where the next state arrives.
 */
export interface CardMotion {
  kind: 'deal' | 'reveal';
  delayBaseMs: number;
  motion: PokerMotion;
  onLanded: () => void;
}

function cardMotionStyle({
  delayBaseMs,
  motion,
}: CardMotion): CSSProperties & Record<string, string> {
  return {
    '--poker-flight-ms': `${String(scaleMs(motion.flightBaseMs, motion.scale))}ms`,
    '--poker-delay-ms': `${String(scaleMs(delayBaseMs, motion.scale))}ms`,
  };
}

/**
 * A card, or an empty slot for a card the viewer may not see. `plays`: the
 * card is one of those that make a winning hand at showdown. It is raised
 * and outlined, as the reference clients mark the winning five; the other
 * cards keep full contrast (never dim).
 */
export function CardView({
  card,
  compact = false,
  motion,
  plays = false,
}: {
  readonly card?: PokerCard | undefined;
  readonly compact?: boolean;
  readonly motion?: CardMotion | undefined;
  readonly plays?: boolean;
}): JSX.Element {
  if (!card) {
    return (
      <span
        className={`poker-card poker-card--empty${
          compact ? ' poker-card--compact' : ''
        }`}
        aria-hidden
      />
    );
  }
  const isRed = card.suit === 'd' || card.suit === 'h';
  return (
    <span
      className={`poker-card poker-card--${card.suit}${
        isRed ? ' poker-card--red' : ''
      }${compact ? ' poker-card--compact' : ''}${
        plays ? ' poker-card--plays' : ''
      }${motion ? ` poker-card--${motion.kind}` : ''}`}
      aria-label={
        plays
          ? `${cardAriaLabel(card)}, in the winning hand`
          : cardAriaLabel(card)
      }
      onAnimationEnd={motion?.onLanded}
      style={motion ? cardMotionStyle(motion) : undefined}
    >
      <span className="poker-card__rank">
        {card.rank === 'T' ? '10' : card.rank}
      </span>
      <span className="poker-card__suit">{suitSymbols[card.suit]}</span>
    </span>
  );
}

function holeMotion(
  motion: PokerMotion,
  slot: number,
  index: number,
  revealLanded: (key: string) => void,
): CardMotion | undefined {
  const key = `${String(slot)}:${String(index)}`;
  const delayBaseMs = motion.revealDelays.get(key);
  return delayBaseMs === undefined
    ? undefined
    : {
        kind: 'reveal',
        delayBaseMs,
        motion,
        onLanded: () => {
          revealLanded(key);
        },
      };
}

/** What a seat is drawn from. */
export interface SeatViewProps {
  readonly seat: PokerSeat;
  /** The hole cards each seat holds. */
  readonly holeCards: number;
  readonly motion: PokerMotion;
  readonly revealLanded: (key: string) => void;
  /** Stack and this street's bet as shown: before any chip still in flight. */
  readonly shown: {stack: number; bet: number};
  /** Codes of the cards that make a winning hand (empty before showdown). */
  readonly playing: ReadonlySet<string>;
  /** Whether this is the viewer's own seat, drawn large at the bottom. */
  readonly isViewer: boolean;
}

function HoleCards({
  seat,
  holeCards,
  motion,
  revealLanded,
  playing,
}: SeatViewProps): JSX.Element {
  return (
    <div className="poker-seat__cards">
      {Array.from({length: holeCards}, (_, index) => {
        const card = seat.cards[index];
        return (
          <CardView
            card={card}
            key={card?.code ?? `hidden-${String(index)}`}
            motion={
              card
                ? holeMotion(motion, seat.slot, index, revealLanded)
                : undefined
            }
            plays={seat.isWinner && playing.has(card?.code ?? '')}
          />
        );
      })}
    </div>
  );
}

/** The seat's line under its stack: folded, its best hand, or what it won. */
function seatNote(seat: PokerSeat): string | undefined {
  if (typeof seat.returnValue === 'number' && seat.returnValue !== 0) {
    return formatSignedChips(seat.returnValue);
  }
  return seat.hasFolded ? 'Folded' : seat.bestHand;
}

/**
 * A seat: an opponent's avatar, name and stack in the top row, or the viewer's
 * hand and plate at the bottom. Its bet this street sits on a chip under it.
 */
export function SeatView(props: SeatViewProps): JSX.Element {
  const {seat, shown, isViewer} = props;
  const name = isViewer ? `${seat.name} (you)` : seat.name;
  const showsCards = isViewer || seat.cards.length > 0;
  const note = seatNote(seat);
  return (
    <div
      className={`poker-seat poker-seat--${String(seat.slot)}${
        seat.isActive ? ' poker-seat--active' : ''
      }${seat.hasFolded ? ' poker-seat--folded' : ''}${seat.isWinner ? ' poker-seat--winner' : ''}${
        isViewer ? ' poker-seat--viewer' : ''
      }`}
      aria-current={seat.isActive ? 'true' : undefined}
      aria-label={seat.isActive ? `${name}, to act` : name}
      role="group"
    >
      {isViewer && <HoleCards {...props} />}
      <div className="poker-seat__plate">
        {isViewer && <span className="poker-seat__note">{note ?? ''}</span>}
        <span className="poker-seat__name">
          {isViewer ? 'You' : seat.name}
          {seat.isDealer && (
            <span className="poker-seat__dealer" aria-label="Dealer">
              D
            </span>
          )}
        </span>
        <span className="poker-seat__stack">{formatChips(shown.stack)}</span>
        {!isViewer && note !== undefined && (
          <span className="poker-seat__note">{note}</span>
        )}
      </div>
      {!isViewer && showsCards && <HoleCards {...props} />}
      {shown.bet > 0 && (
        <span className="poker-seat__bet">{formatChips(shown.bet)}</span>
      )}
    </div>
  );
}

/** A bet or call traveling from its seat to the pot: plain text, the amount. */
export function ChipFlightView({
  chip,
  motion,
  onLanded,
}: {
  readonly chip: ChipFlight;
  readonly motion: PokerMotion;
  readonly onLanded: (key: string) => void;
}): JSX.Element {
  const style: CSSProperties & Record<string, string> = {
    left: `${String(chip.x)}px`,
    top: `${String(chip.y)}px`,
    '--chip-dx': `${String(chip.dx)}px`,
    '--chip-dy': `${String(chip.dy)}px`,
    '--poker-flight-ms': `${String(scaleMs(motion.flightBaseMs, motion.scale))}ms`,
    '--poker-delay-ms': `${String(scaleMs(chip.delayBaseMs, motion.scale))}ms`,
  };
  // A canceled animation fires animationcancel, not animationend, and the
  // pot and the seat's numbers wait for one of them. A native listener:
  // React has no animationcancel prop.
  const ref = useRef<HTMLSpanElement>(null);
  useEffect(() => {
    const el = ref.current;
    if (!el) return undefined;
    const cancel = (): void => {
      onLanded(chip.key);
    };
    el.addEventListener('animationcancel', cancel);
    return () => {
      el.removeEventListener('animationcancel', cancel);
    };
  }, [chip.key, onLanded]);
  return (
    <span
      aria-hidden
      className="poker-chip-flight"
      data-slot={chip.slot}
      onAnimationEnd={() => {
        onLanded(chip.key);
      }}
      ref={ref}
      style={style}
    >
      {formatChips(chip.amount)}
    </span>
  );
}

/**
 * The cards that make the winning hand(s) at a showdown: each winner's best
 * five, board and hole cards alike. Empty before a showdown and when the
 * hand was won by fold (no hand is ranked then).
 */
export function winningCards(
  seats: readonly PokerSeat[],
  ending: PokerEnding | null,
): Set<string> {
  const codes = new Set<string>();
  if (ending !== 'showdown') {
    return codes;
  }
  for (const seat of seats) {
    if (seat.isWinner) {
      seat.bestFive.forEach(card => codes.add(card.code));
    }
  }
  return codes;
}
