"""The chips a player holds, and the treasury's view for admins (`ledger`)."""

import pydantic.dataclasses

from doggybank_server import contract


@pydantic.dataclasses.dataclass(frozen=True, config=contract.CONFIG)
class Me:
    """The signed-in player's account.

    Attributes:
      balance: The chips they hold off the tables.
      kind: person, internal or test, from their listing; null for none.
    """

    balance: int
    kind: str | None


@pydantic.dataclasses.dataclass(frozen=True, config=contract.CONFIG)
class Account:
    """One holder of chips.

    Attributes:
      id: The player's id, `treasury`, or `room:<code>` for a table.
      email: The player's email; null for the treasury and tables.
      kind: The player's listing kind; null for the treasury and tables.
      balance: The chips it holds.
    """

    id: str
    email: str | None
    kind: str | None
    balance: int


@pydantic.dataclasses.dataclass(frozen=True, config=contract.CONFIG)
class Accounts:
    """Every holder of chips, the largest balance first.

    Attributes:
      supply: Every chip there is, which the balances always sum to.
      accounts: The holders.
    """

    supply: int
    accounts: tuple[Account, ...]
