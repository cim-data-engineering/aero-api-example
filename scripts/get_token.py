#!/usr/bin/env python
"""Log in to PEAK and print an offline token.

    uv run scripts/get_token.py

Prompts for username, password and TOTP code, then posts the password grant --
the same call as the curl in the README. What it prints is a long-lived refresh
token, the "offline token": put it in .env as OFFLINE_TOKEN_ACCESS and
get_sites.py can call the API without a password.
"""

import getpass

import httpx

TOKEN_URL = "https://login.cimenviro.com/auth/realms/cimenviro/protocol/openid-connect/token"
CLIENT_ID = "api-external"


def login(username: str, password: str, totp: str) -> str:
    """Return the offline token for these credentials.

    scope "openid offline_access" is what makes the refresh token long-lived.
    """
    response = httpx.post(
        TOKEN_URL,
        data={
            "grant_type": "password",
            "client_id": CLIENT_ID,
            "scope": "openid offline_access",
            "username": username,
            "password": password,
            "totp": totp,
        },
        timeout=30,
    )
    if response.status_code != 200:
        raise SystemExit(f"login failed: HTTP {response.status_code} {response.text}")
    return response.json()["refresh_token"]


def main() -> None:
    username = input("PEAK username: ")
    password = getpass.getpass(f"Password for {username}: ")  # not echoed
    totp = input("TOTP code (blank if the account has no MFA): ")
    print(login(username, password, totp))


if __name__ == "__main__":
    main()
