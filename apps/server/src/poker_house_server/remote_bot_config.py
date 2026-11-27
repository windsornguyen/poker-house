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


"""Remote bot seat settings and the `config` sent with every request.

It is the seat's `config` setting, a JSON object, with its `checkpoint`
setting, when not empty, as `config.checkpoint`: the checkpoint a bot that
plays one reads (REMOTE_BOTS.md).
"""

from collections.abc import Mapping
import json

from poker_house_server import contract
from poker_house_server import controller_settings

# The state setting distinguishes a seat's view from the full state.
SEAT_VIEW = "seat_view"
FULL_STATE = "full_state"
STATE_MODES = (SEAT_VIEW, FULL_STATE)

# The key of the bot's `config` that carries the seat's `checkpoint`
# setting.
CHECKPOINT_KEY = "checkpoint"


def parse(text: str) -> dict[str, contract.JsonValue]:
  """Parses the `config` setting: a JSON object.

  Raises:
    ValueError: If `text` is not a JSON object.
  """
  try:
    value = json.loads(text)
  except json.JSONDecodeError as e:
    raise ValueError(f"The remote bot's config is not JSON: {e.msg}.") from e
  if not isinstance(value, dict):
    raise ValueError("The remote bot's config is not a JSON object.")
  return value


def seat_bot_config(
    config: Mapping[str, contract.ParameterValue],
) -> dict[str, contract.JsonValue]:
  """Returns the `config` a seat's bot is sent: its `config` and `checkpoint`.

  Raises:
    ValueError: If `config` is not a JSON object, or gives a `checkpoint`
      other than the `checkpoint` setting.
  """
  value = parse(str(config["config"]))
  checkpoint = str(config.get("checkpoint", "")).strip()
  if checkpoint:
    given = value.get(CHECKPOINT_KEY)
    if given is not None and given != checkpoint:
      raise ValueError(
          "The remote bot's config gives a checkpoint other than its "
          "checkpoint setting; give it in one place."
      )
    value[CHECKPOINT_KEY] = checkpoint
  return value


def settings() -> tuple[controller_settings.Setting, ...]:
  """The remote bot's settings."""
  return (
      controller_settings.Setting(
          "url",
          str,
          controller_settings.REQUIRED,
          "The bot server's base URL, such as http://localhost:9001.",
          min_length=1,
          max_length=2000,
          pattern="^https?://",
      ),
      controller_settings.Setting(
          "state",
          str,
          SEAT_VIEW,
          "What the bot is sent: seat_view, what its seat may see; or "
          "full_state, the whole state, for a bot that needs it.",
          choices=STATE_MODES,
      ),
      controller_settings.Setting(
          "checkpoint",
          str,
          "",
          "The checkpoint the bot plays, such as /path/to/run@30000, sent "
          "with every request as `config.checkpoint`; empty, the bot server's "
          "own. Only a bot that reads `config.checkpoint` uses it.",
          max_length=2000,
      ),
      controller_settings.Setting(
          "config",
          str,
          "{}",
          "A JSON object passed to the bot with every request, as `config`.",
          max_length=4000,
      ),
      controller_settings.Setting(
          "extras",
          bool,
          False,
          "Whether a seat_view request also carries the seat's observation "
          "string, its legal actions' labels and the history as it sees it. "
          "Off, it carries only the information state string, the legal "
          "actions and a seed, which is all a strict seat-view bot accepts.",
      ),
      controller_settings.Setting(
          "tensors",
          bool,
          False,
          "Whether a seat_view request also carries the seat's observation "
          "and information state tensors, where the game provides them.",
      ),
      controller_settings.Setting(
          "structured",
          bool,
          False,
          "Whether a seat_view request carries the game's structured "
          "observation for that seat. Refused when unavailable or withheld.",
      ),
      controller_settings.Setting(
          "timeout_seconds",
          float,
          0.0,
          "How long to wait for each reply, capped by the move budget; 0 "
          "waits as long as the budget allows.",
          minimum=0.0,
      ),
  )
