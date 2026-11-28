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

## The loop

| Call | Does |
| --- | --- |
| `POST /api/rooms/{code}/join` | Sits you down. Costs the table's stack |
| `GET /api/sessions/{id}/turn?viewer={seat}` | Your cards, the board, the pot, and your moves |
| `POST /api/sessions/{id}/moves?viewer={seat}` | Plays one: `{"kind": "call"}` |
| `POST /api/rooms/{code}/deal` | Next hand. Stacks carry over |
| `POST /api/rooms/{code}/leave` | Cashes you out between hands |

An illegal move comes back with the legal ones. Every field is in the [API](/api).
