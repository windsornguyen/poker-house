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

"""Tests the PokerKit table's amounts and private-card boundaries."""

import json
import random
from collections.abc import Mapping

import pyspiel
from absl.testing import absltest

import poker_house_engine.game  # noqa: F401  registers the poker games with pyspiel
from poker_house_server import adapter, contract, presenters

_GAME = "poker_house"
_ACPC = "poker_house_acpc"
_ORACLE = adapter.Viewpoint(seat=None, omniscient=True)
_SPECTATOR = adapter.Viewpoint(seat=None, omniscient=False)
_HOLE = ("As", "Kc", "Ah", "Kd")
_BOARD = ("2c", "3d", "4h", "7s", "9c")
_STACK = 200
_CALL = 1
_FOLD = 0


def _hand(name: str = _GAME) -> pyspiel.State:
    """Returns a heads-up hand after dealing two known pairs."""
    game = pyspiel.load_game(name, {"blinds": "1 2", "stack_sizes": "200 200"})
    state = game.new_initial_state()
    _deal(state, _HOLE)
    return state


def _deal(state: pyspiel.State, cards: tuple[str, ...]) -> None:
    """Applies the engine's chance IDs for the named cards."""
    codes = {repr(card): action for action, card in state.get_game().int_to_card.items()}
    for card in cards:
        state.apply_action(codes[card])


def _view(state: pyspiel.State, viewpoint: adapter.Viewpoint) -> dict[str, contract.JsonValue]:
    """Returns the registered adapter's wire view."""
    presentation = presenters.present(
        str(state.get_game().get_type().short_name), state, viewpoint, None
    )
    assert presentation is not None, "PokerKit has no table presentation."
    decoded: dict[str, contract.JsonValue] = json.loads(json.dumps(presentation.view))
    return decoded


def _struct(state: pyspiel.State, viewpoint: adapter.Viewpoint) -> Mapping[str, contract.JsonValue]:
    """Returns the poker board's struct."""
    value = _view(state, viewpoint)["struct"]
    assert isinstance(value, Mapping)
    return value


