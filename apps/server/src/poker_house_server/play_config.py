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


"""Launcher settings, seat selection, and command-line parsing."""

import argparse
from collections.abc import Mapping, Sequence
import dataclasses
import sys
from typing import Any

import pyspiel

from poker_house_server import child_servers
from poker_house_server import loader
from poker_house_server import remote_bot_server
from poker_house_server import static

LaunchError = child_servers.LaunchError

# The variable the bot server's factory reads its checkpoint from, unless
# `--checkpoint-env` names another.
CHECKPOINT_ENV = remote_bot_server.CHECKPOINT_ENV
CHECKPOINT_ENVS = (CHECKPOINT_ENV,)
# Seconds; the GUI server's move budget, and so the most the bot seat waits
# for a move. A checkpoint named only in the seat (its Checkpoint field)
# may load and warm up at its first move, beyond the server default of 10 s.
BOT_MOVE_BUDGET_SECONDS = 60.0


@dataclasses.dataclass(frozen=True)
class SeatBot:
  """The bot a seat plays.

  Attributes:
    bot: The bot server's `--bot`: random, mcts or MODULE:FACTORY.
    checkpoint: The checkpoint the bot plays, or empty for none.
  """

  bot: str
  checkpoint: str = ""


@dataclasses.dataclass(frozen=True)
class Options:
  """What to launch.

  Attributes:
    game: The poker game name and parameters, such as `poker_house`.
    bot: The bot server's `--bot`: random, mcts or MODULE:FACTORY.
    checkpoint: The checkpoint the bot plays, or empty for none.
    checkpoint_envs: The environment variables the bot server is given the
      checkpoint in.
    bot_seat: One seat the bot plays, as `bot_seats=(bot_seat,)` does; kept
      for callers that seat one bot.
    bot_seats: The seats the bots play, every other seat human. Empty (the
      default, with no `bot_seat`) is every seat but the human seat.
    human_seat: The seat the printed address opens as; None (the default) is
      seat 0, or the first seat that is not a bot seat.
    spectate: Whether every seat plays a bot and the viewer is a spectator.
    seat_bots: The seats that play a bot or checkpoint other than `bot` and
      `checkpoint`, each a bot seat.
    server_per_seat: Whether every bot seat gets a bot server of its own,
      for a bot that keeps state between requests and cannot key it on the
      request's seat; otherwise the seats with the same bot and checkpoint
      share one.
    host: The address the GUI server listens on.
    port: The GUI server's port; 0 picks a free one.
    client_dir: The built browser client.
    move_budget_seconds: The GUI server's move budget.
    bot_start_seconds: How long the bot server may take to start (a bot that
      loads and warms up a checkpoint takes a while).
    gui_flags: Further flags for the GUI server.
    open_browser: Whether to open the address in a browser too.
    python: The Python interpreter both servers run on.
  """

  game: str
  bot: str
  checkpoint: str = ""
  checkpoint_envs: tuple[str, ...] = CHECKPOINT_ENVS
  bot_seat: int | None = None
  bot_seats: tuple[int, ...] = ()
  human_seat: int | None = None
  spectate: bool = False
  seat_bots: Mapping[int, SeatBot] = dataclasses.field(default_factory=dict)
  server_per_seat: bool = False
  host: str = "127.0.0.1"
  port: int = 8787
  client_dir: str = str(static.DEFAULT_ROOT)
  move_budget_seconds: float = BOT_MOVE_BUDGET_SECONDS
  bot_start_seconds: float = 900.0
  gui_flags: tuple[str, ...] = ()
  open_browser: bool = False
  python: str = sys.executable


def parse_game(text: str) -> tuple[str, dict[str, Any]]:
  """Returns the short name and parameters of the game string `text`.

  Raises:
    LaunchError: If `text` is not a game string of a registered game.
  """
  try:
    parameters = dict(pyspiel.game_parameters_from_string(text))
  except pyspiel.SpielError as e:
    raise LaunchError(f"--game {text!r} is not a game string: {e}") from e
  name = str(parameters.pop("name", ""))
  if name not in loader.registered_types():
    raise LaunchError(f"--game {text!r} names no registered game.")
  return name, parameters


