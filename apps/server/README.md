# Doggybank server

A local poker arena derived from the OpenSpiel GUI server. PokerKit owns
betting rules and payouts; player backends receive private JSON observations
and return an engine-supplied legal action ID.

From the monorepo root:

```sh
uv sync --all-packages --group check
pnpm install
pnpm build
uv run doggybank
```

The browser app is served at `http://127.0.0.1:8787`. Bots play through the
HTTP API; `apps/players` is a Python client.

The server has no authentication and keeps sessions in memory. Use localhost
or a trusted LAN; it is not a public competitive service. The oracle view
intentionally exposes all cards for research. Binding beyond localhost
requires `--host` and, when accessed by a network name, `--allow-host`.

## Deploy to a Dedalus Machine

`pnpm machine:create` makes a Machine and installs Postgres, the tools, the units for two
colors of the game server and sign-in service, and kamal-proxy on two key-protected ports.
It prints the Machine ID and each port's access key once, for the Worker's `PORT_KEY` and
`AUTH_PORT_KEY`.

`pnpm machine:deploy` builds the clean `HEAD` as the idle color and moves traffic to it once
it answers `/readyz`. The release workflow runs it on every push to `main`, then retires the
old color after the smoke test passes, or rolls back to it.

```sh
export DEDALUS_API_KEY=dsk_...
pnpm machine:create
export DOGGYBANK_MACHINE_ID=...           # printed by machine:create
export DOGGYBANK_SITE_URL=https://...     # the site players sign in on
pnpm machine:deploy
```

Only emails in the `poker.player` table can make an account, and each must be confirmed by
the link the sign-up emails. To add a player, insert the lowercase email on the Machine:
`psql "$DATABASE_URL" -c "insert into poker.player (email) values ('friend@example.com')"`.
Deleting a player's row deletes their account and sessions.

The port keys reach the server directly, past the Worker's sign-in, so they live only in
the Worker's secrets.

[HTTP contract](src/doggybank_server/CONTRACT.md)

```sh
uv run --all-packages python -m unittest discover -s apps/server/tests -p '*_test.py'
uv run ruff format --check && uv run ruff check
uv run ty check
```
