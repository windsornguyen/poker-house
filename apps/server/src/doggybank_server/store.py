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


"""An in-memory store of sessions, shared by the server's threads.

The store's lock guards only which sessions exist; each session serializes
its own changes, so requests to different sessions never wait on each other.

Every new game a client sets up is a new session, and no client says when it
is done with one, so the store keeps a bounded number: past its capacity, a
new session displaces the one used least recently.
"""

import collections
import contextlib
import secrets
import threading
from collections.abc import Generator, Mapping, Sequence

import psycopg

from doggybank_server import contract, db, errors, loader, plies, timeouts
from doggybank_server import controllers as controllers_lib
from doggybank_server import ledger as ledger_lib
from doggybank_server import rooms as rooms_lib
from doggybank_server import session as session_lib

# The most sessions a store keeps, far more than the tabs one person opens.
DEFAULT_CAPACITY = 256


def common_prefix(before: Sequence[plies.Ply], current: Sequence[plies.Ply]) -> int:
    """How many leading plies of `before` and `current` match."""
    kept = 0
    for old, new in zip(before, current, strict=False):
        if (old.seat, old.action, old.bot_output) != (new.seat, new.action, new.bot_output):
            break
        kept += 1
    return kept


class Journal:
    """Linearizes each session's changes in Postgres."""

    def __init__(self, database: db.Database) -> None:
        self.database = database
        self.saved: dict[str, tuple[plies.Ply, ...]] = {}
        self.saved_seats: dict[str, tuple[db.StoredSeat, ...]] = {}

    def follow(
        self,
        session: session_lib.Session,
        seats: Sequence[db.StoredSeat],
        *,
        after: str | None = None,
    ) -> str:
        """Records a new session, or returns the id already dealt after `after`."""
        chosen = self.database.insert(
            db.StoredSession(
                id=session.id,
                code=session.code,
                game=session.game_name,
                parameters=session.parameters,
                seed=session.seed,
                chance_policy=session.chance_policy,
                seats=tuple(seats),
                plies=(),
                staked=session.staked,
            ),
            session.played,
            session.returns,
            after=after,
        )
        if chosen == session.id:
            self.resume(session)
        return chosen

    def resume(self, session: session_lib.Session) -> None:
        """Guards every future change to `session` against its stored plies."""
        self.saved[session.id] = session.played
        self.saved_seats[session.id] = session.stored_seats()
        session.guard = self.guard

    @contextlib.contextmanager
    def guard(self, session: session_lib.Session) -> Generator[bool]:
        """Runs one change to `session` under its row lock in one transaction.

        If the stored ply count, history or seats moved on another server,
        `session` is rebuilt from Postgres in the same transaction before the
        change is tried.
        """
        before = self.saved.get(session.id, ())
        before_seats = self.saved_seats.get(session.id, ())
        failed_controller: errors.ControllerFailedError | None = None
        with self.database.lock, self.database.connection.transaction():
            open_before, stale = self.database.lock_session(
                session.id,
                len(before),
                [ply.action for ply in before],
                before_seats,
            )
            if stale is not None:
                session.reload(stale)
                before = session.played
                before_seats = session.stored_seats()
                self.saved[session.id] = before
                self.saved_seats[session.id] = before_seats
            try:
                yield stale is not None
            except errors.ControllerFailedError as error:
                failed_controller = error
            except errors.RequestError:
                raise
            except BaseException:
                self.saved.pop(session.id, None)
                self.saved_seats.pop(session.id, None)
                raise
            current = session.played
            seats_now = session.stored_seats()
            kept = common_prefix(before, current)
            self.database.write_plies(
                session.id,
                open_before=open_before,
                expected=len(before),
                kept=kept,
                added=current[kept:],
                returns=session.returns,
                seats=None if seats_now == before_seats else seats_now,
            )
        self.saved[session.id] = current
        self.saved_seats[session.id] = seats_now
        if failed_controller is not None:
            raise failed_controller

    def refresh(self, session: session_lib.Session) -> bool:
        """Reloads `session` if Postgres moved ahead of it; False if deleted."""
        with session._lock:
            snap = self.database.snapshot(session.id)
            if snap is None:
                self.saved.pop(session.id, None)
                self.saved_seats.pop(session.id, None)
                return False
            before = self.saved.get(session.id, ())
            before_seats = self.saved_seats.get(session.id, ())
            if (
                snap.actions == tuple(ply.action for ply in before)
                and snap.seats == before_seats
                and snap.next == session.next_id
            ):
                return True
            stored = self.database.load(session.id)
            if stored is None:
                self.saved.pop(session.id, None)
                self.saved_seats.pop(session.id, None)
                return False
            session.reload(stored)
            self.saved[session.id] = session.played
            self.saved_seats[session.id] = session.stored_seats()
            return True

    def load(self, session_id: str) -> session_lib.Session | None:
        """Rebuilds a stored session, or returns None if there is none."""
        stored = self.database.load(session_id)
        if stored is None:
            return None
        session = session_lib.Session.restore(stored)
        self.resume(session)
        return session

    def forget(self, session_id: str) -> bool:
        """Deletes a session from the database; returns whether it existed."""
        self.saved.pop(session_id, None)
        self.saved_seats.pop(session_id, None)
        return self.database.delete(session_id)

    def forget_unstarted(self, code: str, session_id: str) -> bool:
        """Deletes `session_id` if `code` still waits for its second player."""
        if not self.database.delete_unstarted(code, session_id):
            return False
        self.saved.pop(session_id, None)
        self.saved_seats.pop(session_id, None)
        return True


