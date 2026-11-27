"""One account at the table, signed in with an API key, through the Worker a browser uses."""

import httpx

from poker_house_server import contract, moves, request, rooms
from poker_house_server import frame as frame_lib

FRAME = contract.adapter(frame_lib.Frame)
TURN = contract.adapter(moves.Turn)
ROOM = contract.adapter(rooms.RoomView)


class Player:
    """An account that opens, joins and plays rooms."""

    def __init__(self, site: str, key: str) -> None:
        """Plays at `site` as the account API key `key` belongs to."""
        self.http = httpx.Client(base_url=site, headers={"x-api-key": key}, timeout=30)

    def create(self, body: dict[str, contract.JsonValue]) -> frame_lib.Frame:
        """Opens a room with `body`, seated at its first seat."""
        return FRAME.validate_json(self.send("POST", "/api/sessions?viewer=0", body))

    def join(self, code: str) -> frame_lib.Frame:
        """Sits at room `code`, buying in."""
        return FRAME.validate_json(self.send("POST", f"/api/rooms/{code}/join", {}))

    def deal(self, code: str, after: str) -> frame_lib.Frame:
        """Deals room `code`'s hand after `after`, or finds it if it is dealt."""
        return FRAME.validate_json(self.send("POST", f"/api/rooms/{code}/deal", {"after": after}))

    def room(self, code: str) -> rooms.RoomView:
        """Room `code` as this account sees it."""
        return ROOM.validate_json(self.send("GET", f"/api/rooms/{code}"))

    def leave(self, code: str) -> rooms.RoomView:
        """Gets up from room `code`, cashing the stack out."""
        return ROOM.validate_json(self.send("POST", f"/api/rooms/{code}/leave", {}))

    def frame(self, session_id: str) -> frame_lib.Frame:
        """The hand as a spectator sees it."""
        return FRAME.validate_json(self.send("GET", f"/api/sessions/{session_id}?viewer=spectator"))

    def turn(self, session_id: str, seat: int) -> moves.Turn:
        """`seat`'s turn: its cards, the pot, the price and its legal moves."""
        return TURN.validate_json(
            self.send("GET", f"/api/sessions/{session_id}/turn?viewer={seat}")
        )

    def move(self, session_id: str, seat: int, move: request.PlayMove) -> frame_lib.Frame:
        """Plays `move` for `seat`."""
        body: dict[str, contract.JsonValue] = {"kind": move.kind, "amount": move.amount}
        return FRAME.validate_json(
            self.send("POST", f"/api/sessions/{session_id}/moves?viewer={seat}", body)
        )

    def send(
        self, method: str, path: str, body: dict[str, contract.JsonValue] | None = None
    ) -> bytes:
        """The body of the site's answer.

        Raises:
          httpx.HTTPStatusError: If the site refused the request.
        """
        response = self.http.request(method, path, json=body)
        response.raise_for_status()
        return response.content
