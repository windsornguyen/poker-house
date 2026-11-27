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
# Modified for Poker House.


"""JSON values and conversion of typed contracts to their wire form."""

import dataclasses
import enum
from collections.abc import Mapping, Sequence

# A value as it appears on the wire.
JsonValue = None | bool | int | float | str | Sequence["JsonValue"] | Mapping[str, "JsonValue"]


def to_json(value: object) -> JsonValue:
    """Converts a contract value to its wire form.

    Dataclasses become objects that carry every field, nulls included; enums
    become their values; tuples become lists.

    Args:
      value: A contract dataclass, or any value one holds.

    Returns:
      The value as dicts, lists, strings, numbers, booleans and None.

    Raises:
      TypeError: If `value` holds anything else.
    """
    if dataclasses.is_dataclass(value) and not isinstance(value, type):
        return {
            field.name: to_json(getattr(value, field.name)) for field in dataclasses.fields(value)
        }
    if isinstance(value, enum.Enum):
        return to_json(value.value)
    if isinstance(value, (tuple, list)):
        return [to_json(item) for item in value]
    if isinstance(value, dict):
        return {str(key): to_json(item) for key, item in value.items()}
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    raise TypeError(f"The contract cannot carry {value!r}.")
