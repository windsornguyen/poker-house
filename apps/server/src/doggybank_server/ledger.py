"""The chips: a fixed supply held by accounts, and every movement between them.

An account is a player (their auth user id), the treasury, or a room's table.
A transfer debits one account and credits another in the caller's transaction,
and refuses a debit the balance cannot cover, so no balance goes negative and
every balance together always sums to `SUPPLY`.
"""

import enum

import psycopg

from doggybank_server import accounts, db, errors

SUPPLY = 1_000_000
WELCOME_GRANT = 1_000
TREASURY = "treasury"


class Reason(enum.StrEnum):
    """Why chips moved."""

    GRANT = "grant"
    BUY_IN = "buy_in"
    CASH_OUT = "cash_out"
    PURCHASE = "purchase"
    RECLAIM = "reclaim"


def room_account(code: str) -> str:
    """The account holding the chips on room `code`'s table."""
    return f"room:{code}"


def transfer(
    connection: psycopg.Connection, source: str, target: str, amount: int, reason: Reason
) -> None:
    """Moves `amount` chips from `source` to `target`, inside the caller's transaction.

    Raises:
      InsufficientChipsError: If `source` holds fewer than `amount` chips.
    """
    debited = connection.execute(
        "update poker.account set balance = balance - %s where id = %s and balance >= %s",
        (amount, source, amount),
    )
    if debited.rowcount == 0:
        raise errors.InsufficientChipsError(
            f"{holder_name(source)} {balance_of(connection, source)} chips,"
            f" fewer than the {amount} this needs."
        )

    connection.execute(
        "update poker.account set balance = balance + %s where id = %s", (amount, target)
    )
    connection.execute(
        "insert into poker.transfer (from_account, to_account, amount, reason)"
        " values (%s, %s, %s, %s)",
        (source, target, amount, reason),
    )


def holder_name(account: str) -> str:
    """How a refusal names the holder of `account`."""
    return "The house has" if account == TREASURY else "You have"


def balance_of(connection: psycopg.Connection, account: str) -> int:
    """The balance of `account`, 0 for one never opened."""
    row = connection.execute(
        "select balance from poker.account where id = %s", (account,)
    ).fetchone()
    return 0 if row is None else row[0]


def open_account(connection: psycopg.Connection, player: str) -> None:
    """Opens `player`'s account with the welcome grant, once, inside the caller's transaction."""
    opened = connection.execute(
        "insert into poker.account (id, balance) values (%s, 0) on conflict do nothing",
        (player,),
    )
    if opened.rowcount == 1:
        transfer(connection, TREASURY, player, WELCOME_GRANT, Reason.GRANT)


def player_of(connection: psycopg.Connection, email: str) -> str:
    """The id of the account with `email`.

    Raises:
      NotFoundError: If no account has the email.
    """
    row = connection.execute(
        'select id from auth."user" where email = %s', (email.lower(),)
    ).fetchone()
    if row is None:
        raise errors.NotFoundError(f"No account has the email {email!r}.")
    return row[0]


class Ledger:
    """The accounts in the database the sessions are kept in."""

    def __init__(self, database: db.Database) -> None:
        self.database = database

    def balance(self, player: str) -> int:
        """`player`'s balance, opening their account on first use."""
        with self.database.lock, self.database.connection.transaction():
            open_account(self.database.connection, player)
            return balance_of(self.database.connection, player)

    def kind(self, player: str) -> str | None:
        """The kind of `player`'s listing, or None for an account no player owns."""
        with self.database.lock:
            row = self.database.connection.execute(
                'select p.kind from auth."user" u join poker.player p on p.email = u.email'
                " where u.id = %s",
                (player,),
            ).fetchone()
        return None if row is None else row[0]

    def holdings(self) -> accounts.Accounts:
        """Every account, the largest balance first."""
        with self.database.lock:
            rows = self.database.connection.execute(
                "select a.id, u.email, p.kind, a.balance from poker.account a"
                ' left join auth."user" u on u.id = a.id'
                " left join poker.player p on p.email = u.email"
                " order by a.balance desc, a.id"
            ).fetchall()
        return accounts.Accounts(SUPPLY, tuple(accounts.Account(*row) for row in rows))

    def grant(self, email: str, amount: int) -> int:
        """Moves `amount` chips from the treasury to `email`'s account, and returns its balance.

        Raises:
          NotFoundError: If no account has the email.
          InsufficientChipsError: If the treasury holds fewer than `amount` chips.
        """
        with self.database.lock, self.database.connection.transaction():
            connection = self.database.connection
            player = player_of(connection, email)
            open_account(connection, player)
            transfer(connection, TREASURY, player, amount, Reason.GRANT)
            return balance_of(connection, player)

    def set_balance(self, email: str, balance: int) -> None:
        """Sets `email`'s balance to exactly `balance`, by a grant or a reclaim to the treasury.

        Raises:
          NotFoundError: If no account has the email.
          InsufficientChipsError: If the treasury cannot cover the difference.
        """
        with self.database.lock, self.database.connection.transaction():
            connection = self.database.connection
            player = player_of(connection, email)
            open_account(connection, player)
            difference = balance - balance_of(connection, player)
            if difference > 0:
                transfer(connection, TREASURY, player, difference, Reason.GRANT)
            elif difference < 0:
                transfer(connection, player, TREASURY, -difference, Reason.RECLAIM)
