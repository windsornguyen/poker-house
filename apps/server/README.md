# Poker House server

A local poker arena derived from the OpenSpiel GUI server. PokerKit owns
betting rules and payouts; player backends receive private JSON observations
and return an engine-supplied legal action ID.

From the monorepo root:

```sh
uv sync --all-packages --group check
pnpm install
pnpm build
uv run poker-house
```

The browser app is served at `http://127.0.0.1:8787`. Run `pnpm demo` to
start two independent example bot servers and watch their hand. Replace a
factory in the demo command with a module implementing the documented
[`step` interface](src/poker_house_server/REMOTE_BOTS.md).

The server has no authentication and keeps sessions in memory. Use localhost
or a trusted LAN; it is not a public competitive service. The oracle view
intentionally exposes all cards for research. Binding beyond localhost
requires `--host` and, when accessed by a network name, `--allow-host`.

## Deploy to a Dedalus Machine

`pnpm deploy:dm` provisions one Dedalus Machine that runs Postgres on localhost
and this server behind a `key_required` port. It deploys the pushed
`HEAD` commit and can be rerun to update it.

```sh
export DEDALUS_API_KEY=dsk_...
export POKER_HOUSE_MACHINE_ID=...   # omit to create a Machine
export POKER_HOUSE_SITE_URL=https://...   # the site players sign in on
pnpm deploy:dm
```

Only emails in the `poker.player` table can make an account, and each must be
confirmed by the link the sign-up emails. To add a player:

1. On the Machine, insert the lowercase email:
   `psql "$DATABASE_URL" -c "insert into poker.player (email) values ('friend@example.com')"`.
2. In `apps/web`, run `npx wrangler email routing addresses create friend@example.com`.
   Cloudflare sends that address a one-time confirmation, and sign-in emails reach it
   only after the player confirms.

Deleting a player's row deletes their account and sessions.

The first run prints the port's access key once. Keys expire, so issue a new one with `dedalus machines ports access-keys mint`. The key keeps strangers out. Everyone who has it sees every seat's
cards in the analysis view, so share it only with trusted players.

[HTTP contract](src/poker_house_server/CONTRACT.md) ·
[Remote bot protocol](src/poker_house_server/REMOTE_BOTS.md)

```sh
uv run --all-packages python -m unittest discover -s apps/server/tests -p '*_test.py'
uv run ruff format --check && uv run ruff check
uv run ty check
```
