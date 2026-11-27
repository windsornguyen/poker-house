"""The player-facing API as an OpenAPI 3.1 document, for LLM tool frameworks.

  python -m doggybank_server.openapi apps/web/public/openapi.json

The site serves the document as a static file, so reading it wakes nothing.
"""

import dataclasses
import json
import pathlib
import sys

from doggybank_server import contract, schema


@dataclasses.dataclass(frozen=True)
class Operation:
    """One route a player calls."""

    method: str
    path: str
    name: str
    summary: str
    request: str | None
    response: str
    viewer: bool


OPERATIONS = (
    Operation(
        "post",
        "/api/sessions",
        "createRoom",
        "Open a room and sit at its first seat.",
        "CreateSession",
        "Frame",
        viewer=True,
    ),
    Operation(
        "post",
        "/api/rooms/{code}/join",
        "joinRoom",
        "Sit at the room with this code, buying in with its stack. The answer is your"
        " seat's view of its hand, or a spectator's when you are dealt into the next.",
        None,
        "Frame",
        viewer=False,
    ),
    Operation(
        "get",
        "/api/rooms/{code}",
        "getRoom",
        "The room: its latest hand, your seat in it and every stack.",
        None,
        "RoomView",
        viewer=False,
    ),
    Operation(
        "post",
        "/api/rooms/{code}/deal",
        "dealNextHand",
        "Deal the hand after the one you saw finish, or get it if it is already dealt.",
        "Deal",
        "Frame",
        viewer=False,
    ),
    Operation(
        "post",
        "/api/rooms/{code}/leave",
        "leaveRoom",
        "Get up between hands, moving your stack back to your account.",
        None,
        "RoomView",
        viewer=False,
    ),
    Operation(
        "get",
        "/api/sessions/{id}/turn",
        "getTurn",
        "Your turn: your cards, the board, the pot, the price and your legal moves.",
        None,
        "Turn",
        viewer=True,
    ),
    Operation(
        "get",
        "/api/me",
        "getMe",
        "Your chips off the tables.",
        None,
        "Me",
        viewer=False,
    ),
    Operation(
        "get",
        "/api/sessions/{id}",
        "getTable",
        "The table as your seat sees it.",
        None,
        "Frame",
        viewer=True,
    ),
    Operation(
        "post",
        "/api/sessions/{id}/moves",
        "playMove",
        "Fold, check, call, or bet or raise to an amount.",
        "PlayMove",
        "Frame",
        viewer=True,
    ),
)

QUICKSTART = """\
Poker for people and agents. Every table plays for chips, and every chip is accounted for.

1. Sign up at [doggybank.io/auth/sign-up](https://doggybank.io/auth/sign-up). You start
   with 1,000 chips.
2. Create a key with `POST /api/auth/api-key/create {"name": "my-bot"}` while signed in,
   and send it as `x-api-key` on every call.
3. Play:
   - `POST /api/rooms/{code}/join` sits you at a table. It costs the table's stack.
   - `GET /api/sessions/{id}/turn?viewer={seat}` shows your cards, the pot and your moves.
   - `POST /api/sessions/{id}/moves?viewer={seat}` plays one, like `{"kind": "call"}`.
   - `POST /api/rooms/{code}/deal` deals the next hand. Your stack carries over.
   - `POST /api/rooms/{code}/leave` cashes your stack out between hands.
"""

VIEWER: dict[str, contract.JsonValue] = {
    "name": "viewer",
    "in": "query",
    "required": True,
    "description": "Your seat's index, the one the room seated you at.",
    "schema": {"type": "string"},
}


def operation(op: Operation) -> dict[str, contract.JsonValue]:
    """The OpenAPI operation object of `op`."""
    parameters: list[contract.JsonValue] = [
        {"name": name, "in": "path", "required": True, "schema": {"type": "string"}}
        for name in ("id", "code")
        if "{" + name + "}" in op.path
    ]
    if op.viewer:
        parameters.append(VIEWER)

    body: dict[str, contract.JsonValue] = {
        "operationId": op.name,
        "summary": op.summary,
        "parameters": parameters,
        "responses": {
            "200": {"description": op.response, "content": json_of(op.response)},
            "default": {"description": "A refusal", "content": json_of("Error")},
        },
    }
    if op.request is not None:
        body["requestBody"] = {"required": True, "content": json_of(op.request)}
    return body


def json_of(name: str) -> dict[str, contract.JsonValue]:
    """A JSON body of the schema `name`."""
    body: dict[str, contract.JsonValue] = {
        "application/json": {"schema": {"$ref": f"#/components/schemas/{name}"}}
    }
    return body


def build() -> dict[str, contract.JsonValue]:
    """The document: every operation, and every schema they name."""
    text = json.dumps(schema.build()["$defs"]).replace("#/$defs/", "#/components/schemas/")
    paths: dict[str, contract.JsonValue] = {}
    for op in OPERATIONS:
        methods = paths.setdefault(op.path, {})
        assert isinstance(methods, dict)
        methods[op.method] = operation(op)

    return {
        "openapi": "3.1.0",
        "info": {
            "title": "Doggybank",
            "version": "0.1.0",
            "description": QUICKSTART,
        },
        "security": [{"apiKey": []}],
        "paths": paths,
        "components": {
            "schemas": json.loads(text),
            "securitySchemes": {"apiKey": {"type": "apiKey", "in": "header", "name": "x-api-key"}},
        },
    }


if __name__ == "__main__":
    pathlib.Path(sys.argv[1]).write_text(json.dumps(build(), indent=2) + "\n")
