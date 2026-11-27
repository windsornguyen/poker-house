"""Rooms in Postgres: who sits at each, with what stack, and the chips behind them.

A room with a buy-in plays for chips. Sitting moves the buy-in from the
player's account to the room's, leaving moves the stack back, and a hand's
end moves chips between stacks inside the room (`db.Database.record`). So
the room's account always holds exactly the sum of its stacks.
"""

import dataclasses

import pydantic.dataclasses

from doggybank_server import accounts, contract, db, errors, ledger


@dataclasses.dataclass(frozen=True)
class Seated:
    """A player at a room's table, and the chips in front of them."""

    player: str
    stack: int


@dataclasses.dataclass(frozen=True)
class Room:
    """A room as stored.

    Attributes:
      code: The code players join it with.
      buy_in: The chips a seat costs; None for a room played for nothing.
      seated: The players at the table, in the order they sat.
      hands: The ids of its hands, the latest last.
    """

    code: str
    buy_in: int | None
    seated: tuple[Seated, ...]
    hands: tuple[str, ...]

    @property
    def latest(self) -> str | None:
        """The id of the latest hand, or None before the first."""
        return self.hands[-1] if self.hands else None

    def stack(self, player: str) -> int | None:
        """`player`'s stack here, or None when they do not sit here."""
        return next((seat.stack for seat in self.seated if seat.player == player), None)


@pydantic.dataclasses.dataclass(frozen=True, config=contract.CONFIG)
class RoomView:
    """A room, as the player asking sees it.

    Attributes:
      code: The code players join it with.
      buy_in: The chips a seat costs; null for a room played for nothing.
      session_id: The id of its latest hand; null once it has closed.
      seat: The seat the player holds in the latest hand; null when they sit it out.
      stack: The player's chips at the table; null when they do not sit there.
      stacks: Every stack at the table, in the order the players sat.
    """

    code: str
    buy_in: int | None
    session_id: str | None
    seat: int | None
    stack: int | None
    stacks: tuple[int, ...]


class Rooms:
    """The rooms in the database the sessions are kept in."""

    def __init__(self, database: db.Database) -> None:
        self.database = database

    def open(self, code: str, buy_in: int | None, founder: str, seats: int) -> None:
        """Records a new room. With a buy-in, also its table's account and `founder`'s seat.

        Raises:
          InsufficientChipsError: If the founder cannot cover the buy-in.
        """
        with self.database.lock, self.database.connection.transaction():
            connection = self.database.connection
            connection.execute(
                "insert into poker.room (code, buy_in) values (%s, %s)", (code, buy_in)
            )
            if buy_in is not None:
                connection.execute(
                    "insert into poker.account (id, balance) values (%s, 0)",
                    (ledger.room_account(code),),
                )
                self.buy_in(code, founder, buy_in, seats)

    def find(self, code: str) -> Room:
        """The room with code `code`.

        Raises:
          NotFoundError: If no room has the code.
        """
        with self.database.lock:
            connection = self.database.connection
            row = connection.execute(
                "select buy_in from poker.room where code = %s", (code,)
            ).fetchone()
            if row is None:
                raise errors.NotFoundError(f"There is no room {code!r}.")

            seated = connection.execute(
                "select player, stack from poker.room_seat where code = %s order by joined_at",
                (code,),
            ).fetchall()
            hands = connection.execute(
                "select id from poker.session where code = %s order by created_at", (code,)
            ).fetchall()
        return Room(
            code, row[0], tuple(Seated(*seat) for seat in seated), tuple(h for (h,) in hands)
        )

    def seats(self, player: str) -> tuple[accounts.TableSeat, ...]:
        """Every table `player` sits at, and their stack there, the earliest first."""
        with self.database.lock:
            rows = self.database.connection.execute(
                "select code, stack from poker.room_seat where player = %s order by joined_at",
                (player,),
            ).fetchall()
        return tuple(accounts.TableSeat(code, stack) for code, stack in rows)

    def sit(self, code: str, player: str, seats: int) -> None:
        """Buys `player` a seat at room `code`, unless they already have one.

        Raises:
          RoomFullError: If the room's `seats` are all taken.
          InsufficientChipsError: If the player cannot cover the buy-in.
        """
        with self.database.lock, self.database.connection.transaction():
            room = self.database.connection.execute(
                "select buy_in from poker.room where code = %s for update", (code,)
            ).fetchone()
            assert room is not None and room[0] is not None
            self.buy_in(code, player, room[0], seats)

    def buy_in(self, code: str, player: str, amount: int, seats: int) -> None:
        """Seats `player` for `amount` chips, inside the caller's transaction, unless seated."""
        connection = self.database.connection
        players = [
            seated
            for (seated,) in connection.execute(
                "select player from poker.room_seat where code = %s", (code,)
            ).fetchall()
        ]
        if player in players:
            return
        if len(players) >= seats:
            raise errors.RoomFullError("Every seat at this table is taken.")

        ledger.open_account(connection, player)
        ledger.transfer(connection, player, ledger.room_account(code), amount, ledger.Reason.BUY_IN)
        connection.execute(
            "insert into poker.room_seat (code, player, stack) values (%s, %s, %s)",
            (code, player, amount),
        )

    def leave(self, code: str, player: str) -> None:
        """Moves `player`'s stack at room `code` back to their account, and frees the seat.

        Raises:
          NotFoundError: If the player does not sit at the room.
        """
        with self.database.lock, self.database.connection.transaction():
            connection = self.database.connection
            row = connection.execute(
                "delete from poker.room_seat where code = %s and player = %s returning stack",
                (code, player),
            ).fetchone()
            if row is None:
                raise errors.NotFoundError("You do not sit at this table.")

            if row[0] > 0:
                ledger.transfer(
                    connection, ledger.room_account(code), player, row[0], ledger.Reason.CASH_OUT
                )
