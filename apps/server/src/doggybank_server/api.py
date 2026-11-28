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
# Modified for Doggybank.


"""The JSON API: the contract's routes, one typed function each.

CONTRACT.md specifies every route and its errors. Each route makes one call on
a session, and a session serializes its calls under its own lock, so calls
that concern one session are serialized and calls that concern different
sessions run concurrently. Routes and dependencies that touch a session or the
database are plain functions, which FastAPI runs on its thread pool; the rest
are coroutines, which never block the event loop.
"""

import dataclasses
import hashlib
import hmac
import json
import math
import re
import time
from collections.abc import AsyncIterator, Callable, Iterator
from typing import Annotated

import anyio
import fastapi
from fastapi import Depends, Header, Path, Query
from fastapi.security import APIKeyHeader
from sse_starlette import EventSourceResponse, ServerSentEvent

from doggybank_server import (
    accounts,
    contract,
    controllers,
    errors,
    moves,
    request,
    store,
    timeouts,
)
from doggybank_server import catalogue as catalogue_lib
from doggybank_server import frame as frame_lib
from doggybank_server import health as health_lib
from doggybank_server import ledger as ledger_lib
from doggybank_server import rooms as rooms_lib
from doggybank_server import session as session_lib

# The path prefix of every API route.
PREFIX = "/api/"

# The header the Worker names the signed-in account in, signed with the player key.
PLAYER_HEADER = "X-Poker-Player"
ADMIN_KIND = "internal"
PLAYER_KEY_ENV = "DOGGYBANK_PLAYER_KEY"

_NON_NEGATIVE_INTEGER = re.compile(r"0|[1-9][0-9]*")

# Seconds between keepalive comments on an idle event stream, under the
# idle timeouts of the proxies in front of a deployed server.
KEEPALIVE_SECONDS = 15.0

# Each event stream holds a thread while it waits for a change. Its own
# unbounded limiter keeps open streams from taking the threads the routes run on.
_STREAMS = anyio.CapacityLimiter(math.inf)

# Players reach the API through the Worker, which takes their key and names
# them in `PLAYER_HEADER`. The server never reads the key; the scheme documents it.
API_KEY = APIKeyHeader(name="x-api-key", scheme_name="apiKey", auto_error=False)

router = fastapi.APIRouter(
    prefix=PREFIX.rstrip("/"),
    dependencies=[fastapi.Security(API_KEY)],
    responses={"default": {"model": errors.Error, "description": "A refusal"}},
)


def signed_player(player: str, key: str) -> str:
    """Returns the player header naming `player`, signed with `key`."""
    digest = hmac.new(key.encode(), player.encode(), hashlib.sha256).hexdigest()
    return f"{player}.{digest}"


@dataclasses.dataclass(frozen=True)
class Arena:
    """What the routes serve.

    Attributes:
      sessions: Holds the sessions the API creates and serves.
      catalogue: Returns the catalogue of every game.
      health: Returns the server's health report.
      player_key: The key the Worker signs the player header with.
    """

    sessions: store.SessionStore
    catalogue: Callable[[], catalogue_lib.Catalogue]
    health: Callable[[], health_lib.Health]
    player_key: str


async def find_arena(req: fastapi.Request) -> Arena:
    """The arena the app serves."""
    return req.app.state.arena


ArenaDep = Annotated[Arena, Depends(find_arena)]


async def identify(
    arena: ArenaDep,
    header: Annotated[str | None, Header(alias=PLAYER_HEADER, include_in_schema=False)] = None,
) -> str | None:
    """The account a signed player header names, or None for any other."""
    if header is None:
        return None

    player, _, _ = header.rpartition(".")
    if not player or not hmac.compare_digest(header, signed_player(player, arena.player_key)):
        return None
    return player


async def require_player(player: Annotated[str | None, Depends(identify)]) -> str:
    """The account the Worker vouches for.

    Raises:
      UnauthorizedError: If the request names no signed-in player.
    """
    if not player:
        raise errors.UnauthorizedError("Sign in to play.")
    return player


Player = Annotated[str, Depends(require_player)]


async def parse_viewer(
    viewer: Annotated[str, Query(description="Your seat's index, the one the room seated you at.")],
) -> contract.Viewer:
    """The viewer the `viewer` query parameter names."""
    if viewer == contract.ViewerKind.ORACLE:
        return contract.Viewer(contract.ViewerKind.ORACLE)
    if viewer == contract.ViewerKind.SPECTATOR:
        return contract.Viewer(contract.ViewerKind.SPECTATOR)
    if _NON_NEGATIVE_INTEGER.fullmatch(viewer):
        return contract.Viewer(contract.ViewerKind.SEAT, int(viewer))
    raise errors.BadRequestError(f"Viewer {viewer!r} is not oracle, spectator or a seat index.")


Viewer = Annotated[contract.Viewer, Depends(parse_viewer)]
SessionId = Annotated[str, Path(alias="id")]
Index = Annotated[int, Path(ge=0)]


@dataclasses.dataclass(frozen=True)
class Seated:
    """A session, and the viewer the request's player may take there."""

    session: session_lib.Session
    viewer: contract.Viewer


