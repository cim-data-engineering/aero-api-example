"""Environment-backed configuration for the PEAK API clients."""

from __future__ import annotations

import getpass
import hashlib
import os
import sys
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

# Repo root = two levels up from src/peak/config.py
REPO_ROOT = Path(__file__).resolve().parents[2]

# Base URLs (mirrors lib/http.js in the JS repo)
CORE_URL = "https://api.cimenviro.com"
TICKETS_URL = f"{CORE_URL}/tickets/tickets"
STATUSES_URL = f"{CORE_URL}/tickets/statuses"
TASKS_URL = f"{CORE_URL}/tasks"
USERS_URL = f"{CORE_URL}/users"
NOTIFICATIONS_URL = f"{CORE_URL}/notifications"

TOKEN_CACHE_DIR = REPO_ROOT / ".peak"

# Not secrets: the realm endpoint and the public client id. Defaults let the
# tools run with nothing but the offline token file. Override in .env or the
# environment (a different realm, or a client with a secret).
DEFAULT_ACCESS_TOKEN_URL = (
    "https://login.cimenviro.com/auth/realms/cimenviro/protocol/openid-connect/token"
)
DEFAULT_CLIENT_ID = "api-external"

# Scopes for the password grant. offline_access is what makes the returned refresh
# token long-lived; without it the token dies with the login session.
OFFLINE_SCOPE = "openid offline_access"

# Where offline (refresh) tokens live when not set inline. One file per tenant,
# e.g. ~/.local/secrets/aero_api — the file holds the raw token, nothing else.
SECRETS_DIR = Path("~/.local/secrets").expanduser()
DEFAULT_TENANT = "aero"


def tenant_token_file(tenant: str) -> Path:
    """Path convention for a tenant's offline token."""
    return SECRETS_DIR / f"{tenant}_api"


class ConfigError(RuntimeError):
    """A required environment variable is missing."""


@dataclass(frozen=True)
class Settings:
    """Everything needed for one token exchange.

    Either ``offline_token`` (refresh-token grant) or ``username`` + ``password``
    (password grant) is set. Secrets carry ``repr=False`` so a settings object in a
    traceback or log line cannot leak them.
    """

    access_token_url: str
    client_id: str
    offline_token: str = field(default="", repr=False)
    client_secret: str | None = field(default=None, repr=False)
    username: str | None = None
    password: str | None = field(default=None, repr=False)
    # One-time code from the authenticator app, when the account enforces MFA.
    totp: str | None = field(default=None, repr=False)
    # Where the credential came from, for error messages and --verbose output.
    token_source: str = "OFFLINE_TOKEN_ACCESS"

    @property
    def token_fingerprint(self) -> str:
        """Short stable digest of the credential, used to key the token cache.

        Keying on the credential means switching tenants — or users — cannot return
        a cached access token minted for a different one.
        """
        material = self.offline_token or f"password:{self.client_id}:{self.username}"
        return hashlib.sha256(material.encode()).hexdigest()[:12]

    @property
    def cache_path(self) -> Path:
        return TOKEN_CACHE_DIR / f"token-{self.token_fingerprint}.json"


def _env(name: str, default: str) -> str:
    return os.environ.get(name, "").strip() or default


def read_token_file(path: Path) -> str:
    """Read an offline token from a file, tolerating a trailing newline."""
    try:
        token = path.read_text().strip()
    except OSError as exc:
        raise ConfigError(f"cannot read offline token from {path}: {exc}") from exc
    if not token:
        raise ConfigError(f"{path} is empty")
    return token


