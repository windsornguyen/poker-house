"""Moves named by what they do, resolved to the action ids the engine plays."""

from collections.abc import Mapping

from poker_house_server import contract, errors, request


def resolve(observation: contract.JsonValue, move: request.PlayMove) -> int:
    """Returns the id of the legal action `move` names in a seat's observation.

    Raises:
      IllegalActionError: If no legal action matches, with the legal moves.
    """
    legal = [entry for entry in actions(observation) if entry["kind"] == move.kind]
    if move.kind in ("bet", "raise") and move.amount is None:
        raise errors.IllegalActionError(f"Name the amount to {move.kind} to.")

    for entry in legal:
        action_id = entry["id"]
        if isinstance(action_id, int) and (move.amount is None or entry["amount"] == move.amount):
            return action_id

    raise errors.IllegalActionError(
        f"{move.kind} {move.amount or ''} is not legal here. Legal moves: {summary(observation)}."
    )


def actions(observation: contract.JsonValue) -> list[Mapping[str, contract.JsonValue]]:
    """The legal actions a seat's poker observation lists."""
    if not isinstance(observation, Mapping):
        raise errors.IllegalActionError("This view has no moves to choose from.")

    entries = observation.get("actions")
    if not isinstance(entries, list):
        raise errors.IllegalActionError("This view has no moves to choose from.")
    return [entry for entry in entries if isinstance(entry, Mapping)]


def summary(observation: contract.JsonValue) -> str:
    """The legal moves, each kind once, with the range of amounts it allows."""
    ranges: dict[str, list[float]] = {}
    for entry in actions(observation):
        amount = entry["amount"]
        if isinstance(amount, int | float):
            ranges.setdefault(str(entry["kind"]), []).append(float(amount))

    parts = []
    for kind, amounts in ranges.items():
        low, high = min(amounts), max(amounts)
        parts.append(
            kind
            if kind in ("fold", "check")
            else f"{kind} {low:g}"
            if low == high
            else f"{kind} {low:g} to {high:g}"
        )
    return ", ".join(parts)
