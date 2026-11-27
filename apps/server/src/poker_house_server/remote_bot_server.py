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
"""Hosts a Python poker strategy behind the bot protocol (REMOTE_BOTS.md).

  python -m poker_house_server.remote_bot_server --port 9001 \
    --bot poker_house_server.poker_bot:make_call_bot

`--bot` is `MODULE:FACTORY`: a function that takes no arguments
and returns a bot. A bot has one method, `move(request)`, given the JSON body
of `POST /move` and returning an action id, or a dict with `action` and the
optional `notice`, `policy`, `value` and `decided_by`. A ValueError is
answered as a refusal (HTTP 422) with its message.

The server listens on 127.0.0.1 unless told otherwise. With `--token-env
VAR` it answers only requests carrying `Authorization: Bearer <token>`, the
token held in the environment variable VAR, and 401 to any other; it refuses
to listen beyond loopback without one.
"""

import argparse
import hmac
import http
import http.server
import importlib
import json
import os
from collections.abc import Sequence
from typing import Protocol

from absl import logging

from poker_house_server import contract, remote_bot

MAX_BODY_BYTES = 16 << 20


class Bot(Protocol):
    """What the server hosts."""

    def move(self, request: dict[str, contract.JsonValue]) -> int | dict[str, contract.JsonValue]:
        """Returns the action to play, or {"action", "notice", ...}."""


def load_bot(name: str) -> Bot:
    """Returns the bot `--bot` names: MODULE:FACTORY.

    Raises:
      ValueError: If `name` is neither, or the factory's bot has no `move`.
    """
    module_name, sep, factory_name = name.partition(":")
    if not sep or not module_name or not factory_name:
        raise ValueError(f"--bot {name!r} is not MODULE:FACTORY.")
    try:
        module = importlib.import_module(module_name)
    except ImportError as e:
        raise ValueError(f"The bot's module {module_name!r} cannot be imported: {e}") from e
    factory = getattr(module, factory_name)
    bot: Bot = factory()
    if not callable(getattr(bot, "move", None)):
        raise ValueError(f"{name}'s bot has no move(request).")
    return bot


def reply_of(
    result: int | dict[str, contract.JsonValue], notice: str | None
) -> dict[str, contract.JsonValue]:
    """Returns the reply body for a bot's result, adding `--notice` when it gives none.

    The game server checks the reply, so a malformed one fails the seat there.
    """
    reply: dict[str, contract.JsonValue] = (
        {"action": result} if isinstance(result, int) else dict(result)
    )
    if notice is not None and reply.get("notice") is None:
        reply["notice"] = notice
    return reply


class Server(http.server.ThreadingHTTPServer):
    """Serves one bot over the remote bot protocol."""

    daemon_threads = True

    def __init__(
        self,
        address: tuple[str, int],
        bot: Bot,
        *,
        name: str,
        notice: str | None = None,
        token: str | None = None,
    ) -> None:
        """Initializes the server.

        Args:
          address: The host and port to listen on.
          bot: The bot to serve.
          name: The bot's name, for /health.
          notice: A notice added to every move the bot gives none for.
          token: The bearer token every request must carry; None for none.

        Raises:
          ValueError: If `address` is beyond loopback and there is no token.
        """
        if token is None and not remote_bot.is_loopback(address[0].lower()):
            raise ValueError(
                f"The bot server would listen on {address[0]}, beyond this "
                "machine, with no token; give --token-env."
            )
        super().__init__(address, _Handler)
        self.bot = bot
        self.name = name
        self.notice = notice
        self.token = token

    @property
    def url(self) -> str:
        """The URL to give a Remote bot seat."""
        host, port = self.server_address[:2]
        return f"http://{host!s}:{port}"


