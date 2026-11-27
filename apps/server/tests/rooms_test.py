"""A room played for chips carries every stack from hand to hand, and loses no chip.

Two players buy in, play hands through the HTTP API, and get up again, against
a real Postgres. After each step the balances still sum to the supply, and the
room's account still holds exactly its stacks: chips are only ever moved, never
made, by a hand, a deal, a bust or a cash-out.
"""

from typing import Any

import cluster
import harness
from absl.testing import absltest

from poker_house_server import contract, db, ledger, store

BUY_IN = 40
TABLE: dict[str, contract.JsonValue] = {
    "game": "poker_house",
    "parameters": {"blinds": "1 2", "stack_sizes": f"{BUY_IN} {BUY_IN}"},
    "chance_policy": "auto",
    "seed": 3,
    "seats": [{"controller": "human", "config": {}, "autoplay": False}] * 2,
}


class RoomsTest(absltest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        super().setUpClass()
        cls.cluster = cluster.Cluster()
        cls.server = harness.start(
            store.SessionStore(journal=store.Journal(db.Database(cls.cluster.url)))
        )

    @classmethod
    def tearDownClass(cls) -> None:
        harness.stop(cls.server)
        cls.cluster.stop()
        super().tearDownClass()

    def setUp(self) -> None:
        super().setUp()
        name = self.id().rsplit(".", 1)[-1].replace("_", "-")
        self.host = self.cluster.add_account(f"host-{name}@test.poker.invalid", "test")
        self.guest = self.cluster.add_account(f"guest-{name}@test.poker.invalid", "test")

    def call(
        self,
        player: str | None,
        method: str,
        target: str,
        body: dict[str, contract.JsonValue] | None = None,
    ) -> tuple[int, Any]:
        return harness.call(self.server.url, method, target, body, player)

    def open_room(self) -> tuple[str, str]:
        """The host opens a room and the guest sits; returns its code and first hand."""
        status, frame = self.call(self.host, "POST", "/api/sessions?viewer=0", TABLE)
        self.assertEqual(status, 200, frame)
        code = frame["session"]["code"]

        status, joined = self.call(self.guest, "POST", f"/api/rooms/{code}/join", {})
        self.assertEqual((status, joined["viewer"]), (200, {"kind": "seat", "seat": 1}))
        return code, frame["session"]["id"]

    def move(
        self, player: str, hand: str, seat: int, kind: str, amount: int | None = None
    ) -> dict[str, Any]:
        status, frame = self.call(
            player,
            "POST",
            f"/api/sessions/{hand}/moves?viewer={seat}",
            {"kind": kind, "amount": amount},
        )
        self.assertEqual(status, 200, frame)
        return frame

    def room(self, player: str, code: str) -> dict[str, Any]:
        status, room = self.call(player, "GET", f"/api/rooms/{code}")
        self.assertEqual(status, 200, room)
        return room

    def assert_chips_kept(self, code: str) -> None:
        self.assertEqual(
            self.cluster.query("select sum(balance) from poker.account"), [(ledger.SUPPLY,)]
        )
        held = self.cluster.query("select balance from poker.account where id = %s", f"room:{code}")
        stacks = self.cluster.query(
            "select coalesce(sum(stack), 0) from poker.room_seat where code = %s", code
        )
        self.assertEqual(held, stacks)

    def test_stacks_carry_into_the_next_hand_and_the_blinds_turn(self) -> None:
        code, first = self.open_room()
        self.assertEqual(
            self.call(self.host, "GET", "/api/me")[1]["balance"], ledger.WELCOME_GRANT - BUY_IN
        )

        self.move(self.guest, first, 1, "fold")
        self.assertEqual(self.room(self.host, code)["stacks"], [BUY_IN + 1, BUY_IN - 1])
        self.assert_chips_kept(code)

        status, refused = self.call(
            self.host, "POST", f"/api/rooms/{code}/deal", {"after": "0" * 16}
        )
        self.assertEqual(status, 200, refused)
        status, dealt = self.call(self.host, "POST", f"/api/rooms/{code}/deal", {"after": first})
        self.assertEqual((status, dealt["viewer"]), (200, {"kind": "seat", "seat": 1}))
        second = dealt["session"]["id"]
        self.assertNotEqual(second, first)
        self.assertEqual(
            dealt["session"]["parameters"]["stack_sizes"], f"{BUY_IN - 1} {BUY_IN + 1}"
        )

        status, same = self.call(self.guest, "POST", f"/api/rooms/{code}/deal", {"after": first})
        self.assertEqual((status, same["session"]["id"], same["viewer"]["seat"]), (200, second, 0))

        _, old = self.call(self.host, "GET", f"/api/sessions/{first}?viewer=spectator")
        self.assertEqual(old["session"]["next"], second)
        self.assertEqual(self.room(self.guest, code)["seat"], 0)
        self.assert_chips_kept(code)

    def test_a_hand_for_chips_is_never_rewound_or_rearranged(self) -> None:
        _, hand = self.open_room()
        self.move(self.guest, hand, 1, "call")

        changes: tuple[tuple[str, str, dict[str, contract.JsonValue] | None], ...] = (
            ("POST", "undo", None),
            ("POST", "reset", {"history": None}),
            ("PUT", "seats/0", {"controller": "random", "config": {}, "autoplay": True}),
            ("DELETE", "", None),
        )
        for method, path, body in changes:
            target = f"/api/sessions/{hand}/{path}?viewer=1".replace("/?", "?")
            status, refused = self.call(self.guest, method, target, body)
            self.assertEqual((status, refused["code"]), (403, "forbidden"), path)

    def test_a_player_who_loses_every_chip_can_only_watch(self) -> None:
        code, hand = self.open_room()
        while True:
            frame = self.move(self.guest, hand, 1, "raise", BUY_IN)
            frame = self.move(self.host, hand, 0, "call")
            room = self.room(self.host, code)
            if len(room["stacks"]) == 1:
                break
            _, frame = self.call(self.host, "POST", f"/api/rooms/{code}/deal", {"after": hand})
            hand = frame["session"]["id"]
            self.assertEqual(frame["viewer"]["seat"], 1)
            self.guest, self.host = self.host, self.guest
        self.assert_chips_kept(code)

        winner, loser = (self.host, self.guest) if room["stack"] else (self.guest, self.host)
        self.assertEqual(self.room(winner, code)["stacks"], [2 * BUY_IN])
        self.assertIsNone(self.room(loser, code)["stack"])

        status, refused = self.call(winner, "POST", f"/api/rooms/{code}/deal", {"after": hand})
        self.assertEqual((status, refused["code"]), (409, "table_not_ready"))
        status, watching = self.call(loser, "GET", f"/api/sessions/{hand}?viewer=spectator")
        self.assertEqual(status, 200, watching)

        status, back = self.call(loser, "POST", f"/api/rooms/{code}/join", {})
        self.assertEqual((status, back["viewer"]["kind"]), (200, "spectator"))
        self.assertEqual(sorted(self.room(loser, code)["stacks"]), [BUY_IN, 2 * BUY_IN])
        self.assert_chips_kept(code)

    def test_leaving_cashes_the_stack_out_between_hands(self) -> None:
        code, hand = self.open_room()
        status, refused = self.call(self.host, "POST", f"/api/rooms/{code}/leave", {})
        self.assertEqual((status, refused["code"]), (409, "table_not_ready"))

        self.move(self.guest, hand, 1, "fold")
        status, room = self.call(self.host, "POST", f"/api/rooms/{code}/leave", {})
        self.assertEqual((status, room["stack"], room["stacks"]), (200, None, [BUY_IN - 1]))
        self.assertEqual(
            self.call(self.host, "GET", "/api/me")[1]["balance"], ledger.WELCOME_GRANT + 1
        )
        self.assert_chips_kept(code)

    def test_a_room_left_before_anyone_joins_closes(self) -> None:
        status, frame = self.call(self.host, "POST", "/api/sessions?viewer=0", TABLE)
        self.assertEqual(status, 200, frame)
        code = frame["session"]["code"]

        status, _ = self.call(self.host, "POST", f"/api/rooms/{code}/leave", {})
        self.assertEqual(status, 200)
        self.assertEqual(self.call(self.host, "GET", "/api/me")[1]["balance"], ledger.WELCOME_GRANT)

        status, closed = self.call(self.guest, "POST", f"/api/rooms/{code}/join", {})
        self.assertEqual((status, closed["code"]), (404, "not_found"))
        self.assert_chips_kept(code)

    def test_a_buy_in_beyond_the_balance_keeps_nothing(self) -> None:
        rooms = self.cluster.query("select count(*) from poker.room")
        table: dict[str, contract.JsonValue] = {
            **TABLE,
            "parameters": {"blinds": "1 2", "stack_sizes": "5000 5000"},
        }

        status, refused = self.call(self.host, "POST", "/api/sessions?viewer=0", table)
        self.assertEqual((status, refused["code"]), (402, "insufficient_chips"))
        self.assertEqual(self.cluster.query("select count(*) from poker.room"), rooms)


if __name__ == "__main__":
    absltest.main()
