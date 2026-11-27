# Copyright 2026 Poker House contributors
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

# The poker board's hand-total chip amounts are projected from PokerKit's
# per-street observations; the engine remains the authority on legal moves.
"""Presents PokerKit Hold'em hands to the shared poker board."""

import json
from collections.abc import Mapping, Sequence
from typing import TYPE_CHECKING, cast

import pyspiel

from poker_house_server import adapter, contract

if TYPE_CHECKING:
    from poker_house_engine.game import PokerObservation

GAME = "poker_house"
ACPC_GAME = "poker_house_acpc"

# The shared board supports community-card games with fixed hole-card counts.
_VARIANTS = {
    "NoLimitTexasHoldem": ("No-limit Texas Hold'em", "nolimit", 2),
    "NoLimitShortDeckHoldem": ("No-limit short-deck Hold'em", "nolimit", 2),
    "FixedLimitTexasHoldem": ("Limit Texas Hold'em", "limit", 2),
    "PotLimitOmahaHoldem": ("Pot-limit Omaha", "nolimit", 4),
}
_BOARD_SIZES = (0, 3, 1, 1)


def _observation(state: pyspiel.State, seat: int) -> "PokerObservation":
    """Reads the engine's typed private observation, never its full state."""
    return cast(
        "PokerObservation",
        json.loads(state.to_observation_struct(seat).to_json()),
    )


def _chips(amount: float) -> int:
    """Requires integral chips, as the board's betting notation does."""
    chips = int(amount)
    if chips != amount:
        raise ValueError(f"The poker board requires integer chips, got {amount}.")
    return chips


def _move(observation: "PokerObservation", action: int) -> tuple[str, str]:
    """Names a legal move and its ACPC hand-total betting token."""
    moves = {move["id"]: move for move in observation["actions"]}
    move = moves[action]
    player = observation["current_player"]
    kind = move["kind"]
    if kind == "fold":
        words, token = "Fold", "f"
    elif kind in ("check", "call"):
        words, token = "Call", "c"
    elif kind in ("bet", "raise"):
        base = (
            observation["starting_stacks"][player]
            - observation["stacks"][player]
            - observation["bets"][player]
        )
        amount = _chips(base + move["amount"])
        words, token = f"Bet{amount}", f"r{amount}"
    else:
        raise ValueError(f"The Hold'em board cannot name the move {kind!r}.")
    return f"player={player} move={words}", token


def _history(
    state: pyspiel.State, viewpoint: adapter.Viewpoint
) -> tuple[list[contract.JsonValue], str]:
    """Projects recorded moves into the board's hand-total notation.

    Replaying asks the engine for each move's meaning before it is made,
    including native and ACPC action IDs and the one-chip all-in encoding.
    """
    game = state.get_game()
    replay = game.new_initial_state()
    labels: list[contract.JsonValue] = []
    rounds: list[list[str]] = [[]]
    for action in state.history():
        player = replay.current_player()
        observation = _observation(replay, max(0, player))
        street = observation["street_index"]
        if street is None:
            raise ValueError("A recorded move has no betting street.")
        while len(rounds) <= street:
            rounds.append([])
        after = replay.child(action)
        if replay.is_chance_node():
            public = len(_observation(after, 0)["board_cards"]) > len(observation["board_cards"])
            code = repr(game.int_to_card[action])
            label = (
                f"player=-1 move=Deal {code}"
                if public or viewpoint.omniscient
                else "Chance outcome (hidden)"
            )
        else:
            label, token = _move(observation, action)
            rounds[street].append(token)
        labels.append(label)
        replay = after
    street = _observation(state, 0)["street_index"]
    if street is not None:
        while len(rounds) <= street:
            rounds.append([])
    return labels, "/".join("".join(round_) for round_ in rounds)


def _hands(state: pyspiel.State, viewpoint: adapter.Viewpoint) -> list[str]:
    """Combines only the card views the viewer may read.

    Another seat's observation is the public authority for a spectator: a
    player's own observation would also contain that player's private hand.
    """
    observations = [_observation(state, seat) for seat in range(state.num_players())]
    hands = []
    for seat in range(state.num_players()):
        observer = seat if viewpoint.sees_private(seat) else (seat + 1) % len(observations)
        cards = observations[observer]["hole_cards"][seat]
        hands.append("".join(card for card in cards if card is not None))
    return hands


class PokerkitAdapter(adapter.Adapter):
    """Draws supported PokerKit community-card games with the poker board."""

    renderer = "poker"

    def supports(self, game: pyspiel.Game) -> bool:
        """Leaves stud, unusual antes and oversized tables in their text view."""
        parameters = game.get_parameters()
        antes = str(parameters["antes"]).split()
        return (
            parameters["variant"] in _VARIANTS
            and 2 <= game.num_players() <= 6
            and 1 <= int(parameters["num_streets"]) <= len(_BOARD_SIZES)
            and len(set(antes)) == 1
        )

    def present(
        self, state: pyspiel.State, viewpoint: adapter.Viewpoint
    ) -> dict[str, contract.JsonValue]:
        """Returns public table amounts and only the viewer's known cards."""
        observation = _observation(state, 0)
        initial = _observation(state.get_game().new_initial_state(), 0)
        history, betting = _history(state, viewpoint)
        count = state.num_players()
        starting = observation["starting_stacks"]
        contributions = (
            [0] * count
            if state.is_terminal()
            else [
                _chips(start - stack)
                for start, stack in zip(starting, observation["stacks"], strict=True)
            ]
        )
        title, betting_kind, holes = _VARIANTS[observation["variant"]]
        ante = _chips(initial["starting_stacks"][0] - initial["stacks"][0] - initial["bets"][0])
        struct: dict[str, contract.JsonValue] = {
            "board_cards": "".join(observation["board_cards"]),
            "player_hands": _hands(state, viewpoint),
            "player_contributions": contributions,
            "starting_stacks": list(starting),
            "pot_size": observation["total_pot"],
            "current_player": observation["current_player"],
            "betting_history": betting,
            "blinds": list(initial["bets"]),
            "ante": ante,
            "best_hand_rank_types": [""] * count,
            "best_five_card_hands": [""] * count,
        }
        game: dict[str, contract.JsonValue] = {
            "title": title,
            "betting": betting_kind,
            "holeCards": holes,
            "boardSizes": list(
                _BOARD_SIZES[: int(state.get_game().get_parameters()["num_streets"])]
            ),
            "fixedSeats": count,
        }
        return {
            "struct": struct,
            "historyActionStrings": history,
            "pokerGame": game,
        }

    def describe_actions(
        self,
        state: pyspiel.State,
        actions: Sequence[int],
        viewpoint: adapter.Viewpoint,
    ) -> Mapping[int, contract.JsonValue]:
        """Keeps native IDs and labels raise sizes in total committed chips."""
        del viewpoint
        if not actions:
            return {}
        observation = _observation(state, state.current_player())
        return {action: {"label": _move(observation, action)[0]} for action in actions}

    def public_action_label(self, state: pyspiel.State, action: int) -> str | None:
        """Exposes betting and board cards while withholding hole-card deals."""
        if not state.is_chance_node():
            return _move(_observation(state, state.current_player()), action)[0]
        before = _observation(state, 0)["board_cards"]
        after = _observation(state.child(action), 0)["board_cards"]
        if len(after) > len(before):
            return f"player=-1 move=Deal {after[-1]}"
        return None


ADAPTER = PokerkitAdapter()
