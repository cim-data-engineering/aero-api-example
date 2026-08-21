#!/usr/bin/env python
"""List sites from the PEAK API.

    uv run scripts/get_sites.py

Reads the offline token from .env (OFFLINE_TOKEN_ACCESS -- get_token.py prints
one), swaps it for a short-lived access token, then calls GET /sites.
"""

import os

import httpx
from dotenv import load_dotenv

TOKEN_URL = "https://login.cimenviro.com/auth/realms/cimenviro/protocol/openid-connect/token"
CLIENT_ID = "api-external"
API_URL = "https://api.cimenviro.com"


def get_access_token(offline_token: str) -> str:
    """Swap the long-lived offline token for a short-lived access token."""
    response = httpx.post(
        TOKEN_URL,
        data={
            "grant_type": "refresh_token",
            "client_id": CLIENT_ID,
            "refresh_token": offline_token,
        },
        timeout=30,
    )
    if response.status_code != 200:
        raise SystemExit(f"token exchange failed: HTTP {response.status_code} {response.text}")
    return response.json()["access_token"]


def get_sites(access_token: str) -> list[dict]:
    """Return sites this account can see. Omit limit to get every site."""
    response = httpx.get(
        f"{API_URL}/sites",
        headers={"Authorization": f"Bearer {access_token}"},
        params={"limit": 25},
        timeout=60,
    )
    if response.status_code != 200:
        raise SystemExit(f"GET /sites failed: HTTP {response.status_code} {response.text}")
    return response.json()["data"]["sites"]


def main() -> None:
    load_dotenv()
    offline_token = os.environ.get("OFFLINE_TOKEN_ACCESS")
    if not offline_token:
        raise SystemExit("no OFFLINE_TOKEN_ACCESS in .env -- run get_token.py to make one")

    for site in get_sites(get_access_token(offline_token)):
        print(f"{site['site_id']:>6}  {site['site_name']}")


if __name__ == "__main__":
    main()
