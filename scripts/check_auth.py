#!/usr/bin/env python
"""Verify auth: exchange the offline token and show what the access token grants.

uv run scripts/check_auth.py            # uses the cached token if still valid
uv run scripts/check_auth.py --refresh  # force a fresh exchange
uv run scripts/check_auth.py --print-token
"""

from __future__ import annotations

import argparse
import datetime as dt
import sys

import httpx

from peak.auth import AuthError, get_access_token
from peak.config import USERS_URL, ConfigError, load_settings


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--refresh", action="store_true", help="ignore the cached token")
    parser.add_argument("--no-cache", action="store_true", help="do not read or write the cache")
    parser.add_argument("--print-token", action="store_true", help="print the raw access token")
    args = parser.parse_args()

    try:
        settings = load_settings()
        token = get_access_token(settings, use_cache=not args.no_cache, force_refresh=args.refresh)
    except (AuthError, ConfigError) as exc:
        print(f"auth failed: {exc}", file=sys.stderr)
        return 1

    claims = token.claims()
    expiry = dt.datetime.fromtimestamp(token.expires_at).astimezone()
    print(f"token url    {settings.access_token_url}")
    print(f"client_id    {settings.client_id}")
    print(f"subject      {claims.get('preferred_username') or claims.get('sub')}")
    print(f"email        {claims.get('email', '-')}")
    print(f"scope        {claims.get('scope', '-')}")
    print(f"expires      {expiry:%Y-%m-%d %H:%M:%S %Z} (in {token.expires_in:.0f}s)")
    roles = (claims.get("realm_access") or {}).get("roles") or []
    if roles:
        print(f"realm roles  {', '.join(sorted(roles))}")
    if args.print_token:
        print(f"\n{token.token}")

    # Live call: prove the token is accepted by the API, not just well-formed.
    try:
        response = httpx.get(
            f"{USERS_URL}/permissions/current-user",
            headers={"Authorization": f"Bearer {token.token}"},
            timeout=30.0,
        )
        print(f"\nGET {USERS_URL}/permissions/current-user -> HTTP {response.status_code}")
        if response.status_code != 200:
            print(response.text[:300])
            return 1
    except httpx.HTTPError as exc:
        print(f"\nlive check failed: {exc}", file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
