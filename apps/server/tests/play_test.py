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

"""The launcher lets valid bot decisions finish within their move budgets."""

import io
import os
import re
import sys
from pathlib import Path
import tempfile
from unittest import mock

from absl.testing import absltest

from poker_house_server import play
from poker_house_server import child_servers

_SLOW_BOT = """
import time
from poker_house_server.poker_bot import PokerBot

class SlowBot(PokerBot):
  def move(self, request):
    time.sleep(0.1)
    return super().move(request)

def make_bot():
  return SlowBot("call")
"""


class LauncherTest(absltest.TestCase):

  def test_a_stopped_child_closes_its_captured_output(self) -> None:
    child = child_servers.ChildServer(
        "fixture",
        [sys.executable, "-c", "print('ready http://127.0.0.1:1', flush=True)"],
        os.environ,
        re.compile(r"ready (http://\S+)"),
        io.StringIO(),
    )
    try:
      child.wait_ready(5)
    finally:
      child.stop()
    assert child.process.stdout is not None
    self.assertTrue(child.process.stdout.closed)

  def test_creation_waits_for_legal_bot_moves_beyond_the_health_timeout(
      self,
  ) -> None:
    with tempfile.TemporaryDirectory() as directory:
      Path(directory, "slow_poker_bot.py").write_text(_SLOW_BOT)
      environment = {
          "PYTHONPATH": os.pathsep.join(
              [directory, os.environ.get("PYTHONPATH", "")]
          )
      }
      options = play.Options(
          game="poker_house(blinds=1 2,stack_sizes=20 20)",
          bot="slow_poker_bot:make_bot",
          spectate=True,
          server_per_seat=True,
          port=0,
          move_budget_seconds=1,
      )
      with mock.patch.dict(os.environ, environment), mock.patch.object(
          play, "_REQUEST_SECONDS", 0.05
      ):
        running = play.launch(options, out=io.StringIO())
        try:
          self.assertIn("viewer=spectator", running.play_url)
          self.assertEqual(len(set(running.bot_urls.values())), 2)
        finally:
          running.stop()


if __name__ == "__main__":
  absltest.main()
