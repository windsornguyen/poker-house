"""A throwaway Postgres with the production schema, the auth tables and real accounts.

Tests that move chips run against this cluster rather than a stand-in, so the
ledger's constraints, the auth service's own migration and the foreign keys
between them are the ones production runs.
"""

import os
import pathlib
import secrets
import shutil
import socket
import subprocess
import tempfile
from typing import LiteralString

import psycopg

REPO = pathlib.Path(__file__).resolve().parents[3]
AUTH = REPO / "apps" / "auth"
BINARIES = ("initdb", "pg_ctl", "psql", "node")


class Cluster:
    """A Postgres started in a temporary directory, stopped by `stop`."""

    def __init__(self) -> None:
        missing = [name for name in BINARIES if shutil.which(name) is None]
        if missing:
            raise RuntimeError(f"These tests need {', '.join(missing)} on PATH.")

        self.directory = tempfile.mkdtemp(prefix="poker-house-pg-")
        port = free_port()
        self.url = f"postgresql://postgres@127.0.0.1:{port}/postgres"

        data = os.path.join(self.directory, "data")
        run("initdb", "-D", data, "-U", "postgres", "--auth=trust", "--no-sync")
        options = f"-p {port} -k {self.directory} -c listen_addresses=127.0.0.1"
        run(
            "pg_ctl",
            "-D",
            data,
            "-o",
            options,
            "-l",
            os.path.join(self.directory, "log"),
            "-w",
            "start",
        )

        self.psql(REPO / "apps" / "server" / "schema.sql")
        self.node("migrate.ts")
        self.psql(AUTH / "players.sql")

    def psql(self, path: pathlib.Path) -> None:
        """Applies the SQL file at `path`."""
        run("psql", self.url, "-v", "ON_ERROR_STOP=1", "-q", "-f", str(path))

    def node(self, script: str, *args: str) -> str:
        """Runs one of the auth service's scripts against the cluster, and returns its output."""
        env = {
            **os.environ,
            "DATABASE_URL": self.url,
            "BETTER_AUTH_URL": "http://127.0.0.1:1",
            "BETTER_AUTH_SECRET": secrets.token_hex(32),
            "MAIL_KEY": secrets.token_hex(32),
        }
        done = subprocess.run(
            ["node", script, *args], cwd=AUTH, env=env, capture_output=True, text=True, check=False
        )
        if done.returncode != 0:
            raise RuntimeError(f"node {script} failed: {done.stderr}")
        return done.stdout

    def add_account(self, email: str, kind: str) -> str:
        """Lists `email` as `kind`, makes its verified account, and returns the account's id."""
        self.node("add-account.ts", email, kind)
        with psycopg.connect(self.url) as connection:
            row = connection.execute(
                'select id from auth."user" where email = %s', (email,)
            ).fetchone()
        assert row is not None
        return row[0]

    def query(self, sql: LiteralString) -> list[tuple[object, ...]]:
        """The rows of one read."""
        with psycopg.connect(self.url) as connection:
            return connection.execute(sql).fetchall()

    def stop(self) -> None:
        """Stops the cluster and deletes its files."""
        run("pg_ctl", "-D", os.path.join(self.directory, "data"), "-m", "immediate", "stop")
        shutil.rmtree(self.directory)


def run(*command: str) -> None:
    """Runs a Postgres tool, raising with its output when it fails."""
    done = subprocess.run(command, capture_output=True, text=True, check=False)
    if done.returncode != 0:
        raise RuntimeError(f"{' '.join(command[:2])} failed: {done.stderr or done.stdout}")


def free_port() -> int:
    """A TCP port nothing listens on now."""
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return probe.getsockname()[1]
