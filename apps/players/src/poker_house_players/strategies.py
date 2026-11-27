"""Two ways to play heads-up hold'em, each from a seat's observation alone.

Both judge a hand by its equity against one random hand, which PokerKit
estimates by sampling the rest of the board. They differ in what they do with it.
"""

import dataclasses
import itertools
from collections.abc import Callable, Mapping, Sequence

from pokerkit import Card, Deck, StandardHighHand, calculate_equities

from poker_house_server import contract

SAMPLES = 400
PREFLOP_STREET = 0


@dataclasses.dataclass(frozen=True)
class Choice:
    """One legal action from the observation."""

    id: int
    kind: str
    amount: float


@dataclasses.dataclass(frozen=True)
class Spot:
    """What a strategy reads from a seat's observation."""

    hole: tuple[Card, ...]
    board: tuple[Card, ...]
    street: int
    pot: float
    to_call: float
    choices: tuple[Choice, ...]

    def first(self, *kinds: str) -> Choice | None:
        """The first legal action of the earliest kind in `kinds`, or None."""
        for kind in kinds:
            for choice in self.choices:
                if choice.kind == kind:
                    return choice
        return None

    def sized(self, fraction: float) -> Choice | None:
        """The legal bet or raise nearest `fraction` of the pot on top of the call."""
        target = self.to_call + fraction * (self.pot + self.to_call)
        aggressive = [c for c in self.choices if c.kind in ("bet", "raise")]
        if not aggressive:
            return None
        return min(aggressive, key=lambda choice: abs(choice.amount - target))

    def passive(self) -> Choice:
        """Check when free, else fold."""
        choice = self.first("check", "fold")
        assert choice is not None
        return choice


@dataclasses.dataclass(frozen=True)
class Decision:
    """An action, with the equity that chose it."""

    choice: Choice
    equity: float


Strategy = Callable[[Spot, float], Choice]


def spot_of(observation: Mapping[str, contract.JsonValue]) -> Spot:
    """Reads the fields the strategies use from a seat's poker observation."""
    seat = int(number(observation["observing_player"]))
    holes = json_list(observation["hole_cards"])
    bets = [number(bet) for bet in json_list(observation["bets"])]
    choices = tuple(
        Choice(int(number(entry["id"])), str(entry["kind"]), number(entry["amount"]))
        for entry in map(json_object, json_list(observation["actions"]))
    )
    street = observation["street_index"]
    return Spot(
        hole=cards_of(json_list(holes[seat])),
        board=cards_of(json_list(observation["board_cards"])),
        street=PREFLOP_STREET if street is None else int(number(street)),
        pot=number(observation["total_pot"]),
        to_call=max(bets) - bets[seat],
        choices=choices,
    )


def equity(spot: Spot) -> float:
    """The hand's share of the pot against one random hand, by sampling."""
    known = set(spot.hole) | set(spot.board)
    rest = [card for card in Deck.STANDARD if card not in known]
    villain = [frozenset(pair) for pair in itertools.combinations(rest, 2)]
    shares = calculate_equities(
        ([frozenset(spot.hole)], villain),
        spot.board,
        2,
        5,
        Deck.STANDARD,
        (StandardHighHand,),
        sample_count=SAMPLES,
    )
    return shares[0]


def pot_odds(spot: Spot) -> float:
    """The share of the final pot a call costs."""
    return spot.to_call / (spot.pot + spot.to_call) if spot.to_call else 0.0


def tight_aggressive(spot: Spot, hand_equity: float) -> Choice:
    """Raises the best fifth of hands, defends the next quarter, folds the rest.

    After the flop it bets two thirds of the pot with a strong hand and calls
    only when its equity beats the price.
    """
    if spot.street == PREFLOP_STREET:
        if hand_equity >= 0.60:
            return spot.sized(0.75) or spot.first("call", "check") or spot.passive()
        if hand_equity >= 0.52 and spot.to_call <= 0.15 * spot.pot + 2:
            return spot.first("call", "check") or spot.passive()
        return spot.passive()

    if hand_equity >= 0.65:
        return spot.sized(0.66) or spot.first("call", "check") or spot.passive()
    if hand_equity > pot_odds(spot):
        return spot.first("check", "call") or spot.passive()
    return spot.passive()


def pot_odds_player(spot: Spot, hand_equity: float) -> Choice:
    """Bets half the pot above 55% equity, otherwise calls whenever the price is right."""
    if hand_equity > 0.55:
        return spot.sized(0.5) or spot.first("call", "check") or spot.passive()
    if hand_equity >= pot_odds(spot):
        return spot.first("check", "call") or spot.passive()
    return spot.passive()


STRATEGIES: dict[str, Strategy] = {
    "tight": tight_aggressive,
    "pot_odds": pot_odds_player,
}


def decide(strategy: Strategy, observation: Mapping[str, contract.JsonValue]) -> Decision:
    """Chooses an action for the seat that observes `observation`."""
    spot = spot_of(observation)
    hand_equity = equity(spot)
    return Decision(strategy(spot, hand_equity), hand_equity)


def cards_of(values: Sequence[contract.JsonValue]) -> tuple[Card, ...]:
    """Parses cards written like `As`."""
    return tuple(card for value in values for card in Card.parse(str(value)))


def number(value: contract.JsonValue) -> float:
    """The JSON number `value`."""
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise ValueError(f"Expected a number, got {value!r}.")
    return float(value)


def json_list(value: contract.JsonValue) -> list[contract.JsonValue]:
    if not isinstance(value, list):
        raise ValueError(f"Expected a list, got {value!r}.")
    return value


def json_object(value: contract.JsonValue) -> dict[str, contract.JsonValue]:
    """The JSON object `value`."""
    if not isinstance(value, dict):
        raise ValueError(f"Expected an object, got {value!r}.")
    return value
