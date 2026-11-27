# Copyright 2026 Doggybank contributors
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

"""Example Hold'em strategies served by remote_bot_server's MODULE:FACTORY.

The call bot checks or calls. The raise bot chooses the smallest bet or
raise, then checks or calls when no aggression is available. Both rank fold
last. Replace choose_action to use cards, stacks, the pot or betting history
from the observation; the server supplies all legal action ids.
"""

import math
from collections.abc import Mapping
from typing import Literal, cast

from doggybank_engine.game import (
    PokerAction,
    PokerActionKind,
)
from doggybank_server import contract

Style = Literal["call", "raise"]
_PREFERENCES: dict[Style, dict[str, int]] = {
    "call": {"check": 0, "call": 1, "bet": 2, "raise": 2, "fold": 3},
    "raise": {"bet": 0, "raise": 0, "check": 1, "call": 2, "fold": 3},
}


def actions(
    observation: Mapping[str, contract.JsonValue],
) -> list[PokerAction]:
    """Decodes the fields these example policies consume at the JSON boundary."""
    values = observation.get("actions")
    if not isinstance(values, list) or not values:
        raise ValueError("The observation needs non-empty actions.")
    actions: list[PokerAction] = []
    for value in values:
        if not isinstance(value, Mapping):
            raise ValueError("Each entry in actions must be an object.")
        action_id, kind, amount = (
            value.get("id"),
            value.get("kind"),
            value.get("amount"),
        )
        if not isinstance(action_id, int) or isinstance(action_id, bool):
            raise ValueError("Each actions entry needs an integer id.")
        if not isinstance(kind, str) or kind not in _PREFERENCES["call"]:
            raise ValueError("Each actions entry needs a Hold'em action kind.")
        if (
            not isinstance(amount, (int, float))
            or isinstance(amount, bool)
            or not math.isfinite(amount)
            or amount < 0
        ):
            raise ValueError("Each actions entry needs a non-negative chip amount.")
        actions.append(
            {
                "id": action_id,
                "kind": cast(PokerActionKind, kind),
                "amount": amount,
            }
        )
    return actions


def choose_action(observation: Mapping[str, contract.JsonValue], style: Style) -> int:
    """Chooses a legal action by policy, using the smallest amount within a kind.

    observation also includes hole_cards, board_cards, stacks, total_pot and
    betting_history for strategies that use the position. Returned ids are
    opaque: bet amounts come from descriptors, never from interpreting the id.
    """
    priorities = _PREFERENCES[style]
    action = min(
        actions(observation),
        key=lambda item: (priorities[item["kind"]], item["amount"], item["id"]),
    )
    return action["id"]


class PokerBot:
    """A deterministic strategy that reads only its seat's private observation."""

    def __init__(self, style: Style) -> None:
        self._style = style

    def move(self, request: dict[str, contract.JsonValue]) -> int:
        """Chooses an action, refusing a malformed or unsupported observation."""
        observation = request.get("observation")
        if not isinstance(observation, Mapping):
            raise ValueError("The move request needs an observation object.")
        version = observation.get("schema_version")
        if not isinstance(version, int) or isinstance(version, bool) or version != 1:
            raise ValueError("PokerBot requires observation schema 1.")
        if observation.get("variant") != "NoLimitTexasHoldem":
            raise ValueError("PokerBot plays only NoLimitTexasHoldem.")
        return choose_action(observation, self._style)


def make_call_bot() -> PokerBot:
    """Creates the check/call example strategy."""
    return PokerBot("call")


def make_raise_bot() -> PokerBot:
    """Creates the minimum-bet/raise example strategy."""
    return PokerBot("raise")
