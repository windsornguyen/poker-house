"""Chips come only from the treasury's fixed supply, and only admins hand them out.

The scenario runs against a real Postgres with the production schema, through
the HTTP API the Worker calls, and checks after every step that the balances
still sum to the supply: the one invariant every other rule of the ledger
exists to keep.
"""

from typing import Any

import cluster
import harness
from absl.testing import absltest

from doggybank_server import contract, db, ledger, store


class LedgerTest(absltest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        super().setUpClass()
        cls.cluster = cluster.Cluster()
        cls.admin = cls.cluster.add_account("admin@test.poker.invalid", "internal")
        cls.person = cls.cluster.add_account("person@test.poker.invalid", "person")
        cls.newcomer = cls.cluster.add_account("newcomer@test.poker.invalid", "person")
        cls.server = harness.start(
            store.SessionStore(journal=store.Journal(db.Database(cls.cluster.url)))
        )

    @classmethod
    def tearDownClass(cls) -> None:
        harness.stop(cls.server)
        cls.cluster.stop()
        super().tearDownClass()

    def call(
        self,
        method: str,
        target: str,
        body: dict[str, contract.JsonValue] | None = None,
        player: str | None = None,
    ) -> tuple[int, Any]:
        return harness.call(self.server.url, method, target, body, player)

    def assert_supply_kept(self) -> None:
        self.assertEqual(
            self.cluster.query("select sum(balance) from poker.account"), [(ledger.SUPPLY,)]
        )

    def test_a_first_request_grants_the_welcome_chips_once(self) -> None:
        for _ in range(2):
            status, me = self.call("GET", "/api/me", player=self.newcomer)
            self.assertEqual(
                (status, me),
                (200, {"balance": ledger.WELCOME_GRANT, "kind": "person", "seats": []}),
            )
        self.assert_supply_kept()

    def test_an_admin_grants_from_the_treasury(self) -> None:
        status, listing = self.call(
            "POST",
            "/api/admin/grants",
            {"email": "person@test.poker.invalid", "amount": 50},
            self.admin,
        )
        self.assertEqual(status, 200, listing)

        balances = {account["id"]: account["balance"] for account in listing["accounts"]}
        self.assertEqual(balances[self.person], ledger.WELCOME_GRANT + 50)
        self.assertEqual(sum(balances.values()), listing["supply"])
        self.assert_supply_kept()

    def test_a_grant_beyond_the_treasury_is_refused(self) -> None:
        status, refused = self.call(
            "POST",
            "/api/admin/grants",
            {"email": "person@test.poker.invalid", "amount": ledger.SUPPLY},
            self.admin,
        )
        self.assertEqual((status, refused["code"]), (402, "insufficient_chips"))
        self.assertIn("The house has", refused["message"])
        self.assert_supply_kept()

    def test_only_an_internal_account_manages_chips(self) -> None:
        grant: dict[str, contract.JsonValue] = {"email": "person@test.poker.invalid", "amount": 1}
        requests: tuple[tuple[str, str, dict[str, contract.JsonValue] | None], ...] = (
            ("GET", "/api/admin/accounts", None),
            ("POST", "/api/admin/grants", grant),
        )
        for method, target, body in requests:
            status, refused = self.call(method, target, body, self.person)
            self.assertEqual((status, refused["code"]), (403, "forbidden"))

        status, refused = self.call("GET", "/api/admin/accounts")
        self.assertEqual((status, refused["code"]), (401, "unauthorized"))


if __name__ == "__main__":
    absltest.main()
