"""No one at a table played for chips can rig, rewind, take over or see into a hand.

Hand-written cases only cover the cheats someone thought of. Here Hypothesis
plays every route of the API as the host, the guest, an outsider and no one,
with any viewer and any body: moves, raw actions at any ply, chance outcomes,
advances, undos, resets with chosen cards, seat changes, closes, joins, deals,
leaves, new rooms and every read. After each request it checks what a fair
game means:

1. A hand never rewinds: its stored plies only grow.
2. Only a seat's holder plays it: every new player ply comes from the seat the
   requesting player holds.
3. No one sees into a seat they do not hold while the hand is played: not its
   cards, not the full state, not the seed.
4. No chip is made or lost: the balances sum to the supply, and every room's
   account holds exactly its stacks.
5. Every refusal is a typed answer, never a fault.

The requests run in process, through the app's own transport, against the
production schema in a real Postgres, so each example costs milliseconds and a
run explores thousands of requests.
"""

import atexit
import contextlib
import json
import os
import unittest.mock
from typing import Any, LiteralString

import cluster
import harness
import httpx2
import hypothesis
import psycopg
from absl.testing import absltest
from fastapi import testclient
from hypothesis import stateful
from hypothesis import strategies as st

from doggybank_server import (
    api,
    app,
    contract,
    db,
    errors,
    health_report,
    ledger,
    loader,
    store,
    timeouts,
)

PLAYERS = ("host", "guest", "outsider", None)
VIEWERS = ("0", "1", "oracle", "spectator")
STACK = 40
TOP_UP = 100_000
HUMAN: dict[str, contract.JsonValue] = {"controller": "human", "config": {}, "autoplay": False}
TABLE: dict[str, contract.JsonValue] = {
    "game": "doggybank",
    "parameters": {"blinds": "1 2", "stack_sizes": f"{STACK} {STACK}"},
    "chance_policy": "auto",
    "seed": None,
    "seats": [HUMAN, HUMAN],
}
# Card ids, ply indexes and amounts drawn well past what a heads-up hand uses,
# so illegal values are tried as often as legal ones.
SMALL = st.integers(min_value=-2, max_value=80)
MAYBE_PLY = st.one_of(st.none(), st.integers(min_value=-1, max_value=30))

hypothesis.settings.register_profile(
    "check", max_examples=100, stateful_step_count=40, derandomize=True, deadline=None
)
hypothesis.settings.register_profile(
    "soak", max_examples=2_000, stateful_step_count=80, deadline=None
)
hypothesis.settings.load_profile(os.environ.get("DOGGYBANK_HYPOTHESIS", "check"))

POSTGRES: cluster.Cluster
CLIENTS: tuple[testclient.TestClient, testclient.TestClient]
READS: psycopg.Connection
DATABASE: db.Database
ACCOUNTS: dict[str, str] = {}


def start() -> None:
    """Starts the cluster, its accounts and two API stores, once, for every example after."""
    global POSTGRES, CLIENTS, READS, DATABASE
    if ACCOUNTS:
        return

    # A clock that acts for an idle player would add plies no request made.
    unittest.mock.patch.object(timeouts, "TURN_SECONDS", 24 * 60 * 60.0).start()
    POSTGRES = cluster.Cluster()
    for name in PLAYERS:
        if name is not None:
            ACCOUNTS[name] = POSTGRES.add_account(f"{name}@test.poker.invalid", "test")

    READS = psycopg.connect(POSTGRES.url, autocommit=True)
    DATABASE = db.Database(POSTGRES.url)
    atexit.register(POSTGRES.stop)
    # One pair of clients for every example, so each request reuses its event loop.
    clients = contextlib.ExitStack()
    built = []
    for _ in range(2):
        served = app.create_app(
            store.SessionStore(journal=store.Journal(db.Database(POSTGRES.url))),
            catalogue=loader.build_catalogue,
            health=health_report.build,
            player_key=harness.PLAYER_KEY,
            client=app.CLIENT_ROOT,
            allowed_hosts=app.LOOPBACK_HOSTS,
        )
        built.append(
            clients.enter_context(testclient.TestClient(served, base_url="http://localhost"))
        )
    CLIENTS = (built[0], built[1])
    atexit.register(clients.close)