class _Handler(http.server.BaseHTTPRequestHandler):
    """Answers the protocol's requests."""

    @property
    def app(self) -> Server:
        """The server this handler answers for."""
        assert isinstance(self.server, Server)
        return self.server

    protocol_version = "HTTP/1.1"

    def send(self, status: int, body: dict[str, contract.JsonValue]) -> None:
        """Sends a JSON reply."""
        data = json.dumps(body).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def authorized(self) -> bool:
        """Whether the request carries the server's token; answers 401 if not."""
        token = self.app.token
        if token is None:
            return True
        given = self.headers.get("Authorization", "")
        if hmac.compare_digest(given.encode(), f"Bearer {token}".encode()):
            return True
        self.send(
            http.HTTPStatus.UNAUTHORIZED,
            {"error": "a bearer token is required", "reason": "unauthorized"},
        )
        return False

    def do_GET(self) -> None:
        """Answers /health."""
        if not self.authorized():
            return
        if self.path == remote_bot.HEALTH_PATH:
            self.send(http.HTTPStatus.OK, {"ok": True, "name": self.app.name})
        else:
            self.send(http.HTTPStatus.NOT_FOUND, {"error": f"no {self.path}"})

    def do_POST(self) -> None:
        """Answers a move request."""
        if not self.authorized():
            return
        if self.path != remote_bot.MOVE_PATH:
            self.send(http.HTTPStatus.NOT_FOUND, {"error": f"no {self.path}"})
            return
        length = int(self.headers.get("Content-Length", "0"))
        if not 0 < length <= MAX_BODY_BYTES:
            self.send(
                http.HTTPStatus.BAD_REQUEST,
                {"error": "bad body length", "reason": "bad_request"},
            )
            return
        try:
            request = json.loads(self.rfile.read(length))
        except json.JSONDecodeError:
            self.send(
                http.HTTPStatus.BAD_REQUEST,
                {"error": "the body is not JSON", "reason": "bad_request"},
            )
            return
        try:
            result = self.app.bot.move(request)
        except ValueError as e:
            self.send(
                http.HTTPStatus.UNPROCESSABLE_ENTITY,
                {"error": str(e), "reason": "bot_refused"},
            )
            return
        except Exception:
            logging.exception("The bot failed on %s.", self.path)
            self.send(
                http.HTTPStatus.INTERNAL_SERVER_ERROR,
                {"error": "the bot failed; see the bot server's log"},
            )
            return
        self.send(http.HTTPStatus.OK, reply_of(result, self.app.notice))


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    """Parses the command line."""
    parser = argparse.ArgumentParser(
        prog="python -m poker_house_server.remote_bot_server",
        description="Host a poker strategy behind the bot protocol.",
    )
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=9001)
    parser.add_argument(
        "--bot",
        required=True,
        help="MODULE:FACTORY: a function returning a bot.",
    )
    parser.add_argument(
        "--token-env",
        metavar="VAR",
        help=(
            "Answer only requests carrying 'Authorization: Bearer <token>', the "
            "token in the environment variable VAR (the game server sends it "
            "with --remote-bot-token-env). Required to listen beyond loopback."
        ),
    )
    parser.add_argument(
        "--notice",
        default=None,
        help=(
            "A notice to send with every move, which the table shows to the "
            "seat's own viewer and to omniscient viewers; for trying it out."
        ),
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> None:
    """Serves until interrupted."""
    args = parse_args(argv)
    logging.set_verbosity(logging.INFO)
    token = None
    if args.token_env is not None:
        token = os.environ.get(args.token_env, "").strip()
        if not token:
            raise SystemExit(f"--token-env names {args.token_env}, which is unset.")
    try:
        bot = load_bot(args.bot)
        server = Server(
            (args.host, args.port),
            bot,
            name=args.bot,
            notice=args.notice,
            token=token,
        )
    except ValueError as e:
        # A mistake on the command line is one line, not a traceback.
        raise SystemExit(f"error: {e}") from e
    with server:
        print(f"Serving the {args.bot} bot at {server.url}", flush=True)
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            logging.info("Interrupted; shutting down.")


if __name__ == "__main__":
    main()
