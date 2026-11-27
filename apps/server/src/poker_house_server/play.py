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


"""Runs a poker session and independently hosted bots in one command.

  python -m poker_house_server.play --game poker_house --spectate \
    --bot poker_house_server.poker_bot:make_call_bot \
    --seat-bot 1=poker_house_server.poker_bot:make_raise_bot

The launcher starts each bot server and the game server, configures their
seats, and prints the session URL. Signals stop the processes it owns.
"""

import dataclasses
import http.client
import json
import os
import re
import signal
import sys
import threading
import types
import urllib.parse
import webbrowser
from collections.abc import Callable, Mapping, Sequence
from typing import Any, TextIO

import pyspiel

from poker_house_server import child_servers, cli, play_config, remote_bot
from poker_house_server import request as request_contract

Options = play_config.Options
SeatBot = play_config.SeatBot
Seating = play_config.Seating
parse_args = play_config.parse_args
parse_game = play_config.parse_game
seating = play_config.seating

# What each server prints once it listens; the first group is its URL.
_BOT_READY = re.compile(r"^Serving the .* bot at (http://\S+)")
_GUI_READY = re.compile(r"^Serving Poker House at (http://\S+)")

# Seconds. The GUI server registers every game first.
GUI_START_SECONDS = 120.0
# Seconds each HTTP request of the launcher may take.
_REQUEST_SECONDS = 30.0
# The signals that stop the launcher and both servers. SIGHUP is closing the
# terminal: the servers run in their own sessions, so it does not reach them.
STOP_SIGNALS = (signal.SIGINT, signal.SIGTERM, signal.SIGHUP)


LaunchError = child_servers.LaunchError


def _request(
    method: str,
    url: str,
    body: Mapping[str, Any] | None = None,
    *,
    timeout_seconds: float | None = None,
) -> object:
    """Sends a JSON request to a server on this machine; returns its JSON reply.

    Raises:
      LaunchError: If the server cannot be reached, or the reply is not 2xx
        JSON.
    """
    parts = urllib.parse.urlsplit(url)
    target = parts.path + (f"?{parts.query}" if parts.query else "")
    headers = {"Accept": "application/json"}
    data = None
    if body is not None:
        data = json.dumps(body).encode()
        headers["Content-Type"] = "application/json"
    connection = http.client.HTTPConnection(
        parts.hostname or "",
        parts.port,
        timeout=_REQUEST_SECONDS if timeout_seconds is None else timeout_seconds,
    )
    try:
        connection.request(method, target, body=data, headers=headers)
        response = connection.getresponse()
        status, raw = response.status, response.read()
    except (OSError, http.client.HTTPException) as e:
        raise LaunchError(f"{method} {url} failed: {e}") from e
    finally:
        connection.close()
    if not 200 <= status < 300:
        raise LaunchError(
            f"{method} {url} answered HTTP {status}: " + raw[:500].decode(errors="replace")
        )
    try:
        return json.loads(raw)
    except (json.JSONDecodeError, UnicodeDecodeError) as e:
        raise LaunchError(f"{method} {url} answered with no JSON.") from e


def bot_unready(bot_url: str) -> str | None:
    """Returns why the bot server at `bot_url` is not ready, or None if it is.

    Ready is its `/health` answering `{"ok": true}`, as the reference server
    does once its bot is loaded.
    """
    try:
        health = _request("GET", bot_url + remote_bot.HEALTH_PATH)
    except LaunchError as e:
        return str(e)
    if not isinstance(health, dict) or health.get("ok") is not True:
        return f"The bot server's /health answered {health!r}."
    return None


def seat_config(options: Options, bot_url: str) -> dict[str, Any]:
    """Returns the Remote bot seat's settings.

    The seat waits for each move as long as the move budget allows
    (`timeout_seconds` 0).
    """
    del options
    return {"url": bot_url, "timeout_seconds": 0.0}


def session_body(
    options: Options,
    bot_url: str | Mapping[int, str],
    num_players: int,
) -> dict[str, Any]:
    """Returns the body that opens the session, its bot seats Remote bots.

    Args:
      options: What is launched.
      bot_url: The bot server's URL, or each bot seat's.
      num_players: The game's number of seats.
    """
    name, parameters = parse_game(options.game)
    who = seating(options, num_players)
    seats = [{"controller": "human", "config": {}, "autoplay": False} for _ in range(num_players)]
    for seat in who.bots:
        url = bot_url if isinstance(bot_url, str) else bot_url[seat]
        seats[seat] = {
            "controller": remote_bot.NAME,
            "config": seat_config(options, url),
            "autoplay": True,
        }
    return {
        "game": name,
        "parameters": parameters,
        "seats": seats,
        "chance_policy": "auto",
        "seed": None,
    }