def reset() -> None:
    """Empties the tables and ledger, so every example starts from the same chips.

    An example leaves chips in its rooms. Carried into the next one, they make a
    failing example play differently when Hypothesis replays it alone.
    """
    with READS.transaction():
        READS.execute(
            "truncate poker.ply, poker.seat, poker.session, poker.room_seat, poker.room,"
            " poker.transfer, poker.account cascade"
        )
        READS.execute(
            "insert into poker.account (id, balance) values (%s, %s)",
            (ledger.TREASURY, ledger.SUPPLY),
        )
    for name in ACCOUNTS:
        ledger.Ledger(DATABASE).grant(f"{name}@test.poker.invalid", TOP_UP)


def rows(sql: LiteralString, *params: object) -> list[tuple[Any, ...]]:
    """The rows of one read of the cluster."""
    return READS.execute(sql, params).fetchall()


def body(response: httpx2.Response) -> dict[str, Any]:
    """An answer's JSON object, at the untyped test boundary."""
    decoded = response.json()
    assert isinstance(decoded, dict), decoded
    return decoded


def headers(who: str | None) -> dict[str, str]:
    """The headers of a JSON request the Worker sends as `who`."""
    sent = {"Content-Type": "application/json"}
    if who is not None:
        sent[api.PLAYER_HEADER] = api.signed_player(ACCOUNTS[who], harness.PLAYER_KEY)
    return sent


