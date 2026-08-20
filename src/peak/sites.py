"""Sites from the core API (``GET /sites``).

Two things about this endpoint are worth knowing before using it:

* **Pagination is keyset on ``site_id``.** ``cursor`` is the last ``site_id``
  already seen (exclusive) and is rejected unless ``order_by_site_id=true``.
  ``iter_sites`` does that for you. The offset form (``start_index``) also works
  and is the only way to get ``response_metadata.record_count``, but it caps the
  page at 25 by default.
* **A site carries client *ids*, not names** — and ``client_id`` is null on most
  records, with the ids living in the ``clients`` list. Names come only from the
  users service (``GET /users/clients``).
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

import httpx

from peak.http import ApiError, core_client, encode_params, get, record_count, unwrap

# Filters accepted by GET /sites. Plural names take a list and are repeated in
# the query string; the singular forms take one value.
SITE_FILTERS = frozenset(
    {
        "building_type",
        "building_types",
        "city",
        "client_id",
        "client_ids",
        "contractor_id",
        "contractor_ids",
        "country",
        "customer_id",
        "customer_ids",
        "email_address",
        "is_active",
        "license_tier",
        "license_tiers",
        "nmi_numbers",
        "postcode",
        "provider_id",
        "provider_ids",
        "site_id",
        "site_ids",
        "site_name",
        "slack_channel",
        "state",
        "thermal_comfort_humidity_available",
        "thermal_comfort_weather_available",
        "timezone",
    }
)

# Page size for keyset paging. The endpoint returns everything when no limit is
# sent, so this only bounds the size of each response.
DEFAULT_PAGE_SIZE = 200


def _check_filters(filters: dict[str, Any]) -> dict[str, Any]:
    unknown = set(filters) - SITE_FILTERS
    if unknown:
        raise ValueError(
            f"unknown site filter(s): {', '.join(sorted(unknown))}. "
            f"Valid: {', '.join(sorted(SITE_FILTERS))}"
        )
    return encode_params(filters)


def iter_sites(
    *,
    api: httpx.Client | None = None,
    page_size: int = DEFAULT_PAGE_SIZE,
    **filters: Any,
) -> Iterator[dict[str, Any]]:
    """Yield sites in ascending site_id order, paging by cursor."""
    params = _check_filters(filters)
    owns_client = api is None
    api = api or core_client()
    try:
        cursor: int | None = None
        while True:
            page = get(
                api,
                "/sites",
                {**params, "order_by_site_id": True, "limit": page_size, "cursor": cursor},
                key="sites",
            )
            if not page:
                return
            yield from page
            if len(page) < page_size:
                return
            cursor = page[-1]["site_id"]
    finally:
        if owns_client:
            api.close()


def fetch_sites(*, api: httpx.Client | None = None, **filters: Any) -> list[dict[str, Any]]:
    """All sites matching the filters, in ascending site_id order."""
    return list(iter_sites(api=api, **filters))


def fetch_sites_page(
    *,
    start_index: int = 0,
    limit: int = 25,
    api: httpx.Client | None = None,
    **filters: Any,
) -> tuple[list[dict[str, Any]], int | None]:
    """One offset-paged slice plus the total record count.

    Use this when the total matters; ``record_count`` is returned only when
    ``start_index`` is sent.
    """
    params = _check_filters(filters)
    owns_client = api is None
    api = api or core_client()
    try:
        response = api.get(
            "/sites", params=encode_params({**params, "start_index": start_index, "limit": limit})
        )
        return unwrap(response, "sites"), record_count(response)
    finally:
        if owns_client:
            api.close()


def fetch_site(
    site_id: int,
    *,
    select_external_references: bool = False,
    api: httpx.Client | None = None,
) -> dict[str, Any]:
    """One site by id."""
    owns_client = api is None
    api = api or core_client()
    try:
        return get(
            api,
            f"/sites/{site_id}",
            {"select_external_references": select_external_references or None},
            key="site",
        )
    except ApiError as exc:
        if exc.status_code == 404:
            raise ApiError(f"no site {site_id} (or no access to it)", status_code=404) from exc
        raise
    finally:
        if owns_client:
            api.close()


SUMMARY_FIELDS = (
    "site_id",
    "site_name",
    "is_active",
    "customer_id",
    "clients",
    "building_type",
    "license_tier",
    "city",
    "state",
    "country",
    "timezone",
    "building_size",
)


def site_summary(site: dict[str, Any]) -> dict[str, Any]:
    """Flatten a site record to the identifying fields, for tables and CSV."""
    row = {field: site.get(field) for field in SUMMARY_FIELDS}
    row["clients"] = ",".join(str(c) for c in site.get("clients") or [])
    return row


DAYS = ("monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday")


def format_working_hours(working_hours: dict[str, Any] | None) -> str:
    """Render ``working_hours`` as ``Mon-Fri 09:00-17:00`` style runs.

    The record holds ``{day}Enabled`` / ``{day}Start`` / ``{day}End`` per day;
    consecutive days sharing a window are collapsed into one run.
    """
    if not working_hours:
        return "-"

    windows: list[tuple[str, str | None]] = []
    for day in DAYS:
        if not working_hours.get(f"{day}Enabled"):
            windows.append((day, None))
            continue
        start, end = working_hours.get(f"{day}Start"), working_hours.get(f"{day}End")
        windows.append((day, f"{start}-{end}"))

    runs: list[tuple[list[str], str | None]] = []
    for day, window in windows:
        if runs and runs[-1][1] == window:
            runs[-1][0].append(day)
        else:
            runs.append(([day], window))

    parts = []
    for days, window in runs:
        label = (
            days[0][:3].title()
            if len(days) == 1
            else f"{days[0][:3].title()}-{days[-1][:3].title()}"
        )
        parts.append(f"{label} {window}" if window else f"{label} closed")
    return ", ".join(parts)


def resolve_site(
    target: str, *, api: httpx.Client | None = None
) -> tuple[dict[str, Any] | None, list[dict[str, Any]]]:
    """Resolve a site id or name to one site.

    Returns ``(site, candidates)``. A digit string is treated as a site id. A
    name is tried as an exact ``site_name`` match first, then as a
    case-insensitive substring across all sites. When the name is ambiguous the
    site is ``None`` and the candidates are returned for the caller to report.
    """
    if target.strip().lstrip("-").isdigit():
        return fetch_site(int(target), api=api), []

    exact = fetch_sites(api=api, site_name=target)
    if len(exact) == 1:
        return exact[0], []

    needle = target.casefold()
    matches = [s for s in fetch_sites(api=api) if needle in (s.get("site_name") or "").casefold()]
    if len(matches) == 1:
        return matches[0], []
    return None, matches
