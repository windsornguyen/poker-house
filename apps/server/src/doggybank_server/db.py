"""Sessions in Postgres: each session's setup and the plies played (schema.sql)."""

import dataclasses
import threading
from collections.abc import Callable, Mapping, Sequence

import psycopg
import pydantic
from psycopg.types.json import Jsonb

from doggybank_server import contract, controllers, errors, plies


@dataclasses.dataclass(frozen=True)
class StoredSeat:
    """A seat's controller as stored."""

    spec: controllers.Spec
    autoplay: bool
    player: str | None


@dataclasses.dataclass(frozen=True)
class StoredPly:
    """A ply as stored: enough to replay it and show its bot output."""

    seat: int | None
    action: int
    bot_output: contract.BotOutput | None


@dataclasses.dataclass(frozen=True)
class StoredSession:
    """A session as stored."""

    id: str
    code: str
    game: str
    parameters: Mapping[str, contract.ParameterValue]
    seed: int
    chance_policy: contract.ChancePolicy
    seats: tuple[StoredSeat, ...]
    plies: tuple[StoredPly, ...]
    staked: bool
    next: str | None = None


@dataclasses.dataclass(frozen=True)
class Snapshot:
    """The mutable fields of a stored session, read in one query to spot stale copies."""

    actions: tuple[int, ...]
    seats: tuple[StoredSeat, ...]
    next: str | None


BOT_OUTPUT = pydantic.TypeAdapter(contract.BotOutput)
PARAMETERS = pydantic.TypeAdapter(dict[str, contract.ParameterValue])
HAND_CHANNEL = "poker_hand"


def dump_ply(session_id: str, index: int, ply: plies.Ply) -> tuple[object, ...]:
    """A ply row ready for `poker.ply`."""
    output = (
        None
        if ply.bot_output is None
        else Jsonb(BOT_OUTPUT.dump_python(ply.bot_output, mode="json"))
    )
    return (session_id, index, ply.seat, ply.action, output)


