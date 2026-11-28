"""Two servers sharing one Postgres linearize every move, rewind and deal on one table."""

import threading
from concurrent import futures
from typing import Any

import cluster
import harness
from absl.testing import absltest

from doggybank_server import contract, db, errors, ledger, loader, plies, store

BUY_IN = 40
HANDS = 6
RACE_COPIES = 4
HUMAN: dict[str, contract.JsonValue] = {"controller": "human", "config": {}, "autoplay": False}
TABLE: dict[str, contract.JsonValue] = {
    "game": "doggybank",
    "parameters": {"blinds": "1 2", "stack_sizes": f"{BUY_IN} {BUY_IN}"},
    "chance_policy": "auto",
    "seed": 11,
    "seats": [HUMAN, HUMAN],
}
UNSTAKED: dict[str, contract.JsonValue] = {
    "game": "doggybank",
    "parameters": {"blinds": "1 2", "stack_sizes": f"{BUY_IN} {BUY_IN}"},
    "chance_policy": "auto",
    "seed": 19,
    "seats": [HUMAN, {"controller": "random", "config": {}, "autoplay": True}],
}
REFUSALS = frozenset(
    {
        errors.ErrorCode.NOT_YOUR_TURN,
        errors.ErrorCode.ILLEGAL_ACTION,
        errors.ErrorCode.TABLE_NOT_READY,
    }
)


