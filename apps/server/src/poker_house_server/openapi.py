"""The player-facing API as an OpenAPI 3.1 document, for LLM tool frameworks.

  python -m poker_house_server.openapi apps/web/public/openapi.json

The site serves the document as a static file, so reading it wakes nothing.
"""

import dataclasses
import json
import pathlib
import sys

from poker_house_server import contract, schema


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
        "Sit at the lowest open seat of the room with this code.",
        None,
        "Frame",
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
            "title": "Poker House",
            "version": "0.1.0",
            "description": (
                "Sign in with POST /api/auth/sign-in/email to get the session cookie every"
                " call carries. Renew it every four minutes with"
                " GET /api/auth/get-session?disableCookieCache=true."
            ),
        },
        "paths": paths,
        "components": {"schemas": json.loads(text)},
    }


if __name__ == "__main__":
    pathlib.Path(sys.argv[1]).write_text(json.dumps(build(), indent=2) + "\n")
