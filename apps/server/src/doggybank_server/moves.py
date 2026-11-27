"""A poker seat's turn and moves, named by what they do, for people and LLMs.

The engine plays numbered actions from a seat's observation. Here the
observation is read once into typed fields, its legal actions are grouped into
moves (a kind and the amounts it allows), and a move named by kind and amount
resolves back to the action id the engine plays.
"""

import pydantic
import pydantic.dataclasses

from doggybank_server import contract, errors, request

FREE_KINDS = ("fold", "check")


@pydantic.dataclasses.dataclass(frozen=True)
class Action:
    """One legal action as the observation lists it."""

    id: int
    kind: request.MoveKind
    amount: int


@pydantic.dataclasses.dataclass(frozen=True)
class Observation:
    """The fields of a poker seat's observation that a turn is read from."""

    observing_player: int
    current_player: int
    is_terminal: bool
    street_index: int | None
    hole_cards: list[list[str | None]]
    board_cards: list[str]
    total_pot: int
    stacks: list[int]
    bets: list[int]
    actions: list[Action]


OBSERVATION = pydantic.TypeAdapter(Observation)


@pydantic.dataclasses.dataclass(frozen=True, config=contract.CONFIG)
class Move:
    """A kind of legal move.

    Attributes:
      kind: fold, check, call, bet or raise.
      min: For a call, bet or raise, the least amount it allows; null for a
        fold or a check. A bet or raise amount is the total the seat's bet
        rises to, and a call's is the chips it adds.
      max: The most it allows, as `min`.
    """

    kind: request.MoveKind
    min: int | None
    max: int | None


@pydantic.dataclasses.dataclass(frozen=True, config=contract.CONFIG)
class Turn:
    """A seat's turn, in the few fields a decision is made from.

    Attributes:
      seat: The seat whose turn it is to read.
      to_move: Whether the seat is to act now.
      finished: Whether the hand is over.
      street: 0 preflop, then 1 to 3 for the flop, turn and river; null once over.
      hole: The seat's two cards, written like `As`.
      board: The cards on the board.
      pot: Every chip bet this hand, the current bets included.
      to_call: The chips the seat adds to call.
      stacks: Each seat's chips behind, not yet bet.
      bets: Each seat's bet on this street.
      moves: The seat's legal moves; empty unless it is to act.
    """

    seat: int
    to_move: bool
    finished: bool
    street: int | None
    hole: tuple[str, ...]
    board: tuple[str, ...]
    pot: int
    to_call: int
    stacks: tuple[int, ...]
    bets: tuple[int, ...]
    moves: tuple[Move, ...]


def observe(observation: contract.JsonValue) -> Observation:
    """Reads a seat's poker observation.

    Raises:
      ViewerUnavailableError: If the view is not a poker seat's.
    """
    try:
        return OBSERVATION.validate_python(observation)
    except pydantic.ValidationError as error:
        raise errors.ViewerUnavailableError("Only a poker seat's view has a turn.") from error


def turn_of(observation: contract.JsonValue) -> Turn:
    """The turn a seat's poker observation shows."""
    seen = observe(observation)
    seat = seen.observing_player
    to_move = seen.current_player == seat and not seen.is_terminal
    return Turn(
        seat=seat,
        to_move=to_move,
        finished=seen.is_terminal,
        street=seen.street_index,
        hole=tuple(card for card in seen.hole_cards[seat] if card is not None),
        board=tuple(seen.board_cards),
        pot=seen.total_pot,
        to_call=max(seen.bets) - seen.bets[seat],
        stacks=tuple(seen.stacks),
        bets=tuple(seen.bets),
        moves=legal(seen) if to_move else (),
    )


def legal(seen: Observation) -> tuple[Move, ...]:
    """The legal actions grouped into moves, each kind once with its range of amounts."""
    amounts: dict[request.MoveKind, list[int]] = {}
    for action in seen.actions:
        amounts.setdefault(action.kind, []).append(action.amount)

    return tuple(
        Move(kind, None, None) if kind in FREE_KINDS else Move(kind, min(values), max(values))
        for kind, values in amounts.items()
    )


def resolve(observation: contract.JsonValue, move: request.PlayMove) -> int:
    """Returns the id of the legal action `move` names in a seat's observation.

    Raises:
      IllegalActionError: If no legal action matches, with the legal moves.
    """
    seen = observe(observation)
    if move.kind in ("bet", "raise") and move.amount is None:
        raise errors.IllegalActionError(f"Name the amount to {move.kind} to.")

    for action in seen.actions:
        if action.kind == move.kind and move.amount in (None, action.amount):
            return action.id

    raise errors.IllegalActionError(
        f"{move.kind} {move.amount or ''} is not legal here. Legal moves: {summary(seen)}."
    )


def summary(seen: Observation) -> str:
    """The legal moves in words, such as `fold, call 1, raise 4 to 40`."""
    parts = []
    for move in legal(seen):
        if move.min is None:
            parts.append(move.kind)
        elif move.min == move.max:
            parts.append(f"{move.kind} {move.min}")
        else:
            parts.append(f"{move.kind} {move.min} to {move.max}")
    return ", ".join(parts)
