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

// The poker board: the hand bar (the game, the street, blinds or ante,
// stacks, seats and New hand), the table (the board's cards, the pot and a
// plate per seat, with chips flying to the pot), the controls, and the
// Action History.

import {
  type JSX,
  type ReactNode,
  type RefObject,
  useCallback,
  useMemo,
  useRef,
} from 'react';

import {PokerControls} from './poker-controls.tsx';
import {type SessionPayload, usePokerSession} from './poker-session.ts';
import {
  type PokerSeat,
  type PokerUiState,
  derivePokerState,
  roundName,
} from './poker-state.ts';
import {
  CardView,
  ChipFlightView,
  SeatView,
  formatChips,
  terminalSummary,
  winningCards,
} from './poker-table-parts.tsx';
import {useBoardInDealOrder} from './use-board-in-deal-order.ts';
import {
  type PokerMotion,
  motionSettled,
  shownNumbers,
  usePokerMotion,
} from './use-poker-motion.ts';

import './poker.css';

// The seat counts the hand bar offers.
function BoardCards({
  state,
  motion,
  boardLanded,
  playing,
  slots,
}: {
  readonly state: PokerUiState;
  readonly motion: ReturnType<typeof usePokerMotion>['motion'];
  readonly boardLanded: (index: number) => void;
  readonly playing: ReadonlySet<string>;
  readonly slots: number;
}): JSX.Element {
  return (
    <div className="poker-board__cards">
      {Array.from({length: slots}, (_, index) => {
        const card = state.board[index];
        const delayBaseMs = motion.boardDelays.get(index);
        return (
          <CardView
            card={card}
            key={card?.code ?? `empty-${String(index)}`}
            motion={
              card && delayBaseMs !== undefined
                ? {
                    kind: 'deal',
                    delayBaseMs,
                    motion,
                    onLanded: () => {
                      boardLanded(index);
                    },
                  }
                : undefined
            }
            plays={card !== undefined && playing.has(card.code)}
          />
        );
      })}
    </div>
  );
}

/**
 * The table as it may be drawn while chips fly and cards turn: the hand's
 * outcome (the result, the winner, a showdown's hand names, a fold that came
 * with the chips) waits until everything has landed, so the opponent's
 * action is seen before the result it leads to.
 */
export function heldTable(
  state: PokerUiState,
  motion: PokerMotion,
  boardSizes: readonly number[],
): PokerUiState {
  if (motionSettled(motion)) return state;
  const turning = new Set(
    [...motion.revealDelays.keys()].map(key => Number(key.split(':')[0])),
  );
  return {
    ...state,
    ending: null,
    returns: null,
    currentStreet: state.isTerminal
      ? roundName(state.board, boardSizes)
      : state.currentStreet,
    seats: state.seats.map(seat => ({
      ...seat,
      returnValue: undefined,
      isWinner: false,
      hasFolded: seat.hasFolded && !motion.heldFolds.has(seat.slot),
      bestHand: turning.has(seat.slot) ? undefined : seat.bestHand,
    })),
  };
}

function Table({
  state,
  session,
  motionState,
  tableRef,
  potRef,
  viewerSeat,
  actions,
}: {
  readonly state: PokerUiState;
  readonly session: SessionPayload;
  readonly motionState: ReturnType<typeof usePokerMotion>;
  readonly tableRef: RefObject<HTMLDivElement | null>;
  readonly potRef: RefObject<HTMLDivElement | null>;
  readonly viewerSeat: number | null;
  readonly actions: ReactNode;
}): JSX.Element {
  const {motion, chipLanded, boardLanded, revealLanded} = motionState;
  const shown = shownNumbers(state, motion);
  const playing = winningCards(state.seats, state.ending);
  const slots = session.game.boardSizes.reduce((sum, size) => sum + size, 0);
  const seatView = (seat: PokerSeat): JSX.Element => (
    <SeatView
      key={seat.slot}
      motion={motion}
      revealLanded={revealLanded}
      seat={seat}
      holeCards={session.game.holeCards}
      shown={{
        stack: shown.stack(seat.slot, seat.stack),
        bet: Math.max(
          0,
          shown.contribution(seat.slot, seat.contribution) - state.streetBase,
        ),
      }}
      playing={playing}
      isViewer={seat.slot === viewerSeat}
    />
  );
  const viewer = state.seats.find(seat => seat.slot === viewerSeat);
  return (
    <section
      className={`poker-table${state.isTerminal ? ' poker-table--terminal' : ''}`}
      aria-label="Poker table"
      ref={tableRef}
    >
      <div className="poker-table__opponents">
        {state.seats.filter(seat => seat.slot !== viewerSeat).map(seatView)}
      </div>
      <div className="poker-board">
        <BoardCards
          state={state}
          motion={motion}
          boardLanded={boardLanded}
          playing={playing}
          slots={slots}
        />
        <div className="poker-pot" ref={potRef} aria-label="Pot">
          {formatChips(shown.pot)}
        </div>
      </div>
      {actions}
      {viewer !== undefined && seatView(viewer)}
      {motion.chips.map(chip => (
        <ChipFlightView
          chip={chip}
          motion={motion}
          key={chip.key}
          onLanded={chipLanded}
        />
      ))}
    </section>
  );
}

