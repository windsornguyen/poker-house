# Copyright 2026 DeepMind Technologies Limited
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
# Modified for Doggybank.
"""The HTTP server: the JSON API under `/api/`, the probes, and the browser client.

The server is meant for one machine. It has no authentication, and an oracle
frame shows every player's private information, so by default it listens on
the loopback interface only. It also answers only requests whose `Host`
names an allowed host, which stops a web page that rebinds its own domain to
the loopback address from reading the API, and it accepts state-changing
requests only as JSON from its own origin (the scheme, host and port the
request's `Host` names), which stops a page on another origin, another port
of the same host included, from posting to it.
"""

import contextlib
import http
import os
import pathlib
import re
import socket
import subprocess
import urllib.parse
from collections.abc import AsyncGenerator, Callable
from typing import Annotated

import fastapi
import uvicorn
from absl import logging
from fastapi import routing
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, PlainTextResponse, Response
from fastapi.staticfiles import StaticFiles
from starlette.concurrency import run_in_threadpool
from starlette.datastructures import Headers, MutableHeaders
from starlette.exceptions import HTTPException
from starlette.routing import Match
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from doggybank_server import api, contract, errors, store
from doggybank_server import catalogue as catalogue_lib
from doggybank_server import health as health_lib

# The host names that reach the loopback interface.
LOOPBACK_HOSTS = frozenset({"localhost", "127.0.0.1", "::1"})

# Where the client's build writes it, relative to this package.
CLIENT_ROOT = pathlib.Path(__file__).resolve().parents[3] / "web" / "dist" / "client"

# The largest request body the server reads, in bytes.
MAX_BODY_BYTES = 1 << 20

LIVE_PATH = "/livez"
READY_PATH = "/readyz"

# The listen backlog: connections the system holds while the server has not
# yet accepted them, enough for a burst such as a page loading while a move
# is played.
_BACKLOG = 128

_BODY_METHODS = frozenset({"POST", "PUT"})
_STATE_METHODS = _BODY_METHODS | {"DELETE"}

_DIGITS = re.compile(r"[0-9]+")

_SECURITY_HEADERS = {
    "Cache-Control": "no-cache",
    "Content-Security-Policy": "frame-ancestors 'none'",
    "Referrer-Policy": "no-referrer",
    "X-Content-Type-Options": "nosniff",
}


def create_app(
    sessions: store.SessionStore,
    *,
    catalogue: Callable[[], catalogue_lib.Catalogue],
    health: Callable[[], health_lib.Health],
    player_key: str,
    client: pathlib.Path,
    allowed_hosts: frozenset[str],
) -> fastapi.FastAPI:
    """Returns the app: the API, the probes and the client.

    Args:
      sessions: Holds the sessions the API creates and serves.
      catalogue: Returns the catalogue of every game.
      health: Returns the server's health report.
      player_key: The key the Worker signs the player header with.
      client: The directory the client's build wrote. It need not exist yet;
        a client path is refused until it does, so a build needs no restart.
      allowed_hosts: The host names, without ports, that a request's `Host`
        and `Origin` may name.
    """

    @contextlib.asynccontextmanager
    async def lifespan(unused_app: fastapi.FastAPI) -> AsyncGenerator[None]:
        """Tells systemd the server is ready once its database answers."""
        problem = await run_in_threadpool(sessions.problem)
        if problem is not None:
            raise RuntimeError(f"The database does not answer: {problem}")
        notify_ready()
        yield

    app = fastapi.FastAPI(
        title="Doggybank",
        version="0.1.0",
        lifespan=lifespan,
        docs_url=None,
        redoc_url=None,
        # `python -m doggybank_server.openapi` writes the document offline.
        openapi_url=None,
        redirect_slashes=False,
        separate_input_output_schemas=False,
        generate_unique_id_function=operation_id,
        exception_handlers={
            errors.RequestError: refuse,
            RequestValidationError: refuse_malformed,
            HTTPException: refuse_route,
        },
    )
    app.state.arena = api.Arena(sessions, catalogue, health, player_key)
    app.include_router(api.router)
    app.include_router(probes)
    app.router.default = client_files(client)
    app.add_middleware(Guard, allowed_hosts=allowed_hosts)
    return app