class StoresTest(absltest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        super().setUpClass()
        cls.cluster = cluster.Cluster()
        cls.databases = (db.Database(cls.cluster.url), db.Database(cls.cluster.url))
        cls.stores = (
            store.SessionStore(journal=store.Journal(cls.databases[0])),
            store.SessionStore(journal=store.Journal(cls.databases[1])),
        )
        cls.servers = (harness.start(cls.stores[0]), harness.start(cls.stores[1]))

    @classmethod
    def tearDownClass(cls) -> None:
        for listener in cls.servers:
            harness.stop(listener)
        for database in cls.databases:
            database.connection.close()
        cls.cluster.stop()
        super().tearDownClass()

    def setUp(self) -> None:
        super().setUp()
        name = self.id().rsplit(".", 1)[-1].replace("_", "-")
        self.host = self.cluster.add_account(f"host-{name}@test.poker.invalid", "test")
        self.guest = self.cluster.add_account(f"guest-{name}@test.poker.invalid", "test")

    def call(
        self,
        which: int,
        player: str,
        method: str,
        target: str,
        body: dict[str, contract.JsonValue] | None = None,
    ) -> tuple[int, Any]:
        return harness.call(self.servers[which].url, method, target, body, player)

    def assert_legal_history(self, hand: str, parameters: dict[str, Any]) -> list[int]:
        stored = self.cluster.query(
            "select ply, action from poker.ply where session_id = %s order by ply", hand
        )
        self.assertEqual([ply for ply, _ in stored], list(range(len(stored))))
        actions = [int(action) for _, action in stored if isinstance(action, int)]
        state, _ = plies.rebuild(loader.load("doggybank", parameters).game, actions)
        self.assertTrue(state.is_terminal())
        return actions

    def assert_chips_kept(self, code: str) -> None:
        self.assertEqual(
            self.cluster.query("select sum(balance) from poker.account"), [(ledger.SUPPLY,)]
        )
        held = self.cluster.query("select balance from poker.account where id = %s", f"room:{code}")
        stacks = self.cluster.query(
            "select coalesce(sum(stack), 0) from poker.room_seat where code = %s", code
        )
        self.assertEqual(held, stacks)

    def race_actions_at_ply(
        self, hand: str, ply: int, seat: int, actor: str, other: str, action: int
    ) -> list[tuple[int, Any]]:
        """Races the same ply across both servers, plus out-of-turn attempts."""
        barrier = threading.Barrier(RACE_COPIES)

        def attempt(attempt_index: int) -> tuple[int, Any]:
            which = attempt_index % 2
            who = actor if attempt_index < 2 else other
            viewer = seat if attempt_index < 2 else 1 - seat
            barrier.wait()
            return self.call(
                which,
                who,
                "POST",
                f"/api/sessions/{hand}/actions?viewer={viewer}",
                {"action": action, "ply": ply},
            )

        with futures.ThreadPoolExecutor(max_workers=RACE_COPIES) as pool:
            pending = [pool.submit(attempt, i) for i in range(RACE_COPIES)]
            return [future.result() for future in pending]

    def race_moves(
        self, hand: str, seat: int, actor: str, other: str, chosen: str
    ) -> list[tuple[int, tuple[int, Any]]]:
        """Races unindexed moves across both servers, returning `(seat_tried, response)`."""
        barrier = threading.Barrier(RACE_COPIES)

        def attempt(attempt_index: int) -> tuple[int, tuple[int, Any]]:
            which = attempt_index % 2
            who = actor if attempt_index < 2 else other
            viewer = seat if attempt_index < 2 else 1 - seat
            barrier.wait()
            response = self.call(
                which,
                who,
                "POST",
                f"/api/sessions/{hand}/moves?viewer={viewer}",
                {"kind": chosen, "amount": None},
            )
            return viewer, response

        with futures.ThreadPoolExecutor(max_workers=RACE_COPIES) as pool:
            pending = [pool.submit(attempt, i) for i in range(RACE_COPIES)]
            return [future.result() for future in pending]

    def race_deal(
        self, code: str, previous: str, players: list[str]
    ) -> tuple[tuple[int, Any], tuple[int, Any]]:
        """Races `deal` for the same finished hand across both servers."""
        barrier = threading.Barrier(2)

        def deal(which: int, who: str) -> tuple[int, Any]:
            barrier.wait()
            return self.call(which, who, "POST", f"/api/rooms/{code}/deal", {"after": previous})

        with futures.ThreadPoolExecutor(max_workers=2) as pool:
            first = pool.submit(deal, 0, players[0])
            second = pool.submit(deal, 1, players[1])
            return first.result(), second.result()

    def test_two_servers_race_moves_and_deals_on_one_table_without_losing_a_ply(self) -> None:
        status, created = self.call(0, self.host, "POST", "/api/sessions?viewer=0", TABLE)
        self.assertEqual(status, 200, created)
        code = created["session"]["code"]
        hand = created["session"]["id"]

        status, joined = self.call(1, self.guest, "POST", f"/api/rooms/{code}/join", {})
        self.assertEqual((status, joined["viewer"]["seat"]), (200, 1))

        players = [self.host, self.guest]
        step = 0
        for index in range(HANDS):
            while True:
                _, turn_zero = self.call(
                    index % 2, players[0], "GET", f"/api/sessions/{hand}/turn?viewer=0"
                )
                _, turn_one = self.call(
                    (index + 1) % 2, players[1], "GET", f"/api/sessions/{hand}/turn?viewer=1"
                )
                if turn_zero["finished"]:
                    self.assertTrue(turn_one["finished"])
                    break

                seat = 0 if turn_zero["to_move"] else 1
                turn = turn_zero if seat == 0 else turn_one
                before = self.cluster.query(
                    "select action from poker.ply where session_id = %s order by ply", hand
                )

                if step % 2 == 0:
                    _, view = self.call(
                        0, players[seat], "GET", f"/api/sessions/{hand}?viewer={seat}"
                    )
                    action = view["observation_struct"]["legal_actions"][0]
                    results = self.race_actions_at_ply(
                        hand, len(before), seat, players[seat], players[1 - seat], action
                    )
                    accepted = [body for status, body in results if status == 200]
                    refused = [(status, body) for status, body in results if status != 200]
                    self.assertEqual(len(accepted), 1, results)
                    for status, body in refused:
                        self.assertLess(status, 500, body)
                        self.assertIn(body["code"], REFUSALS, body)
                    expected_seats = [seat]
                else:
                    kinds = [move["kind"] for move in turn["moves"]]
                    chosen = (
                        "call" if "call" in kinds else ("check" if "check" in kinds else "fold")
                    )
                    move_results = self.race_moves(
                        hand, seat, players[seat], players[1 - seat], chosen
                    )
                    accepted_seats = [tried for tried, (status, _) in move_results if status == 200]
                    self.assertGreaterEqual(len(accepted_seats), 1, move_results)
                    for _, (status, body) in move_results:
                        if status != 200:
                            self.assertLess(status, 500, body)
                            self.assertIn(body["code"], REFUSALS, body)
                    expected_seats = accepted_seats

                step += 1
                after = self.cluster.query(
                    "select seat, action from poker.ply where session_id = %s order by ply", hand
                )
                self.assertEqual([a for _, a in after[: len(before)]], [a for (a,) in before])
                human_added = [s for s, _ in after[len(before) :] if isinstance(s, int)]
                self.assertEqual(sorted(human_added), sorted(expected_seats))

            _, frame_a = self.call(0, players[0], "GET", f"/api/sessions/{hand}?viewer=spectator")
            _, frame_b = self.call(1, players[0], "GET", f"/api/sessions/{hand}?viewer=spectator")
            self.assertEqual(frame_a["history"], frame_b["history"])
            self.assert_legal_history(hand, frame_a["session"]["parameters"])
            self.assert_chips_kept(code)

            room = self.call(0, players[0], "GET", f"/api/rooms/{code}")[1]
            if len(room["stacks"]) < 2 or index + 1 == HANDS:
                break

            dealt_a, dealt_b = self.race_deal(code, hand, players)
            self.assertEqual((dealt_a[0], dealt_b[0]), (200, 200))
            self.assertEqual(dealt_a[1]["session"]["id"], dealt_b[1]["session"]["id"])
            hand = dealt_a[1]["session"]["id"]
            players.reverse()

        for player in players:
            if self.call(0, player, "GET", f"/api/rooms/{code}")[1]["stack"] is not None:
                status, _ = self.call(1, player, "POST", f"/api/rooms/{code}/leave", {})
                self.assertEqual(status, 200)
        self.assert_chips_kept(code)

    def test_unstaked_undo_and_reset_stay_consistent_across_two_servers(self) -> None:
        status, created = self.call(0, self.host, "POST", "/api/sessions?viewer=0", UNSTAKED)
        self.assertEqual(status, 200, created)
        hand = created["session"]["id"]

        status, moved = self.call(
            1, self.host, "POST", f"/api/sessions/{hand}/moves?viewer=0", {"kind": "call"}
        )
        self.assertEqual(status, 200, moved)
        self.assertGreater(len(moved["history"]), len(created["history"]))

        status, undone = self.call(0, self.host, "POST", f"/api/sessions/{hand}/undo?viewer=0", {})
        self.assertEqual(status, 200, undone)

        status, reset = self.call(
            1, self.host, "POST", f"/api/sessions/{hand}/reset?viewer=0", {"history": None}
        )
        self.assertEqual(status, 200, reset)

        _, on_zero = self.call(0, self.host, "GET", f"/api/sessions/{hand}?viewer=0")
        self.assertEqual(on_zero["history"], reset["history"])


if __name__ == "__main__":
    absltest.main()
