# Doggybank

<div align="center">
  <img src="docs/doggybank.webp" alt="A long dachshund carrying stacks of poker chips and a fanned hand of cards on its back" width="720">
</div>

WELCOME TO DOGGYBANK.

sponsored by dedalus machines.

live at doggybank.io  


=====================================================================

## Start

Install Python 3.14, [uv](https://docs.astral.sh/uv/), Node.js 26, pnpm 10.30.3 and
Postgres 19, then run `pnpm setup`. Locally the stack runs as in production: the page
and the Worker in front, the sign-in service and the game server behind it, and
Postgres under both.

1. Create a database and apply `apps/server/schema.sql`, then in `apps/auth` run
   `node migrate.ts` and apply `players.sql`.
2. Start the sign-in service: `node apps/auth/server.ts`, with `DATABASE_URL`,
   `BETTER_AUTH_URL=http://localhost:5173`, `BETTER_AUTH_SECRET` and `MAIL_KEY`.
3. Start the game server: `uv run --package doggybank-server python -m
   doggybank_server`, with `DATABASE_URL` and `DOGGYBANK_PLAYER_KEY`.
4. Copy `apps/web/.dev.vars.example` to `apps/web/.dev.vars`, fill in the same
   secrets, and run `npx wrangler dev --port 8789` in `apps/web`.
5. Run `pnpm dev` and open [localhost:5173](http://localhost:5173).

Only emails in `poker.player` can make an account. Locally, insert yours and mark
it verified in `auth."user"`, since local email goes nowhere.

## Play with friends

Every table is a room with a six-character code, shown at the top of the table. A
table whose every seat is a player's is played for chips.

1. Sign in. A new account holds 1,000 chips, shown in the lobby.
2. Open a table. It costs its stack, 200 chips at 1/2 blinds, and you hold seat 0.
3. Share the code. A friend signs in, enters it under **Join**, buys in the same way
   and holds seat 1. Each player sees only their own cards.
4. Play. Each move reaches the other player at once. When the hand ends, **New hand**
   deals the next one at the same room: every stack carries over, the blinds
   alternate, and both pages move to it.
5. A player whose stack reaches zero loses the seat and can still watch. Joining
   again buys back in.

Chips come from a fixed supply of 1,000,000 held by the house. An account of kind
`internal` lists every account and grants chips from the house at `/admin`.

### From code

An agent plays with an API key instead of a browser. Sign in once, create a key with
`POST /api/auth/api-key/create {"name": "my-bot"}`, and send it in the `x-api-key`
header on every call. A key plays games but cannot change its account.

| Call | Does |
| --- | --- |
| `POST /api/sessions?viewer=0` | Opens a room, buying in at seat 0 |
| `POST /api/rooms/{code}/join` | Buys in at a room |
| `GET /api/sessions/{id}/turn?viewer={seat}` | Your cards, the board, the pot, the price, every stack and your legal moves |
| `POST /api/sessions/{id}/moves?viewer={seat}` | Plays `{"kind": "raise", "amount": 40}`, or refuses with the legal moves |
| `POST /api/rooms/{code}/deal` | Deals the hand after `{"after": "<hand id>"}` |
| `GET /api/rooms/{code}` | The latest hand, your seat in it and every stack |
| `POST /api/rooms/{code}/leave` | Cashes your stack out between hands |
| `GET /api/me` | Your chips off the tables |

The site publishes these as OpenAPI 3.1 at `/openapi.json`, which LLM tool frameworks
read directly. Updates arrive as server-sent events from
`/api/sessions/{id}/events?viewer={seat}`, each event one `Frame`. Regenerate the
document with
`uv run --all-packages python -m doggybank_server.openapi apps/web/public/openapi.json`.

`apps/players` is a Python client on keys, with two strategies. Its match runner
plays them duplicate style, or hand after hand at one room with `--room-hands`.

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
uv run --package doggybank-server python -m doggybank_server.remote_bot_server \
  --port 9001 --bot my_bot:make_bot
```

The factory returns an object with a `move(request)` method. Start from
[poker_bot.py](apps/server/src/doggybank_server/poker_bot.py), replacing
its action-selection function with your strategy. Any language can implement
the same HTTP protocol.

See the [bot protocol](apps/server/src/doggybank_server/REMOTE_BOTS.md),
[engine observation schema](packages/python/engine/README.md), and
[HTTP API contract](apps/server/src/doggybank_server/CONTRACT.md).

## Hosting

`pnpm deploy:dm` provisions a Dedalus Machine running Postgres, the game server and
the sign-in service (see `apps/server/README.md`). `pnpm --filter @doggybank/web run
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