def operation_id(route: routing.APIRoute) -> str:
    """A route's operation id: its function's name in camel case, as `getTurn`."""
    first, *rest = route.name.split("_")
    return first + "".join(word.title() for word in rest)


def notify_ready() -> None:
    """Tells systemd the server is ready, when systemd runs it."""
    if "NOTIFY_SOCKET" in os.environ:
        subprocess.run(["systemd-notify", "--ready"], check=True)


probes = fastapi.APIRouter(include_in_schema=False, default_response_class=PlainTextResponse)


@probes.get(LIVE_PATH)
async def live() -> str:
    """Answers while the process serves."""
    return "live"


@probes.get(READY_PATH)
def ready(arena: Annotated[api.Arena, fastapi.Depends(api.find_arena)]) -> Response:
    """Answers whether the server can serve sessions."""
    problem = arena.sessions.problem()
    if problem is None:
        return PlainTextResponse("ready")
    return PlainTextResponse(problem, http.HTTPStatus.SERVICE_UNAVAILABLE)


def client_files(root: pathlib.Path) -> ASGIApp:
    """Serves the client at every path outside the API that no route serves."""
    files = StaticFiles(directory=root, html=True, check_dir=False)

    async def serve(scope: Scope, receive: Receive, send: Send) -> None:
        if scope["path"].startswith(api.PREFIX):
            raise HTTPException(http.HTTPStatus.NOT_FOUND)
        await files(scope, receive, send)

    return serve


def refusal(error: errors.RequestError) -> JSONResponse:
    """The contract's answer to a refused request: its error body and status."""
    body = error.to_error()
    return JSONResponse(contract.to_json(body), body.code.http_status)


async def refuse(unused_request: fastapi.Request, error: errors.RequestError) -> JSONResponse:
    """Answers a request the contract refuses."""
    return refusal(error)


async def refuse_malformed(
    unused_request: fastapi.Request, error: RequestValidationError
) -> JSONResponse:
    """Answers a request whose body or parameters do not decode, naming the first fault."""
    first = error.errors()[0]
    # The first part of a location is where the value came from, such as `body`.
    where = ".".join(str(part) for part in first["loc"][1:]) or "body"
    return refusal(errors.BadRequestError(f"{where}: {first['msg']}."))


async def refuse_route(req: fastapi.Request, error: HTTPException) -> Response:
    """Answers a path or method no route serves: in the API with the contract's error."""
    path = req.url.path
    if not path.startswith(api.PREFIX):
        return PlainTextResponse(str(error.detail), error.status_code, error.headers)
    methods = [
        method
        for route in routing.iter_route_contexts(req.app.routes)
        if route.matches(req.scope)[0] is Match.PARTIAL
        for method in route.methods or ()
    ]
    if not methods:
        return refusal(errors.NotFoundError(f"There is no route {path}."))
    return refusal(
        errors.MethodNotAllowedError(f"{path} accepts {' and '.join(methods)}, not {req.method}.")
    )


