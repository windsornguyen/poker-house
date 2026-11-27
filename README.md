# Poker House

A heads-up poker arena for independently hosted strategy bots. The server
deals no-limit Texas Hold'em, sends each bot its private JSON observation,
validates the returned action, and settles the hand. A browser table shows
the action and lets you replay it.

Poker House uses the OpenSpiel server and poker renderer, with PokerKit
handling the game rules. The relevant components live here; the OpenSpiel
native runtime and PokerKit are installed dependencies. See [NOTICE](NOTICE)
for the source revision and attribution.

## Start

Install Python 3.12, [uv](https://docs.astral.sh/uv/), Node.js 22.22.2 or
newer supported LTS, and pnpm 10.30.3. From the repository root:

```sh
pnpm setup
pnpm demo
```

The demo starts the web server and two independent bot servers, plays a
200-chip hand at blinds 1/2, and prints its browser URL. One example bot
checks/calls; the other bets or raises the minimum legal amount. Ctrl-C
stops all three processes. The examples demonstrate the interface; they are
not strong poker strategies.

To start just the application:

```sh
pnpm dev
```

Open [localhost:8787](http://127.0.0.1:8787), enter the two bot URLs and
stakes, then press **Start hand**. The lobby selects private structured
observations for both bots. **New hand** deals again with the same settings
from the operator's view. Each hand starts with the configured stacks; the
terminal returns report each player's net chips for that hand.

For the included bot servers, run `pnpm bot:call` and `pnpm bot:raise` in
separate terminals. Their addresses are prefilled in the lobby. A manual
table and each seat's settings are also available in the browser.

## Bring your own bot

Your backend implements two HTTP methods:

| Method | Purpose |
| --- | --- |
| `GET /health` | Return HTTP 200 with JSON such as `{"ok": true}` when ready. |
| `POST /spiel/observe` | Read the JSON observation and return `{"action": id}`. |

Every move request has `Spiel-Protocol: 1`. Poker data is in
`observation.observation_struct`; its `schema_version` is `1`. It contains
cards, stacks, bets, pots, the public betting history, and typed legal
actions. Unknown opponent cards are `null`. No deck order or burn cards are
sent.

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

The factory returns an object declaring `state_modes = ("seat_view",)` and
implementing `step(mode, request)`. Start from
[poker_bot.py](apps/server/src/poker_house_server/poker_bot.py), replacing
its action-selection function with your strategy. Any language can implement
the same HTTP protocol.

See the [bot protocol](apps/server/src/poker_house_server/REMOTE_BOTS.md),
[engine observation schema](packages/python/engine/README.md), and
[HTTP API contract](apps/server/src/poker_house_server/CONTRACT.md).

## Hosting

Localhost is the default. On a trusted LAN:

```sh
pnpm dev:lan --allow-host YOUR_LAN_IP
```

For a bot on another machine, explicitly allow its hostname with
`--remote-bot-host HOST`. The remote bot host supports bearer authentication
through `--token-env`; the game server's corresponding option is
`--remote-bot-token-env HOST:PORT=VARIABLE`.

This initial server inherits OpenSpiel's research model: sessions live in
memory, and the browser's analysis view can inspect every player's cards.
Use it with trusted participants on localhost or a private network. A
public competitive service needs authentication, authorization and durable
match storage.

The Python/native engine does not run directly in Cloudflare Workers.
Run the server on a computer or VM. A protected tunnel can provide remote
access, but does not move the engine into Workers.

## Layout

```text
apps/
  server/                  Python HTTP server, sessions and bot protocol
  web/                     React browser client and poker table
packages/python/
  engine/                  PokerKit adapter and private observations
```

The repository uses pnpm and uv workspaces. Browser wire types are generated
from the server's JSON schema; poker rules live in the engine dependency.

```sh
pnpm test
pnpm check
```

Licensed under Apache-2.0. Original upstream notices are retained.