@dataclasses.dataclass
class Running:
    """Launched bot servers, a GUI server and a session.

    Attributes:
      bot_url: The first bot seat's bot server's URL.
      gui_url: The GUI server's URL, without a trailing slash.
      session: The session's id.
      play_url: The address to play the session at, as the human seat.
      bot_urls: Each bot seat's bot server's URL, in seat order.
    """

    bot_url: str
    gui_url: str
    session: str
    play_url: str
    _bots: tuple[child_servers.ChildServer, ...]
    _gui: child_servers.ChildServer | None
    bot_urls: Mapping[int, str] = dataclasses.field(default_factory=dict)

    def exited(self) -> str | None:
        """Returns the label of a server that has exited, or None."""
        for child in (*self._bots, self._gui):
            if child is not None and child.process.poll() is not None:
                return child.label
        return None

    def stop(self) -> None:
        """Stops the GUI server, then the bot servers."""
        child_servers.stop_all((self._gui, *self._bots))


def _start_bot(
    options: Options,
    bot: SeatBot,
    label: str,
    out: TextIO,
    started: list[child_servers.ChildServer],
) -> str:
    """Starts a bot server serving `bot`; returns its URL once it is healthy.

    The server is appended to `started` as soon as it runs, so the caller
    stops it whatever happens next.
    """
    env = dict(os.environ)
    child = child_servers.ChildServer(
        label,
        [
            options.python,
            "-m",
            "poker_house_server.remote_bot_server",
            "--host",
            "127.0.0.1",
            "--port",
            "0",
            "--bot",
            bot.bot,
        ],
        env,
        _BOT_READY,
        out,
    )
    started.append(child)
    url = child.wait_ready(options.bot_start_seconds)
    reason = bot_unready(url)
    if reason is not None:
        raise LaunchError(reason)
    return url


def _start_bots(
    options: Options,
    who: Seating,
    out: TextIO,
    started: list[child_servers.ChildServer],
) -> dict[int, str]:
    """Starts the bot servers `who` needs; returns each bot seat's URL.

    Each server is appended to `started` as soon as it runs.
    """
    urls: dict[tuple[int | None, SeatBot], str] = {}
    for i, served in enumerate(who.servers()):
        label = "bot" if i == 0 else f"bot {i + 1}"
        urls[served] = _start_bot(options, served[1], label, out, started)
    return {seat: urls[who.server_of(seat)] for seat in who.bots}