class Guard:
    """Refuses a request that fails a transport check, and marks every response."""

    def __init__(self, app: ASGIApp, allowed_hosts: frozenset[str]) -> None:
        self.app = app
        self.allowed_hosts = allowed_hosts

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        async def send_marked(message: Message) -> None:
            """Adds the security headers, and logs a request that failed."""
            if message["type"] == "http.response.start":
                MutableHeaders(scope=message).update(_SECURITY_HEADERS)
                if message["status"] >= http.HTTPStatus.BAD_REQUEST:
                    logging.info("%s %s %d", scope["method"], scope["path"], message["status"])
            await send(message)

        refused = self.check(scope)
        await (self.app if refused is None else refused)(scope, receive, send_marked)

    def check(self, scope: Scope) -> Response | None:
        """Returns the answer refusing the request, or None when it passes every check."""
        headers = Headers(scope=scope)
        host = host_name(headers.get("Host", ""))
        if host not in self.allowed_hosts:
            return PlainTextResponse(f"Host {host!r} is refused.", http.HTTPStatus.FORBIDDEN)

        method, is_api = scope["method"], scope["path"].startswith(api.PREFIX)
        if method not in _BODY_METHODS and has_body(headers):
            message = f"A {method} request has no body."
            if is_api:
                return refusal(errors.BadRequestError(message))
            return PlainTextResponse(message, http.HTTPStatus.BAD_REQUEST)
        if not is_api or method not in _STATE_METHODS:
            return None
        problem = self.check_origin(headers)
        if problem is None and method in _BODY_METHODS:
            problem = check_body(headers)
        return None if problem is None else refusal(errors.BadRequestError(problem))

    def check_origin(self, headers: Headers) -> str | None:
        """Returns why the request's origin is refused, or None."""
        origin = headers.get("Origin")
        if origin is None:
            return None
        refused = f"Requests from {origin} are refused."
        url = urllib.parse.urlsplit(origin)
        if url.scheme != "http" or url.hostname not in self.allowed_hosts:
            return refused
        own = urllib.parse.urlsplit("//" + headers.get("Host", "").strip())
        try:
            same = (url.hostname, url.port or 80) == (own.hostname, own.port or 80)
        except ValueError:  # A port that is not a number.
            return refused
        return None if same else refused


def check_body(headers: Headers) -> str | None:
    """Returns why the request's body is refused, or None."""
    if headers.get("Content-Type", "").partition(";")[0].strip().lower() != "application/json":
        return "The body must be application/json."
    if "Transfer-Encoding" in headers:
        return "The body must have a Content-Length."
    length = headers.get("Content-Length", "0")
    if not _DIGITS.fullmatch(length) or int(length) > MAX_BODY_BYTES:
        return f"The body must be at most {MAX_BODY_BYTES} bytes."
    return None


def has_body(headers: Headers) -> bool:
    """Whether a request's headers announce a body."""
    length = headers.get("Content-Length", "0").strip()
    return "Transfer-Encoding" in headers or length != "0"


def host_name(authority: str) -> str:
    """Returns the host name of a URL authority, without port or brackets.

    Args:
      authority: A `Host` header value, such as `localhost:8080` or `[::1]:80`.

    Returns:
      The host name in lower case, such as `localhost` or `::1`.
    """
    authority = authority.strip().lower()
    if authority.startswith("["):
        return authority[1:].partition("]")[0]
    if authority.count(":") == 1:
        return authority.partition(":")[0]
    return authority


def listen(host: str, port: int) -> socket.socket:
    """Returns a socket listening on `host` and `port`; port 0 picks a free port."""
    family = socket.AF_INET6 if ":" in host else socket.AF_INET
    return socket.create_server((host, port), family=family, backlog=_BACKLOG)


def url_of(listener: socket.socket) -> str:
    """The URL a listening socket is reachable at."""
    host, port = listener.getsockname()[:2]
    return f"http://[{host}]:{port}/" if ":" in host else f"http://{host}:{port}/"


def server(app: fastapi.FastAPI) -> uvicorn.Server:
    """A uvicorn server of `app` that logs only warnings and failed requests.

    It requires uvloop and httptools: uvicorn imports each one it is named,
    and an import that fails stops the server.
    """
    # One worker: sessions, their locks and `session.wait` wake-ups live in this process.
    config = uvicorn.Config(
        app,
        loop="uvloop",
        http="httptools",
        workers=1,
        log_level="warning",
        access_log=False,
    )
    return uvicorn.Server(config)
