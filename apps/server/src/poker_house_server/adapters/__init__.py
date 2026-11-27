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


"""Game adapters: one module per game, each named `<game>_adapter.py`.

Each module defines `GAME`, the game's short name, and `ADAPTER`, an
`adapter.Adapter`, and is listed once below; `presenters` registers every
adapter listed. An adapter stands alone, so a game can replace its adapter
without touching another.
"""

from collections.abc import Mapping
import types

from poker_house_server import adapter
from poker_house_server.adapters import pokerkit_adapter

ADAPTERS: Mapping[str, adapter.Adapter] = types.MappingProxyType({
    pokerkit_adapter.GAME: pokerkit_adapter.ADAPTER,
    pokerkit_adapter.ACPC_GAME: pokerkit_adapter.ADAPTER,
})
