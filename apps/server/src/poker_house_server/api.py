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


"""The JSON API: the contract's routes, independent of the HTTP transport.

`Api.handle` takes a request's method, target and body and returns the
response's status and JSON body. CONTRACT.md specifies every route and its
errors.
"""

import dataclasses
import hashlib
import hmac
import http
import re
import urllib.parse
from collections.abc import Callable
from typing import TYPE_CHECKING, TypeVar

import pydantic

if TYPE_CHECKING:
    from _typeshed import DataclassInstance

from poker_house_server import accounts, contract, controllers, errors, moves, request, store
from poker_house_server import catalogue as catalogue_lib
from poker_house_server import health as health_lib
from poker_house_server import ledger as ledger_lib
from poker_house_server import rooms as rooms_lib
from poker_house_server import session as session_lib

# The path prefix of every API route.
PREFIX = "/api/"

_T = TypeVar("_T")

# The header the Worker names the signed-in account in, signed with the player key.
PLAYER_HEADER = "X-Poker-Player"
ADMIN_KIND = "internal"
PLAYER_KEY_ENV = "POKER_HOUSE_PLAYER_KEY"


def signed_player(player: str, key: str) -> str:
    """Returns the player header naming `player`, signed with `key`."""
    digest = hmac.new(key.encode(), player.encode(), hashlib.sha256).hexdigest()
    return f"{player}.{digest}"


_NON_NEGATIVE_INTEGER = re.compile(r"0|[1-9][0-9]*")

_EVENTS = re.compile(PREFIX + r"sessions/(?P<id>[^/]+)/events")


@dataclasses.dataclass(frozen=True)
class Response:
    """An API response.

    Attributes:
      status: The HTTP status.
      body: A contract object in its wire form.
    """

    status: http.HTTPStatus
    body: contract.JsonValue


def ok(value: DataclassInstance) -> Response:
    """Answers with a contract object."""
    return Response(http.HTTPStatus.OK, contract.to_json(value))


def refusal(error: errors.Error) -> Response:
    """Answers with an error body and its status."""
    return Response(error.code.http_status, contract.to_json(error))


@dataclasses.dataclass(frozen=True)
class _Request:
    """A request, with the path parameters its route matched."""

    query: dict[str, list[str]]
    body: bytes
    path: dict[str, str]
    player: str | None

    @property
    def session_id(self) -> str:
        """The session the request concerns."""
        return self.path["id"]

    def room_code(self) -> str:
        """The room code the path names, as players type it in either case."""
        return self.path["code"].upper()

    def viewer(self) -> contract.Viewer:
        """Returns the viewer named by the `viewer` query parameter."""
        values = self.query.get("viewer", [])
        if len(values) != 1:
            raise errors.BadRequestError(
                "Name one viewer: viewer=oracle, viewer=spectator or viewer=<seat>."
            )
        value = values[0]
        if value == contract.ViewerKind.ORACLE:
            return contract.Viewer(contract.ViewerKind.ORACLE)
        if value == contract.ViewerKind.SPECTATOR:
            return contract.Viewer(contract.ViewerKind.SPECTATOR)
        if _NON_NEGATIVE_INTEGER.fullmatch(value):
            return contract.Viewer(contract.ViewerKind.SEAT, int(value))
        raise errors.BadRequestError(f"Viewer {value!r} is not oracle, spectator or a seat index.")

    def signed_in(self) -> str:
        """The account the Worker vouches for.

        Raises:
          UnauthorizedError: If the request names no signed-in player.
        """
        if not self.player:
            raise errors.UnauthorizedError("Sign in to play.")
        return self.player

    def index(self, name: str) -> int:
        """Returns the path parameter `name`, a non-negative integer."""
        value = self.path[name]
        if not _NON_NEGATIVE_INTEGER.fullmatch(value):
            raise errors.BadRequestError(f"The {name} {value!r} is not a non-negative integer.")
        return int(value)

    def decode(self, cls: type[_T]) -> _T:
        """Returns the body decoded as the request type `cls`."""
        try:
            return contract.adapter(cls).validate_json(self.body, strict=True)
        except pydantic.ValidationError as e:
            first = e.errors()[0]
            where = ".".join(str(part) for part in first["loc"]) or "body"
            raise errors.BadRequestError(f"{where}: {first['msg']}.") from e