@dataclasses.dataclass(frozen=True)
class Seating:
  """Who plays each seat.

  Attributes:
    bots: Every bot seat, in seat order, and the bot it plays.
    human: The human seat the address opens as, or None for a spectator.
    server_per_seat: Whether every bot seat has a bot server of its own,
      rather than one shared by the seats with the same bot.
  """

  bots: Mapping[int, SeatBot]
  human: int | None
  server_per_seat: bool = False

  def server_of(self, seat: int) -> tuple[int | None, SeatBot]:
    """Returns the key of the bot server the bot seat `seat` plays on.

    That is its bot, with the seat too when every seat has its own server.
    """
    return (seat if self.server_per_seat else None, self.bots[seat])

  def servers(self) -> list[tuple[int | None, SeatBot]]:
    """Returns the keys of the bot servers to start, in seat order."""
    return list(dict.fromkeys(self.server_of(seat) for seat in self.bots))


def seating(options: Options, num_players: int) -> Seating:
  """Returns who plays each seat of the game `options.game`.

  Raises:
    LaunchError: If a seat named is not a seat of the game, the human seat
      is a bot seat, or the seats disagree with the requested viewer mode.
  """
  name, _ = parse_game(options.game)
  human: int | None
  if options.spectate and options.human_seat is not None:
    raise LaunchError("--spectate cannot be combined with --human-seat.")
  named = list(options.bot_seats)
  if options.bot_seat is not None:
    named.append(options.bot_seat)
  checks = [("--bot-seat", seat) for seat in named]
  checks += [("--seat-bot", seat) for seat in options.seat_bots]
  if options.human_seat is not None:
    checks.append(("--human-seat", options.human_seat))
  for flag, seat in checks:
    if not 0 <= seat < num_players:
      raise LaunchError(
          f"{flag} {seat} is not a seat of {name}, which has {num_players}."
      )
  if named:
    seats = set(named)
  elif options.spectate:
    seats = set(range(num_players))
  else:
    human = 0 if options.human_seat is None else options.human_seat
    if options.human_seat is None and human in options.seat_bots:
      raise LaunchError(
          f"--seat-bot {human} is the human seat ({human}); pass "
          "--human-seat to sit at another."
      )
    seats = set(range(num_players)) - {human}
  seats |= set(options.seat_bots)
  if options.human_seat in seats:
    raise LaunchError(f"--human-seat {options.human_seat} is a bot seat.")
  humans = [seat for seat in range(num_players) if seat not in seats]
  if options.spectate and humans:
    raise LaunchError("--spectate requires a bot in every seat.")
  if not options.spectate and not humans:
    raise LaunchError(
        f"Every seat of {name} is a bot seat, so no one plays against the bots."
    )
  human = None
  if not options.spectate:
    human = humans[0] if options.human_seat is None else options.human_seat
  default = SeatBot(options.bot, options.checkpoint)
  return Seating(
      bots={
          seat: options.seat_bots.get(seat, default) for seat in sorted(seats)
      },
      human=human,
      server_per_seat=options.server_per_seat,
  )


def _seat_values(
    parser: argparse.ArgumentParser, flag: str, values: Sequence[str]
) -> dict[int, str]:
  """Returns `flag`'s SEAT=VALUE arguments as a map from seat to value.

  Exits through `parser.error` if one is not SEAT=VALUE with SEAT a number
  and VALUE not empty, or a seat is named twice.
  """
  result: dict[int, str] = {}
  for value in values:
    seat, _, text = value.partition("=")
    if not seat.strip().isdigit() or not text.strip():
      parser.error(f"{flag} {value!r} is not SEAT=VALUE.")
    if int(seat) in result:
      parser.error(f"{flag} names seat {int(seat)} twice.")
    result[int(seat)] = text.strip()
  return result


