"""Environment-backed configuration for the PEAK API clients."""

from __future__ import annotations

import os
from dataclasses import dataclass
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

TOKEN_CACHE_PATH = REPO_ROOT / ".peak" / "token.json"


class ConfigError(RuntimeError):
    """A required environment variable is missing."""


@dataclass(frozen=True)
class Settings:
    access_token_url: str
    client_id: str
    offline_token: str
    client_secret: str | None = None


def _require(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise ConfigError(f"{name} is not set — add it to {REPO_ROOT / '.env'}")
    return value


def load_settings(env_file: Path | None = None) -> Settings:
    """Read auth settings from .env (real environment variables win)."""
    load_dotenv(env_file or REPO_ROOT / ".env", override=False)
    return Settings(
        access_token_url=_require("ACCESS_TOKEN_URL"),
        client_id=_require("CLIENT_ID"),
        offline_token=_require("OFFLINE_TOKEN_ACCESS"),
        client_secret=os.environ.get("CLIENT_SECRET") or None,
    )
