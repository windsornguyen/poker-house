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

"""Refused requests: the error body, and the exceptions that carry it.

Every refusal raises a `RequestError`, one subclass per `ErrorCode`. Whatever
refuses a request (the session, the game loader, the controllers, the request
decoder) raises one of these or a subclass of one, so the server answers every
refusal the same way: `to_error()` gives the body, and its code the status.
"""

import enum
import http
from typing import ClassVar, Self

import pydantic.dataclasses

from poker_house_server import contract


class ErrorCode(enum.StrEnum):
    """Why a request was refused.

    Attributes:
      BAD_REQUEST: The request is malformed.
      NOT_FOUND: The session, game, seat or ply does not exist.
      METHOD_NOT_ALLOWED: The path exists but does not accept the method.
      GAME_UNAVAILABLE: The game cannot be served; its catalogue entry says why.
      VIEWER_UNAVAILABLE: The game cannot build a frame for the viewer.
      NOT_YOUR_TURN: The viewer may not choose the next action.
      ILLEGAL_ACTION: The action is not legal at the position.
      CONTROLLER_UNAVAILABLE: The controller cannot play the game, or its
        settings do not satisfy its `config_schema`.
      CONTROLLER_FAILED: A seat's controller failed and the session is paused.
      NOTHING_TO_UNDO: The live game has no action to undo.
      UNAUTHORIZED: The request names no signed-in player.
      ROOM_FULL: Every human seat of the room is taken.
      FORBIDDEN: The player may not make the request.
      INSUFFICIENT_CHIPS: The account holds fewer chips than the request moves.
      TABLE_NOT_READY: The room cannot deal its next hand yet.
      LEDGER_UNAVAILABLE: The server keeps no ledger, so it cannot stake chips.
    """

    http_status: http.HTTPStatus

    def __new__(cls, value: str, http_status: http.HTTPStatus) -> Self:
        """Makes a code whose responses carry `http_status`."""
        member = str.__new__(cls, value)
        member._value_ = value
        member.http_status = http_status
        return member

    BAD_REQUEST = "bad_request", http.HTTPStatus.BAD_REQUEST
    NOT_FOUND = "not_found", http.HTTPStatus.NOT_FOUND
    METHOD_NOT_ALLOWED = "method_not_allowed", http.HTTPStatus.METHOD_NOT_ALLOWED
    GAME_UNAVAILABLE = "game_unavailable", http.HTTPStatus.CONFLICT
    VIEWER_UNAVAILABLE = "viewer_unavailable", http.HTTPStatus.CONFLICT
    NOT_YOUR_TURN = "not_your_turn", http.HTTPStatus.CONFLICT
    ILLEGAL_ACTION = "illegal_action", http.HTTPStatus.CONFLICT
    CONTROLLER_UNAVAILABLE = "controller_unavailable", http.HTTPStatus.CONFLICT
    CONTROLLER_FAILED = "controller_failed", http.HTTPStatus.CONFLICT
    NOTHING_TO_UNDO = "nothing_to_undo", http.HTTPStatus.CONFLICT
    UNAUTHORIZED = "unauthorized", http.HTTPStatus.UNAUTHORIZED
    ROOM_FULL = "room_full", http.HTTPStatus.CONFLICT
    FORBIDDEN = "forbidden", http.HTTPStatus.FORBIDDEN
    INSUFFICIENT_CHIPS = "insufficient_chips", http.HTTPStatus.PAYMENT_REQUIRED
    TABLE_NOT_READY = "table_not_ready", http.HTTPStatus.CONFLICT
    LEDGER_UNAVAILABLE = "ledger_unavailable", http.HTTPStatus.SERVICE_UNAVAILABLE


