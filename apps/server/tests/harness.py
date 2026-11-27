"""An API server on a loopback port, and a client that signs requests as the Worker does."""

import http.client
import json
import threading
import urllib.parse
from typing import Any

from poker_house_server import api, contract, health_report, loader, server, static, store

PLAYER_KEY = "test-player-key"


def start(sessions: store.SessionStore) -> server.Server:
    """Serves `sessions` on a free loopback port until `stop`."""
    listener = server.Server(
        ("127.0.0.1", 0),
        api.Api(
            sessions,
            catalogue=loader.build_catalogue,
            health=health_report.build,
            player_key=PLAYER_KEY,
        ),
        static.ClientFiles(static.DEFAULT_ROOT),
        server.LOOPBACK_HOSTS,
    )
    threading.Thread(target=listener.serve_forever, daemon=True).start()
    return listener


def stop(listener: server.Server) -> None:
    """Stops a server `start` started."""
    listener.shutdown()
    listener.server_close()


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
