"""One account at the table, through the same Worker a browser uses."""

import time

import httpx

from poker_house_server import contract
from poker_house_server import frame as frame_lib

FRAME = contract.adapter(frame_lib.Frame)

# The Worker trusts a session cookie for five minutes, so a player renews it
# before then, as the site's pages do.
RENEW_SECONDS = 4 * 60


class Player:
    """A signed-in account that creates, joins and plays rooms."""

    def __init__(self, site: str, email: str, password: str) -> None:
        """Signs in to `site`.

        Raises:
          httpx.HTTPStatusError: If the site refuses the email and password.
        """
        self.http = httpx.Client(base_url=site, headers={"Origin": site}, timeout=30)
        signed_in = self.http.post(
            "/api/auth/sign-in/email", json={"email": email, "password": password}
        )
        signed_in.raise_for_status()
        self.renewed_at = time.monotonic()

    def renew(self) -> None:
        """Has the session cookie reissued once it is old enough to lapse soon."""
        if time.monotonic() - self.renewed_at < RENEW_SECONDS:
            return

        renewed = self.http.get("/api/auth/get-session", params={"disableCookieCache": "true"})
        renewed.raise_for_status()
        self.renewed_at = time.monotonic()

    def create(self, body: dict[str, contract.JsonValue]) -> frame_lib.Frame:
        """Opens a room with `body`, seated at its first seat."""
        self.renew()
        return self.frame_of(self.http.post("/api/sessions", params={"viewer": 0}, json=body))

    def join(self, code: str) -> frame_lib.Frame:
        """Sits in the room `code` names."""
        self.renew()
        return self.frame_of(self.http.post(f"/api/rooms/{code}/join", json={}))

    def frame(self, session_id: str, seat: int) -> frame_lib.Frame:
        """The live position as `seat` sees it."""
        self.renew()
        return self.frame_of(self.http.get(f"/api/sessions/{session_id}", params={"viewer": seat}))

    def act(self, session_id: str, seat: int, action: int) -> frame_lib.Frame:
        """Plays `action` for `seat`."""
        self.renew()
        response = self.http.post(
            f"/api/sessions/{session_id}/actions",
            params={"viewer": seat},
            json={"action": action, "ply": None},
        )
        return self.frame_of(response)

    def frame_of(self, response: httpx.Response) -> frame_lib.Frame:
        """The frame `response` carries.

        Raises:
          httpx.HTTPStatusError: If the server refused the request.
        """
        response.raise_for_status()
        return FRAME.validate_json(response.content)
