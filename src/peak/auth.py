"""OAuth auth against Keycloak, by either of two grants.

* ``login`` — ``grant_type=password`` with username, password and (when the account
  enforces MFA) a TOTP code, scoped ``openid offline_access``. This is how an offline
  token is minted in the first place: the response carries both an access token and
  the long-lived refresh token to keep.
* ``exchange_offline_token`` — ``grant_type=refresh_token`` against a stored offline
  token, which is what every routine run does. No password involved.

Access tokens are cached on disk so repeated script runs reuse one until it nears
expiry.
"""

from __future__ import annotations

import base64
import binascii
import json
import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx

from peak.config import OFFLINE_SCOPE, Settings, load_settings

# Refresh this many seconds before the token actually expires.
EXPIRY_MARGIN_S = 60


class AuthError(RuntimeError):
    """The token exchange failed."""


@dataclass(frozen=True)
class AccessToken:
    token: str
    expires_at: float  # epoch seconds

    @property
    def expires_in(self) -> float:
        return self.expires_at - time.time()

    def is_usable(self, margin_s: int = EXPIRY_MARGIN_S) -> bool:
        return self.expires_in > margin_s

    def claims(self) -> dict[str, Any]:
        return decode_jwt_payload(self.token)


def decode_jwt_payload(token: str) -> dict[str, Any]:
    """Decode a JWT payload without verifying the signature (inspection only)."""
    try:
        payload = token.split(".")[1]
    except IndexError as exc:
        raise AuthError("not a JWT — no payload segment") from exc
    padded = payload + "=" * (-len(payload) % 4)
    try:
        return json.loads(base64.urlsafe_b64decode(padded))
    except (binascii.Error, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise AuthError(f"could not decode JWT payload: {exc}") from exc


def _read_cache(path: Path) -> AccessToken | None:
    try:
        raw = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError):
        return None
    token, expires_at = raw.get("access_token"), raw.get("expires_at")
    if not isinstance(token, str) or not isinstance(expires_at, int | float):
        return None
    return AccessToken(token=token, expires_at=float(expires_at))


def _write_cache(path: Path, token: AccessToken) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"access_token": token.token, "expires_at": token.expires_at}))
    os.chmod(path, 0o600)


def _post_form(settings: Settings, form: dict[str, str], *, timeout: float) -> dict[str, Any]:
    """POST a grant to the token endpoint and return the parsed body."""
    if settings.client_secret:
        form["client_secret"] = settings.client_secret

    try:
        response = httpx.post(settings.access_token_url, data=form, timeout=timeout)
    except httpx.HTTPError as exc:
        raise AuthError(f"could not reach {settings.access_token_url}: {exc}") from exc

    if response.status_code != 200:
        detail = response.text[:500]
        try:
            error = response.json()
            detail = f"{error.get('error')}: {error.get('error_description', detail)}"
        except ValueError:
            pass
        raise AuthError(f"token exchange failed with HTTP {response.status_code}: {detail}")

    body = response.json()
    if not body.get("access_token"):
        raise AuthError(f"no access_token in response: {json.dumps(body)[:500]}")
    return body


def _access_token(body: dict[str, Any]) -> AccessToken:
    expires_in = float(body.get("expires_in", 300))
    return AccessToken(token=body["access_token"], expires_at=time.time() + expires_in)


def exchange_offline_token(settings: Settings, *, timeout: float = 30.0) -> AccessToken:
    """POST the offline token to Keycloak and return a fresh access token."""
    if not settings.offline_token:
        raise AuthError("no offline token in settings — use login() for the password grant")

    # Keycloak may return a rotated refresh token; the stored offline token stays
    # valid, so it is deliberately not written back.
    body = _post_form(
        settings,
        {
            "grant_type": "refresh_token",
            "client_id": settings.client_id,
            "refresh_token": settings.offline_token,
        },
        timeout=timeout,
    )
    return _access_token(body)


def login(
    settings: Settings, *, scope: str = OFFLINE_SCOPE, timeout: float = 30.0
) -> tuple[AccessToken, str | None]:
    """Authenticate with username and password; mint an offline token too.

    Returns the access token and the refresh token from the same response. With
    ``offline_access`` in *scope* that refresh token is the long-lived offline token
    to save for later runs — this is how an offline token is created in the first
    place. ``settings.totp`` is sent when the account enforces MFA.
    """
    if not settings.username or not settings.password:
        raise AuthError("username and password are required for the password grant")

    form = {
        "grant_type": "password",
        "client_id": settings.client_id,
        "username": settings.username,
        "password": settings.password,
        "scope": scope,
    }
    if settings.totp:
        form["totp"] = settings.totp

    body = _post_form(settings, form, timeout=timeout)
    return _access_token(body), body.get("refresh_token")


def get_access_token(
    settings: Settings | None = None,
    *,
    use_cache: bool = True,
    force_refresh: bool = False,
    cache_path: Path | None = None,
) -> AccessToken:
    """Return a usable access token, from cache when possible.

    The cache file is keyed on a digest of the offline token, so several tenants
    can be used from one checkout without one's access token being served for
    another.
    """
    settings = settings or load_settings()
    cache_path = cache_path or settings.cache_path

    if use_cache and not force_refresh:
        cached = _read_cache(cache_path)
        if cached and cached.is_usable():
            return cached

    token = exchange_offline_token(settings)
    if use_cache:
        _write_cache(cache_path, token)
    return token


def auth_headers(**kwargs: Any) -> dict[str, str]:
    """Authorization header for a PEAK API request."""
    return {"Authorization": f"Bearer {get_access_token(**kwargs).token}"}


def client(base_url: str = "", *, timeout: float = 60.0, **kwargs: Any) -> httpx.Client:
    """An httpx.Client carrying the bearer token, for one base URL."""
    return httpx.Client(
        base_url=base_url,
        headers={**auth_headers(**kwargs), "Accept": "application/json"},
        timeout=timeout,
        follow_redirects=True,
    )