class SessionStore:
    """The sessions a server holds, keyed by id, least recently used first."""

    def __init__(self, capacity: int = DEFAULT_CAPACITY, journal: Journal | None = None) -> None:
        """Starts a store that keeps at most `capacity` sessions in memory.

        With a `journal`, every session is also kept in the database, and one
        forgotten from memory is rebuilt from it on its next request.
        """
        if capacity < 1:
            raise ValueError(f"A store keeps at least one session, not {capacity}.")
        self._capacity = capacity
        self._sessions: collections.OrderedDict[str, session_lib.Session] = (
            collections.OrderedDict()
        )
        self._lock = threading.Lock()
        self.journal = journal
        self.chips = None if journal is None else ledger_lib.Ledger(journal.database)
        self.tables = None if journal is None else rooms_lib.Rooms(journal.database)
        self._dealing = threading.Lock()
        self.turns = timeouts.TurnClock()
        self.hands = timeouts.HandClock(self.expire)
        if self.journal is not None:
            self.journal.database.listen(self.on_notice)

    def on_notice(self, session_id: str) -> None:
        """Reloads a held session when another process commits a change to it."""
        with self._lock:
            session = self._sessions.get(session_id)
        if session is None or self.journal is None:
            return
        try:
            if not self.journal.refresh(session):
                self.expire(session_id)
        except psycopg.OperationalError, psycopg.InterfaceError:
            return

    def create(
        self,
        game_name: str,
        parameters: Mapping[str, contract.ParameterValue],
        *,
        seed: int | None = None,
        chance_policy: contract.ChancePolicy,
        controllers: Sequence[controllers_lib.Spec],
        autoplay: Sequence[bool] = (),
        player: str,
        viewer: contract.Viewer,
    ) -> session_lib.Session:
        """Opens a room with its first hand, `player` at its first human seat.

        A table whose every seat is human plays for chips: the player buys in
        with the table's stack. Nothing is kept unless `player` may take
        `viewer`.

        Args:
          game_name: A registered short name.
          parameters: Game parameters; omitted ones take their defaults.
          seed: Seeds every chance outcome and controller; None: a random seed.
          chance_policy: How chance nodes are resolved.
          controllers: Who plays each seat, in seat order.
          autoplay: Whether each seat's controller plays as soon as it is to move,
            in seat order; empty for none.
          player: The account that opens the room.
          viewer: The view the player opens it at.

        Raises:
          errors.RequestError: If the room cannot be opened.
        """
        staked = all(spec.kind == contract.HUMAN for spec in controllers)
        buy_in = stake(game_name, parameters, chance_policy) if staked else None
        if staked:
            self.rooms()

        code = "".join(
            secrets.choice(session_lib.CODE_ALPHABET) for _ in range(session_lib.CODE_LENGTH)
        )
        session = session_lib.Session.create(
            game_name,
            parameters,
            seed=seed,
            chance_policy=chance_policy,
            controllers=controllers,
            autoplay=autoplay,
            players=[player],
            code=code,
            staked=staked,
        )
        session.authorize(viewer, player)

        if self.tables is not None:
            self.tables.open(code, buy_in, player, len(controllers))
        return self.keep(session, controllers, autoplay)

    def keep(
        self,
        session: session_lib.Session,
        controllers: Sequence[controllers_lib.Spec],
        autoplay: Sequence[bool],
        *,
        after: str | None = None,
    ) -> session_lib.Session:
        """Stores a new hand, and keeps its clocks."""
        if self.journal is not None:
            chosen = self.journal.follow(
                session,
                [
                    db.StoredSeat(spec, play, holder)
                    for spec, play, holder in zip(
                        controllers,
                        autoplay or [False] * len(controllers),
                        session.holders,
                        strict=True,
                    )
                ],
                after=after,
            )
            if chosen != session.id:
                return self.get(chosen)
        self.turns.follow(session)
        self.hands.follow(session)
        with self._lock:
            self._sessions[session.id] = session
            self.evict_locked()
        return session

    def evict_locked(self) -> None:
        """Drops the oldest sessions past `_capacity`; caller holds `_lock`."""
        while len(self._sessions) > self._capacity:
            evicted = self._sessions.popitem(last=False)[1]
            evicted.guard = None
            evicted.listeners.clear()
            evicted.close()

    def get(self, session_id: str) -> session_lib.Session:
        """Returns the session with id `session_id`.

        Args:
          session_id: The id of the session.

        Raises:
          errors.NotFoundError: If there is no such session, or it was forgotten
            to make room for newer ones.
        """
        with self._lock:
            session = self._sessions.get(session_id)
            if session is not None:
                self._sessions.move_to_end(session_id)
        if session is not None and self.journal is not None:
            if not self.journal.refresh(session):
                self.expire(session_id)
                raise errors.NotFoundError(f"There is no session {session_id!r}.")
            return session
        if session is None and self.journal is not None:
            loaded = self.journal.load(session_id)
            if loaded is not None:
                with self._lock:
                    existing = self._sessions.get(session_id)
                    if existing is None:
                        self._sessions[session_id] = loaded
                        self.evict_locked()
                        session = loaded
                    else:
                        session = existing
                if session is loaded:
                    self.turns.follow(session)
                    self.hands.follow(session)
                elif not self.journal.refresh(session):
                    self.expire(session_id)
                    raise errors.NotFoundError(f"There is no session {session_id!r}.")
        if session is None:
            raise errors.NotFoundError(f"There is no session {session_id!r}.")
        return session

    def ledger(self) -> ledger_lib.Ledger:
        """The accounts, kept in the same database as the sessions.

        Raises:
          errors.LedgerUnavailableError: If the store keeps no database.
        """
        if self.chips is None:
            raise errors.LedgerUnavailableError(
                "This server keeps no database, so it holds no chips."
            )
        return self.chips

    def problem(self) -> str | None:
        """Returns why the store cannot keep sessions, or None when it can."""
        return None if self.journal is None else self.journal.database.problem()

    def join(self, code: str, player: str) -> tuple[session_lib.Session, int | None]:
        """Sits `player` at room `code`, buying in at a table played for chips.

        Returns:
          The room's latest hand, and the seat the player holds in it: None
          when they sit out this hand and are dealt into the next.

        Raises:
          errors.NotFoundError: If no room has the code, or it has closed.
          errors.RoomFullError: If every seat is held by another player.
          errors.InsufficientChipsError: If the player cannot cover the buy-in.
        """
        room = self.rooms().find(code)
        if room.latest is None:
            raise errors.NotFoundError(f"The room {code!r} has closed.")

        session = self.get(room.latest)
        if room.buy_in is not None:
            self.rooms().sit(code, player, session.num_seats)
            if self.rooms().find(code).latest is None:
                self.rooms().leave(code, player)
                raise errors.NotFoundError(f"The room {code!r} has closed.")

        try:
            seat = session.claim(player)
        except errors.NotFoundError:
            if room.buy_in is not None:
                self.rooms().leave(code, player)
            raise errors.NotFoundError(f"The room {code!r} has closed.") from None
        if seat is None and room.buy_in is None:
            raise errors.RoomFullError("Every seat at this table is taken.")
        return session, seat

    def deal(self, code: str, after: str, player: str) -> tuple[session_lib.Session, int | None]:
        """Deals room `code`'s next hand after hand `after`, or finds it if it is dealt.

        Each player's stack carries over, and the seats turn by one each hand,
        so the blinds alternate.

        Returns:
          The hand after `after`, and the seat the player holds in it: None
          when they sat down after it was dealt.

        Raises:
          errors.ForbiddenError: If `player` does not sit at the room.
          errors.TableNotReadyError: If the hand is still being played, or a
            seat is empty.
        """
        with self._dealing:
            room = self.rooms().find(code)
            if room.buy_in is None or room.latest is None:
                raise errors.TableNotReadyError(
                    "Only a table played for chips deals the next hand."
                )
            if room.stack(player) is None:
                raise errors.ForbiddenError("You do not sit at this table.")

            latest = self.get(room.latest)
            if room.latest == after:
                latest = self.next_hand(room, latest)

        return latest, latest.holders.index(player) if player in latest.holders else None

    def next_hand(self, room: rooms_lib.Room, latest: session_lib.Session) -> session_lib.Session:
        """Deals the hand after `latest` at `room`, to the players seated there now."""
        if latest.returns is None:
            raise errors.TableNotReadyError("The hand is still being played.")
        if len(room.seated) < latest.num_seats:
            raise errors.TableNotReadyError("Waiting for players.")

        turn = len(room.hands) % len(room.seated)
        order = room.seated[turn:] + room.seated[:turn]
        parameters = {
            **latest.parameters,
            "stack_sizes": " ".join(str(seat.stack) for seat in order),
        }
        controllers = [controllers_lib.Spec(contract.HUMAN, {})] * latest.num_seats
        session = session_lib.Session.create(
            latest.game_name,
            parameters,
            chance_policy=latest.chance_policy,
            controllers=controllers,
            players=[seat.player for seat in order],
            code=room.code,
            staked=True,
        )
        dealt = self.keep(session, controllers, (), after=latest.id)
        latest.succeed(dealt.id)
        return dealt

    def leave(self, code: str, player: str) -> rooms_lib.Room:
        """Gets up from room `code`, moving `player`'s stack back to their account.

        A first hand still waiting for its second player never starts, so it
        is forgotten. Any other hand is finished before its players leave.

        Raises:
          errors.NotFoundError: If `player` does not sit at the room.
          errors.TableNotReadyError: If `player` is in a hand still being played.
        """
        with self._dealing:
            room = self.rooms().find(code)
            latest = None if room.latest is None else self.get(room.latest)
            if latest is not None and latest.returns is None and player in latest.holders:
                if None not in latest.holders or (
                    self.journal is not None and not self.journal.forget_unstarted(code, latest.id)
                ):
                    raise errors.TableNotReadyError("Finish the hand before you leave.")
                self.expire(latest.id)
                if self.journal is None:
                    self.delete(latest.id)

            self.rooms().leave(code, player)
            return self.rooms().find(code)

    def rooms(self) -> rooms_lib.Rooms:
        """The rooms, kept in the same database as the sessions.

        Raises:
          errors.LedgerUnavailableError: If the store keeps no database.
        """
        if self.tables is None:
            raise errors.LedgerUnavailableError(
                "This server keeps no database, so it seats no one for chips."
            )
        return self.tables

    def find(self, code: str) -> str:
        """Returns the id of the stored session with room code `code`.

        Raises:
          errors.NotFoundError: If no room has the code.
        """
        session_id = None if self.journal is None else self.journal.database.find(code)
        if session_id is None:
            raise errors.NotFoundError(f"There is no room {code!r}.")
        return session_id

    def delete(self, session_id: str) -> None:
        """Forgets the session with id `session_id`.

        Args:
          session_id: The id of the session.

        Raises:
          errors.NotFoundError: If there is no such session.
        """
        with self._lock:
            session = self._sessions.pop(session_id, None)
        if session is not None:
            session.guard = None
            session.listeners.clear()
            session.close()
        if self.journal is not None:
            if not self.journal.forget(session_id):
                raise errors.NotFoundError(f"There is no session {session_id!r}.")
        elif session is None:
            raise errors.NotFoundError(f"There is no session {session_id!r}.")

    def expire(self, session_id: str) -> None:
        """Drops a session from memory and ends its streams; its record stays."""
        with self._lock:
            session = self._sessions.pop(session_id, None)
        if session is not None:
            session.guard = None
            session.listeners.clear()
            session.close()

    def __len__(self) -> int:
        with self._lock:
            return len(self._sessions)


def stake(
    game_name: str,
    parameters: Mapping[str, contract.ParameterValue],
    chance_policy: contract.ChancePolicy,
) -> int:
    """The buy-in of a table played for chips: its stack, the same for every seat.

    Raises:
      errors.BadRequestError: If the stacks differ, or the table does not deal
        its own cards.
    """
    if chance_policy != contract.ChancePolicy.AUTO:
        raise errors.BadRequestError("A table played for chips deals its own cards.")

    stacks = str(loader.load(game_name, parameters).parameters["stack_sizes"]).split()
    if len(set(stacks)) != 1:
        raise errors.BadRequestError(
            "Every seat at a table played for chips buys in with the same stack."
        )
    return int(stacks[0])
