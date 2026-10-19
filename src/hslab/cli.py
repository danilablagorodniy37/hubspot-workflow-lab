"""hslab: check | setup | map | scenarios"""

from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

from . import __version__


def cmd_check(args) -> int:
    from .client import HubSpot

    hs = HubSpot()
    info = hs.get("/account-info/v3/details")
    print(
        json.dumps(
            {k: info.get(k) for k in ("portalId", "accountType", "timeZone", "dataHostingLocation")}
        )
    )
    flows = list(hs.paged("/automation/v4/flows"))
    print(f"workflows visible to the key: {len(flows)}")
    return 0


def cmd_setup(args) -> int:
    from .client import HubSpot
    from .portal import ensure_properties, seed_contacts, seed_deals

    hs = HubSpot()
    created = ensure_properties(hs)
    print("properties created:", ", ".join(created) or "none (already there)")
    ids = seed_contacts(hs, args.contacts)
    print(f"contacts upserted: {len(ids)}")
    print(f"deals created: {seed_deals(hs, ids, args.deals)}")
    return 0


def cmd_map(args) -> int:
    from .client import HubSpot
    from .flowmap import export, fetch_all, summarise, to_markdown

    hs = HubSpot()
    flows = fetch_all(hs)
    paths = export(flows, args.out)
    summaries = [summarise(f) for f in flows]
    Path(args.markdown).write_text(to_markdown(summaries), encoding="utf-8")
    print(f"exported {len(paths)} workflows to {args.out}, map written to {args.markdown}")
    return 0


def cmd_scenarios(args) -> int:
    from .client import HubSpot
    from .scenarios import run, to_markdown

    hs = HubSpot()
    started = datetime.now(UTC)
    outcomes = run(
        hs,
        act_after=timedelta(minutes=args.act_after),
        check_after=timedelta(minutes=args.check_after),
    )
    note = (
        f"Run {started:%d %b %Y %H:%M} UTC on the HubSpot developer test account. Contacts act "
        f"{args.act_after} min after booking; follow-ups read back after {args.check_after} min "
        "(the workflow delay is 5 min, a stand-in for 2 days)."
    )
    md = to_markdown(outcomes, note)
    Path(args.markdown).write_text(md, encoding="utf-8")
    print(md)
    return 0 if all(o.ok for o in outcomes if o.variant == "fixed") else 1


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="hslab", description=__doc__)
    p.add_argument("--version", action="version", version=__version__)
    sub = p.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("check", help="auth, account and how many workflows the key can see")
    s.set_defaults(func=cmd_check)
    s = sub.add_parser("setup", help="properties, contacts and deals for the inherited portal")
    s.add_argument("--contacts", type=int, default=30)
    s.add_argument("--deals", type=int, default=10)
    s.set_defaults(func=cmd_setup)
    s = sub.add_parser("map", help="export workflows as JSON and write docs/workflow-map.md")
    s.add_argument("--out", default="workflows")
    s.add_argument("--markdown", default="docs/workflow-map.md")
    s.set_defaults(func=cmd_map)
    s = sub.add_parser("scenarios", help="book, act, wait, read back the follow-up flag")
    s.add_argument("--act-after", type=float, default=2)
    s.add_argument("--check-after", type=float, default=9)
    s.add_argument("--markdown", default="docs/scenario-results.md")
    s.set_defaults(func=cmd_scenarios)
    args = p.parse_args(argv)
    return int(args.func(args) or 0)


if __name__ == "__main__":
    raise SystemExit(main())