def seat_view(seat: int | None) -> contract.Viewer:
    """The view of a player at `seat`, or the spectator's when they sit the hand out."""
    if seat is None:
        return contract.Viewer(contract.ViewerKind.SPECTATOR)
    return contract.Viewer(contract.ViewerKind.SEAT, seat)


def spec(seat: request.SeatConfig) -> controllers.Spec:
    """Returns the controller a seat asks for."""
    return controllers.Spec(seat.controller, seat.config)


_Handler = Callable[["Api", _Request], Response]
_Route = tuple[str, re.Pattern[str], _Handler]


def route(method: str, path: str, handler: _Handler) -> _Route:
    """Compiles a route under `PREFIX`; `{name}` matches one path segment."""
    pattern = re.sub(r"{(\w+)}", r"(?P<\1>[^/]+)", PREFIX + path)
    return method, re.compile(pattern), handler


class Api:
    """Answers the contract's routes.

    Safe to call from several threads. Each route makes one call on a session,
    and a session serializes its calls under its own lock, so calls that
    concern one session are serialized and calls that concern different
    sessions run concurrently.
    """

    def __init__(
        self,
        sessions: store.SessionStore,
        *,
        catalogue: Callable[[], catalogue_lib.Catalogue],
        health: Callable[[], health_lib.Health],
        player_key: str,
    ) -> None:
        """Initializes the API.

        Args:
          sessions: Holds the sessions the API creates and serves.
          catalogue: Returns the catalogue of every game.
          health: Returns the server's health report.
          player_key: The key the Worker signs the player header with.
        """
        self._sessions = sessions
        self._player_key = player_key
        self._catalogue_of = catalogue
        self._health_of = health

    def problem(self) -> str | None:
        """Returns why the API cannot serve sessions, or None when it can."""
        return self._sessions.problem()

    def identify(self, header: str | None) -> str | None:
        """Returns the account a signed player header names, or None for any other."""
        if header is None:
            return None

        player, _, _ = header.rpartition(".")
        if not player or not hmac.compare_digest(header, signed_player(player, self._player_key)):
            return None
        return player

    def handle(
        self, method: str, target: str, body: bytes = b"", player_header: str | None = None
    ) -> Response:
        """Answers one request.

        Args:
          method: The HTTP method.
          target: The request target: an API path and its query string.
          body: The request body.
          player_header: The Worker's signed player header, or None.

        Returns:
          The response. A request the contract refuses (an `errors.RequestError`)
          is answered with its error body. Any other exception is a fault, not a
          refusal, and propagates.
        """
        url = urllib.parse.urlsplit(target)
        query = urllib.parse.parse_qs(url.query, keep_blank_values=True)
        try:
            handler, path = self.match_route(method, url.path)
            return handler(self, _Request(query, body, path, self.identify(player_header)))
        except errors.RequestError as error:
            return refusal(error.to_error())

    def is_events(self, method: str, target: str) -> bool:
        """Whether the request subscribes to a session's events."""
        path = urllib.parse.urlsplit(target).path
        return method == "GET" and _EVENTS.fullmatch(path) is not None

    def subscribe(
        self, target: str, player_header: str | None
    ) -> tuple[session_lib.Session, contract.Viewer, str]:
        """Returns the session, viewer and player an events request subscribes.

        Raises:
          errors.RequestError: If the session or viewer does not exist.
        """
        url = urllib.parse.urlsplit(target)
        match = _EVENTS.fullmatch(url.path)
        assert match is not None
        req = _Request(
            urllib.parse.parse_qs(url.query, keep_blank_values=True),
            b"",
            match.groupdict(),
            self.identify(player_header),
        )
        session, viewer = self.seated(req)
        session.frame(viewer)
        return session, viewer, req.signed_in()

    def match_route(self, method: str, path: str) -> tuple[_Handler, dict[str, str]]:
        """Returns the handler for a request and its path parameters."""
        methods = []
        for route_method, pattern, handler in self._ROUTES:
            match = pattern.fullmatch(path)
            if match is None:
                continue
            if route_method == method:
                return handler, match.groupdict()
            methods.append(route_method)
        if methods:
            raise errors.MethodNotAllowedError(
                f"{path} accepts {' and '.join(methods)}, not {method}."
            )
        raise errors.NotFoundError(f"There is no route {path}.")

    def health(self, unused_request: _Request) -> Response:
        """Answers with the health report."""
        return ok(self._health_of())

    def catalogue(self, unused_request: _Request) -> Response:
        """Answers with the catalogue."""
        return ok(self._catalogue_of())

    def me(self, req: _Request) -> Response:
        """Answers with the signed-in player's balance and kind."""
        player = req.signed_in()
        chips = self._sessions.ledger()
        return ok(accounts.Me(balance=chips.balance(player), kind=chips.kind(player)))

    def admin(self, req: _Request) -> ledger_lib.Ledger:
        """The ledger, for a player whose listing is internal.

        Raises:
          errors.ForbiddenError: If the player's listing is not internal.
        """
        chips = self._sessions.ledger()
        if chips.kind(req.signed_in()) != ADMIN_KIND:
            raise errors.ForbiddenError("Only an internal account may manage chips.")
        return chips

    def list_accounts(self, req: _Request) -> Response:
        """Answers with every account, for an admin."""
        return ok(self.admin(req).holdings())

    def grant(self, req: _Request) -> Response:
        """Gives a player chips from the treasury, for an admin, and answers with every account."""
        chips = self.admin(req)
        body = req.decode(request.Grant)

        chips.grant(body.email, body.amount)
        return ok(chips.holdings())

    def seated(self, req: _Request) -> tuple[session_lib.Session, contract.Viewer]:
        """The session the request concerns, and the viewer its player may take there."""
        viewer, player = req.viewer(), req.signed_in()
        session = self._sessions.get(req.session_id)
        session.authorize(viewer, player)
        return session, viewer

    def create(self, req: _Request) -> Response:
        """Starts a session with its player seated, keeping it only if the viewer may see it."""
        viewer, player = req.viewer(), req.signed_in()
        body = req.decode(request.CreateSession)
        session = self._sessions.create(
            body.game,
            body.parameters,
            seed=body.seed,
            chance_policy=body.chance_policy,
            controllers=[spec(seat) for seat in body.seats],
            autoplay=[seat.autoplay for seat in body.seats],
            player=player,
            viewer=viewer,
        )
        return ok(session.frame(viewer))

    def join(self, req: _Request) -> Response:
        """Sits the player at a room by its code, and answers with their view of its hand."""
        session, seat = self._sessions.join(req.room_code(), req.signed_in())
        return ok(session.frame(seat_view(seat)))

    def room(self, req: _Request) -> Response:
        """Answers with the room as the player sees it."""
        player = req.signed_in()
        return ok(self.room_view(self._sessions.rooms().find(req.room_code()), player))

    def room_view(self, room: rooms_lib.Room, player: str) -> rooms_lib.RoomView:
        """`room` as `player` sees it."""
        holders = () if room.latest is None else self._sessions.get(room.latest).holders
        return rooms_lib.RoomView(
            code=room.code,
            buy_in=room.buy_in,
            session_id=room.latest,
            seat=holders.index(player) if player in holders else None,
            stack=room.stack(player),
            stacks=tuple(seat.stack for seat in room.seated),
        )

    def deal(self, req: _Request) -> Response:
        """Deals the room's next hand, and answers with the player's view of it."""
        body = req.decode(request.Deal)
        session, seat = self._sessions.deal(req.room_code(), body.after, req.signed_in())
        return ok(session.frame(seat_view(seat)))

    def leave(self, req: _Request) -> Response:
        """Gets the player up from the room's table, and answers with the room."""
        player = req.signed_in()
        return ok(self.room_view(self._sessions.leave(req.room_code(), player), player))

    def get_frame(self, req: _Request) -> Response:
        """Answers with the live position."""
        session, viewer = self.seated(req)
        return ok(session.frame(viewer))

    def replay(self, req: _Request) -> Response:
        """Answers with an earlier position."""
        session, viewer = self.seated(req)
        return ok(session.replay_frame(viewer, req.index("ply")))

    def action(self, req: _Request) -> Response:
        """Plays a seat's action."""
        session, viewer = self.seated(req)
        body = req.decode(request.ApplyAction)
        return ok(session.apply_action(viewer, body.action, ply=body.ply))

    def move(self, req: _Request) -> Response:
        """Plays a move named by its kind and amount, resolved to its action id."""
        session, viewer = self.seated(req)
        body = req.decode(request.PlayMove)

        action = moves.resolve(session.frame(viewer).observation_struct, body)
        return ok(session.apply_action(viewer, action))

    def turn(self, req: _Request) -> Response:
        """Answers with the seat's turn: its cards, the pot, the price and its legal moves."""
        session, viewer = self.seated(req)
        return ok(moves.turn_of(session.frame(viewer).observation_struct))

    def chance(self, req: _Request) -> Response:
        """Chooses a chance outcome."""
        session, viewer = self.seated(req)
        body = req.decode(request.ApplyChanceOutcome)
        return ok(session.apply_chance(viewer, body.outcome, ply=body.ply))

    def advance(self, req: _Request) -> Response:
        """Lets controllers play, at most `request.MAX_ADVANCE_PLIES` actions."""
        session, viewer = self.seated(req)
        body = req.decode(request.Advance)
        return ok(session.advance(viewer, max_plies=body.limit))

    def undo(self, req: _Request) -> Response:
        """Undoes the latest choice of a seat."""
        session, viewer = self.seated(req)
        return ok(session.undo(viewer))

    def reset(self, req: _Request) -> Response:
        """Restarts the game."""
        session, viewer = self.seated(req)
        body = req.decode(request.Reset)
        return ok(session.reset(viewer, history=body.history or ()))

    def close(self, req: _Request) -> Response:
        """Forgets a session; any viewer but a spectator closes it."""
        session, viewer = self.seated(req)
        session.check_closer(viewer)
        self._sessions.delete(req.session_id)
        return ok(contract.SessionClosed(id=req.session_id))

    def set_seat(self, req: _Request) -> Response:
        """Changes a seat's controller."""
        session, viewer = self.seated(req)
        seat, body = req.index("seat"), req.decode(request.SeatConfig)
        return ok(session.set_controller(viewer, seat, spec(body), autoplay=body.autoplay))

    _ROUTES: tuple[_Route, ...] = (
        route("GET", "health", health),
        route("GET", "games", catalogue),
        route("GET", "me", me),
        route("GET", "admin/accounts", list_accounts),
        route("POST", "admin/grants", grant),
        route("POST", "sessions", create),
        route("GET", "rooms/{code}", room),
        route("POST", "rooms/{code}/join", join),
        route("POST", "rooms/{code}/deal", deal),
        route("POST", "rooms/{code}/leave", leave),
        route("GET", "sessions/{id}", get_frame),
        route("DELETE", "sessions/{id}", close),
        route("GET", "sessions/{id}/plies/{ply}", replay),
        route("POST", "sessions/{id}/actions", action),
        route("GET", "sessions/{id}/turn", turn),
        route("POST", "sessions/{id}/moves", move),
        route("POST", "sessions/{id}/chance", chance),
        route("POST", "sessions/{id}/advance", advance),
        route("POST", "sessions/{id}/undo", undo),
        route("POST", "sessions/{id}/reset", reset),
        route("PUT", "sessions/{id}/seats/{seat}", set_seat),
    )
