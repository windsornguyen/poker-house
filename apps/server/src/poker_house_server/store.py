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


"""An in-memory store of sessions, shared by the server's threads.

The store's lock guards only which sessions exist; each session serialises
its own changes, so requests to different sessions never wait on each other.

Every new game a client sets up is a new session, and no client says when it
is done with one, so the store keeps a bounded number: past its capacity, a
new session displaces the one used least recently.
"""

import collections
import threading
from collections.abc import Mapping, Sequence

from poker_house_server import contract, db, errors, plies, timeouts
from poker_house_server import controllers as controllers_lib
from poker_house_server import session as session_lib

# The most sessions a store keeps, far more than the tabs one person opens.
DEFAULT_CAPACITY = 256


class Journal:
    """Writes each session's changes to the database as they happen."""

    def __init__(self, database: db.Database) -> None:
        self.database = database
        self.saved: dict[str, tuple[plies.Ply, ...]] = {}

    def follow(self, session: session_lib.Session, seats: Sequence[db.StoredSeat]) -> None:
        """Records a new session and every change to it from now on."""
        self.database.insert(
            db.StoredSession(
                id=session.id,
                game=session.game_name,
                parameters=session.parameters,
                seed=session.seed,
                chance_policy=session.chance_policy,
                seats=tuple(seats),
                plies=(),
            )
        )
        self.resume(session, ())

    def resume(self, session: session_lib.Session, saved: tuple[plies.Ply, ...]) -> None:
        """Records every change to a session whose first `saved` plies are stored."""
        self.saved[session.id] = saved
        session.listeners.append(self.sync)
        self.sync(session)

    def sync(self, session: session_lib.Session) -> None:
        """Writes the plies that differ from those stored, and the hand's result."""
        current = session.played
        before = self.saved.get(session.id, ())
        kept = 0
        for old, new in zip(before, current, strict=False):
            if (old.seat, old.action, old.bot_output) != (new.seat, new.action, new.bot_output):
                break
            kept += 1
        self.database.record(session.id, kept, current[kept:], session.returns)
        self.saved[session.id] = current

    def load(self, session_id: str) -> session_lib.Session | None:
        """Rebuilds a stored session, or returns None if there is none."""
        stored = self.database.load(session_id)
        if stored is None:
            return None
        session = session_lib.Session.restore(stored)
        self.resume(session, session.played)
        return session

    def forget(self, session_id: str) -> None:
        """Deletes a session from the database."""
        self.saved.pop(session_id, None)
        self.database.delete(session_id)


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
        self.turns = timeouts.TurnClock()
        self.hands = timeouts.HandClock(self.expire)

    def create(
        self,
        game_name: str,
        parameters: Mapping[str, contract.ParameterValue],
        *,
        seed: int | None = None,
        chance_policy: contract.ChancePolicy,
        controllers: Sequence[controllers_lib.Spec],
        autoplay: Sequence[bool] = (),
    ) -> session_lib.Session:
        """Starts a session and stores it; see `session.Session.create`.

        When the store is full, the session used least recently is forgotten.

        Args:
          game_name: A registered short name.
          parameters: Game parameters; omitted ones take their defaults.
          seed: Seeds every chance outcome and controller; None: a random seed.
          chance_policy: How chance nodes are resolved.
          controllers: Who plays each seat, in seat order.
          autoplay: Whether each seat's controller plays as soon as it is to move,
            in seat order; empty for none.

        Returns:
          The session started.

        Raises:
          errors.RequestError: If the session cannot be started.
        """
        session = session_lib.Session.create(
            game_name,
            parameters,
            seed=seed,
            chance_policy=chance_policy,
            controllers=controllers,
            autoplay=autoplay,
        )
        if self.journal is not None:
            self.journal.follow(
                session,
                [
                    db.StoredSeat(spec, play)
                    for spec, play in zip(
                        controllers, autoplay or [False] * len(controllers), strict=True
                    )
                ],
            )
        self.turns.follow(session)
        self.hands.follow(session)
        with self._lock:
            self._sessions[session.id] = session
            while len(self._sessions) > self._capacity:
                evicted = self._sessions.popitem(last=False)[1]
                evicted.listeners.clear()
                evicted.close()
        return session

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
        if session is None and self.journal is not None:
            session = self.journal.load(session_id)
            if session is not None:
                self.turns.follow(session)
                self.hands.follow(session)
                with self._lock:
                    session = self._sessions.setdefault(session_id, session)
        if session is None:
            raise errors.NotFoundError(f"There is no session {session_id!r}.")
        return session

    def delete(self, session_id: str) -> None:
        """Forgets the session with id `session_id`.

        Args:
          session_id: The id of the session.

        Raises:
          errors.NotFoundError: If there is no such session.
        """
        with self._lock:
            session = self._sessions.pop(session_id, None)
        if session is None:
            raise errors.NotFoundError(f"There is no session {session_id!r}.")
        session.close()
        if self.journal is not None:
            self.journal.forget(session_id)

    def expire(self, session_id: str) -> None:
        """Drops a session from memory and ends its streams; its record stays."""
        with self._lock:
            session = self._sessions.pop(session_id, None)
        if session is not None:
            session.listeners.clear()
            session.close()

    def __len__(self) -> int:
        with self._lock:
            return len(self._sessions)
