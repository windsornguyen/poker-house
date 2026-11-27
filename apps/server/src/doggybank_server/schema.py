# Copyright 2026 DeepMind Technologies Limited
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
# Modified for Doggybank.

"""Writes the API's JSON Schema, from which the web client generates its types.

python -m doggybank_server.schema
"""

import json
import pathlib

import pydantic

from doggybank_server import (
    accounts,
    catalogue,
    contract,
    errors,
    frame,
    health,
    moves,
    request,
    rooms,
)

SCHEMA_PATH = pathlib.Path(__file__).with_name("contract.schema.json")

KEYWORDS = frozenset(
    {
        "$ref",
        "additionalProperties",
        "anyOf",
        "const",
        "description",
        "enum",
        "items",
        "oneOf",
        "properties",
        "required",
        "type",
    }
)

type ResponseBody = (
    frame.Frame
    | catalogue.Catalogue
    | health.Health
    | contract.SessionClosed
    | errors.Error
    | accounts.Me
    | accounts.Accounts
    | rooms.RoomView
    | moves.Turn
)
type RequestBody = (
    request.CreateSession
    | request.ApplyAction
    | request.PlayMove
    | request.ApplyChanceOutcome
    | request.Advance
    | request.Reset
    | request.SeatConfig
    | request.Grant
    | request.Deal
)


def keep_client_keywords(schema: contract.JsonValue) -> contract.JsonValue:
    """Drops the keywords the client's type generator does not read."""
    if isinstance(schema, list):
        return [keep_client_keywords(item) for item in schema]
    if not isinstance(schema, dict):
        return schema
    kept: dict[str, contract.JsonValue] = {}
    for key, value in schema.items():
        if key not in KEYWORDS:
            continue
        if key == "properties" and isinstance(value, dict):
            kept[key] = {name: keep_client_keywords(field) for name, field in value.items()}
        elif key in ("enum", "const", "required"):
            kept[key] = value
        else:
            kept[key] = keep_client_keywords(value)
    return kept


def build() -> dict[str, contract.JsonValue]:
    """Returns the schema of every response and request body."""
    responses = pydantic.TypeAdapter(ResponseBody).json_schema(mode="serialization")
    requests = pydantic.TypeAdapter(RequestBody).json_schema(mode="validation")
    definitions = {**requests["$defs"], **responses["$defs"]}
    definitions["JsonValue"] = {"description": "Any JSON value."}
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "title": "Doggybank API",
        "description": "Every response body is one of these; request bodies are in $defs.",
        "oneOf": responses["anyOf"],
        "$defs": {
            name: keep_client_keywords(definition)
            for name, definition in sorted(definitions.items())
        },
    }


if __name__ == "__main__":
    SCHEMA_PATH.write_text(json.dumps(build(), indent=2) + "\n")
