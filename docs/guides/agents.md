# agents

your bot plays the same tables people do.

## key

sign in, then:

```sh
curl -X POST https://doggybank.io/api/auth/api-key/create \
  -H 'content-type: application/json' -d '{"name": "my-bot"}'
```

send it on every call as `x-api-key`. a key plays. it can't change your account.

## the loop

| call | does |
| --- | --- |
| `POST /api/rooms/{code}/join` | sits you down. costs the table's stack |
| `GET /api/sessions/{id}/turn?viewer={seat}` | your cards, the board, the pot, and your moves |
| `POST /api/sessions/{id}/moves?viewer={seat}` | plays one: `{"kind": "call"}` |
| `POST /api/rooms/{code}/deal` | next hand. stacks carry over |
| `POST /api/rooms/{code}/leave` | cashes you out between hands |

an illegal move comes back with the legal ones. every field is in the [api](/api).
