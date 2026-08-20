#!/usr/bin/env python
"""List sites from the core API.

uv run scripts/fetch_sites.py                             # all sites, table
uv run scripts/fetch_sites.py --active                    # active only
uv run scripts/fetch_sites.py --state Illinois --csv      # filtered, CSV to stdout
uv run scripts/fetch_sites.py --site-id 411 --json        # one full record
uv run scripts/fetch_sites.py --count                     # just the total
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from typing import Any

from peak.auth import AuthError
from peak.config import ConfigError
from peak.http import ApiError, core_client
from peak.sites import SUMMARY_FIELDS, fetch_site, fetch_sites, fetch_sites_page, site_summary


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    flt = parser.add_argument_group("filters")
    flt.add_argument("--site-id", type=int, action="append", dest="site_ids", metavar="ID")
    flt.add_argument("--client-id", type=int, action="append", dest="client_ids", metavar="ID")
    flt.add_argument("--customer-id", type=int, action="append", dest="customer_ids", metavar="ID")
    flt.add_argument(
        "--name", dest="site_name", help="exact site_name match (server-side); see --search"
    )
    flt.add_argument(
        "--search",
        metavar="TEXT",
        help="case-insensitive substring match on site_name, applied after fetching",
    )
    flt.add_argument(
        "--building-type",
        action="append",
        dest="building_types",
        metavar="TYPE",
        help="University|Retail|Manufacturing|Hotel|Commercial|Museum|Other",
    )
    flt.add_argument(
        "--license-tier",
        action="append",
        dest="license_tiers",
        metavar="TIER",
        help="Premium|Standard",
    )
    flt.add_argument("--city")
    flt.add_argument("--state")
    flt.add_argument("--country")
    flt.add_argument("--postcode")
    flt.add_argument("--timezone")
    active = flt.add_mutually_exclusive_group()
    active.add_argument(
        "--active", dest="is_active", action="store_const", const=True, help="active sites only"
    )
    active.add_argument(
        "--inactive", dest="is_active", action="store_const", const=False, help="inactive only"
    )

    out = parser.add_argument_group("output")
    fmt = out.add_mutually_exclusive_group()
    fmt.add_argument("--json", action="store_true", help="full records as JSON")
    fmt.add_argument("--csv", action="store_true", help="summary fields as CSV")
    fmt.add_argument("--count", action="store_true", help="print the matching record count only")
    out.add_argument(
        "--fields",
        help=f"comma-separated fields for table/CSV (default: {','.join(SUMMARY_FIELDS)})",
    )
    out.add_argument("--sort", default="site_id", help="field to sort rows by (default: site_id)")
    return parser


def collect_filters(args: argparse.Namespace) -> dict[str, Any]:
    names = (
        "site_ids",
        "client_ids",
        "customer_ids",
        "site_name",
        "building_types",
        "license_tiers",
        "city",
        "state",
        "country",
        "postcode",
        "timezone",
        "is_active",
    )
    return {n: getattr(args, n) for n in names if getattr(args, n) not in (None, [])}


def print_table(rows: list[dict[str, Any]], fields: list[str]) -> None:
    if not rows:
        print("no sites matched", file=sys.stderr)
        return
    cells = [[("" if r.get(f) is None else str(r.get(f))) for f in fields] for r in rows]
    widths = [max(len(f), *(len(c[i]) for c in cells)) for i, f in enumerate(fields)]
    print("  ".join(f.ljust(w) for f, w in zip(fields, widths, strict=True)))
    print("  ".join("-" * w for w in widths))
    for row in cells:
        print("  ".join(c.ljust(w) for c, w in zip(row, widths, strict=True)))
    print(f"\n{len(rows)} site(s)", file=sys.stderr)


def main() -> int:
    args = build_parser().parse_args()
    filters = collect_filters(args)

    try:
        if args.count and not args.search:
            _, total = fetch_sites_page(limit=1, **filters)
            print(total if total is not None else "unknown")
            return 0

        with core_client() as api:
            single = filters.get("site_ids")
            if args.json and single and len(single) == 1 and len(filters) == 1:
                # Full single record, including fields only /sites/{id} returns.
                sites = [fetch_site(single[0], select_external_references=True, api=api)]
            else:
                sites = fetch_sites(api=api, **filters)

        if args.search:
            needle = args.search.casefold()
            sites = [s for s in sites if needle in (s.get("site_name") or "").casefold()]
    except (ApiError, AuthError, ConfigError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    if args.count:
        print(len(sites))
        return 0

    if args.json:
        json.dump(sites, sys.stdout, indent=2, default=str)
        print()
        print(f"{len(sites)} site(s)", file=sys.stderr)
        return 0

    fields = [f.strip() for f in args.fields.split(",")] if args.fields else list(SUMMARY_FIELDS)
    rows = [site_summary(s) if not args.fields else {f: s.get(f) for f in fields} for s in sites]
    if args.sort in (fields + ["site_id"]):
        rows.sort(key=lambda r: (r.get(args.sort) is None, r.get(args.sort)))

    if args.csv:
        writer = csv.DictWriter(sys.stdout, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)
        print(f"{len(rows)} site(s)", file=sys.stderr)
        return 0

    print_table(rows, fields)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
