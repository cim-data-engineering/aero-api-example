#!/usr/bin/env python
"""Show one site in detail.

uv run scripts/get_site.py 411                  # by id
uv run scripts/get_site.py "110 N Wacker"       # by exact name
uv run scripts/get_site.py wacker               # by substring, if unambiguous
uv run scripts/get_site.py 411 --json           # full raw record
uv run scripts/get_site.py 411 --field timezone # one value, for scripting
"""

from __future__ import annotations

import argparse
import json
import sys
from typing import Any

from peak.auth import AuthError
from peak.config import ConfigError
from peak.http import ApiError, core_client
from peak.sites import fetch_site, format_working_hours, resolve_site


def fmt(value: Any) -> str:
    if value is None or value == [] or value == {}:
        return "-"
    if isinstance(value, bool):
        return "yes" if value else "no"
    if isinstance(value, list):
        return ", ".join(str(v) for v in value)
    if isinstance(value, float):
        return f"{value:,.1f}"
    return str(value)


def temp_range(site: dict[str, Any]) -> str:
    """Comfort band as a bare range — the site record carries no unit.

    Values are mixed across sites (20-23.3 and 67-75 both appear for USA sites),
    so the scale is not inferable here. The unit lives on the thermal comfort
    score endpoints (``ThermalComfortSiteScore.unit``), not on the site.
    """
    low, high = site.get("thermal_comfort_min_temp"), site.get("thermal_comfort_max_temp")
    if low is None and high is None:
        return "-"
    margin = site.get("thermal_comfort_margin")
    suffix = f" (margin {margin})" if margin not in (None, 0) else ""
    return f"{fmt(low)}-{fmt(high)}{suffix}"


def humidity_range(site: dict[str, Any]) -> str:
    low, high = site.get("ideal_relative_humidity_min"), site.get("ideal_relative_humidity_max")
    if not low and not high:
        return "-"
    margin = site.get("ideal_relative_humidity_margin")
    suffix = f" (margin {margin})" if margin not in (None, 0) else ""
    return f"{fmt(low)}-{fmt(high)}%{suffix}"


def address(site: dict[str, Any]) -> str:
    lines = [site.get("address_line_1"), site.get("address_line_2")]
    return ", ".join(line for line in lines if line) or "-"


def mapping_summary(mappings: dict[str, Any] | None) -> str:
    """``{"198": [], "326": [uuid, uuid]}`` -> ``198: 0 users, 326: 2 users``."""
    if not mappings:
        return "-"
    return ", ".join(f"{key}: {len(value or [])} users" for key, value in sorted(mappings.items()))


