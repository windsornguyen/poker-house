"""An API server on a loopback port, and a client that signs requests as the Worker does."""

import dataclasses
import http.client
import json
import threading
import urllib.parse
from typing import Any

import uvicorn

from doggybank_server import api, app, contract, health_report, loader, store

PLAYER_KEY = "test-player-key"


@dataclasses.dataclass(frozen=True)
class Listener:
    """A server `start` started, and the thread it serves on."""

    server: uvicorn.Server
    thread: threading.Thread
    url: str


def start(sessions: store.SessionStore) -> Listener:
    """Serves `sessions` on a free loopback port until `stop`."""
    socket = app.listen("127.0.0.1", 0)
    server = app.server(
        app.create_app(
            sessions,
            catalogue=loader.build_catalogue,
            health=health_report.build,
            player_key=PLAYER_KEY,
            client=app.CLIENT_ROOT,
            allowed_hosts=app.LOOPBACK_HOSTS,
        )
    )
    thread = threading.Thread(target=server.run, kwargs={"sockets": [socket]}, daemon=True)
    thread.start()
    return Listener(server, thread, app.url_of(socket))


def stop(listener: Listener) -> None:
    """Stops a server `start` started."""
    listener.server.should_exit = True
    listener.thread.join()


def call(
    url: str,
    method: str,
    target: str,
    body: dict[str, contract.JsonValue] | None = None,
    player: str | None = None,
    key: str = PLAYER_KEY,
) -> tuple[int, Any]:
    """Decodes an HTTP response, at the untyped JSON test boundary.

    `player` is the account the Worker would name, signed with `key`. None
    sends no account.
    """
    address = urllib.parse.urlsplit(url)
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
