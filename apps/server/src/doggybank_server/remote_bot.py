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


"""The remote bot: a seat played by a bot server, over HTTP.

For each move the server sends `POST {url}/move` with the seat, a seed and
the seat's private observation, and plays the action id the bot answers
with. `GET {url}/health` must answer 2xx before the seat plays.
REMOTE_BOTS.md documents the protocol, and `remote_bot_server` hosts any
Python strategy behind it.

The server posts only to loopback addresses unless it is started with
`--remote-bot-host` (`configure`), so a viewer who sets a seat's URL cannot
make it post a game's state to an arbitrary host.
"""

import dataclasses
import ipaddress
import json
import urllib.parse
from collections.abc import Mapping, Sequence

import pydantic
import pyspiel

from doggybank_server import (
    contract,
    controller_registry,
    controller_settings,
    information,
    move_budget,
    remote_bot_config,
    remote_bot_http,
)

NAME = "remote"

MOVE_PATH = "/move"
HEALTH_PATH = "/health"

CHECK_TIMEOUT_SECONDS = 10.0

_MARGIN_SECONDS = 0.5

RemoteBotRefusedError = remote_bot_http.RemoteBotRefusedError
RemoteBotUnreachableError = remote_bot_http.RemoteBotUnreachableError
RemoteBotReplyError = remote_bot_http.RemoteBotReplyError


class RemoteBotObservationError(RuntimeError):
    """The game cannot supply the observation a bot is sent."""


def observation(state: pyspiel.State, seat: int) -> contract.JsonValue:
    """Returns what `seat` may see at `state`, refusing a withheld one."""
    name = state.get_game().get_type().short_name
    try:
        observed = information.observation_struct(state, seat)
    except (pyspiel.SpielError, pydantic.ValidationError) as e:
        raise RemoteBotObservationError(
            f"{name} cannot provide an observation for seat {seat}."
        ) from e
    if observed is None:
        raise RemoteBotObservationError(
            f"{name}'s observation is withheld for seat {seat} at this position."
        )
    return observed


@dataclasses.dataclass
class _Configured:
    """Where remote bots may be, and their tokens (`configure`)."""

    hosts: frozenset[str] = frozenset()
    tokens: Mapping[str, str] = dataclasses.field(default_factory=dict)


_CONFIGURED = _Configured()


def configure(*, hosts: Sequence[str] = (), tokens: Mapping[str, str] | None = None) -> None:
    """Sets where remote bots may be, and the bearer tokens sent to them.

    Call it before serving.

    Args:
      hosts: Host names, beyond loopback, that a seat's URL may name; `*`
        admits any host.
      tokens: Bearer tokens by `host` or `host:port`. A request to a bot
        server at that host (and port, if given) carries
        `Authorization: Bearer <token>`; a request anywhere else carries none,
        so a seat pointed at another listener never receives it. A token is
        never part of a seat's settings, which every viewer sees.

    Raises:
      ValueError: If a host name is blank or `*` is given a token, or a token
        is blank.
    """
    for host in hosts:
        if not host.strip():
            raise ValueError("A remote bot host is blank.")
    scoped = {}
    for where, token in (tokens or {}).items():
        where = where.strip().lower()
        if not where or where == "*":
            raise ValueError(
                "A remote bot token is for one host (or host:port), not "
                f"{where or 'a blank one'!r}."
            )
        if not token.strip():
            raise ValueError(f"The remote bot token for {where} is blank.")
        scoped[where] = token
    _CONFIGURED.hosts = frozenset(host.strip().lower() for host in hosts)
    _CONFIGURED.tokens = scoped


def token_for(url: str) -> str | None:
    """Returns the token for the bot server at `url`, or None if it has none."""
    parts = urllib.parse.urlsplit(url)
    host = (parts.hostname or "").lower()
    port = parts.port or (443 if parts.scheme == "https" else 80)
    tokens = _CONFIGURED.tokens
    return tokens.get(f"{host}:{port}", tokens.get(host))


def allowed_hosts() -> frozenset[str]:
    """Returns the host names beyond loopback a seat's URL may name."""
    return _CONFIGURED.hosts


def is_loopback(host: str) -> bool:
    """Whether `host` names this machine: `localhost` or a loopback address."""
    if host == "localhost":
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


def url_refusal(url: str) -> str | None:
    """Returns why the server may not post to `url`, or None if it may."""
    try:
        parts = urllib.parse.urlsplit(url)
        host = (parts.hostname or "").lower()
        port = parts.port  # Raises on a port that is not a number.
    except ValueError:
        return f"The remote bot URL {controller_settings.shown(url)} is invalid."
    if parts.scheme not in ("http", "https") or not host:
        return (
            f"The remote bot URL {controller_settings.shown(url)} is not an "
            "http or https URL with a host."
        )
    if port == 0:
        return "The remote bot URL names port 0."
    if parts.query or parts.fragment or parts.username or parts.password:
        return (
            "The remote bot URL takes no query, fragment or credentials; give the "
            "bot server's base URL."
        )
    if is_loopback(host) or "*" in allowed_hosts() or host in allowed_hosts():
        return None
    return (
        "The server posts only to this machine and to the hosts it is started "
        f"with (--remote-bot-host), and {host} is not one."
    )


