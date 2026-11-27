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
import http
import re
import urllib.parse
from collections.abc import Callable
from typing import TYPE_CHECKING, TypeVar

import pydantic

if TYPE_CHECKING:
    from _typeshed import DataclassInstance

from poker_house_server import catalogue as catalogue_lib
from poker_house_server import contract, controllers, errors, request, store
from poker_house_server import health as health_lib
from poker_house_server import session as session_lib

# The path prefix of every API route.
PREFIX = "/api/"

_T = TypeVar("_T")

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

    @property
    def session_id(self) -> str:
        """The session the request concerns."""
        return self.path["id"]

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
    and a session serialises its calls under its own lock, so calls that
    concern one session are serialised and calls that concern different
    sessions run concurrently.
    """

    def __init__(
        self,
        sessions: store.SessionStore,
        *,
        catalogue: Callable[[], catalogue_lib.Catalogue],
        health: Callable[[], health_lib.Health],
    ) -> None:
        """Initializes the API.

        Args:
          sessions: Holds the sessions the API creates and serves.
          catalogue: Returns the catalogue of every game.
          health: Returns the server's health report.
        """
        self._sessions = sessions
        self._catalogue_of = catalogue
        self._health_of = health

    def handle(self, method: str, target: str, body: bytes = b"") -> Response:
        """Answers one request.

        Args:
          method: The HTTP method.
          target: The request target: an API path and its query string.
          body: The request body.

        Returns:
          The response. A request the contract refuses (an `errors.RequestError`)
          is answered with its error body. Any other exception is a fault, not a
          refusal, and propagates.
        """
        url = urllib.parse.urlsplit(target)
        query = urllib.parse.parse_qs(url.query, keep_blank_values=True)
        try:
            handler, path = self.match_route(method, url.path)
            return handler(self, _Request(query, body, path))
        except errors.RequestError as error:
            return refusal(error.to_error())

    def is_events(self, method: str, target: str) -> bool:
        """Whether the request subscribes to a session's events."""
        path = urllib.parse.urlsplit(target).path
        return method == "GET" and _EVENTS.fullmatch(path) is not None

    def subscribe(self, target: str) -> tuple[session_lib.Session, contract.Viewer]:
        """Returns the session and viewer an events request subscribes.

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
        )
        viewer = req.viewer()
        session = self._sessions.get(req.session_id)
        session.frame(viewer)
        return session, viewer

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

    def create(self, req: _Request) -> Response:
        """Starts a session, keeping it only if the viewer may see it."""
        viewer, body = req.viewer(), req.decode(request.CreateSession)
        session = self._sessions.create(
            body.game,
            body.parameters,
            seed=body.seed,
            chance_policy=body.chance_policy,
            controllers=[spec(seat) for seat in body.seats],
            autoplay=[seat.autoplay for seat in body.seats],
        )
        try:
            frame = session.frame(viewer)
        except errors.RequestError:
            self._sessions.delete(session.id)
            raise
        return ok(frame)

    def get_frame(self, req: _Request) -> Response:
        """Answers with the live position."""
        viewer = req.viewer()
        return ok(self._sessions.get(req.session_id).frame(viewer))

    def replay(self, req: _Request) -> Response:
        """Answers with an earlier position."""
        viewer, ply = req.viewer(), req.index("ply")
        session = self._sessions.get(req.session_id)
        return ok(session.replay_frame(viewer, ply))

    def action(self, req: _Request) -> Response:
        """Plays a seat's action."""
        viewer, body = req.viewer(), req.decode(request.ApplyAction)
        session = self._sessions.get(req.session_id)
        return ok(session.apply_action(viewer, body.action, ply=body.ply))

    def chance(self, req: _Request) -> Response:
        """Chooses a chance outcome."""
        viewer, body = req.viewer(), req.decode(request.ApplyChanceOutcome)
        session = self._sessions.get(req.session_id)
        return ok(session.apply_chance(viewer, body.outcome, ply=body.ply))

    def advance(self, req: _Request) -> Response:
        """Lets controllers play, at most `request.MAX_ADVANCE_PLIES` actions."""
        viewer, body = req.viewer(), req.decode(request.Advance)
        session = self._sessions.get(req.session_id)
        return ok(session.advance(viewer, max_plies=body.limit))

    def undo(self, req: _Request) -> Response:
        """Undoes the latest choice of a seat."""
        viewer = req.viewer()
        return ok(self._sessions.get(req.session_id).undo(viewer))

    def reset(self, req: _Request) -> Response:
        """Restarts the game."""
        viewer, body = req.viewer(), req.decode(request.Reset)
        session = self._sessions.get(req.session_id)
        return ok(session.reset(viewer, history=body.history or ()))

    def close(self, req: _Request) -> Response:
        """Forgets a session; any viewer but a spectator closes it."""
        viewer = req.viewer()
        session = self._sessions.get(req.session_id)
        session.check_closer(viewer)
        self._sessions.delete(req.session_id)
        return ok(contract.SessionClosed(id=req.session_id))

    def set_seat(self, req: _Request) -> Response:
        """Changes a seat's controller."""
        viewer, seat = req.viewer(), req.index("seat")
        body = req.decode(request.SeatConfig)
        session = self._sessions.get(req.session_id)
        return ok(session.set_controller(viewer, seat, spec(body), autoplay=body.autoplay))

    _ROUTES: tuple[_Route, ...] = (
        route("GET", "health", health),
        route("GET", "games", catalogue),
        route("POST", "sessions", create),
        route("GET", "sessions/{id}", get_frame),
        route("DELETE", "sessions/{id}", close),
        route("GET", "sessions/{id}/plies/{ply}", replay),
        route("POST", "sessions/{id}/actions", action),
        route("POST", "sessions/{id}/chance", chance),
        route("POST", "sessions/{id}/advance", advance),
        route("POST", "sessions/{id}/undo", undo),
        route("POST", "sessions/{id}/reset", reset),
        route("PUT", "sessions/{id}/seats/{seat}", set_seat),
    )