def resolve_offline_token(
    *, token: str | None = None, token_file: Path | None = None, tenant: str | None = None
) -> tuple[str, str]:
    """Find the offline token and say where it came from.

    Precedence: an explicit token, then an explicit file, then a tenant name,
    then ``OFFLINE_TOKEN_ACCESS``, then ``OFFLINE_TOKEN_FILE``, then the default
    tenant's file under ~/.local/secrets.
    """
    if token:
        return token, "argument"
    if token_file:
        path = Path(token_file).expanduser()
        return read_token_file(path), str(path)
    if tenant:
        path = tenant_token_file(tenant)
        return read_token_file(path), str(path)

    from_env = os.environ.get("OFFLINE_TOKEN_ACCESS", "").strip()
    if from_env:
        return from_env, "OFFLINE_TOKEN_ACCESS"

    from_env_file = os.environ.get("OFFLINE_TOKEN_FILE", "").strip()
    if from_env_file:
        path = Path(from_env_file).expanduser()
        return read_token_file(path), str(path)

    default_path = tenant_token_file(DEFAULT_TENANT)
    if default_path.exists():
        return read_token_file(default_path), str(default_path)

    raise ConfigError(
        "no offline token found. Set OFFLINE_TOKEN_ACCESS or OFFLINE_TOKEN_FILE in "
        f"{REPO_ROOT / '.env'}, or put the token in {default_path}"
    )


def load_settings(
    env_file: Path | None = None,
    *,
    token: str | None = None,
    token_file: Path | None = None,
    tenant: str | None = None,
) -> Settings:
    """Read auth settings from .env and the offline-token sources.

    Real environment variables win over .env. The offline token itself may come
    from a file — see ``resolve_offline_token``.
    """
    load_dotenv(env_file or REPO_ROOT / ".env", override=False)
    offline_token, source = resolve_offline_token(token=token, token_file=token_file, tenant=tenant)
    return Settings(
        access_token_url=_env("ACCESS_TOKEN_URL", DEFAULT_ACCESS_TOKEN_URL),
        client_id=_env("CLIENT_ID", DEFAULT_CLIENT_ID),
        offline_token=offline_token,
        client_secret=os.environ.get("CLIENT_SECRET") or None,
        token_source=source,
    )


def _prompt(label: str, *, secret: bool = False) -> str:
    """Ask for one value. Returns "" when there is no terminal to ask at."""
    if not sys.stdin.isatty():
        return ""
    try:
        return getpass.getpass(label) if secret else input(label).strip()
    except EOFError:
        return ""


def write_token_file(path: Path, token: str, *, overwrite: bool = False) -> Path:
    """Write an offline token to *path*, owner-readable only where the OS allows.

    On Windows ``chmod`` cannot express owner-only, so the file is written with
    whatever the directory grants — put it somewhere already private, or keep the
    token in ``.env`` instead.
    """
    path = Path(path).expanduser()
    if path.exists() and not overwrite:
        raise ConfigError(f"{path} already exists — pass --force to replace it")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(token + "\n")
    if os.name == "posix":
        path.chmod(0o600)
    return path


def load_login_settings(
    env_file: Path | None = None,
    *,
    username: str | None = None,
    password: str | None = None,
    totp: str | None = None,
    prompt: bool = True,
) -> Settings:
    """Settings for the password grant — no offline token needed.

    Each value comes from the argument, then the environment (``PEAK_USERNAME``,
    ``PEAK_PASSWORD``, ``PEAK_TOTP``), then a prompt. The password is read without
    echo and nothing is written to disk, so credentials stay out of shell history
    and out of ``.env`` unless the caller puts them there.
    """
    load_dotenv(env_file or REPO_ROOT / ".env", override=False)

    username = username or os.environ.get("PEAK_USERNAME", "").strip()
    if not username and prompt:
        username = _prompt("PEAK username: ")
    if not username:
        raise ConfigError("no username — pass --username or set PEAK_USERNAME")

    password = password or os.environ.get("PEAK_PASSWORD", "")
    if not password and prompt:
        password = _prompt(f"Password for {username}: ", secret=True)
    if not password:
        raise ConfigError("no password — set PEAK_PASSWORD or run interactively")

    # MFA is per-account: blank is valid, and the grant simply fails without a code
    # if the account requires one.
    totp = totp or os.environ.get("PEAK_TOTP", "").strip()
    if not totp and prompt:
        totp = _prompt("TOTP code (blank if the account has no MFA): ")

    return Settings(
        access_token_url=_env("ACCESS_TOKEN_URL", DEFAULT_ACCESS_TOKEN_URL),
        client_id=_env("CLIENT_ID", DEFAULT_CLIENT_ID),
        client_secret=os.environ.get("CLIENT_SECRET") or None,
        username=username,
        password=password,
        totp=totp or None,
        token_source=f"password grant as {username}",
    )
