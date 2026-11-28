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

"""The launcher lets valid bot decisions finish within their move budgets."""

import io
import os
import re
import sys

from absl.testing import absltest

from doggybank_server import child_servers

_SLOW_BOT = """
import time
from doggybank_server.poker_bot import PokerBot

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


if __name__ == "__main__":
    absltest.main()
