#!/usr/bin/env python
"""Mint an access token from an offline (refresh) token and print it.

The Python equivalent of the curl one-liner:

    TOKEN=$(uv run scripts/get_token.py)          # token on stdout
    uv run scripts/get_token.py --length          # len=1234, no secret shown
    uv run scripts/get_token.py --tenant benmax   # ~/.local/secrets/benmax_api
    uv run scripts/get_token.py --token-file ~/.local/secrets/aero_api
    uv run scripts/get_token.py --export          # export PEAK_TOKEN=... for eval
    uv run scripts/get_token.py --claims          # who the token is for

A fresh token is minted on each run. Pass --cached to reuse the cached one
while it is still valid (the API clients do this by default).
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import sys

from peak.auth import AuthError, exchange_offline_token, get_access_token
from peak.config import ConfigError, load_settings


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    src = parser.add_argument_group("offline token source")
    src.add_argument("--tenant", help="read ~/.local/secrets/<tenant>_api")
    src.add_argument("--token-file", metavar="PATH", help="read the offline token from PATH")

    out = parser.add_argument_group("output")
    mode = out.add_mutually_exclusive_group()
    mode.add_argument("--length", action="store_true", help="print len=N instead of the token")
    mode.add_argument("--export", action="store_true", help="print an export statement for eval")
    mode.add_argument("--claims", action="store_true", help="print the token's claims as JSON")
    mode.add_argument("--json", action="store_true", help="print token, expiry and source as JSON")
    out.add_argument(
        "--var", default="PEAK_TOKEN", help="variable name for --export (default: PEAK_TOKEN)"
    )
    out.add_argument("--cached", action="store_true", help="reuse the cached token if still valid")
    out.add_argument(
        "--verbose", "-v", action="store_true", help="report the source and expiry on stderr"
    )
    return parser


def main() -> int:
    args = build_parser().parse_args()

    try:
        settings = load_settings(tenant=args.tenant, token_file=args.token_file)
        token = get_access_token(settings) if args.cached else exchange_offline_token(settings)
    except (AuthError, ConfigError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    if args.verbose:
        expiry = dt.datetime.fromtimestamp(token.expires_at).astimezone()
        print(
            f"offline token from {settings.token_source}\n"
            f"client_id {settings.client_id}\n"
            f"expires {expiry:%H:%M:%S} (in {token.expires_in:.0f}s)",
            file=sys.stderr,
        )

    if args.length:
        print(f"len={len(token.token)}")
    elif args.export:
        print(f"export {args.var}={token.token}")
    elif args.claims:
        json.dump(token.claims(), sys.stdout, indent=2, sort_keys=True)
        print()
    elif args.json:
        json.dump(
            {
                "access_token": token.token,
                "expires_at": token.expires_at,
                "expires_in": round(token.expires_in),
                "source": settings.token_source,
            },
            sys.stdout,
            indent=2,
        )
        print()
    else:
        print(token.token)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
