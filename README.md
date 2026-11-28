# Doggybank

<div align="center">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="assets/logo-wordmark-dark.svg">
    <img src="assets/logo-wordmark.svg" alt="Doggybank" width="380">
  </picture>
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

## Play

- **In the browser:** sign up at [doggybank.io](https://doggybank.io). You start with
  1,000 chips. Open a table, share its 6-letter code, and play. **New hand** keeps
  your stack.
- **From code:** create a key, send it as `x-api-key`, then join, read your turn,
  move, and deal. [docs.doggybank.io](https://docs.doggybank.io) has the five calls
  and every field.
- **Watch it play:** `apps/players` is a Python client with two strategies.
  `python -m doggybank_players.match --room-hands 10` sits them at one table.

## Bring your own bot

Bots play through the same HTTP API as everyone else: create a key, send it as
`x-api-key`, then join, read your turn, move, and deal.
[docs.doggybank.io](https://docs.doggybank.io) has every call, and
[`apps/players`](apps/players) is a Python client to start from.

## Hosting

`pnpm deploy:dm` provisions a Dedalus Machine running Postgres, the game server and
the sign-in service (see `apps/server/README.md`). `pnpm --filter @doggybank/web run
deploy` deploys the Cloudflare Worker, which serves the page, checks each player's
session, and signs the player into every request it forwards. The game server trusts
only that signature.

## Layout

```text
apps/
  server/                  Python HTTP server, sessions and API
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
