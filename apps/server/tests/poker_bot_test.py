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

"""Reference strategies use structured legal moves without hidden state."""

import json
import random

from absl.testing import absltest

from poker_house_server import contract
from poker_house_server import loader
from poker_house_server import poker_bot
from poker_house_server import remote_bot


def _request(
    actions: list[contract.JsonValue],
) -> dict[str, contract.JsonValue]:
  """Wraps action descriptors in the structured seat-view request."""
  return {
      "observation": {
          "observation_struct": {
              "schema_version": 1,
              "variant": "NoLimitTexasHoldem",
              "actions": actions,
          },
      },
  }


class PokerBotTest(absltest.TestCase):

  def test_passive_and_aggressive_policies_choose_from_the_given_moves(
      self,
  ) -> None:
    request = _request([
        {"id": 0, "kind": "fold", "amount": 0},
        {"id": 91, "kind": "raise", "amount": 10},
        {"id": 82, "kind": "raise", "amount": 5},
        {"id": 1, "kind": "call", "amount": 2},
    ])
    self.assertEqual(poker_bot.make_call_bot().step("seat_view", request), 1)
    self.assertEqual(poker_bot.make_raise_bot().step("seat_view", request), 82)

  def test_both_policies_check_when_no_bet_is_available(self) -> None:
    request = _request([{"id": 7, "kind": "check", "amount": 0}])
    for bot in (poker_bot.make_call_bot(), poker_bot.make_raise_bot()):
      self.assertEqual(bot.state_modes, ("seat_view",))
      self.assertEqual(bot.step("seat_view", request), 7)

  def test_fold_is_an_explicit_policy_choice_when_it_is_the_only_move(
      self,
  ) -> None:
    request = _request([{"id": 9, "kind": "fold", "amount": 0}])
    for bot in (poker_bot.make_call_bot(), poker_bot.make_raise_bot()):
      self.assertEqual(bot.step("seat_view", request), 9)

  def test_missing_or_malformed_structured_inputs_are_refused(self) -> None:
    bot = poker_bot.make_call_bot()
    requests: tuple[dict[str, contract.JsonValue], ...] = (
        {},
        {"observation": {}},
        {"observation": None},
    )
    for request in requests:
      with self.subTest(request=request):
        with self.assertRaisesRegex(ValueError, "structured"):
          bot.step("seat_view", request)
    bad_actions: tuple[list[contract.JsonValue], ...] = (
        [],
        [{"id": True, "kind": "check", "amount": 0}],
        [{"id": 1, "kind": "teleport", "amount": 0}],
        [{"id": 1, "kind": "call", "amount": -1}],
    )
    for actions in bad_actions:
      with self.subTest(actions=actions):
        with self.assertRaisesRegex(ValueError, "actions"):
          bot.step("seat_view", _request(actions))
    with self.assertRaisesRegex(ValueError, "seat_view"):
      bot.step("full_state", _request([]))

  def test_live_holdem_games_end_with_only_legal_moves(self) -> None:
    for name in (
        "poker_house",
        "poker_house_acpc",
    ):
      game = loader.load(
          name,
          {
              "variant": "NoLimitTexasHoldem",
              "num_players": 2,
              "blinds": "1 2",
              "stack_sizes": "40 40",
          },
      ).game
      transport = remote_bot.RemoteBot(
          game,
          url="http://127.0.0.1:9001",
          state_mode="seat_view",
          bot_config={},
          extras=False,
          tensors=False,
          structured=True,
          timeout_seconds=0,
          seed=3,
      )
      for factories in (
          (poker_bot.make_call_bot, poker_bot.make_call_bot),
          (poker_bot.make_raise_bot, poker_bot.make_call_bot),
          (poker_bot.make_raise_bot, poker_bot.make_raise_bot),
      ):
        with self.subTest(game=name, factories=factories):
          state = game.new_initial_state()
          bots = [factory() for factory in factories]
          rng = random.Random(17)
          decisions = 0
          while not state.is_terminal():
            if state.is_chance_node():
              action = rng.choice(state.chance_outcomes())[0]
            else:
              seat = state.current_player()
              _, body = transport.request(state, seat)
              action = bots[seat].step("seat_view", json.loads(body))
              self.assertIn(action, state.legal_actions())
              decisions += 1
              self.assertLess(decisions, 200)
            state.apply_action(action)
          self.assertGreater(decisions, 0)
          self.assertEqual(sum(state.returns()), 0)


if __name__ == "__main__":
  absltest.main()
