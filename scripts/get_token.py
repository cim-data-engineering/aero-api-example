#!/usr/bin/env python
"""Mint a PEAK access token, and create the offline token in the first place.

Two ways in. Log in with username and password (the way to get started):

    uv run scripts/get_token.py --login --save       # mint + store the offline token
    uv run scripts/get_token.py --login --username you@cimenviro.com --totp 123456

or exchange an offline token you already have (what routine runs do):

    TOKEN=$(uv run scripts/get_token.py)             # token on stdout
    uv run scripts/get_token.py --length             # len=1234, no secret shown
    uv run scripts/get_token.py --tenant benmax      # ~/.local/secrets/benmax_api
    uv run scripts/get_token.py --token-file ~/.local/secrets/aero_api
    uv run scripts/get_token.py --export             # export PEAK_TOKEN=... for eval
    uv run scripts/get_token.py --claims             # who the token is for

With --login, username, password and TOTP code are prompted for unless passed as
flags or set in PEAK_USERNAME / PEAK_PASSWORD / PEAK_TOTP. The password is never
taken from a flag, so it stays out of shell history and the process list.

A fresh token is minted on each run. Pass --cached to reuse the cached one while it
is still valid (the API clients do this by default).
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
from pathlib import Path

from peak.auth import AuthError, exchange_offline_token, get_access_token, login
from peak.config import (
    DEFAULT_TENANT,
    ConfigError,
    load_login_settings,
    load_settings,
    tenant_token_file,
    write_token_file,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    src = parser.add_argument_group("offline token source")
    src.add_argument("--tenant", help="read ~/.local/secrets/<tenant>_api")
    src.add_argument("--token-file", metavar="PATH", help="read the offline token from PATH")

    log = parser.add_argument_group("log in with username and password")
    log.add_argument(
        "--login", action="store_true", help="use the password grant instead of an offline token"
    )
    log.add_argument("--username", help="PEAK username (implies --login); else PEAK_USERNAME")
    log.add_argument("--totp", help="one-time code if the account enforces MFA; else prompted")
    log.add_argument(
        "--save",
        action="store_true",
        help="write the minted offline token to --token-file, or the tenant's file",
    )
    log.add_argument("--force", action="store_true", help="let --save overwrite an existing file")

    out = parser.add_argument_group("output")
    mode = out.add_mutually_exclusive_group()
    mode.add_argument("--length", action="store_true", help="print len=N instead of the token")
    mode.add_argument("--export", action="store_true", help="print an export statement for eval")
    mode.add_argument("--claims", action="store_true", help="print the token's claims as JSON")
    mode.add_argument("--json", action="store_true", help="print token, expiry and source as JSON")
    mode.add_argument(
        "--offline-token",
        action="store_true",
        help="print the minted offline token instead of the access token (--login only)",
    )
    out.add_argument(
        "--var", default="PEAK_TOKEN", help="variable name for --export (default: PEAK_TOKEN)"
    )
    out.add_argument("--cached", action="store_true", help="reuse the cached token if still valid")
    out.add_argument(
        "--verbose", "-v", action="store_true", help="report the source and expiry on stderr"
    )
    return parser


def save_path(args: argparse.Namespace) -> Path:
    """Where --save writes: the explicit file, else the tenant's conventional path."""
    if args.token_file:
        return Path(args.token_file).expanduser()
    return tenant_token_file(args.tenant or DEFAULT_TENANT)


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    if args.offline_token and not (args.login or args.username):
        parser.error("--offline-token only applies with --login")
    if args.save and not (args.login or args.username):
        parser.error("--save only applies with --login — there is nothing new to save")

    offline_token: str | None = None
    try:
        if args.login or args.username:
            settings = load_login_settings(username=args.username, totp=args.totp)
            token, offline_token = login(settings)
        else:
            settings = load_settings(tenant=args.tenant, token_file=args.token_file)
            token = get_access_token(settings) if args.cached else exchange_offline_token(settings)
    except (AuthError, ConfigError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    if args.save:
        if not offline_token:
            print(
                "error: no refresh token in the response — the realm refused "
                "offline_access, so there is no offline token to save",
                file=sys.stderr,
            )
            return 1
        try:
            path = write_token_file(save_path(args), offline_token, overwrite=args.force)
        except ConfigError as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 1
        print(f"offline token saved to {path}", file=sys.stderr)

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
    elif args.offline_token:
        if not offline_token:
            print("error: the realm returned no refresh token", file=sys.stderr)
            return 1
        print(offline_token)
    elif args.json:
        json.dump(
            {
                "access_token": token.token,
                "expires_at": token.expires_at,
                "expires_in": round(token.expires_in),
                "source": settings.token_source,
                "offline_token_minted": bool(offline_token),
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
