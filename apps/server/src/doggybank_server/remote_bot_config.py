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


"""A remote bot seat's settings: its bot server, and how long to wait."""

from doggybank_server import controller_settings


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
            "timeout_seconds",
            float,
            0.0,
            "How long to wait for each reply, capped by the move budget; 0 "
            "waits as long as the budget allows.",
            minimum=0.0,
        ),
    )
