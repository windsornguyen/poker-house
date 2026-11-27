# Poker House

A heads-up poker arena for independently hosted strategy bots. The server
deals no-limit Texas Hold'em, sends each bot its private JSON observation,
validates the returned action, and settles the hand. A browser table shows
the action and lets you replay it.

Poker House uses the OpenSpiel server and poker renderer, with PokerKit
handling the game rules. The relevant components live here. The OpenSpiel
native runtime and PokerKit are installed dependencies. See [NOTICE](NOTICE)
for the source revision and attribution.

## Start

Install Python 3.14, [uv](https://docs.astral.sh/uv/), Node.js 26, pnpm 10.30.3 and
Postgres 19, then run `pnpm setup`. Locally the stack runs as in production: the page
and the Worker in front, the sign-in service and the game server behind it, and
Postgres under both.

1. Create a database and apply `apps/server/schema.sql`, then in `apps/auth` run
   `node migrate.ts` and apply `players.sql`.
2. Start the sign-in service: `node apps/auth/server.ts`, with `DATABASE_URL`,
   `BETTER_AUTH_URL=http://localhost:5173`, `BETTER_AUTH_SECRET` and `MAIL_KEY`.
3. Start the game server: `uv run --package poker-house-server python -m
   poker_house_server`, with `DATABASE_URL` and `POKER_HOUSE_PLAYER_KEY`.
4. Copy `apps/web/.dev.vars.example` to `apps/web/.dev.vars`, fill in the same
   secrets, and run `npx wrangler dev --port 8789` in `apps/web`.
5. Run `pnpm dev` and open [localhost:5173](http://localhost:5173).

Only emails in `poker.player` can make an account. Locally, insert yours and mark
it verified in `auth."user"`, since local email goes nowhere.

## Play with friends

Every table is a room with a six-character code, shown at the top of the table.

1. Sign in and open a table. You hold seat 0.
2. Share the code. A friend signs in and enters it under **Join**. They hold the
   lowest open seat and see only their own cards.
3. Play. Each move reaches the other player at once.

The server decides what each account may see. You see every card only while no one
else holds a seat, and the page switches to your own seat when a friend sits down.

### From code

`apps/web/scripts/join-room.ts` is a complete client in 80 lines. It signs in with
Better Auth's client, joins by code, and checks every answer against the generated
Zod contract (`apps/web/src/contract/contract.ts`):

```sh
POKER_HOUSE_EMAIL=you@example.com POKER_HOUSE_PASSWORD=… \
  node apps/web/scripts/join-room.ts https://your-site ABC123
```

Import `signIn`, `joinRoom` and `play` from it to write a player of your own. A client that
plays longer than five minutes renews its session every four, with
`GET /api/auth/get-session?disableCookieCache=true`, because the site trusts a session
cookie for five. `apps/players` is a Python client that does so, with two strategies and
a duplicate match runner.
Updates arrive as server-sent events from
`/api/sessions/{id}/events?viewer={seat}`. Each event is one `Frame`.

## Bring your own bot

Your backend implements two HTTP methods:

| Method | Purpose |
| --- | --- |
| `GET /health` | Return HTTP 200 with JSON such as `{"ok": true}` when ready. |
| `POST /move` | Read the seat's observation and return `{"action": id}`. |

A move request is `{"seat", "seed", "observation"}`. The observation's
`schema_version` is `1`. It contains cards, stacks, bets, pots, the public
betting history, and the legal actions as `actions`. Unknown opponent cards
are `null`. No deck order or burn cards are sent.

```json
{
  "id": 6,
  "kind": "raise",
  "amount": 6
}
```

Return an **ID from the supplied legal actions**. For bets and raises,
`amount` is the total commitment on the current street. For a call it is
the chips added. An all-in is one of the legal actions, not a separate
command. The server rejects an illegal response and pauses that seat.

For Python strategies, reuse the included HTTP host:

```sh
uv run --package poker-house-server python -m poker_house_server.remote_bot_server \
  --port 9001 --bot my_bot:make_bot
```

The factory returns an object with a `move(request)` method. Start from
[poker_bot.py](apps/server/src/poker_house_server/poker_bot.py), replacing
its action-selection function with your strategy. Any language can implement
the same HTTP protocol.

See the [bot protocol](apps/server/src/poker_house_server/REMOTE_BOTS.md),
[engine observation schema](packages/python/engine/README.md), and
[HTTP API contract](apps/server/src/poker_house_server/CONTRACT.md).

## Hosting

`pnpm deploy:dm` provisions a Dedalus Machine running Postgres, the game server and
the sign-in service (see `apps/server/README.md`). `pnpm --filter @poker-house/web run
deploy` deploys the Cloudflare Worker, which serves the page, checks each player's
session, and signs the player into every request it forwards. The game server trusts
only that signature.

## Layout

```text
apps/
  server/                  Python HTTP server, sessions and bot protocol
  web/                     React browser client and poker table
packages/python/
  engine/                  PokerKit adapter and private observations
```

The repository uses pnpm and uv workspaces. Browser wire types are generated
from the server's JSON schema. Poker rules live in the engine dependency.

```sh
pnpm test
pnpm check
```

Licensed under Apache-2.0. Original upstream notices are retained.
