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

"""The health body: what code the server runs and what it can do."""

import pydantic.dataclasses

from doggybank_server import contract


@pydantic.dataclasses.dataclass(frozen=True, config=contract.CONFIG)
class Capabilities:
    """What the server can do, independent of any one game.

    Attributes:
      controllers: Every registered controller, starting with the human one.
      chance_policies: The chance policies the server accepts.
    """

    controllers: tuple[contract.Controller, ...]
    chance_policies: tuple[contract.ChancePolicy, ...]

    def __post_init__(self) -> None:
        contract.require(
            bool(self.controllers) and self.controllers[0].name == contract.HUMAN,
            "The human controller is listed first.",
        )
        contract.require(bool(self.chance_policies), "The server accepts a chance policy.")


@pydantic.dataclasses.dataclass(frozen=True, config=contract.CONFIG)
class Health:
    """The server's identity and capabilities.

    Attributes:
      version: The installed Doggybank server package's version.
      revision: The source revision the server runs from, or null when unknown.
      capabilities: What the server can do.
    """

    version: str
    revision: str | None
    capabilities: Capabilities