class Database:
    """One connection, shared by the server's request threads."""

    def __init__(self, url: str) -> None:
        self.url = url
        self.connection = psycopg.connect(url, autocommit=True)
        self.lock = threading.Lock()
        self.listeners: list[psycopg.Connection] = []

    def listen(self, on_hand: Callable[[str], None]) -> None:
        """Opens one LISTEN connection and calls `on_hand` when another process updates a hand."""
        listener = psycopg.connect(self.url, autocommit=True)
        listener.execute(f"listen {HAND_CHANNEL}")
        self.listeners.append(listener)
        own_pid = self.connection.info.backend_pid

        def watch() -> None:
            try:
                for notice in listener.notifies():
                    if notice.pid != own_pid:
                        on_hand(notice.payload)
            except psycopg.OperationalError, psycopg.InterfaceError:
                return

        threading.Thread(target=watch, name="poker-hand-listen", daemon=True).start()

    def notify(self, session_id: str) -> None:
        """Queues a wakeup on `HAND_CHANNEL` for delivery once the transaction commits."""
        self.connection.execute("select pg_notify(%s, %s)", (HAND_CHANNEL, session_id))

    def close(self) -> None:
        """Closes every connection this database opened."""
        for listener in self.listeners:
            listener.close()
        self.connection.close()

    def insert(
        self,
        stored: StoredSession,
        played: Sequence[plies.Ply] = (),
        returns: Sequence[float] | None = None,
        *,
        after: str | None = None,
    ) -> str:
        """Records a new session, its seats and its initial plies.

        When `after` is given, locks the room and inserts `stored` only while
        `after` is still its latest hand, returning the id of the hand after
        `after` either way.
        """
        with self.lock, self.connection.transaction():
            if after is not None:
                self.connection.execute(
                    "select 1 from poker.room where code = %s for update", (stored.code,)
                )
                latest = self._latest(stored.code)
                if latest is not None and latest != after:
                    return latest
            self.connection.execute(
                "insert into poker.session (id, code, game, parameters, seed, chance_policy)"
                " values (%s, %s, %s, %s, %s, %s)",
                (
                    stored.id,
                    stored.code,
                    stored.game,
                    Jsonb(dict(stored.parameters)),
                    stored.seed,
                    stored.chance_policy.value,
                ),
            )
            self.connection.cursor().executemany(
                "insert into poker.seat (session_id, seat, controller, config, autoplay, player)"
                " values (%s, %s, %s, %s, %s, %s)",
                [
                    (
                        stored.id,
                        index,
                        seat.spec.kind,
                        Jsonb(dict(seat.spec.config)),
                        seat.autoplay,
                        seat.player,
                    )
                    for index, seat in enumerate(stored.seats)
                ],
            )
            if played or returns is not None:
                self.write_plies(
                    stored.id,
                    open_before=True,
                    expected=0,
                    kept=0,
                    added=played,
                    returns=returns,
                )
            if after is not None:
                self.notify(after)
            return stored.id

    def lock_session(
        self,
        session_id: str,
        expected: int,
        actions: Sequence[int],
        seats: Sequence[StoredSeat],
    ) -> tuple[bool, StoredSession | None]:
        """Locks `session_id` in the caller's transaction and checks its ply count.

        Returns whether the hand was still open, and the stored session when the
        caller's copy is stale (its ply count, history or seats differ), else None.

        Raises:
          errors.NotFoundError: If `session_id` is not in the database.
        """
        row = self.connection.execute(
            "select finished_at is null,"
            " (select count(*) from poker.ply where session_id = %s)"
            " from poker.session where id = %s for update",
            (session_id, session_id),
        ).fetchone()
        if row is None:
            raise errors.NotFoundError(f"There is no session {session_id!r}.")
        open_before, count = row
        if count != expected:
            return open_before, self._load(session_id)
        snap = self._snapshot(session_id)
        assert snap is not None
        if snap.actions != tuple(actions) or snap.seats != tuple(seats):
            return open_before, self._load(session_id)
        return open_before, None

    def record(
        self,
        session_id: str,
        expected: int,
        kept: int,
        added: Sequence[plies.Ply],
        returns: Sequence[float] | None,
    ) -> StoredSession | None:
        """Compares the stored ply count with `expected` and writes the change if current.

        Returns None when the write committed, or the fresh `StoredSession` when
        the stored ply count differed from `expected` and nothing was written.
        """
        with self.lock, self.connection.transaction():
            row = self.connection.execute(
                "select finished_at is null,"
                " (select count(*) from poker.ply where session_id = %s)"
                " from poker.session where id = %s for update",
                (session_id, session_id),
            ).fetchone()
            if row is None:
                raise errors.NotFoundError(f"There is no session {session_id!r}.")
            open_before, count = row
            if count != expected:
                return self._load(session_id)
            self.write_plies(
                session_id,
                open_before=open_before,
                expected=expected,
                kept=kept,
                added=added,
                returns=returns,
            )
            return None

    def write_plies(
        self,
        session_id: str,
        *,
        open_before: bool,
        expected: int,
        kept: int,
        added: Sequence[plies.Ply],
        returns: Sequence[float] | None,
        seats: Sequence[StoredSeat] | None = None,
    ) -> None:
        """Writes a locked session's changed plies, seats and result in the caller's transaction.

        The moment a hand finishes, each seated player's stack at the room takes
        the seat's return, in the same transaction, and a stack left empty frees
        its seat. A hand played for nothing has no stacks, so nothing changes.
        """
        if kept < expected:
            self.connection.execute(
                "delete from poker.ply where session_id = %s and ply >= %s",
                (session_id, kept),
            )
        if added:
            self.connection.cursor().executemany(
                "insert into poker.ply (session_id, ply, seat, action, bot_output)"
                " values (%s, %s, %s, %s, %s)",
                [dump_ply(session_id, kept + offset, ply) for offset, ply in enumerate(added)],
            )
        if kept < expected or added or (returns is not None and open_before):
            self.connection.execute(
                "update poker.session set returns = %s,"
                " finished_at = case when %s::float8[] is null then null"
                " else coalesce(finished_at, now()) end where id = %s",
                (
                    None if returns is None else list(returns),
                    None if returns is None else list(returns),
                    session_id,
                ),
            )
            if returns is not None and open_before:
                self.settle(session_id, returns)
        if seats is not None:
            self.connection.cursor().executemany(
                "update poker.seat set controller = %s, config = %s, autoplay = %s, player = %s"
                " where session_id = %s and seat = %s",
                [
                    (
                        seat.spec.kind,
                        Jsonb(dict(seat.spec.config)),
                        seat.autoplay,
                        seat.player,
                        session_id,
                        index,
                    )
                    for index, seat in enumerate(seats)
                ],
            )
        if kept < expected or added or seats is not None or (returns is not None and open_before):
            self.notify(session_id)

    def settle(self, session_id: str, returns: Sequence[float]) -> None:
        """Adds a finished hand's returns to its players' stacks, in the caller's transaction."""
        self.connection.execute(
            "update poker.room_seat r"
            " set stack = r.stack + round((%s::float8[])[s.seat + 1])::bigint"
            " from poker.seat s join poker.session x on x.id = s.session_id"
            " where s.session_id = %s and s.player = r.player and r.code = x.code",
            (list(returns), session_id),
        )
        self.connection.execute(
            "delete from poker.room_seat r using poker.session x"
            " where x.id = %s and r.code = x.code and r.stack = 0",
            (session_id,),
        )

    def snapshot(self, session_id: str) -> Snapshot | None:
        """Returns the mutable fields of `session_id`, or None if there is none."""
        with self.lock:
            return self._snapshot(session_id)

    def _snapshot(self, session_id: str) -> Snapshot | None:
        row = self.connection.execute(
            "select coalesce("
            "  (select array_agg(action order by ply) from poker.ply where session_id = s.id),"
            "  '{}'"
            "),"
            " (select n.id from poker.session n where n.code = s.code"
            "  and n.created_at > s.created_at order by n.created_at limit 1)"
            " from poker.session s where s.id = %s",
            (session_id,),
        ).fetchone()
        if row is None:
            return None
        seats = self.connection.execute(
            "select controller, config, autoplay, player from poker.seat"
            " where session_id = %s order by seat",
            (session_id,),
        ).fetchall()
        actions, next_id = row
        return Snapshot(
            actions=tuple(actions),
            seats=tuple(
                StoredSeat(
                    controllers.Spec(kind, PARAMETERS.validate_python(config)), autoplay, player
                )
                for kind, config, autoplay, player in seats
            ),
            next=next_id,
        )

    def load(self, session_id: str) -> StoredSession | None:
        """Returns the stored session, or None if there is none."""
        with self.lock:
            return self._load(session_id)

    def _load(self, session_id: str) -> StoredSession | None:
        row = self.connection.execute(
            "select s.code, s.game, s.parameters, s.seed, s.chance_policy, r.buy_in is not null,"
            " (select n.id from poker.session n where n.code = s.code"
            "  and n.created_at > s.created_at order by n.created_at limit 1)"
            " from poker.session s join poker.room r on r.code = s.code where s.id = %s",
            (session_id,),
        ).fetchone()
        if row is None:
            return None
        seats = self.connection.execute(
            "select controller, config, autoplay, player from poker.seat"
            " where session_id = %s order by seat",
            (session_id,),
        ).fetchall()
        played = self.connection.execute(
            "select seat, action, bot_output from poker.ply where session_id = %s order by ply",
            (session_id,),
        ).fetchall()
        code, game, parameters, seed, chance_policy, staked, next_id = row
        return StoredSession(
            id=session_id,
            code=code,
            game=game,
            parameters=PARAMETERS.validate_python(parameters),
            seed=seed,
            chance_policy=contract.ChancePolicy(chance_policy),
            seats=tuple(
                StoredSeat(
                    controllers.Spec(kind, PARAMETERS.validate_python(config)), autoplay, player
                )
                for kind, config, autoplay, player in seats
            ),
            plies=tuple(
                StoredPly(
                    seat, action, None if output is None else BOT_OUTPUT.validate_python(output)
                )
                for seat, action, output in played
            ),
            staked=staked,
            next=next_id,
        )

    def problem(self) -> str | None:
        """Returns why the database cannot answer a query, or None when it can."""
        try:
            with self.lock:
                self.connection.execute("select 1")
        except psycopg.Error as error:
            return str(error)
        return None

    def find(self, code: str) -> str | None:
        """Returns the id of the latest hand of room `code`, or None."""
        with self.lock:
            return self._latest(code)

    def _latest(self, code: str) -> str | None:
        row = self.connection.execute(
            "select id from poker.session where code = %s order by created_at desc limit 1",
            (code,),
        ).fetchone()
        return None if row is None else row[0]

    def delete(self, session_id: str) -> bool:
        """Forgets a session, its seats and its plies; returns whether it existed."""
        with self.lock, self.connection.transaction():
            deleted = self.connection.execute(
                "delete from poker.session where id = %s", (session_id,)
            )
            if deleted.rowcount > 0:
                self.notify(session_id)
                return True
            return False

    def delete_unstarted(self, code: str, session_id: str) -> bool:
        """Deletes `session_id` while `code` locked has an open human seat and no second buy-in."""
        with self.lock, self.connection.transaction():
            self.connection.execute("select 1 from poker.room where code = %s for update", (code,))
            seated = self.connection.execute(
                "select count(*) from poker.room_seat where code = %s", (code,)
            ).fetchone()
            open_seats = self.connection.execute(
                "select count(*) from poker.seat"
                " where session_id = %s and controller = 'human' and player is null",
                (session_id,),
            ).fetchone()
            if (seated is not None and seated[0] > 1) or open_seats == (0,):
                return False
            self.connection.execute("delete from poker.session where id = %s", (session_id,))
            self.notify(session_id)
            return True
