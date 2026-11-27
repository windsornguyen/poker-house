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
import json
import threading
import urllib.parse
from typing import Any

from absl.testing import absltest

from poker_house_server import (
    api,
    builds,
    contract,
    health_report,
    loader,
    poker_bot,
    remote_bot_server,
    server,
    static,
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


PLAYER_KEY = "test-player-key"
HOST = "host-account"
GUEST = "guest-account"


class ArenaTest(absltest.TestCase):
    def setUp(self) -> None:
        super().setUp()
        self.addCleanup(builds.set_wait_seconds, builds.wait_seconds())
        builds.set_wait_seconds(10)
        self.arena = server.Server(
            ("127.0.0.1", 0),
            api.Api(
                store.SessionStore(),
                catalogue=loader.build_catalogue,
                health=health_report.build,
                player_key=PLAYER_KEY,
            ),
            static.ClientFiles(static.DEFAULT_ROOT),
            server.LOOPBACK_HOSTS,
        )
        self.serve(self.arena)

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
        player: str | None = HOST,
        key: str = PLAYER_KEY,
    ) -> tuple[int, Any]:
        """Decodes an HTTP response, at the untyped JSON test boundary.

        `player` is the account the Worker would name, signed with `key`. None
        sends no account.
        """
        address = urllib.parse.urlsplit(self.arena.url)
        assert address.hostname is not None
        connection = http.client.HTTPConnection(address.hostname, address.port, timeout=15)

        encoded = None if body is None else json.dumps(body)
        headers = {"Content-Type": "application/json"}
        if player is not None:
            headers[api.PLAYER_HEADER] = api.signed_player(player, key)
        connection.request(method, target, encoded, headers)
        response = connection.getresponse()
        decoded = json.loads(response.read())
        connection.close()
        return response.status, decoded

    def create(
        self,
        seats: list[contract.JsonValue] | None = None,
    ) -> dict[str, Any]:
        """Creates a deterministic, 20-big-blind heads-up hand."""
        if seats is None:
            seats = [
                {"controller": "human", "config": {}, "autoplay": False},
                {"controller": "human", "config": {}, "autoplay": False},
            ]
        status, frame = self.request(
            "POST",
            "/api/sessions?viewer=oracle",
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
        result = self.create(seats)
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

    def join(self, frame: dict[str, Any], player: str = GUEST) -> tuple[int, Any]:
        """Joins the room `frame` shows as `player`."""
        return self.request("POST", f"/api/rooms/{frame['session']['code']}/join", player=player)

    def test_seat_and_spectator_views_hide_other_hole_cards(self) -> None:
        frame = self.create()
        session_id = frame["session"]["id"]
        holes = frame["presentation"]["view"]["struct"]["player_hands"]
        self.assertTrue(all(len(hand) == 4 for hand in holes))
        self.assertEqual(self.join(frame)[0], 200)

        for seat, player in ((0, HOST), (1, GUEST)):
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
            (1, GUEST, 10_000, "illegal_action"),
            (0, HOST, 1, "not_your_turn"),
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

        status, full = self.join(frame, player="third-account")
        self.assertEqual((status, full["code"]), (409, "room_full"))

        for target, player, key, code in (
            (f"/api/sessions/{session_id}?viewer=oracle", HOST, PLAYER_KEY, "viewer_unavailable"),
            (f"/api/sessions/{session_id}?viewer=0", GUEST, PLAYER_KEY, "viewer_unavailable"),
            (f"/api/sessions/{session_id}?viewer=0", None, PLAYER_KEY, "unauthorized"),
            (f"/api/sessions/{session_id}?viewer=0", HOST, "wrong-key", "unauthorized"),
        ):
            status, error = self.request("GET", target, player=player, key=key)
            self.assertEqual(error["code"], code, target)
            self.assertGreaterEqual(status, 400)

    def test_an_unknown_code_finds_no_room(self) -> None:
        status, error = self.request("POST", "/api/rooms/ZZZZZZ/join", player=GUEST)
        self.assertEqual((status, error["code"]), (404, "not_found"))

    def test_the_hosts_every_card_stream_ends_when_a_guest_sits(self) -> None:
        frame = self.create()
        address = urllib.parse.urlsplit(self.arena.url)
        assert address.hostname is not None
        connection = http.client.HTTPConnection(address.hostname, address.port, timeout=15)
        connection.request(
            "GET",
            f"/api/sessions/{frame['session']['id']}/events?viewer=oracle",
            headers={api.PLAYER_HEADER: api.signed_player(HOST, PLAYER_KEY)},
        )
        stream = connection.getresponse()
        self.assertTrue(stream.readline().startswith(b"data: "))

        self.assertEqual(self.join(frame)[0], 200)

        lines = [stream.readline() for _ in range(2)]
        connection.close()
        self.assertIn(b"event: refused\n", lines)


if __name__ == "__main__":
    absltest.main()