def launch(
    options: Options,
    out: TextIO = sys.stderr,
    started: Callable[[Running], object] | None = None,
) -> Running:
    """Starts the bot servers and the GUI server, and opens the session.

    Every bot seat's bot (`seating`) runs in a bot server; seats with the same
    bot share one. Every server started is stopped again if a
    later step fails or is interrupted.

    Args:
      options: What to launch.
      out: Where every server's output is copied.
      started: Called with the `Running` before it is returned. A caller that
        stops the servers on a signal hands its handler the `Running` here: if
        `started` raises, or a signal interrupts it, the servers are stopped,
        so no signal finds them running and in no one's hands.

    Raises:
      LaunchError: If the options are invalid, the GUI's port is taken (found
        before a bot server starts), a server does not start, or the
        session cannot be opened.
    """
    name, _ = parse_game(options.game)
    game = pyspiel.load_game(options.game)
    num_players = game.num_players()
    if num_players < 2:
        raise LaunchError(f"{name} has one seat, so no one plays against the bot.")
    who = seating(options, num_players)
    reason = child_servers.port_unavailable(options.host, options.port)
    if reason is not None:
        raise LaunchError(reason)
    bots: list[child_servers.ChildServer] = []
    gui: child_servers.ChildServer | None = None
    try:
        bot_urls = _start_bots(options, who, out, bots)
        gui_args = [
            "--host",
            options.host,
            "--port",
            str(options.port),
            "--client-dir",
            options.client_dir,
            "--move-budget-seconds",
            f"{options.move_budget_seconds:g}",
            *options.gui_flags,
        ]
        configured = cli.parse_args(gui_args)
        # Creation settles autoplay synchronously. Its request must cover every
        # permitted move and controller build, not just a health-check round trip.
        settlement_seconds = (
            request_contract.MAX_ADVANCE_PLIES * configured.move_budget_seconds
            + num_players * configured.build_budget_seconds
            + _REQUEST_SECONDS
        )
        gui = child_servers.ChildServer(
            "gui",
            [options.python, "-m", "poker_house_server", *gui_args],
            os.environ,
            _GUI_READY,
            out,
        )
        gui_url = gui.wait_ready(GUI_START_SECONDS)
        # The API is asked on loopback, which the GUI server always accepts.
        port = urllib.parse.urlsplit(gui_url).port
        local_api = f"http://127.0.0.1:{port}/api"
        frame = _request(
            "POST",
            f"{local_api}/sessions?viewer=oracle",
            session_body(options, bot_urls, num_players),
            timeout_seconds=settlement_seconds,
        )
        session = str(frame["session"]["id"])
        for seat_number in who.bots:
            seat = frame["seats"][seat_number]
            if seat.get("controller") != remote_bot.NAME:
                raise LaunchError(f"The bot seat {seat_number} is {seat!r}, not a Remote bot.")
            if seat.get("failure"):
                raise LaunchError(f"The bot seat {seat_number} failed: {seat['failure']}.")
        viewer = "spectator" if who.human is None else str(who.human)
        query = urllib.parse.urlencode({"session": session, "viewer": viewer})
        running = Running(
            bot_url=next(iter(bot_urls.values())),
            gui_url=gui_url,
            session=session,
            play_url=f"{gui_url}/game/{urllib.parse.quote(name)}?{query}",
            _bots=tuple(bots),
            _gui=gui,
            bot_urls=bot_urls,
        )
        if started is not None:
            started(running)
        return running
    except BaseException:
        child_servers.stop_all((gui, *bots))
        raise


def serve(
    running: Running,
    stopping: threading.Event,
    opener: Callable[[str], object] | None = None,
) -> int:
    """Prints the address, then waits for a stop or a server exiting.

    Both servers are stopped however it ends: a stop, a server exiting, or an
    error (printing to a closed stdout, say, or the opener failing).

    Returns:
      0 when stopped, 1 when a server exited by itself.
    """
    try:
        print(f"Play {running.play_url}", flush=True)
        if opener is not None:
            opener(running.play_url)
        while not stopping.wait(0.5):
            exited = running.exited()
            if exited is not None:
                print(f"The {exited} server exited; stopping.", file=sys.stderr)
                return 1
        return 0
    finally:
        running.stop()


class _Stopper:
    """The launcher's handler of `STOP_SIGNALS`, installed before the launch.

    The first signal sets `stopping`. Until the launch has handed over its
    `Running` (`started`), it also raises KeyboardInterrupt, which unwinds the
    launch, and `launch` stops what it started; after, `serve` sees `stopping`
    and stops both servers. The hand-over is one assignment, so every signal
    lands on one side of it. A later signal does nothing, so it cannot cut a
    stop short.
    """

    def __init__(self) -> None:
        self.stopping = threading.Event()
        self._serving = False

    def started(self, unused_running: Running) -> None:
        """Called by `launch` with the servers; from here a signal ends `serve`."""
        self._serving = True

    def __call__(self, signum: int, unused_frame: types.FrameType | None) -> None:
        if self.stopping.is_set():
            return
        self.stopping.set()
        name = signal.Signals(signum).name
        if not self._serving:
            raise KeyboardInterrupt(name)
        print(f"Received {name}; stopping.", file=sys.stderr, flush=True)


def main(argv: Sequence[str] | None = None) -> None:
    """Launches, serves until interrupted, then stops both servers."""
    options = parse_args(argv)
    opener = webbrowser.open if options.open_browser else None
    stopper = _Stopper()
    for signum in STOP_SIGNALS:
        signal.signal(signum, stopper)
    try:
        running = launch(options, started=stopper.started)
    except LaunchError as e:
        raise SystemExit(f"error: {e}") from e
    except KeyboardInterrupt:
        raise SystemExit("Interrupted; both servers stopped.") from None
    raise SystemExit(serve(running, stopper.stopping, opener))


if __name__ == "__main__":
    main()
