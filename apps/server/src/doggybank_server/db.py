"""Sessions in Postgres: each session's setup and the plies played (schema.sql)."""

import dataclasses
import threading
from collections.abc import Mapping, Sequence

import psycopg
import pydantic
from psycopg.types.json import Jsonb

from doggybank_server import contract, controllers, plies


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


BOT_OUTPUT = pydantic.TypeAdapter(contract.BotOutput)
PARAMETERS = pydantic.TypeAdapter(dict[str, contract.ParameterValue])


class Database:
    """One connection, shared by the server's request threads."""

    def __init__(self, url: str) -> None:
        self.connection = psycopg.connect(url, autocommit=True)
        self.lock = threading.Lock()

    def insert(self, stored: StoredSession) -> None:
        """Records a new session and its seats."""
        with self.lock, self.connection.transaction():
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

    def record(
        self,
        session_id: str,
        kept: int,
        added: Sequence[plies.Ply],
        returns: Sequence[float] | None,
    ) -> None:
        """Keeps the first `kept` plies, appends `added`, and marks a finished hand.

        The moment a hand finishes, each seated player's stack at the room takes
        the seat's return, in the same transaction, and a stack left empty frees
        its seat. A hand played for nothing has no stacks, so nothing changes.
        """
        with self.lock, self.connection.transaction():
            open_before = self.connection.execute(
                "select finished_at is null from poker.session where id = %s for update",
                (session_id,),
            ).fetchone()
            self.connection.execute(
                "delete from poker.ply where session_id = %s and ply >= %s", (session_id, kept)
            )
            self.connection.cursor().executemany(
                "insert into poker.ply (session_id, ply, seat, action, bot_output)"
                " values (%s, %s, %s, %s, %s)",
                [
                    (
                        session_id,
                        kept + offset,
                        ply.seat,
                        ply.action,
                        None
                        if ply.bot_output is None
                        else Jsonb(BOT_OUTPUT.dump_python(ply.bot_output, mode="json")),
                    )
                    for offset, ply in enumerate(added)
                ],
            )
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
            if returns is not None and open_before == (True,):
                self.settle(session_id, returns)

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

    def load(self, session_id: str) -> StoredSession | None:
        """Returns the stored session, or None if there is none."""
        with self.lock:
            row = self.connection.execute(
                "select s.code, s.game, s.parameters, s.seed, s.chance_policy, r.buy_in is not null"
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
        code, game, parameters, seed, chance_policy, staked = row
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
        )

    def problem(self) -> str | None:
        """Returns why the database cannot answer a query, or None when it can."""
        try:
            with self.lock:
                self.connection.execute("select 1")
        except psycopg.Error as error:
            return str(error)
        return None

    def claim(self, session_id: str, seat: int, player: str) -> None:
        """Records `player` holding `seat`."""
        with self.lock:
            self.connection.execute(
                "update poker.seat set player = %s where session_id = %s and seat = %s",
                (player, session_id, seat),
            )

    def find(self, code: str) -> str | None:
        """Returns the id of the latest hand of room `code`, or None."""
        with self.lock:
            row = self.connection.execute(
                "select id from poker.session where code = %s order by created_at desc limit 1",
                (code,),
            ).fetchone()
        return None if row is None else row[0]

    def delete(self, session_id: str) -> None:
        """Forgets a session, its seats and its plies."""
        with self.lock:
            self.connection.execute("delete from poker.session where id = %s", (session_id,))
