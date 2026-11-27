# Copyright 2026 Poker House contributors
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#      https://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Tests the private, structured PokerKit observation boundary."""

import json
from typing import cast

import pyspiel
from absl.testing import absltest, parameterized

try:
    import pokerkit

    from poker_house_engine import game as pokerkit_wrapper
except ImportError:
    pokerkit_wrapper = None


_BASE = "poker_house"
_ACPC = "poker_house_acpc"
_FORBIDDEN = {"deck", "deck_cards", "burn_cards", "mucked_cards", "operations"}


def _game(name: str = _BASE, stacks: str = "200 200") -> pyspiel.Game:
    return pyspiel.load_game(
        name,
        {
            "variant": "NoLimitTexasHoldem",
            "num_players": 2,
            "blinds": "1 2",
            "stack_sizes": stacks,
        },
    )


def _deal(state: pyspiel.State) -> None:
    while state.is_chance_node():
        state.apply_action(state.chance_outcomes()[0][0])


def _view(state: pyspiel.State, player: int) -> pokerkit_wrapper.PokerObservation:
    return cast(
        "pokerkit_wrapper.PokerObservation",
        json.loads(state.to_observation_struct(player).to_json()),
    )


@absltest.skipIf(pokerkit_wrapper is None, "PokerKit is not installed")
class PokerkitObservationTest(parameterized.TestCase):
    @parameterized.parameters(_BASE, _ACPC)
    def test_dealing_reveals_only_the_observers_cards(self, name: str) -> None:
        state = _game(name).new_initial_state()
        while state.is_chance_node():
            for player in range(2):
                view = _view(state, player)
                self.assertEqual(view["schema_version"], 1)
                self.assertEmpty(_FORBIDDEN.intersection(view))
                self.assertEmpty(view["legal_actions"])
                self.assertEmpty(view["actions"])
                self.assertTrue(all(card is None for card in view["hole_cards"][1 - player]))
            state.apply_action(state.chance_outcomes()[0][0])
        for player in range(2):
            own = _view(state, player)
            other = _view(state, 1 - player)
            self.assertLen(own["hole_cards"][player], 2)
            self.assertEqual(other["hole_cards"][player], [None, None])
            for card in own["hole_cards"][player]:
                self.assertNotIn(card, json.dumps(other))

    @parameterized.parameters(_BASE, _ACPC)
    def test_legal_actions_belong_only_to_the_acting_seat(self, name: str) -> None:
        state = _game(name).new_initial_state()
        _deal(state)
        player = state.current_player()
        view = _view(state, player)
        self.assertEqual(view["legal_actions"], state.legal_actions())
        self.assertEqual([a["id"] for a in view["actions"]], state.legal_actions())
        self.assertIn({"id": 0, "kind": "fold", "amount": 0}, view["actions"])
        self.assertIn({"id": 1, "kind": "call", "amount": 1}, view["actions"])
        self.assertIn({"id": 4, "kind": "raise", "amount": 4}, view["actions"])
        self.assertEqual(view["total_pot"], 3)
        other = _view(state, 1 - player)
        self.assertEmpty(other["actions"])
        self.assertEmpty(other["legal_actions"])

    @parameterized.parameters((_BASE, 5), (_ACPC, 7))
    def test_raise_amounts_are_street_totals_in_both_encodings(
        self, name: str, action: int
    ) -> None:
        state = _game(name).new_initial_state()
        _deal(state)
        state.apply_action(1)
        state.apply_action(1)
        _deal(state)
        view = _view(state, state.current_player())
        self.assertIn({"id": action, "kind": "bet", "amount": 5}, view["actions"])
        self.assertEqual(view["pots"], [{"amount": 4, "eligible_players": [0, 1]}])
        state.apply_action(action)
        view = _view(state, state.current_player())
        self.assertEqual(
            view["betting_history"][-1],
            {
                "player": 0,
                "street_index": 1,
                "kind": "bet",
                "amount": 5,
            },
        )
        self.assertEqual(view["street_index"], 1)
        self.assertEqual(view["total_pot"], 9)

    @parameterized.parameters((_BASE, 2), (_ACPC, 3))
    def test_one_chip_all_in_retains_its_actual_amount(self, name: str, action: int) -> None:
        state = _game(name, stacks="3 3").new_initial_state()
        _deal(state)
        state.apply_action(1)
        state.apply_action(1)
        _deal(state)
        self.assertIn(
            {"id": action, "kind": "bet", "amount": 1},
            _view(state, state.current_player())["actions"],
        )
        state.apply_action(action)
        state.apply_action(1)
        _deal(state)
        self.assertTrue(state.is_terminal())
        self.assertEqual(sum(_view(state, 0)["stacks"]), 6)

    def test_folding_does_not_publish_either_private_hand(self) -> None:
        state = _game().new_initial_state()
        _deal(state)
        private_cards = [_view(state, player)["hole_cards"][player] for player in range(2)]
        state.apply_action(0)
        self.assertTrue(state.is_terminal())
        for player in range(2):
            view = _view(state, player)
            self.assertEqual(view["hole_cards"][player], private_cards[player])
            self.assertEmpty(view["actions"])
            self.assertEmpty(_FORBIDDEN.intersection(view))
            for card in private_cards[1 - player]:
                self.assertNotIn(card, json.dumps(view))

    def test_showdown_reveals_only_publicly_shown_cards(self) -> None:
        game = _game()
        state = game.new_initial_state()
        for card in pokerkit.Card.parse("AcKcAdKd"):
            state.apply_action(game.card_to_int[card])
        state.apply_action(200)
        state.apply_action(1)
        for card in pokerkit.Card.parse("2c3h7d9sJc"):
            state.apply_action(game.card_to_int[card])
        self.assertTrue(state.is_terminal())
        first, second = _view(state, 0), _view(state, 1)
        self.assertEqual(first["hole_cards"], second["hole_cards"])
        self.assertEqual(first["hole_cards"], [["Ac", "Ad"], ["Kc", "Kd"]])
        self.assertLen(first["board_cards"], 5)
        self.assertEmpty(first["legal_actions"])
        self.assertEmpty(_FORBIDDEN.intersection(first))
        self.assertEqual(sum(first["stacks"]), 400)

    def test_stud_upcards_are_public_and_downcards_are_private(self) -> None:
        game = pyspiel.load_game(_BASE, {"variant": "FixedLimitSevenCardStud"})
        state = game.new_initial_state()
        _deal(state)
        for player in range(2):
            own = _view(state, player)["hole_cards"][player]
            other = _view(state, 1 - player)["hole_cards"][player]
            self.assertEqual(other, [None, None, own[2]])

    @parameterized.parameters(-1, 2)
    def test_viewer_must_be_a_real_player(self, player: int) -> None:
        state = _game().new_initial_state()
        with self.assertRaisesRegex(ValueError, "out of range"):
            _view(state, player)


if __name__ == "__main__":
    absltest.main()