class Cheaters(stateful.RuleBasedStateMachine):
    """Players at one room, each trying anything the API accepts."""

    def __init__(self) -> None:
        super().__init__()
        start()
        reset()
        self.codes: list[str] = []
        self.seen: dict[str, list[tuple[int | None, int]]] = {}
        # The stack each player should hold at each room: their buy-in, plus
        # the returns of every hand that has finished since they sat.
        self.stacks: dict[str, dict[str, int]] = {}
        self.settled: set[str] = set()
        self.which = 0
        self.alternating = False
        frame = body(self.call("host", "POST", "/api/sessions?viewer=0", TABLE))
        self.codes.append(frame["session"]["code"])
        self.call("guest", "POST", f"/api/rooms/{self.codes[0]}/join", {})

    def hands(self) -> list[str]:
        """Every hand of every room opened in this run, oldest first."""
        return [
            hand
            for code in self.codes
            for (hand,) in rows(
                "select id from poker.session where code = %s order by created_at", code
            )
        ]

    def call(
        self,
        who: str | None,
        method: str,
        target: str,
        body: dict[str, contract.JsonValue] | None = None,
    ) -> httpx2.Response:
        """Sends one request as `who`, and checks invariants 1, 2, 3 and 5 on its answer."""
        encoded = b"" if body is None else json.dumps(body).encode()
        client = CLIENTS[self.which]
        if self.alternating:
            self.which = 1 - self.which
        response = client.request(method, target, content=encoded, headers=headers(who))

        answer = response.json()
        assert response.status_code < 500, (target, answer)
        assert isinstance(answer, dict), (target, answer)
        if response.status_code == 200:
            self.check_sight(who, answer)
        self.check_plies(who)
        self.check_stacks()
        return response

    def check_sight(self, who: str | None, body: dict[str, Any]) -> None:
        """Invariant 3: an answer shows nothing of a seat `who` does not hold mid-hand."""
        if "hole" in body and not body["finished"]:
            hand = self.hand_of_turn(body)
            assert self.holders(hand)[body["seat"]] == ACCOUNTS.get(who or ""), body

        if "session" not in body or body["status"] == "terminal":
            return

        holders = self.holders(body["session"]["id"])
        mine = ACCOUNTS.get(who or "")
        assert body["struct"] is None, "the full state reached a player"
        assert body["session"]["seed"] is None, "the seed reached a player"
        for seat, holder in holders.items():
            if holder == mine:
                continue
            observation = body["observation_struct"]
            if isinstance(observation, dict):
                hidden = all(card is None for card in observation["hole_cards"][seat])
                assert hidden, (seat, observation)
            presentation = body.get("presentation") or {}
            hands = ((presentation.get("view") or {}).get("struct") or {}).get("player_hands")
            if isinstance(hands, list):
                assert hands[seat] == "", (seat, hands)

    def hand_of_turn(self, turn: dict[str, Any]) -> str:
        """The hand a turn answer came from: the latest hand dealt, which turns are read of."""
        return self.last_target

    def holders(self, hand: str) -> dict[int, str | None]:
        """Each seat of `hand` and the account holding it."""
        return dict(rows("select seat, player from poker.seat where session_id = %s", hand))

    def check_plies(self, who: str | None) -> None:
        """Invariants 1 and 2: plies only grow, and only by the seats `who` holds."""
        for hand in self.hands():
            plies = [
                (seat, action)
                for seat, action in rows(
                    "select seat, action from poker.ply where session_id = %s order by ply", hand
                )
            ]
            before = self.seen.get(hand, [])
            assert plies[: len(before)] == before, f"hand {hand} was rewound"

            holders = self.holders(hand)
            for seat, _ in plies[len(before) :]:
                if seat is not None:
                    assert holders[seat] == ACCOUNTS.get(who or ""), (
                        f"{who} played seat {seat} of {hand}"
                    )
            self.seen[hand] = plies

    def check_stacks(self) -> None:
        """Invariant 4: every stack is its buy-in plus the returns of the hands since."""
        for code in self.codes:
            model = self.stacks.setdefault(code, {})
            finished = rows(
                "select id, returns from poker.session"
                " where code = %s and finished_at is not null order by created_at",
                code,
            )
            for hand, returns in finished:
                if hand in self.settled:
                    continue
                self.settled.add(hand)
                for seat, holder in self.holders(hand).items():
                    if holder in model:
                        model[holder] += round(returns[seat])

            seated = dict(rows("select player, stack from poker.room_seat where code = %s", code))
            for player in list(model):
                if player not in seated:
                    del model[player]
            for player, stack in seated.items():
                model.setdefault(player, STACK)
                assert stack == model[player], (code, player, stack, model[player])

    @stateful.invariant()
    def chips_are_kept(self) -> None:
        """Invariant 4: the supply is whole and every room holds exactly its stacks."""
        assert rows("select sum(balance) from poker.account") == [(ledger.SUPPLY,)]
        uneven = rows(
            "select r.code from poker.room r join poker.account a on a.id = 'room:' || r.code"
            " where a.balance <> (select coalesce(sum(stack), 0) from poker.room_seat s"
            " where s.code = r.code)"
        )
        assert uneven == [], uneven

    def target(self, older: int) -> str:
        """The latest hand, or one `older` hands before it."""
        hands = self.hands()
        self.last_target = hands[max(0, len(hands) - 1 - older)]
        return self.last_target

    @stateful.rule(
        who=st.sampled_from(PLAYERS),
        viewer=st.sampled_from(VIEWERS),
        kind=st.sampled_from(("fold", "check", "call", "bet", "raise")),
        amount=st.one_of(st.none(), SMALL),
    )
    def move(self, who: str | None, viewer: str, kind: str, amount: int | None) -> None:
        self.call(
            who,
            "POST",
            f"/api/sessions/{self.target(0)}/moves?viewer={viewer}",
            {"kind": kind, "amount": amount},
        )

    @stateful.rule(data=st.data())
    def play_fair(self, data: st.DataObject) -> None:
        """The seat to move plays a legal move, so hands reach every street and their end.

        Without it a random move is rarely legal, and the cheats would only be
        tried at the first position of a hand.
        """
        hand = self.target(0)
        for seat, holder in self.holders(hand).items():
            name = next((n for n, account in ACCOUNTS.items() if account == holder), None)
            if name is None:
                continue
            turn = body(self.call(name, "GET", f"/api/sessions/{hand}/turn?viewer={seat}"))
            if not turn.get("to_move"):
                continue

            move = data.draw(st.sampled_from(turn["moves"]))
            amount = None
            if move["kind"] in ("bet", "raise"):
                amount = data.draw(st.integers(move["min"], move["max"]))
            self.call(
                name,
                "POST",
                f"/api/sessions/{hand}/moves?viewer={seat}",
                {"kind": move["kind"], "amount": amount},
            )
            return

    @stateful.rule(
        seat=st.integers(0, 1),
        cheat=st.sampled_from(("undo", "reset", "seat", "close", "replay")),
        history=st.lists(SMALL, max_size=12),
        action=SMALL,
    )
    def cheat_from_own_seat(self, seat: int, cheat: str, history: list[int], action: int) -> None:
        """A seat's own holder, the likeliest cheat, tries every rewind and takeover from it.

        Random players at random viewers rarely line up as the holder at their own
        seat just after their own move, so this rule always does.
        """
        hand = self.target(0)
        holder = self.holders(hand).get(seat)
        name = next((n for n, account in ACCOUNTS.items() if account == holder), None)
        if name is None:
            return

        path = f"/api/sessions/{hand}"
        cheats: dict[str, tuple[str, str, dict[str, contract.JsonValue] | None]] = {
            "undo": ("POST", f"{path}/undo?viewer={seat}", {}),
            "reset": (
                "POST",
                f"{path}/reset?viewer={seat}",
                {"history": list[contract.JsonValue](history)},
            ),
            "seat": (
                "PUT",
                f"{path}/seats/{1 - seat}?viewer={seat}",
                {"controller": "random", "config": {}, "autoplay": True},
            ),
            "close": ("DELETE", f"{path}?viewer={seat}", None),
            "replay": ("POST", f"{path}/actions?viewer={seat}", {"action": action, "ply": 0}),
        }
        method, target, body = cheats[cheat]
        self.call(name, method, target, body)

    @stateful.rule(
        who=st.sampled_from(PLAYERS),
        viewer=st.sampled_from(VIEWERS),
        action=SMALL,
        ply=MAYBE_PLY,
        older=st.integers(0, 2),
    )
    def act(self, who: str | None, viewer: str, action: int, ply: int | None, older: int) -> None:
        self.call(
            who,
            "POST",
            f"/api/sessions/{self.target(older)}/actions?viewer={viewer}",
            {"action": action, "ply": ply},
        )

    @stateful.rule(
        who=st.sampled_from(PLAYERS), viewer=st.sampled_from(VIEWERS), outcome=SMALL, ply=MAYBE_PLY
    )
    def choose_chance(self, who: str | None, viewer: str, outcome: int, ply: int | None) -> None:
        self.call(
            who,
            "POST",
            f"/api/sessions/{self.target(0)}/chance?viewer={viewer}",
            {"outcome": outcome, "ply": ply},
        )

    @stateful.rule(
        who=st.sampled_from(PLAYERS),
        viewer=st.sampled_from(VIEWERS),
        history=st.one_of(st.none(), st.lists(SMALL, max_size=12)),
        older=st.integers(0, 2),
    )
    def reset(self, who: str | None, viewer: str, history: list[int] | None, older: int) -> None:
        body: dict[str, contract.JsonValue] = {
            "history": None if history is None else list[contract.JsonValue](history)
        }
        self.call(who, "POST", f"/api/sessions/{self.target(older)}/reset?viewer={viewer}", body)

    @stateful.rule(
        who=st.sampled_from(PLAYERS),
        viewer=st.sampled_from(VIEWERS),
        route=st.sampled_from(("undo", "advance")),
        older=st.integers(0, 2),
    )
    def rewind_or_advance(self, who: str | None, viewer: str, route: str, older: int) -> None:
        body: dict[str, contract.JsonValue] = {"max_plies": 5} if route == "advance" else {}
        self.call(who, "POST", f"/api/sessions/{self.target(older)}/{route}?viewer={viewer}", body)

    @stateful.rule(
        who=st.sampled_from(PLAYERS),
        viewer=st.sampled_from(VIEWERS),
        seat=st.integers(-1, 2),
        controller=st.sampled_from(("random", "human", "call", "remote")),
        autoplay=st.booleans(),
    )
    def take_a_seat_over(
        self, who: str | None, viewer: str, seat: int, controller: str, autoplay: bool
    ) -> None:
        self.call(
            who,
            "PUT",
            f"/api/sessions/{self.target(0)}/seats/{seat}?viewer={viewer}",
            {"controller": controller, "config": {}, "autoplay": autoplay},
        )

    @stateful.rule(who=st.sampled_from(PLAYERS), viewer=st.sampled_from(VIEWERS))
    def close(self, who: str | None, viewer: str) -> None:
        self.call(who, "DELETE", f"/api/sessions/{self.target(0)}?viewer={viewer}")

    @stateful.rule(
        who=st.sampled_from(PLAYERS),
        route=st.sampled_from(("join", "leave", "deal")),
        after=st.sampled_from(("latest", "older", "garbage")),
        room=st.integers(0, 3),
    )
    def use_the_room(self, who: str | None, route: str, after: str, room: int) -> None:
        code = self.codes[min(room, len(self.codes) - 1)]
        hands = [hand for (hand,) in rows("select id from poker.session where code = %s", code)]
        # A room its only player left before anyone joined has closed, with no hands.
        named = {"latest": hands[-1], "older": hands[0]}.get(after) if hands else None
        named = named or "0" * 16
        body: dict[str, contract.JsonValue] = {"after": named} if route == "deal" else {}
        self.call(who, "POST", f"/api/rooms/{code}/{route}", body)

    @stateful.rule(who=st.sampled_from(PLAYERS), viewer=st.sampled_from(VIEWERS))
    def open_another_room(self, who: str | None, viewer: str) -> None:
        response = self.call(who, "POST", f"/api/sessions?viewer={viewer}", TABLE)
        if response.status_code == 200:
            self.codes.append(body(response)["session"]["code"])

    @stateful.rule(
        who=st.sampled_from(PLAYERS),
        viewer=st.sampled_from(VIEWERS),
        read=st.sampled_from(("", "/turn", "/plies/0", "/plies/3")),
        older=st.integers(0, 2),
    )
    def look(self, who: str | None, viewer: str, read: str, older: int) -> None:
        self.call(who, "GET", f"/api/sessions/{self.target(older)}{read}?viewer={viewer}")

    @stateful.rule()
    def alternate_stores(self) -> None:
        """Switches the active store and alternates every request after between the two."""
        self.which = 1 - self.which
        self.alternating = not self.alternating

    @stateful.rule(who=st.sampled_from(PLAYERS), viewer=st.sampled_from(VIEWERS))
    def watch(self, who: str | None, viewer: str) -> None:
        """An event stream opens only for a view its player may take."""
        hand = self.target(0)
        target = f"/api/sessions/{hand}/events?viewer={viewer}"
        with CLIENTS[self.which].stream("GET", target, headers=headers(who)) as response:
            if response.status_code != 200:
                response.read()
                assert response.status_code < 500, (target, response.text)
                assert body(response)["code"] in errors.ErrorCode, response.text
                return
            # The stream opens with the live frame; reading it is enough.
            first = next(line for line in response.iter_lines() if line)

        assert first.startswith("data: "), first
        frame = json.loads(first.removeprefix("data: "))
        opened = frame["viewer"]
        assert opened["kind"] != contract.ViewerKind.ORACLE or frame["returns"] is not None
        if opened["seat"] is not None:
            assert self.holders(hand)[opened["seat"]] == ACCOUNTS.get(who or "")
        self.check_sight(who, frame)


CheatingTest = Cheaters.TestCase


if __name__ == "__main__":
    absltest.main()