class PokerkitAdapterTest(absltest.TestCase):
    def test_draws_native_and_acpc_heads_up_holdem(self) -> None:
        for name in (_GAME, _ACPC):
            with self.subTest(game=name):
                state = _hand(name)
                struct = _struct(state, _ORACLE)
                self.assertEqual(struct["player_hands"], ["AsAh", "KcKd"])
                self.assertEqual(struct["player_contributions"], [2, 1])
                self.assertEqual(struct["starting_stacks"], [_STACK, _STACK])
                self.assertEqual(struct["blinds"], [2, 1])
                self.assertEqual(struct["pot_size"], 3)
                self.assertEqual(struct["current_player"], 1)
                self.assertEqual(
                    _view(state, _ORACLE)["pokerGame"],
                    {
                        "title": "No-limit Texas Hold'em",
                        "betting": "nolimit",
                        "holeCards": 2,
                        "boardSizes": [0, 3, 1, 1],
                        "fixedSeats": 2,
                    },
                )

    def test_a_seat_sees_only_its_cards_and_public_betting(self) -> None:
        state = _hand()
        state.apply_action(6)
        for seat, holes in ((0, ["AsAh", ""]), (1, ["", "KcKd"])):
            view = _view(state, adapter.Viewpoint(seat, False))
            struct = view["struct"]
            assert isinstance(struct, Mapping)
            self.assertEqual(struct["player_hands"], holes)
            self.assertEqual(
                view["historyActionStrings"],
                [
                    "Chance outcome (hidden)",
                    "Chance outcome (hidden)",
                    "Chance outcome (hidden)",
                    "Chance outcome (hidden)",
                    "player=1 move=Bet6",
                ],
            )
        spectator = _view(state, _SPECTATOR)
        self.assertEqual(_struct(state, _SPECTATOR)["player_hands"], ["", ""])
        for card in _HOLE:
            self.assertNotIn(card, json.dumps(spectator))

    def test_street_raise_ids_keep_their_hand_total_board_labels(self) -> None:
        for name in (_GAME, _ACPC):
            with self.subTest(game=name):
                state = _hand(name)
                state.apply_action(_CALL)
                state.apply_action(_CALL)
                _deal(state, _BOARD[:3])
                minimum = 2 if name == _GAME else 4
                presentation = presenters.present(name, state, _ORACLE, [minimum, _CALL])
                assert presentation is not None
                self.assertEqual(
                    {hint.id: hint.hint for hint in presentation.actions or ()},
                    {
                        minimum: {"label": "player=0 move=Bet4"},
                        _CALL: {"label": "player=0 move=Call"},
                    },
                )
                state.apply_action(10 if name == _GAME else 12)
                struct = _struct(state, _ORACLE)
                self.assertEqual(struct["betting_history"], "cc/r12")
                self.assertEqual(struct["player_contributions"], [12, 2])
                self.assertEqual(struct["pot_size"], 14)
                self.assertEqual(struct["board_cards"], "2c3d4h")

    def test_a_fold_never_reveals_the_opponents_cards(self) -> None:
        state = _hand()
        state.apply_action(_FOLD)
        struct = _struct(state, _SPECTATOR)
        self.assertEqual(struct["player_hands"], ["", ""])
        self.assertEqual(struct["current_player"], pyspiel.PlayerId.TERMINAL)
        self.assertEqual(struct["pot_size"], 0)
        self.assertEqual(struct["player_contributions"], [0, 0])
        self.assertEqual(struct["betting_history"], "f")
        for card in _HOLE:
            self.assertNotIn(card, json.dumps(_view(state, _SPECTATOR)))

    def test_showdown_reveals_only_cards_actually_shown(self) -> None:
        state = _hand()
        state.apply_action(_STACK)
        state.apply_action(_CALL)
        _deal(state, _BOARD)
        self.assertTrue(state.is_terminal())
        self.assertEqual(state.returns(), [_STACK, -_STACK])
        struct = _struct(state, _SPECTATOR)
        self.assertEqual(struct["player_hands"], ["AsAh", "KcKd"])
        self.assertEqual(struct["board_cards"], "2c3d4h7s9c")
        self.assertEqual(struct["pot_size"], 0)
        self.assertEqual(struct["player_contributions"], [0, 0])

    def test_public_labels_reveal_board_cards_and_bets_only(self) -> None:
        state = _hand()
        self.assertEqual(presenters.public_action_label(state, _CALL), "player=1 move=Call")
        opening = state.get_game().new_initial_state()
        self.assertIsNone(presenters.public_action_label(opening, opening.legal_actions()[0]))
        state.apply_action(_CALL)
        state.apply_action(_CALL)
        action = state.chance_outcomes()[0][0]
        card = repr(state.get_game().int_to_card[action])
        self.assertEqual(
            presenters.public_action_label(state, action),
            f"player=-1 move=Deal {card}",
        )

    def test_chance_and_terminal_states_offer_no_player_moves(self) -> None:
        state = _hand()
        opening = state.get_game().new_initial_state()
        state.apply_action(_FOLD)
        for position in (opening, state):
            presentation = presenters.present(_GAME, position, _ORACLE, [])
            assert presentation is not None
            self.assertEqual(presentation.actions, ())

    def test_stud_and_razz_keep_their_text_view(self) -> None:
        for variant in ("FixedLimitSevenCardStud", "FixedLimitRazz"):
            with self.subTest(variant=variant):
                state = pyspiel.load_game(_GAME, {"variant": variant}).new_initial_state()
                self.assertIsNone(presenters.present(_GAME, state, _ORACLE, None))
                self.assertIsNone(presenters.public_action_label(state, 0))

    def test_hidden_cards_stay_hidden_through_random_hands(self) -> None:
        rng = random.Random(7)
        for _ in range(10):
            state = pyspiel.load_game(
                _GAME, {"blinds": "1 2", "stack_sizes": "20 20"}
            ).new_initial_state()
            while True:
                view = _view(state, _SPECTATOR)
                labels = view["historyActionStrings"]
                assert isinstance(labels, list)
                self.assertEqual(len(labels), len(state.history()))
                public = state.deepcopy_wrapped_state()
                text = json.dumps(view)
                for seat, cards in enumerate(public.hole_cards):
                    for card, shown in zip(cards, public.hole_card_statuses[seat], strict=False):
                        if not shown:
                            self.assertNotIn(repr(card), text)
                if state.is_terminal():
                    break
                state.apply_action(rng.choice(state.legal_actions()))


if __name__ == "__main__":
    absltest.main()