@pydantic.dataclasses.dataclass(frozen=True, config=contract.CONFIG)
class Error:
    """A refused request.

    Attributes:
      code: Why the request was refused.
      message: A human-readable explanation, safe to show the requester: it
        never holds state the requester may not see.
      seat: The seat the refusal concerns, or null.
      ply: The index of the history entry the refusal concerns, or null.
    """

    code: ErrorCode
    message: str
    seat: int | None = None
    ply: int | None = None

    def __post_init__(self) -> None:
        contract.require(
            self.seat is None or self.seat >= 0,
            f"An error cannot concern seat {self.seat}.",
        )
        contract.require(
            self.ply is None or self.ply >= 0,
            f"An error cannot concern ply {self.ply}.",
        )


class RequestError(Exception):
    """A refused request; subclasses fix the contract's code.

    `RequestError` itself has no code and cannot be raised; every subclass
    declares one, which is checked when the subclass is defined.

    Attributes:
      code: Why the request was refused.
      seat: The seat the refusal concerns, or None.
      ply: The index of the history entry the refusal concerns, or None.
    """

    code: ClassVar[ErrorCode]

    def __init_subclass__(cls) -> None:
        super().__init_subclass__()
        if not isinstance(getattr(cls, "code", None), ErrorCode):
            raise TypeError(f"{cls.__name__} declares no ErrorCode `code`.")

    def __init__(self, message: str, *, seat: int | None = None, ply: int | None = None) -> None:
        if not isinstance(getattr(self, "code", None), ErrorCode):
            raise TypeError("Raise a subclass of RequestError, which has a code.")
        super().__init__(message)
        self.seat = seat
        self.ply = ply

    def to_error(self) -> Error:
        """Returns the refusal as the contract's error body."""
        return Error(code=self.code, message=str(self), seat=self.seat, ply=self.ply)


class BadRequestError(RequestError):
    """The request is malformed."""

    code = ErrorCode.BAD_REQUEST


class NotFoundError(RequestError):
    """The session, game, seat or ply does not exist."""

    code = ErrorCode.NOT_FOUND


class MethodNotAllowedError(RequestError):
    """The path exists but does not accept the method."""

    code = ErrorCode.METHOD_NOT_ALLOWED


class GameUnavailableError(RequestError):
    """The game cannot be served."""

    code = ErrorCode.GAME_UNAVAILABLE


class ViewerUnavailableError(RequestError):
    """The game cannot build a frame for the viewer."""

    code = ErrorCode.VIEWER_UNAVAILABLE


class NotYourTurnError(RequestError):
    """The viewer may not choose the next action."""

    code = ErrorCode.NOT_YOUR_TURN


class IllegalActionError(RequestError):
    """The action is not legal at the position."""

    code = ErrorCode.ILLEGAL_ACTION


class ControllerUnavailableError(RequestError):
    """The controller cannot play the game with the given settings."""

    code = ErrorCode.CONTROLLER_UNAVAILABLE


class ControllerFailedError(RequestError):
    """A seat's controller failed, so the session is paused.

    The message names only the seat: what the controller raised may describe
    private state, so it reaches only an omniscient viewer, as the seat's
    `failure.message` in a frame.
    """

    code = ErrorCode.CONTROLLER_FAILED

    def __init__(self, *, seat: int) -> None:
        super().__init__(
            f"Seat {seat}'s controller failed; undo, reset or change it.",
            seat=seat,
        )


class NothingToUndoError(RequestError):
    """The live game has no action to undo."""

    code = ErrorCode.NOTHING_TO_UNDO


class UnauthorizedError(RequestError):
    """The request names no signed-in player."""

    code = ErrorCode.UNAUTHORIZED


class RoomFullError(RequestError):
    """Every human seat of the room is taken."""

    code = ErrorCode.ROOM_FULL


class ForbiddenError(RequestError):
    """The player may not make the request."""

    code = ErrorCode.FORBIDDEN


class InsufficientChipsError(RequestError):
    """The account holds fewer chips than the request moves."""

    code = ErrorCode.INSUFFICIENT_CHIPS


class TableNotReadyError(RequestError):
    """The room cannot deal its next hand yet."""

    code = ErrorCode.TABLE_NOT_READY


class LedgerUnavailableError(RequestError):
    """The server keeps no ledger, so it cannot stake chips."""

    code = ErrorCode.LEDGER_UNAVAILABLE
