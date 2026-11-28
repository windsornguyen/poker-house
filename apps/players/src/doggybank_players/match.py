"""Plays two strategies against each other through the site.

By default each deal is played twice with the seats swapped, so both
strategies hold both hands and the cards' luck cancels: each hand opens a room,
and both players leave it after, cashing out. With --room-hands, they instead
sit at one room and play hand after hand, their stacks carried over, until the
count is reached or one of them busts. One request is in flight at a time.

  DOGGYBANK_ACCOUNTS=accounts.json python -m doggybank_players.match \\
    --site https://doggybank.example --deals 150

`accounts.json` maps each strategy name to {"key": <API key>}.
"""

import argparse
import dataclasses
import json
import math
import os
import pathlib
import random
import statistics
from collections.abc import Sequence

from doggybank_players import client, strategies
from doggybank_server import contract, moves

BIG_BLIND = 2
STACK = 200


@dataclasses.dataclass(frozen=True)
class Seat:
    """A strategy and the account that plays it."""

    name: str
    strategy: strategies.Strategy
    player: client.Player


def table(seed: int | None) -> dict[str, contract.JsonValue]:
    """A heads-up table at 1/2 blinds with 200-chip stacks, its first hand dealt from `seed`."""
    human: dict[str, contract.JsonValue] = {"controller": "human", "config": {}, "autoplay": False}
    return {
        "game": "doggybank",
        "parameters": {
            "blinds": f"{BIG_BLIND // 2} {BIG_BLIND}",
            "stack_sizes": f"{STACK} {STACK}",
        },
        "chance_policy": "auto",
        "seed": seed,
        "seats": [human, human],
    }


def play_hand(host: Seat, guest: Seat, seed: int, log: pathlib.Path) -> list[float]:
    """Plays one hand at a room of its own, `host` at seat 0, and returns each seat's chips won."""
    created = host.player.create(table(seed))
    code = created.session.code
    guest.player.join(code)

    returns = play_out((host, guest), created.session.id, seed, log)
    host.player.leave(code)
    guest.player.leave(code)
    return returns


def play_room(tight: Seat, odds: Seat, hands: int, log: pathlib.Path) -> None:
    """Plays up to `hands` hands at one room, then both players leave it."""
    dealt = tight.player.create(table(None))
    code = dealt.session.code
    odds.player.join(code)

    for played in range(1, hands + 1):
        seats = (tight, odds) if dealt.viewer.seat == 0 else (odds, tight)
        play_out(seats, dealt.session.id, played, log)
        room = tight.player.room(code)
        print(f"hand {played}: stacks {list(room.stacks)}")
        if len(room.stacks) < len(seats) or played == hands:
            break
        dealt = tight.player.deal(code, dealt.session.id)

    # A player who busted has no seat left to leave.
    for seat in (tight, odds):
        if seat.player.room(code).stack is not None:
            seat.player.leave(code)


def play_out(seats: Sequence[Seat], hand: str, seed: int, log: pathlib.Path) -> list[float]:
    """Plays `hand` to its end with `seats` in seat order, and returns each seat's chips won."""
    while True:
        for index, actor in enumerate(seats):
            turn = actor.player.turn(hand, index)
            if turn.finished:
                returns = actor.player.frame(hand).returns
                assert returns is not None
                return list(returns)
            if turn.to_move:
                decision = strategies.decide(actor.strategy, turn)
                record(log, seed, actor.name, turn, decision)
                actor.player.move(hand, index, decision.move)
                break
        else:
            raise RuntimeError(f"Hand {hand} waits on no seat.")


def record(
    log: pathlib.Path,
    seed: int,
    name: str,
    turn: moves.Turn,
    decision: strategies.Decision,
) -> None:
    """Appends one decision to the log as a JSON line."""
    line = {
        "seed": seed,
        "seat": turn.seat,
        "strategy": name,
        "street": turn.street,
        "hole": list(turn.hole),
        "board": list(turn.board),
        "pot": turn.pot,
        "to_call": turn.to_call,
        "equity": round(decision.equity, 3),
        "action": decision.move.kind,
        "amount": decision.move.amount,
    }
    with log.open("a") as out:
        out.write(json.dumps(line) + "\n")


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    """Parses the command line."""
    parser = argparse.ArgumentParser(prog="python -m doggybank_players.match")
    parser.add_argument("--site", required=True)
    parser.add_argument("--deals", type=int, default=150)
    parser.add_argument("--log", type=pathlib.Path, default=pathlib.Path("match.jsonl"))
    parser.add_argument("--seed", type=int, default=0, help="Seeds the deals, so a run repeats.")
    parser.add_argument("--room-hands", type=int, help="Plays this many hands at one room instead.")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> None:
    """Plays the match and prints each strategy's big blinds per hand."""
    args = parse_args(argv)
    accounts = json.loads(pathlib.Path(os.environ["DOGGYBANK_ACCOUNTS"]).read_text())
    tight, odds = (
        Seat(name, strategies.STRATEGIES[name], client.Player(args.site, accounts[name]["key"]))
        for name in ("tight", "pot_odds")
    )
    if args.room_hands is not None:
        play_room(tight, odds, args.room_hands, args.log)
        return

    deals = random.Random(args.seed)
    per_deal: list[float] = []
    for deal in range(args.deals):
        seed = deals.randrange(2**31)
        first = play_hand(tight, odds, seed, args.log)
        second = play_hand(odds, tight, seed, args.log)

        tight_won = (first[0] + second[1]) / 2 / BIG_BLIND
        per_deal.append(tight_won)
        mean = statistics.fmean(per_deal)
        spread = statistics.stdev(per_deal) / math.sqrt(len(per_deal)) if len(per_deal) > 1 else 0.0
        running = f"{mean:+.2f} ± {spread:.2f} bb/hand"
        print(f"deal {deal + 1}: tight {tight_won:+.1f} bb, running {running}")

    mean = statistics.fmean(per_deal)
    spread = statistics.stdev(per_deal) / math.sqrt(len(per_deal))
    print(
        f"final over {len(per_deal)} deals: tight {mean:+.2f} ± {spread:.2f} bb/hand,"
        f" pot_odds {-mean:+.2f} ± {spread:.2f} bb/hand"
    )


if __name__ == "__main__":
    main()