def config_refusal(game: pyspiel.Game, config: Mapping[str, contract.ParameterValue]) -> str | None:
    """Returns why a remote bot with `config` cannot play `game`, or None."""
    reason = url_refusal(str(config["url"]))
    if reason is not None:
        return reason
    try:
        observation(game.new_initial_state(), 0)
    except RemoteBotObservationError as e:
        return str(e)
    return None


class RemoteBot:
    """Plays a seat by asking a bot server for each move.

    Attributes:
      last_notice: The bot server's notice about its latest choice, or None.
      last_output: What the bot server said about its latest choice beyond the
        action (its policy, value and `decided_by`), or None.
    """

    def __init__(self, *, url: str, timeout_seconds: float, seed: int) -> None:
        self._url = url.rstrip("/")
        self._timeout_seconds = timeout_seconds
        self._seed = seed
        self.last_notice: str | None = None
        self.last_output: contract.BotOutput | None = None

    def send(self, path: str, body: bytes | None, timeout: float) -> tuple[int, contract.JsonValue]:
        """Sends a request to the bot server, with its configured token."""
        url = self._url + path
        return remote_bot_http.send(url, body, timeout, token_for(url))

    def check(self) -> None:
        """Checks the bot server's `/health` answers 2xx.

        Raises:
          RemoteBotUnreachableError: If it cannot be reached or answers otherwise.
          RemoteBotReplyError: If its body is not JSON.
        """
        status, _ = self.send(HEALTH_PATH, None, CHECK_TIMEOUT_SECONDS)
        if not 200 <= status < 300:
            raise RemoteBotUnreachableError(
                f"The bot server's {HEALTH_PATH} answered HTTP {status}."
            )

    def timeout(self) -> float:
        """How long to wait for a reply: within the move budget."""
        budget = move_budget.seconds()
        limit = budget - _MARGIN_SECONDS if budget > 2 * _MARGIN_SECONDS else (budget / 2)
        if self._timeout_seconds > 0:
            return min(self._timeout_seconds, limit)
        return limit

    def request(self, state: pyspiel.State, seat: int) -> bytes:
        """Returns the JSON body of the move request for `seat` at `state`."""
        return json.dumps(
            {
                "seat": seat,
                "seed": controller_registry.choice_seed(self._seed, state),
                "observation": observation(state, seat),
            }
        ).encode()

    def choose_action(self, state: pyspiel.State, seat: int) -> int:
        """Asks the bot server for `seat`'s action at `state`.

        Raises:
          RemoteBotRefusedError: If the bot server refuses.
          RemoteBotUnreachableError: If it cannot be reached, or does not answer
            within the timeout.
          RemoteBotReplyError: If its reply is malformed, or its action is not
            legal.
        """
        self.last_notice = None
        self.last_output = None
        status, reply = self.send(MOVE_PATH, self.request(state, seat), self.timeout())
        if status in remote_bot_http.REFUSAL_STATUSES:
            raise RemoteBotRefusedError(
                f"The bot server refused (HTTP {status}): {remote_bot_http.refusal_text(reply)}."
            )
        if not 200 <= status < 300:
            raise RemoteBotUnreachableError(f"The bot server answered HTTP {status}.")
        legal = state.legal_actions(seat)
        action, notice = remote_bot_http.parse_reply(reply, legal)
        output = remote_bot_http.parse_bot_output(
            reply, legal, lambda a: str(state.action_to_string(seat, a))
        )
        self.last_notice, self.last_output = notice, output
        return action


def build_bot(
    game: pyspiel.Game, config: Mapping[str, contract.ParameterValue], seed: int
) -> controller_registry.Controller:
    """Builds a remote bot, checking its bot server answers.

    Raises:
      controller_registry.UnavailableError: If the bot server is not ready.
    """
    del game
    url = str(config["url"])
    bot = RemoteBot(url=url, timeout_seconds=float(config["timeout_seconds"]), seed=seed)
    try:
        bot.check()
    except (RemoteBotUnreachableError, RemoteBotReplyError) as e:
        raise controller_registry.UnavailableError(
            f"The bot server at {url} is not ready: {e}"
        ) from e
    return bot


def kind() -> controller_registry.Kind:
    """Returns the remote bot as it is registered."""
    return controller_registry.Kind(
        "Remote bot",
        remote_bot_config.settings(),
        reads_full_state=False,
        build=build_bot,
        config_refusal=config_refusal,
    )
