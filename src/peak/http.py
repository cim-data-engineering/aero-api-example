"""Shared HTTP plumbing: response envelope, param encoding, service clients."""

from __future__ import annotations

from typing import Any

import httpx

from peak.auth import client
from peak.config import CORE_URL, NOTIFICATIONS_URL, TASKS_URL, TICKETS_URL, USERS_URL


class ApiError(RuntimeError):
    """The API returned an error status or an unexpected envelope."""

    def __init__(self, message: str, *, status_code: int | None = None, payload: Any = None):
        super().__init__(message)
        self.status_code = status_code
        self.payload = payload


def encode_params(params: dict[str, Any]) -> dict[str, Any]:
    """Drop None values so httpx does not send them as empty strings.

    Lists are left as-is: httpx repeats the key (``site_ids=411&site_ids=412``),
    which is the form the API expects. Do not use ``site_ids[]`` — the API
    ignores it silently and returns every record.
    """
    return {k: v for k, v in params.items() if v is not None and v != []}


def unwrap(response: httpx.Response, key: str | None = None) -> Any:
    """Return the payload from a ``{status, data}`` envelope, or raise ApiError."""
    try:
        body = response.json()
    except ValueError as exc:
        raise ApiError(
            f"non-JSON response from {response.request.url}: {response.text[:300]}",
            status_code=response.status_code,
        ) from exc

    if isinstance(body, dict) and body.get("status") == "error":
        raise ApiError(
            f"{response.request.url} -> {body.get('message') or 'error with no message'}",
            status_code=response.status_code,
            payload=body,
        )

    if response.status_code >= 400:
        raise ApiError(
            f"{response.request.url} -> HTTP {response.status_code}: {response.text[:300]}",
            status_code=response.status_code,
            payload=body,
        )

    data = body.get("data", body) if isinstance(body, dict) else body
    if key is None:
        return data
    if not isinstance(data, dict) or key not in data:
        raise ApiError(f"no '{key}' in response data (keys: {list(data)})", payload=body)
    return data[key]


def get(
    api: httpx.Client,
    path: str,
    params: dict[str, Any] | None = None,
    *,
    key: str | None = None,
) -> Any:
    """GET a path on an authed client and unwrap the envelope."""
    response = api.get(path, params=encode_params(params or {}))
    return unwrap(response, key)


def record_count(response: httpx.Response) -> int | None:
    """Total matching records, present only when ``start_index`` was sent."""
    body = response.json()
    metadata = body.get("response_metadata") if isinstance(body, dict) else None
    return (metadata or {}).get("record_count")


def core_client(**kwargs: Any) -> httpx.Client:
    return client(CORE_URL, **kwargs)


def users_client(**kwargs: Any) -> httpx.Client:
    return client(USERS_URL, **kwargs)


def tickets_client(**kwargs: Any) -> httpx.Client:
    return client(TICKETS_URL, **kwargs)


def tasks_client(**kwargs: Any) -> httpx.Client:
    return client(TASKS_URL, **kwargs)


def notifications_client(**kwargs: Any) -> httpx.Client:
    return client(NOTIFICATIONS_URL, **kwargs)
