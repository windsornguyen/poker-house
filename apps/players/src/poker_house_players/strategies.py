"""Two ways to play heads-up hold'em, each from a seat's turn alone.

Both judge a hand by its equity against one random hand, which PokerKit
estimates by sampling the rest of the board. They differ in what they do with it.
"""

import dataclasses
import itertools
from collections.abc import Callable

from pokerkit import Card, Deck, StandardHighHand, calculate_equities

from poker_house_server import moves, request

SAMPLES = 400
PREFLOP_STREET = 0


@dataclasses.dataclass(frozen=True)
class Decision:
    """A move, with the equity that chose it."""

    move: request.PlayMove
    equity: float


Strategy = Callable[[moves.Turn, float], request.PlayMove]


def first(turn: moves.Turn, *kinds: request.MoveKind) -> request.PlayMove | None:
    """The earliest of `kinds` the turn allows, or None."""
    allowed = {move.kind for move in turn.moves}
    kind = next((kind for kind in kinds if kind in allowed), None)
    return None if kind is None else request.PlayMove(kind)


def sized(turn: moves.Turn, fraction: float) -> request.PlayMove | None:
    """A bet or raise to `fraction` of the pot on top of the call, within the legal range."""
    target = round(turn.to_call + fraction * (turn.pot + turn.to_call))
    for move in turn.moves:
        if move.kind in ("bet", "raise") and move.min is not None and move.max is not None:
            return request.PlayMove(move.kind, min(max(target, move.min), move.max))
    return None


def passive(turn: moves.Turn) -> request.PlayMove:
    """Check when free, else fold."""
    move = first(turn, "check", "fold")
    assert move is not None
    return move


def equity(turn: moves.Turn) -> float:
    """The hand's share of the pot against one random hand, by sampling."""
    hole = cards_of(turn.hole)
    board = cards_of(turn.board)
    known = set(hole) | set(board)
    rest = [card for card in Deck.STANDARD if card not in known]
    villain = [frozenset(pair) for pair in itertools.combinations(rest, 2)]
    shares = calculate_equities(
        ([frozenset(hole)], villain),
        board,
        2,
        5,
        Deck.STANDARD,
        (StandardHighHand,),
        sample_count=SAMPLES,
    )
    return shares[0]


def pot_odds(turn: moves.Turn) -> float:
    """The share of the final pot a call costs."""
    return turn.to_call / (turn.pot + turn.to_call) if turn.to_call else 0.0


def tight_aggressive(turn: moves.Turn, hand_equity: float) -> request.PlayMove:
    """Raises the best fifth of hands, defends the next quarter, folds the rest.

    After the flop it bets two thirds of the pot with a strong hand and calls
    only when its equity beats the price.
    """
    if turn.street == PREFLOP_STREET:
        if hand_equity >= 0.60:
            return sized(turn, 0.75) or first(turn, "call", "check") or passive(turn)
        if hand_equity >= 0.52 and turn.to_call <= 0.15 * turn.pot + 2:
            return first(turn, "call", "check") or passive(turn)
        return passive(turn)

    if hand_equity >= 0.65:
        return sized(turn, 0.66) or first(turn, "call", "check") or passive(turn)
    if hand_equity > pot_odds(turn):
        return first(turn, "check", "call") or passive(turn)
    return passive(turn)


def pot_odds_player(turn: moves.Turn, hand_equity: float) -> request.PlayMove:
    """Bets half the pot above 55% equity, otherwise calls whenever the price is right."""
    if hand_equity > 0.55:
        return sized(turn, 0.5) or first(turn, "call", "check") or passive(turn)
    if hand_equity >= pot_odds(turn):
        return first(turn, "check", "call") or passive(turn)
    return passive(turn)


STRATEGIES: dict[str, Strategy] = {
    "tight": tight_aggressive,
    "pot_odds": pot_odds_player,
}


def decide(strategy: Strategy, turn: moves.Turn) -> Decision:
    """Chooses a move for the seat whose turn it is."""
    hand_equity = equity(turn)
    return Decision(strategy(turn, hand_equity), hand_equity)


def cards_of(written: tuple[str, ...]) -> tuple[Card, ...]:
    """Parses cards written like `As`."""
    return tuple(card for text in written for card in Card.parse(text))
