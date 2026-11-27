"""Plays two strategies against each other through the site, duplicate style.

Each deal is played twice with the seats swapped, so both strategies hold both
hands and the cards' luck cancels. One request is in flight at a time.

  POKER_HOUSE_ACCOUNTS=accounts.json python -m poker_house_players.match \\
    --site https://poker-house.example --deals 150

`accounts.json` maps each strategy name to {"email", "password"}.
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

from poker_house_players import client, strategies
from poker_house_server import contract

BIG_BLIND = 2
STACK = 200


@dataclasses.dataclass(frozen=True)
class Seat:
    """A strategy and the account that plays it."""

    name: str
    strategy: strategies.Strategy
    player: client.Player


def table(seed: int) -> dict[str, contract.JsonValue]:
    """A heads-up hand at 1/2 blinds with 200-chip stacks, dealt from `seed`."""
    human: dict[str, contract.JsonValue] = {"controller": "human", "config": {}, "autoplay": False}
    return {
        "game": "poker_house",
        "parameters": {
            "blinds": f"{BIG_BLIND // 2} {BIG_BLIND}",
            "stack_sizes": f"{STACK} {STACK}",
        },
        "chance_policy": "auto",
        "seed": seed,
        "seats": [human, human],
    }


def play_hand(host: Seat, guest: Seat, seed: int, log: pathlib.Path) -> list[float]:
    """Plays one hand, `host` at seat 0, and returns each seat's chips won."""
    created = host.player.create(table(seed))
    session_id = created.session.id
    guest.player.join(created.session.code)
    seats = (host, guest)

    frame = host.player.frame(session_id, 0)
    while frame.returns is None:
        seat = frame.to_move.seat
        if seat is None:
            raise RuntimeError(f"Hand {session_id} waits on no seat.")

        actor = seats[seat]
        view = actor.player.frame(session_id, seat)
        observation = view.observation_struct
        if not isinstance(observation, dict):
            raise RuntimeError(f"Seat {seat} has no observation.")
        decision = strategies.decide(actor.strategy, observation)
        record(log, seed, seat, actor.name, observation, decision)
        frame = actor.player.act(session_id, seat, decision.choice.id)

    return list(frame.returns)


def record(
    log: pathlib.Path,
    seed: int,
    seat: int,
    name: str,
    observation: dict[str, contract.JsonValue],
    decision: strategies.Decision,
) -> None:
    """Appends one decision to the log as a JSON line."""
    spot = strategies.spot_of(observation)
    line = {
        "seed": seed,
        "seat": seat,
        "strategy": name,
        "street": spot.street,
        "hole": [repr(card) for card in spot.hole],
        "board": [repr(card) for card in spot.board],
        "pot": spot.pot,
        "to_call": spot.to_call,
        "equity": round(decision.equity, 3),
        "action": decision.choice.kind,
        "amount": decision.choice.amount,
    }
    with log.open("a") as out:
        out.write(json.dumps(line) + "\n")


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    """Parses the command line."""
    parser = argparse.ArgumentParser(prog="python -m poker_house_players.match")
    parser.add_argument("--site", required=True)
    parser.add_argument("--deals", type=int, default=150)
    parser.add_argument("--log", type=pathlib.Path, default=pathlib.Path("match.jsonl"))
    parser.add_argument("--seed", type=int, default=0, help="Seeds the deals, so a run repeats.")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> None:
    """Plays the match and prints each strategy's big blinds per hand."""
    args = parse_args(argv)
    accounts = json.loads(pathlib.Path(os.environ["POKER_HOUSE_ACCOUNTS"]).read_text())
    tight, odds = (
        Seat(name, strategies.STRATEGIES[name], client.Player(args.site, **accounts[name]))
        for name in ("tight", "pot_odds")
    )

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
