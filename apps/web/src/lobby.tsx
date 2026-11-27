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
} from './contract/contract.ts';
import {openRoom} from './game/game-page.tsx';
import type {SessionClient} from './session/client.ts';

import './lobby.css';

const ROOM_CODE_LENGTH = 6;
const GAME = 'doggybank';

/** The two bot endpoints and the hand's integer-chip stakes. */
export interface MatchSettings {
  readonly bot0: string;
  readonly bot1: string;
  readonly stack: number;
  readonly smallBlind: number;
  readonly bigBlind: number;
}

const DEFAULT_SETTINGS: MatchSettings = {
  bot0: 'http://127.0.0.1:9001',
  bot1: 'http://127.0.0.1:9002',
  stack: 200,
  smallBlind: 1,
  bigBlind: 2,
};

/** Builds one heads-up hand whose remote bots receive private JSON views. */
export function pokerMatchRequest(settings: MatchSettings): CreateSession {
  const {stack, smallBlind, bigBlind} = settings;
  if (
    ![stack, smallBlind, bigBlind].every(Number.isInteger) ||
    smallBlind < 1 ||
    bigBlind <= smallBlind ||
    stack < bigBlind
  ) {
    throw new Error(
      'Use whole chips, a larger big blind, and a stack at least as large as the big blind.',
    );
  }
  const urls = [settings.bot0, settings.bot1].map(value => {
    const url = new URL(value);
    if (!['http:', 'https:'].includes(url.protocol)) {
      throw new Error('Bot URLs must use HTTP or HTTPS.');
    }
    return url.href.replace(/\/$/, '');
  });
  return {
    game: GAME,
    parameters: {
      variant: 'NoLimitTexasHoldem',
      num_players: 2,
      blinds: `${String(smallBlind)} ${String(bigBlind)}`,
      stack_sizes: `${String(stack)} ${String(stack)}`,
    },
    seats: urls.map(url => ({
      controller: 'remote',
      config: {url},
      autoplay: true,
    })),
    chance_policy: 'auto',
    seed: null,
  };
}

/** Creates a hand between independent bot servers, or opens a manual table. */
export function PokerLobby({
  entry,
  client,
  onOpen,
}: {
  readonly entry: CatalogueEntry | undefined;
  readonly client: SessionClient;
  readonly onOpen: (frame: Frame) => void;
}): JSX.Element {
  const [settings, setSettings] = useState(DEFAULT_SETTINGS);
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  async function start(event: SyntheticEvent<HTMLFormElement>): Promise<void> {
    event.preventDefault();
    setPending(true);
    setError(null);
    try {
      const frame = await client.create(
        {kind: 'oracle', seat: null},
        pokerMatchRequest(settings),
      );
      onOpen(frame);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : String(caught));
    } finally {
      setPending(false);
    }
  }
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
        <a href="/game/doggybank">Open a manual table</a>
      </div>
      <MatchForm
        entry={entry}
        settings={settings}
        pending={pending}
        error={error}
        onChange={setSettings}
        onSubmit={event => {
          void start(event);
        }}
      />
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

  async function join(event: SyntheticEvent<HTMLFormElement>): Promise<void> {
    event.preventDefault();
    setPending(true);
    setError(null);

    try {
      onOpen(await client.join(code));
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : String(caught));
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
      {error !== null && <p role="alert">{error}</p>}
    </form>
  );
}

interface MatchFormProps {
  readonly entry: CatalogueEntry | undefined;
  readonly settings: MatchSettings;
  readonly pending: boolean;
  readonly error: string | null;
  readonly onChange: (settings: MatchSettings) => void;
  readonly onSubmit: (event: SyntheticEvent<HTMLFormElement>) => void;
}

function MatchForm({
  entry,
  settings,
  pending,
  error,
  onChange,
  onSubmit,
}: MatchFormProps): JSX.Element {
  const available = entry?.loadable === true;
  const stakes = [
    ['stack', 'Starting stack'],
    ['smallBlind', 'Small blind'],
    ['bigBlind', 'Big blind'],
  ] as const;
  return (
    <form className="lobby__form" onSubmit={onSubmit}>
      <h3>Bot versus bot</h3>
      <BotEndpoint
        seat={0}
        url={settings.bot0}
        disabled={pending}
        onChange={bot0 => {
          onChange({...settings, bot0});
        }}
      />
      <BotEndpoint
        seat={1}
        url={settings.bot1}
        disabled={pending}
        onChange={bot1 => {
          onChange({...settings, bot1});
        }}
      />
      <div className="lobby__stakes">
        {stakes.map(([key, label]) => (
          <Stake
            key={key}
            label={label}
            value={settings[key]}
            disabled={pending}
            onChange={value => {
              onChange({...settings, [key]: value});
            }}
          />
        ))}
      </div>
      <p className="lobby__hint">
        Each bot serves <code>GET /health</code> and <code>POST /move</code>.
        The default addresses match the example bots.
      </p>
      {!available && (
        <p role="alert">
          The poker engine is unavailable. {entry?.unavailable_reason}
        </p>
      )}
      {error !== null && (
        <p role="alert" className="lobby__error">
          {error}
        </p>
      )}
      <button type="submit" disabled={pending || !available}>
        {pending ? 'Starting hand…' : 'Start hand'}
      </button>
    </form>
  );
}

function BotEndpoint({
  seat,
  url,
  disabled,
  onChange,
}: {
  readonly seat: number;
  readonly url: string;
  readonly disabled: boolean;
  readonly onChange: (value: string) => void;
}): JSX.Element {
  return (
    <label className="lobby__field">
      Player {seat + 1} bot URL
      <input
        type="url"
        value={url}
        required
        disabled={disabled}
        onChange={event => {
          onChange(event.currentTarget.value);
        }}
      />
    </label>
  );
}

function Stake({
  label,
  value,
  disabled,
  onChange,
}: {
  readonly label: string;
  readonly value: number;
  readonly disabled: boolean;
  readonly onChange: (value: number) => void;
}): JSX.Element {
  return (
    <label className="lobby__field">
      {label}
      <input
        type="number"
        min={1}
        step={1}
        value={value}
        required
        disabled={disabled}
        onChange={event => {
          onChange(Number(event.currentTarget.value));
        }}
      />
    </label>
  );
}