def parse_args(argv: Sequence[str] | None = None) -> Options:
  """Parses the command line; flags after `--` go to the GUI server."""
  argv = list(sys.argv[1:] if argv is None else argv)
  gui_flags: list[str] = []
  if "--" in argv:
    split = argv.index("--")
    argv, gui_flags = argv[:split], argv[split + 1 :]
  parser = argparse.ArgumentParser(
      prog="python -m poker_house_server.play",
      description=(
          "Play a game against a bot in one step: start a bot server and "
          "the GUI server, and open a session with a Remote bot seat. Flags "
          "after -- go to the GUI server."
      ),
  )
  parser.add_argument(
      "--game", default="poker_house", help="The poker game and parameters."
  )
  parser.add_argument(
      "--bot",
      required=True,
      help=(
          "The bot server's --bot: random, mcts, or MODULE:FACTORY, a "
          "function returning a bot (REMOTE_BOTS.md)."
      ),
  )
  parser.add_argument(
      "--checkpoint",
      default="",
      help=(
          "The checkpoint the bot plays, <location>@<step>: a directory, "
          "or any path or URL the bot reads (a cloud bucket, say); given to "
          "the bot server in its environment and set as the seat's "
          "checkpoint."
      ),
  )
  parser.add_argument(
      "--checkpoint-env",
      default=None,
      metavar="VAR",
      help=(
          "The one variable the bot reads its checkpoint from. Default: "
          f"set all of {', '.join(CHECKPOINT_ENVS)}."
      ),
  )
  parser.add_argument(
      "--bot-seat",
      type=int,
      action="append",
      default=None,
      metavar="SEAT",
      help=(
          "A seat the bot plays; repeat it for several, every other seat "
          "human. Default: every seat but --human-seat."
      ),
  )
  parser.add_argument(
      "--human-seat",
      type=int,
      default=None,
      metavar="SEAT",
      help=(
          "The seat you play, which the printed address opens as. Default: "
          "seat 0, or the first seat that is not a --bot-seat."
      ),
  )
  parser.add_argument(
      "--spectate",
      action="store_true",
      help="Watch bots play every seat, without taking a human seat.",
  )
  parser.add_argument(
      "--seat-bot",
      action="append",
      default=[],
      metavar="SEAT=BOT",
      help=(
          "A bot seat's own bot server --bot, instead of --bot, with no "
          "checkpoint unless --seat-checkpoint gives one; may be repeated."
      ),
  )
  parser.add_argument(
      "--seat-checkpoint",
      action="append",
      default=[],
      metavar="SEAT=CHECKPOINT",
      help=(
          "A bot seat's own checkpoint, instead of --checkpoint; may be "
          "repeated."
      ),
  )
  parser.add_argument("--host", default="127.0.0.1")
  parser.add_argument(
      "--port", type=int, default=8787, help="The GUI's port; 0 picks one."
  )
  parser.add_argument("--client-dir", default=str(static.DEFAULT_ROOT))
  parser.add_argument(
      "--move-budget-seconds",
      type=float,
      default=BOT_MOVE_BUDGET_SECONDS,
      help=(
          "How long the bot may take per move (its first move with a new "
          "checkpoint may load and warm it up). Default: %(default)g."
      ),
  )
  parser.add_argument(
      "--bot-start-seconds",
      type=float,
      default=900.0,
      help=(
          "How long the bot server may take to load its bot and listen. "
          "Default: %(default)g."
      ),
  )
  parser.add_argument(
      "--open",
      action="store_true",
      help="Open the address in a browser too.",
  )
  parser.add_argument(
      "--server-per-seat",
      action="store_true",
      help=(
          "Give every bot seat a bot server of its own, for a bot that keeps "
          "state between requests and cannot key it on the request's seat. "
          "Default: seats with the same bot and checkpoint share one."
      ),
  )
  args = parser.parse_args(argv)
  bots = _seat_values(parser, "--seat-bot", args.seat_bot)
  checkpoints = _seat_values(parser, "--seat-checkpoint", args.seat_checkpoint)
  seat_bots = {
      seat: SeatBot(
          bots.get(seat, args.bot),
          checkpoints.get(
              seat, "" if seat in bots else args.checkpoint.strip()
          ),
      )
      for seat in sorted(set(bots) | set(checkpoints))
  }
  options = Options(
      game=args.game,
      bot=args.bot,
      checkpoint=args.checkpoint.strip(),
      checkpoint_envs=(
          CHECKPOINT_ENVS
          if args.checkpoint_env is None
          else (args.checkpoint_env,)
      ),
      bot_seats=tuple(args.bot_seat or ()),
      human_seat=args.human_seat,
      spectate=args.spectate,
      seat_bots=seat_bots,
      server_per_seat=args.server_per_seat,
      host=args.host,
      port=args.port,
      client_dir=args.client_dir,
      move_budget_seconds=args.move_budget_seconds,
      bot_start_seconds=args.bot_start_seconds,
      gui_flags=tuple(gui_flags),
      open_browser=args.open,
  )
  return options
