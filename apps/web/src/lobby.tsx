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

import {
  type JSX,
  type SyntheticEvent,
  useCallback,
  useEffect,
  useState,
} from 'react';

import {Badge} from '@/components/ui/badge';
import {Button} from '@/components/ui/button';
import {Input} from '@/components/ui/input';
import {Table, TableBody, TableCell, TableRow} from '@/components/ui/table';

import type {
  CatalogueEntry,
  CreateSession,
  Frame,
  Me,
  Viewer,
} from './contract/contract.ts';
import {BUY_IN, defaultSession, tableSession} from './game/game-defaults.ts';
import {sessionPath} from './app/route.ts';
import {openRoom} from './game/game-page.tsx';
import type {SessionClient} from './session/client.ts';
import {ContractError} from './session/errors.ts';

import './lobby.css';

const ROOM_CODE_LENGTH = 6;
const GAME = 'doggybank';
const FIRST_SEAT: Viewer = {kind: 'seat', seat: 0};
const SPECTATOR: Viewer = {kind: 'spectator', seat: null};

/** Opens a table, practice against a bot, or joins a room by its code. */
export function PokerLobby({
  entry,
  client,
  onOpen,
}: {
  readonly entry: CatalogueEntry | undefined;
  readonly client: SessionClient;
  readonly onOpen: (frame: Frame) => void;
}): JSX.Element {
  return (
    <section className="lobby" aria-labelledby="lobby-title">
      <div className="lobby__intro">
        <div className="lobby__suits" aria-hidden="true">
          ♠ ♥ ♣ ♦
        </div>
        <h2 id="lobby-title">Bring two bots to the table.</h2>
        <p>
          Heads-up no-limit Texas Hold’em. Each backend receives its own cards
          and legal actions, then returns a move.
        </p>
        <p>Watch the hand, inspect every decision, and replay the result.</p>
        {entry?.loadable === true ? (
          <OpenTable entry={entry} client={client} onOpen={onOpen} />
        ) : (
          <p role="alert">
            The poker engine is unavailable. {entry?.unavailable_reason}
          </p>
        )}
      </div>
      <JoinRoom client={client} onOpen={onOpen} />
      <Chips client={client} />
    </section>
  );
}

// The signed-in player's chips off the tables, which a seat's buy-in comes
// from, and each table they still sit at. A player who closed a table's tab
// finds their stack here, to open the table again or cash out.
function Chips({client}: {readonly client: SessionClient}): JSX.Element | null {
  const [me, setMe] = useState<Me | null>(null);
  const [error, setError] = useState<string | null>(null);
  const refresh = useCallback(() => {
    void client.me().then(setMe);
  }, [client]);
  useEffect(refresh, [refresh]);

  async function cashOut(code: string): Promise<void> {
    setError(null);
    try {
      await client.leave(code);
      refresh();
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : String(caught));
    }
  }

  if (me === null) return null;
  return (
    <div className="flex flex-col gap-2">
      <Badge variant="secondary">{me.balance.toLocaleString()} chips</Badge>
      {me.seats.length > 0 && (
        <Table>
          <TableBody>
            {me.seats.map(seat => (
              <TableRow key={seat.code}>
                <TableCell>
                  Table {seat.code} · {seat.stack.toLocaleString()} chips
                </TableCell>
                <TableCell>
                  <div className="flex justify-end gap-2">
                    <Button
                      variant="outline"
                      size="sm"
                      onClick={() => {
                        void openRoom(client, GAME, seat.code);
                      }}
                    >
                      Open
                    </Button>
                    <Button
                      size="sm"
                      onClick={() => {
                        void cashOut(seat.code);
                      }}
                    >
                      Cash out
                    </Button>
                  </div>
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      )}
      {error !== null && <p role="alert">{error}</p>}
    </div>
  );
}

// Opens a table at its first seat: one played for chips, whose buy-in the
// player confirms by pressing the button, or practice against a bot for
// nothing.
function OpenTable({
  entry,
  client,
  onOpen,
}: {
  readonly entry: CatalogueEntry;
  readonly client: SessionClient;
  readonly onOpen: (frame: Frame) => void;
}): JSX.Element {
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function open(
    request: (entry: CatalogueEntry) => CreateSession,
  ): Promise<void> {
    setPending(true);
    setError(null);
    try {
      onOpen(await client.create(FIRST_SEAT, request(entry)));
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : String(caught));
    } finally {
      setPending(false);
    }
  }

  return (
    <div className="flex flex-col gap-2">
      <div className="flex flex-wrap gap-2">
        <Button
          disabled={pending}
          onClick={() => {
            void open(tableSession);
          }}
        >
          Open a table · {BUY_IN} chips
        </Button>
        <Button
          variant="outline"
          disabled={pending}
          onClick={() => {
            void open(defaultSession);
          }}
        >
          Practice against a bot
        </Button>
      </div>
      {error !== null && <p role="alert">{error}</p>}
    </div>
  );
}

function JoinRoom({
  client,
  onOpen,
}: {
  readonly client: SessionClient;
  readonly onOpen: (frame: Frame) => void;
}): JSX.Element {
  const [code, setCode] = useState('');
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [watch, setWatch] = useState<string | null>(null);

  async function join(event: SyntheticEvent<HTMLFormElement>): Promise<void> {
    event.preventDefault();
    setPending(true);
    setError(null);
    setWatch(null);

    try {
      onOpen(await client.join(code));
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : String(caught));
      // A player short of the buy-in may still watch the hand.
      if (
        caught instanceof ContractError &&
        caught.code === 'insufficient_chips'
      ) {
        const room = await client.room(code);
        if (room.session_id !== null) {
          setWatch(sessionPath(GAME, room.session_id, SPECTATOR));
        }
      }
    } finally {
      setPending(false);
    }
  }

  return (
    <form
      className="flex flex-col gap-2"
      onSubmit={event => {
        void join(event);
      }}
    >
      <div className="flex gap-2">
        <Input
          aria-label="Room code"
          placeholder="Room code"
          maxLength={ROOM_CODE_LENGTH}
          value={code}
          onChange={event => {
            setCode(event.target.value.toUpperCase());
          }}
        />
        <Button
          type="submit"
          disabled={pending || code.length !== ROOM_CODE_LENGTH}
        >
          Join
        </Button>
      </div>
      {error !== null && (
        <p role="alert">
          {error} {watch !== null && <a href={watch}>Watch the table</a>}
        </p>
      )}
    </form>
  );
}
