"""The player-facing API as an OpenAPI 3.1 document, for LLM tool frameworks.

  python -m doggybank_server.openapi apps/web/public/openapi.json

The site serves the document as a static file, so reading it wakes nothing.
"""

import json
import pathlib
import sys

from doggybank_server import app, contract, health_report, loader, store

QUICKSTART = """\
Poker for people and agents. Every table plays for chips, and every chip is accounted for.

1. Sign up at [doggybank.io/auth/sign-up](https://doggybank.io/auth/sign-up). You start
   with 1,000 chips.
2. Create a key with `POST /api/auth/api-key/create {"name": "my-bot"}` while signed in,
   and send it as `x-api-key` on every call.
3. Play:
   - `POST /api/rooms/{code}/join` sits you at a table. It costs the table's stack.
   - `GET /api/sessions/{id}/turn?viewer={seat}` shows your cards, the pot, and your moves.
   - `POST /api/sessions/{id}/moves?viewer={seat}` plays one, like `{"kind": "call"}`.
   - `POST /api/rooms/{code}/deal` deals the next hand. Your stack carries over.
   - `POST /api/rooms/{code}/leave` cashes your stack out between hands.
"""


def build() -> dict[str, contract.JsonValue]:
    """The document of the app's player-facing routes."""
    served = app.create_app(
        store.SessionStore(),
        catalogue=loader.build_catalogue,
        health=health_report.build,
        player_key="",
        client=app.CLIENT_ROOT,
        allowed_hosts=frozenset(),
    )
    served.description = QUICKSTART
    return served.openapi()


if __name__ == "__main__":
    pathlib.Path(sys.argv[1]).write_text(json.dumps(build(), indent=2) + "\n")
