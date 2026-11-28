"""Sets each bot's chips to the same balance, so no deploy smoke inherits another's losses.

  DOGGYBANK_DEPLOY_KEY=<internal account's key> python -m doggybank_players.reset \\
    --site https://doggybank.io tight@test.poker.invalid pot-odds@test.poker.invalid
"""

import argparse
import os
from collections.abc import Sequence

import httpx

BALANCE = 1_000


def main(argv: Sequence[str] | None = None) -> None:
    """Sets every named bot to `BALANCE` chips, moving the difference to or from the treasury."""
    parser = argparse.ArgumentParser(prog="python -m doggybank_players.reset")
    parser.add_argument("--site", required=True)
    parser.add_argument("emails", nargs="+")
    args = parser.parse_args(argv)

    key = os.environ["DOGGYBANK_DEPLOY_KEY"]
    with httpx.Client(base_url=args.site, headers={"x-api-key": key}, timeout=60) as admin:
        for email in args.emails:
            body = {"email": email, "balance": BALANCE}
            admin.post("/api/admin/balances", json=body).raise_for_status()


if __name__ == "__main__":
    main()