def sections(site: dict[str, Any]) -> list[tuple[str, list[tuple[str, str]]]]:
    schedule = site.get("thermalcomfort_schedule") or {}
    return [
        (
            "identity",
            [
                ("site_id", fmt(site.get("site_id"))),
                ("name", fmt(site.get("site_name"))),
                ("active", fmt(site.get("is_active"))),
                ("building type", fmt(site.get("building_type"))),
                ("building size", fmt(site.get("building_size"))),
                ("license tier", fmt(site.get("license_tier"))),
                ("customer", fmt(site.get("customer_id"))),
                ("clients", fmt(site.get("clients"))),
            ],
        ),
        (
            "location",
            [
                ("address", address(site)),
                ("city", fmt(site.get("city"))),
                ("state", fmt(site.get("state"))),
                ("postcode", fmt(site.get("postcode"))),
                ("country", fmt(site.get("country"))),
                ("coordinates", fmt(site.get("geo_coordinates"))),
                ("timezone", fmt(site.get("timezone"))),
            ],
        ),
        (
            "hours",
            [
                ("working hours", format_working_hours(site.get("working_hours"))),
                (
                    "comfort schedule",
                    f"{schedule.get('day_start', '-')}-{schedule.get('day_end', '-')}"
                    + (", weekends excluded" if schedule.get("exclude_weekends") else "")
                    if schedule
                    else "-",
                ),
            ],
        ),
        (
            "thermal comfort",
            [
                ("temperature", temp_range(site)),
                ("humidity", humidity_range(site)),
                ("humidity available", fmt(site.get("thermal_comfort_humidity_available"))),
                ("weather available", fmt(site.get("thermal_comfort_weather_available"))),
            ],
        ),
        (
            "rates",
            [
                ("currency", fmt(site.get("monetary_currency"))),
                ("electricity", fmt(site.get("electricity_charge_rate"))),
                ("gas", fmt(site.get("gas_charge_rate"))),
                ("water", fmt(site.get("water_charge_rate"))),
                ("cop", fmt(site.get("cop"))),
                ("base temperature", fmt(site.get("base_temperature"))),
                ("demand billing", fmt(site.get("demand_peak_billing_model"))),
                ("nmi numbers", fmt(site.get("nmi_numbers"))),
            ],
        ),
        (
            "targets",
            [
                ("equipment health pass rate", fmt(site.get("equipment_health_target_pass_rate"))),
                ("contractor closure rate", fmt(site.get("contractor_target_closure_rate"))),
                ("potential annual savings", fmt(site.get("potential_annual_savings"))),
            ],
        ),
        (
            "timeline",
            [
                ("consulting start", fmt(site.get("consulting_start_ts"))),
                ("reporting start", fmt(site.get("reporting_start_ts"))),
                ("first report", fmt(site.get("first_report_issued_ts"))),
                ("first resolved issue", fmt(site.get("first_resolved_issue_ts"))),
                ("last modified", fmt(site.get("last_modified_at"))),
            ],
        ),
        (
            "access",
            [
                ("email", fmt(site.get("email_address"))),
                ("slack channel", fmt(site.get("slack_channel"))),
                ("client mappings", mapping_summary(site.get("client_mappings"))),
                ("customer mappings", mapping_summary(site.get("customer_mappings"))),
                ("external references", fmt(len(site.get("external_references") or []) or None)),
            ],
        ),
    ]


def print_detail(site: dict[str, Any], *, show_empty: bool) -> None:
    for title, rows in sections(site):
        shown = rows if show_empty else [r for r in rows if r[1] != "-"]
        if not shown:
            continue
        print(f"\n{title.upper()}")
        width = max(len(label) for label, _ in shown)
        for label, value in shown:
            print(f"  {label.ljust(width)}  {value}")


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("target", help="site id, exact site name, or name substring")
    parser.add_argument("--json", action="store_true", help="print the full raw record")
    parser.add_argument("--field", help="print one field's raw value and exit")
    parser.add_argument("--all-fields", action="store_true", help="include fields that are empty")
    parser.add_argument(
        "--no-refs",
        action="store_true",
        help="skip external references (one less join server-side)",
    )
    args = parser.parse_args()

    try:
        with core_client() as api:
            if args.target.strip().lstrip("-").isdigit():
                site = fetch_site(
                    int(args.target), select_external_references=not args.no_refs, api=api
                )
            else:
                site, candidates = resolve_site(args.target, api=api)
                if site is None:
                    if not candidates:
                        print(f"no site matched {args.target!r}", file=sys.stderr)
                        return 1
                    print(f"{args.target!r} matched {len(candidates)} sites:", file=sys.stderr)
                    for candidate in candidates:
                        print(
                            f"  {candidate['site_id']:<6} {candidate.get('site_name')}",
                            file=sys.stderr,
                        )
                    return 2
                if not args.no_refs:
                    site = fetch_site(site["site_id"], select_external_references=True, api=api)
    except (ApiError, AuthError, ConfigError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    if args.field:
        if args.field not in site:
            print(f"no field {args.field!r}; available: {', '.join(sorted(site))}", file=sys.stderr)
            return 2
        value = site[args.field]
        print(json.dumps(value, default=str) if isinstance(value, dict | list) else value)
        return 0

    if args.json:
        json.dump(site, sys.stdout, indent=2, default=str)
        print()
        return 0

    print_detail(site, show_empty=args.all_fields)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