def seat_player(arena: ArenaDep, session_id: SessionId, viewer: Viewer, player: Player) -> Seated:
    """The session the request concerns, and the viewer its player may take there."""
    session = arena.sessions.get(session_id)
    session.authorize(viewer, player)
    return Seated(session, viewer)


SeatedView = Annotated[Seated, Depends(seat_player)]


def admin(arena: ArenaDep, player: Player) -> ledger_lib.Ledger:
    """The ledger, for a player whose listing is internal.

    Raises:
      errors.ForbiddenError: If the player's listing is not internal.
    """
    chips = arena.sessions.ledger()
    if chips.kind(player) != ADMIN_KIND:
        raise errors.ForbiddenError("Only an internal account may manage chips.")
    return chips


Admin = Annotated[ledger_lib.Ledger, Depends(admin)]


def seat_view(seat: int | None) -> contract.Viewer:
    """The view of a player at `seat`, or the spectator's when they sit the hand out."""
    if seat is None:
        return contract.Viewer(contract.ViewerKind.SPECTATOR)
    return contract.Viewer(contract.ViewerKind.SEAT, seat)


def spec(seat: request.SeatConfig) -> controllers.Spec:
    """Returns the controller a seat asks for."""
    return controllers.Spec(seat.controller, seat.config)


def room_view(arena: Arena, room: rooms_lib.Room, player: str) -> rooms_lib.RoomView:
    """`room` as `player` sees it."""
    holders = () if room.latest is None else arena.sessions.get(room.latest).holders
    return rooms_lib.RoomView(
        code=room.code,
        buy_in=room.buy_in,
        session_id=room.latest,
        seat=holders.index(player) if player in holders else None,
        stack=room.stack(player),
        stacks=tuple(seat.stack for seat in room.seated),
    )


@router.get("/health", include_in_schema=False)
def health(arena: ArenaDep) -> health_lib.Health:
    """Answers with the health report."""
    return arena.health()


@router.get("/games", include_in_schema=False)
def games(arena: ArenaDep) -> catalogue_lib.Catalogue:
    """Answers with the catalogue."""
    return arena.catalogue()


@router.get("/me", summary="Your chips and open tables")
def get_me(arena: ArenaDep, player: Player) -> accounts.Me:
    """Answers with the signed-in player's balance, kind and seats."""
    chips = arena.sessions.ledger()
    return accounts.Me(
        balance=chips.balance(player),
        kind=chips.kind(player),
        seats=arena.sessions.rooms().seats(player),
    )


@router.get("/admin/accounts", include_in_schema=False)
def list_accounts(chips: Admin) -> accounts.Accounts:
    """Answers with every account, for an admin."""
    return chips.holdings()


@router.post("/admin/grants", include_in_schema=False)
def grant(chips: Admin, body: request.Grant) -> accounts.Accounts:
    """Gives a player chips from the treasury, for an admin, and answers with every account."""
    chips.grant(body.email, body.amount)
    return chips.holdings()


@router.post("/admin/balances", include_in_schema=False)
def set_balance(chips: Admin, body: request.SetBalance) -> accounts.Accounts:
    """Sets a player's chips exactly, for an admin, and answers with every account."""
    chips.set_balance(body.email, body.balance)
    return chips.holdings()


@router.post("/sessions", summary="Open a table and take a seat")
def create_room(
    arena: ArenaDep, viewer: Viewer, player: Player, body: request.CreateSession
) -> frame_lib.Frame:
    """Starts a session with its player seated, keeping it only if the viewer may see it."""
    session = arena.sessions.create(
        body.game,
        body.parameters,
        seed=body.seed,
        chance_policy=body.chance_policy,
        controllers=[spec(seat) for seat in body.seats],
        autoplay=[seat.autoplay for seat in body.seats],
        player=player,
        viewer=viewer,
    )
    return session.frame(viewer)


@router.get("/rooms/{code}", summary="A table's latest hand and stacks")
def get_room(arena: ArenaDep, code: str, player: Player) -> rooms_lib.RoomView:
    """Answers with the room as the player sees it."""
    return room_view(arena, arena.sessions.rooms().find(code.upper()), player)


@router.post("/rooms/{code}/join", summary="Sit at a table by its code")
def join_room(arena: ArenaDep, code: str, player: Player) -> frame_lib.Frame:
    """Sits the player at a room by its code, and answers with their view of its hand."""
    session, seat = arena.sessions.join(code.upper(), player)
    return session.frame(seat_view(seat))


@router.post("/rooms/{code}/deal", summary="Deal the next hand")
def deal_next_hand(
    arena: ArenaDep, code: str, player: Player, body: request.Deal
) -> frame_lib.Frame:
    """Deals the room's next hand, and answers with the player's view of it."""
    session, seat = arena.sessions.deal(code.upper(), body.after, player)
    return session.frame(seat_view(seat))


@router.post("/rooms/{code}/leave", summary="Cash out between hands")
def leave_room(arena: ArenaDep, code: str, player: Player) -> rooms_lib.RoomView:
    """Gets the player up from the room's table, and answers with the room."""
    return room_view(arena, arena.sessions.leave(code.upper(), player), player)


