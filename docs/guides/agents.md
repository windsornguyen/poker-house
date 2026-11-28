# Agents

Your bot plays the same tables people do.

## Key

Sign in, then:

```sh
curl -X POST https://doggybank.io/api/auth/api-key/create \
  -H 'content-type: application/json' -d '{"name": "my-bot"}'
```

> [!NOTE]
> Send it on every call as `x-api-key`. A key plays. It can't change your account.

## Open a table

`POST /api/sessions?viewer=0` sits your bot at seat `0` for the table's stack and returns `session.code` and `session.id`:

```json
{
  "game": "doggybank",
  "parameters": {"blinds": "1 2", "stack_sizes": "200 200"},
  "chance_policy": "auto",
  "seed": null,
  "seats": [
    {"controller": "human", "config": {}, "autoplay": false},
    {"controller": "human", "config": {}, "autoplay": false}
  ]
}
```

## The loop

| Call | Does |
| --- | --- |
| `POST /api/sessions?viewer=0` | Opens a table at seat `0` and returns `session.code` and `session.id` |
| `POST /api/rooms/{code}/join` | Sits you down for the table's stack and returns `session.id` and `viewer.seat` |
| `GET /api/rooms/{code}` | Returns the latest hand's `session_id`, your `seat`, and `stacks` |
| `GET /api/sessions/{id}/turn?viewer={seat}` | Your `hole` cards, `board`, `pot`, `to_call`, and legal `moves` |
| `POST /api/sessions/{id}/moves?viewer={seat}` | Plays one, like `{"kind": "call"}` or `{"kind": "raise", "amount": 6}` |
| `POST /api/rooms/{code}/deal` | Deals the next hand from `{"after": id}`. Stacks carry over |
| `POST /api/rooms/{code}/leave` | Cashes you out between hands |

An illegal move comes back with the legal ones. Every field is in the [API](/api).

## Ways to play

- **Bot vs. person:** Open a table and share the 6-letter code with a friend.
- **Bot vs. bot:** Two accounts, two keys, one table.
- **Watch in the browser:** Open the table code at [doggybank.io](https://doggybank.io) while signed in, or spectate at `/game/doggybank?session={id}&viewer=spectator`.

## Working client

`apps/players` is a Python client with two strategies:

```sh
DOGGYBANK_ACCOUNTS=accounts.json uv run --package doggybank-players \
  python -m doggybank_players.match \
  --site https://doggybank.io --room-hands 10
```

`accounts.json` maps `"tight"` and `"pot_odds"` to `{"key": "<api-key>"}`.
