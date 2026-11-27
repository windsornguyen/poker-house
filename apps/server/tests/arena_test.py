# Copyright 2026 Poker House contributors
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

"""The HTTP arena runs private bots and preserves poker's public boundaries."""

import http.client
import threading
import urllib.parse
from typing import Any

import cluster
import harness
from absl.testing import absltest

from poker_house_server import (
    builds,
    contract,
    db,
    loader,
    poker_bot,
    remote_bot_server,
    server,
    store,
)


class RecordingBot:
    """Keeps the JSON received at the bot's own HTTP boundary."""

    def __init__(self, strategy: poker_bot.PokerBot) -> None:
        self.strategy = strategy
        self.requests: list[dict[str, contract.JsonValue]] = []

    def move(self, request: dict[str, contract.JsonValue]) -> int:
        """Records the server's observation and returns a strategy's legal move."""
        self.requests.append(request)
        return self.strategy.move(request)


PLAYER_KEY = harness.PLAYER_KEY


class ArenaTest(absltest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        super().setUpClass()
        cls.cluster = cluster.Cluster()
        cls.host = cls.cluster.add_account("host@test.poker.invalid", "test")
        cls.guest = cls.cluster.add_account("guest@test.poker.invalid", "test")
        cls.third = cls.cluster.add_account("third@test.poker.invalid", "test")
        cls.arena = harness.start(
            store.SessionStore(journal=store.Journal(db.Database(cls.cluster.url)))
        )

    @classmethod
    def tearDownClass(cls) -> None:
        harness.stop(cls.arena)
        cls.cluster.stop()
        super().tearDownClass()

    def setUp(self) -> None:
        super().setUp()
        self.addCleanup(builds.set_wait_seconds, builds.wait_seconds())
        builds.set_wait_seconds(10)

    def serve(self, listener: server.Server | remote_bot_server.Server) -> None:
        """Starts an isolated HTTP listener and closes it after the test."""
        thread = threading.Thread(target=listener.serve_forever, daemon=True)
        thread.start()
        self.addCleanup(listener.server_close)
        self.addCleanup(listener.shutdown)

    def request(
        self,
        method: str,
        target: str,
        body: dict[str, contract.JsonValue] | None = None,
        player: str | None = "host",
        key: str = PLAYER_KEY,
    ) -> tuple[int, Any]:
        """Calls the arena as `player`: "host", "guest", "third", or None for no account."""
        account = None if player is None else getattr(self, player)
        return harness.call(self.arena.url, method, target, body, account, key)

    def create(
        self,
        seats: list[contract.JsonValue] | None = None,
        viewer: str = "0",
    ) -> dict[str, Any]:
        """Creates a deterministic, 20-big-blind heads-up hand."""
        if seats is None:
            seats = [
                {"controller": "human", "config": {}, "autoplay": False},
                {"controller": "human", "config": {}, "autoplay": False},
            ]
        status, frame = self.request(
            "POST",
            f"/api/sessions?viewer={viewer}",
            {
                "game": "poker_house",
                "parameters": {"blinds": "1 2", "stack_sizes": "40 40"},
                "chance_policy": "auto",
                "seed": 17,
                "seats": seats,
            },
        )
        self.assertEqual(status, 200, frame)
        assert isinstance(frame, dict)
        return frame

    def test_catalogue_and_loader_offer_only_poker_house_games(self) -> None:
        status, catalogue = self.request("GET", "/api/games")
        self.assertEqual(status, 200)
        self.assertEqual(
            {game["name"] for game in catalogue["games"]},
            {"poker_house", "poker_house_acpc"},
        )
        self.assertTrue(all(game["renderer"] == "poker" for game in catalogue["games"]))
        with self.assertRaises(loader.UnknownGameError):
            loader.load("tic_tac_toe", {})

    def test_two_independent_bot_servers_finish_a_hand_with_private_inputs(
        self,
    ) -> None:
        bots = [
            RecordingBot(poker_bot.make_call_bot()),
            RecordingBot(poker_bot.make_raise_bot()),
        ]
        seats: list[contract.JsonValue] = []
        for bot in bots:
            listener = remote_bot_server.Server(("127.0.0.1", 0), bot, name="test")
            self.serve(listener)
            seats.append(
                {
                    "controller": "remote",
                    "autoplay": True,
                    "config": {"url": listener.url},
                }
            )
        result = self.create(seats, viewer="oracle")
        self.assertEqual(result["status"], "terminal")
        self.assertEqual(sum(result["returns"]), 0)
        self.assertEqual([seat["failure"] for seat in result["seats"]], [None, None])
        for seat, bot in enumerate(bots):
            self.assertTrue(bot.requests)
            for request in bot.requests:
                self.assertEqual(set(request), {"seat", "seed", "observation"})
                self.assertEqual(request["seat"], seat)
                structured = request["observation"]
                assert isinstance(structured, dict)
                self.assertEqual(structured["observing_player"], seat)
                hands = structured["hole_cards"]
                assert isinstance(hands, list)
                self.assertEqual(hands[1 - seat], [None, None])
                own = hands[seat]
                assert isinstance(own, list)
                self.assertTrue(all(isinstance(card, str) for card in own))
                self.assertNotIn("deck", structured)
                self.assertNotIn("burn_cards", structured)

    def join(self, frame: dict[str, Any], player: str = "guest") -> tuple[int, Any]:
        """Joins the room `frame` shows as `player`."""
        return self.request("POST", f"/api/rooms/{frame['session']['code']}/join", player=player)

    def test_seat_and_spectator_views_hide_other_hole_cards(self) -> None:
        frame = self.create()
        session_id = frame["session"]["id"]
        status, joined = self.join(frame)
        self.assertEqual(status, 200)
        holes = [
            frame["presentation"]["view"]["struct"]["player_hands"][0],
            joined["presentation"]["view"]["struct"]["player_hands"][1],
        ]
        self.assertTrue(all(len(hand) == 4 for hand in holes))
        self.assertEqual(frame["presentation"]["view"]["struct"]["player_hands"][1], "")

        for seat, player in ((0, "host"), (1, "guest")):
            status, view = self.request(
                "GET", f"/api/sessions/{session_id}?viewer={seat}", player=player
            )
            self.assertEqual(status, 200)
            self.assertIsNone(view["struct"])
            self.assertIsNone(view["session"]["seed"])
            self.assertEqual(view["observation_struct"]["hole_cards"][1 - seat], [None, None])
            own_hands = view["presentation"]["view"]["struct"]["player_hands"]
            self.assertEqual(own_hands[seat], holes[seat])
            self.assertEqual(own_hands[1 - seat], "")
        _, spectator = self.request("GET", f"/api/sessions/{session_id}?viewer=spectator")
        self.assertIsNone(spectator["observation_struct"])
        self.assertEqual(spectator["presentation"]["view"]["struct"]["player_hands"], ["", ""])

    def test_illegal_actions_and_wrong_turns_leave_the_hand_unchanged(
        self,
    ) -> None:
        frame = self.create()
        session_id = frame["session"]["id"]
        self.assertEqual(self.join(frame)[0], 200)

        for seat, player, action, code in (
            (1, "guest", 10_000, "illegal_action"),
            (0, "host", 1, "not_your_turn"),
        ):
            status, error = self.request(
                "POST",
                f"/api/sessions/{session_id}/actions?viewer={seat}",
                {"action": action, "ply": None},
                player=player,
            )
            self.assertGreaterEqual(status, 400)
            self.assertEqual(error["code"], code)

            _, after = self.request("GET", f"/api/sessions/{session_id}?viewer=spectator")
            self.assertEqual(len(after["history"]), len(frame["history"]))

    def test_a_guest_joins_by_code_and_holds_only_their_seat(self) -> None:
        frame = self.create()
        session_id = frame["session"]["id"]

        status, joined = self.join(frame)
        self.assertEqual(status, 200, joined)
        self.assertEqual(joined["viewer"], {"kind": "seat", "seat": 1})
        self.assertEqual([seat["taken"] for seat in joined["seats"]], [True, True])
        self.assertEqual(self.join(frame)[1]["viewer"], joined["viewer"])

        status, full = self.join(frame, player="third")
        self.assertEqual((status, full["code"]), (409, "room_full"))

        for target, player, key, code in (
            (f"/api/sessions/{session_id}?viewer=oracle", "host", PLAYER_KEY, "viewer_unavailable"),
            (f"/api/sessions/{session_id}?viewer=0", "guest", PLAYER_KEY, "viewer_unavailable"),
            (f"/api/sessions/{session_id}?viewer=0", None, PLAYER_KEY, "unauthorized"),
            (f"/api/sessions/{session_id}?viewer=0", "host", "wrong-key", "unauthorized"),
        ):
            status, error = self.request("GET", target, player=player, key=key)
            self.assertEqual(error["code"], code, target)
            self.assertGreaterEqual(status, 400)

    def test_the_probes_answer_without_a_player(self) -> None:
        for path, body in ((server.LIVE_PATH, b"live"), (server.READY_PATH, b"ready")):
            address = urllib.parse.urlsplit(self.arena.url)
            assert address.hostname is not None
            connection = http.client.HTTPConnection(address.hostname, address.port, timeout=15)
            connection.request("GET", path)
            response = connection.getresponse()
            self.assertEqual((response.status, response.read()), (200, body), path)
            connection.close()

    def test_a_move_by_meaning_resolves_or_lists_the_legal_moves(self) -> None:
        frame = self.create()
        session_id = frame["session"]["id"]
        self.assertEqual(self.join(frame)[0], 200)
        target = f"/api/sessions/{session_id}/moves?viewer=1"

        status, refused = self.request("POST", target, {"kind": "raise"}, player="guest")
        self.assertEqual((status, refused["code"]), (409, "illegal_action"))
        self.assertIn("Name the amount", refused["message"])

        status, refused = self.request("POST", target, {"kind": "check"}, player="guest")
        self.assertEqual((status, refused["code"]), (409, "illegal_action"))
        self.assertIn("Legal moves: fold, call", refused["message"])

        status, called = self.request("POST", target, {"kind": "call"}, player="guest")
        self.assertEqual(status, 200, called)
        self.assertEqual(len(called["history"]), len(frame["history"]) + 1)

    def test_an_unknown_code_finds_no_room(self) -> None:
        status, error = self.request("POST", "/api/rooms/ZZZZZZ/join", player="guest")
        self.assertEqual((status, error["code"]), (404, "not_found"))

    def test_no_one_sees_the_cards_of_a_seat_another_player_will_take(self) -> None:
        status, refused = self.request(
            "POST",
            "/api/sessions?viewer=oracle",
            {
                "game": "poker_house",
                "parameters": {"blinds": "1 2", "stack_sizes": "40 40"},
                "chance_policy": "auto",
                "seed": None,
                "seats": [{"controller": "human", "config": {}, "autoplay": False}] * 2,
            },
        )
        self.assertEqual((status, refused["code"]), (409, "viewer_unavailable"))

        frame = self.create()
        session_id = frame["session"]["id"]
        status, refused = self.request("GET", f"/api/sessions/{session_id}?viewer=oracle")
        self.assertEqual((status, refused["code"]), (409, "viewer_unavailable"))


if __name__ == "__main__":
    absltest.main()