@router.get("/sessions/{id}", summary="The table as your seat sees it")
def get_table(seated: SeatedView) -> frame_lib.Frame:
    """Answers with the live position."""
    return seated.session.frame(seated.viewer)


@router.delete("/sessions/{id}", include_in_schema=False)
def close(arena: ArenaDep, seated: SeatedView, session_id: SessionId) -> contract.SessionClosed:
    """Forgets a session; any viewer but a spectator closes it."""
    seated.session.check_closer(seated.viewer)
    arena.sessions.delete(session_id)
    return contract.SessionClosed(id=session_id)


@router.get("/sessions/{id}/events", include_in_schema=False)
def watch(seated: SeatedView, player: Player) -> EventSourceResponse:
    """Streams the viewer's live frame as Server-Sent Events."""
    seated.session.frame(seated.viewer)
    # The stream writes its own keepalives, so it never pings.
    return EventSourceResponse(in_threads(events(seated.session, seated.viewer, player)), ping=0)


def events(
    session: session_lib.Session, viewer: contract.Viewer, player: str
) -> Iterator[ServerSentEvent]:
    """The viewer's live frame after every change, while the player may still take the view.

    A view that another player's arrival closes ends with a `refused` event, and
    a session idle for `timeouts.STREAM_IDLE_SECONDS` ends its streams with an
    `idle` event.
    """
    version = -1
    while not session.closed:
        version, frame = session.wait(viewer, version, KEEPALIVE_SECONDS)
        if frame is None:
            if time.monotonic() - session.changed_at >= timeouts.STREAM_IDLE_SECONDS:
                yield ServerSentEvent(event="idle", data="")
                return
            yield ServerSentEvent(comment="keepalive")
            continue
        try:
            session.authorize(viewer, player)
        except errors.RequestError:
            yield ServerSentEvent(event="refused", data="")
            return
        data = json.dumps(contract.to_json(frame), allow_nan=False, separators=(",", ":"))
        yield ServerSentEvent(data=data)


async def in_threads[T](items: Iterator[T]) -> AsyncIterator[T]:
    """Yields `items`, drawing each on a thread of `_STREAMS`.

    A cancelled draw abandons its thread, which ends with its wait, so a client
    that disconnects is let go at once.
    """
    while True:
        item = await anyio.to_thread.run_sync(
            next, items, None, limiter=_STREAMS, abandon_on_cancel=True
        )
        if item is None:
            return
        yield item


@router.get("/sessions/{id}/plies/{ply}", include_in_schema=False)
def replay(seated: SeatedView, ply: Index) -> frame_lib.Frame:
    """Answers with an earlier position."""
    return seated.session.replay_frame(seated.viewer, ply)


@router.post("/sessions/{id}/actions", include_in_schema=False)
def act(seated: SeatedView, body: request.ApplyAction) -> frame_lib.Frame:
    """Plays a seat's action."""
    return seated.session.apply_action(seated.viewer, body.action, ply=body.ply)


@router.get("/sessions/{id}/turn", summary="Your cards, the pot, and your moves")
def get_turn(seated: SeatedView) -> moves.Turn:
    """Answers with the seat's turn: its cards, the pot, the price and its legal moves."""
    return moves.turn_of(seated.session.frame(seated.viewer).observation_struct)


@router.post("/sessions/{id}/moves", summary="Fold, check, call, bet, or raise")
def play_move(seated: SeatedView, body: request.PlayMove) -> frame_lib.Frame:
    """Plays a move named by its kind and amount, resolved to its action id."""
    action = moves.resolve(seated.session.frame(seated.viewer).observation_struct, body)
    return seated.session.apply_action(seated.viewer, action)


@router.post("/sessions/{id}/chance", include_in_schema=False)
def chance(seated: SeatedView, body: request.ApplyChanceOutcome) -> frame_lib.Frame:
    """Chooses a chance outcome."""
    return seated.session.apply_chance(seated.viewer, body.outcome, ply=body.ply)


@router.post("/sessions/{id}/advance", include_in_schema=False)
def advance(seated: SeatedView, body: request.Advance) -> frame_lib.Frame:
    """Lets controllers play, at most `request.MAX_ADVANCE_PLIES` actions."""
    return seated.session.advance(seated.viewer, max_plies=body.limit)


@router.post("/sessions/{id}/undo", include_in_schema=False)
def undo(seated: SeatedView) -> frame_lib.Frame:
    """Undoes the latest choice of a seat."""
    return seated.session.undo(seated.viewer)


@router.post("/sessions/{id}/reset", include_in_schema=False)
def reset(seated: SeatedView, body: request.Reset) -> frame_lib.Frame:
    """Restarts the game."""
    return seated.session.reset(seated.viewer, history=body.history or ())


@router.put("/sessions/{id}/seats/{seat}", include_in_schema=False)
def set_seat(seated: SeatedView, seat: Index, body: request.SeatConfig) -> frame_lib.Frame:
    """Changes a seat's controller."""
    return seated.session.set_controller(seated.viewer, seat, spec(body), autoplay=body.autoplay)