function useDerived(session: SessionPayload): {
  state: PokerUiState | null;
  error: string | null;
} {
  // A record the table cannot be drawn from (a history row that disagrees
  // with the betting string, a fold by no seat) is said on the panel, in
  // full, not a blank pane.
  return useMemo(() => {
    try {
      return {state: derivePokerState(session), error: null};
    } catch (caught) {
      return {
        state: null,
        error: `This hand's record cannot be drawn: ${caught instanceof Error ? caught.message : String(caught)}`,
      };
    }
  }, [session]);
}

/** The viewer's own seat, marked on the table; null for a spectator or the
 *  oracle. */
function seatOf(viewer: {participantId: string | null}): number | null {
  return viewer.participantId === null ? null : Number(viewer.participantId);
}

/** The result line under the table; empty until the outcome may be shown. */
function showdownLine(state: PokerUiState, viewerSeat: number | null): string {
  return state.ending === null
    ? ''
    : terminalSummary(state.seats, state.returns, state.ending, viewerSeat);
}

/** The poker board, drawn from the session of the renderer it is in. */
export function PokerGameplay(): JSX.Element {
  const {session, error, submitAction, isBusy, createSession, viewer} =
    usePokerSession();
  const derived = useDerived(session);
  const pokerState = useBoardInDealOrder(derived.state, session.sessionId);
  const tableRef = useRef<HTMLDivElement>(null);
  const potRef = useRef<HTMLDivElement>(null);
  const motionState = usePokerMotion(pokerState, tableRef, potRef);
  const viewerSeat = seatOf(viewer);
  const submitIfReady = useCallback(
    (action: number | undefined) => {
      if (typeof action !== 'number' || isBusy) return;
      void submitAction(action);
    },
    [isBusy, submitAction],
  );
  const startNewHand = useCallback(() => {
    createSession({
      seats: session.game.fixedSeats ?? pokerState?.seats.length ?? 2,
    });
  }, [createSession, pokerState?.seats.length, session.game.fixedSeats]);
  if (!pokerState) {
    return (
      <div className="ogs-panel poker-error">
        <div className="ogs-error" role="alert">
          {derived.error ?? error ?? 'Poker session unavailable.'}
        </div>
      </div>
    );
  }
  const {boardSizes} = session.game;
  const canChangeTable = session.mode === 'analysis' || viewerSeat !== null;
  const shownState = heldTable(pokerState, motionState.motion, boardSizes);
  // Only the seat to act may act; another seat's turn offers no presses.
  const canAct =
    viewer.canAct &&
    !pokerState.isTerminal &&
    pokerState.currentPlayer >= 0 &&
    session.state.legalActions.length > 0 &&
    !isBusy;
  return (
    <div className="poker-gameplay">
      {error !== null && (
        <div className="poker-notice" role="alert">
          {error}
        </div>
      )}
      <Table
        state={shownState}
        session={session}
        motionState={motionState}
        tableRef={tableRef}
        potRef={potRef}
        viewerSeat={viewerSeat}
        actions={
          <PokerControls
            state={pokerState}
            canAct={canAct}
            isBusy={isBusy || !canChangeTable}
            fixedLimit={session.game.betting === 'limit'}
            showdownText={showdownLine(shownState, viewerSeat)}
            submitIfReady={submitIfReady}
            startNewHand={startNewHand}
          />
        }
      />
    </div>
  );
}
