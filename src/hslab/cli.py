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


def cmd_build(args) -> int:
    from .build import SPECS, apply
    from .client import HubSpot

    which = args.only or list(SPECS)
    for key, outcome in apply(HubSpot(), which, enable=not args.off).items():
        print(f"{key}: {outcome}")
    return 0


def cmd_history(args) -> int:
    """Property history of contacts: when each value changed and what changed it."""
    from .client import HubSpot

    hs = HubSpot()
    props = "discovery_call_status,follow_up_sent"
    lines = [
        "# Property history",
        "",
        "Read with `hslab history` (CRM v3 `propertiesWithHistory`).",
        "",
    ]
    for cid in args.contact_ids:
        d = hs.get(f"/crm/v3/objects/contacts/{cid}", propertiesWithHistory=props)
        events = sorted(
            (h["timestamp"], prop, h.get("value"), h.get("sourceType"))
            for prop, hist in (d.get("propertiesWithHistory") or {}).items()
            for h in hist
        )
        lines += [f"## Contact {cid}", "", "| Time (UTC) | Property | Value | Changed by |"]
        lines += ["|---|---|---|---|"]
        for ts, prop, value, source in events:
            who = "the workflow" if source == "AUTOMATION_PLATFORM" else "the scenario script (API)"
            lines.append(f"| {ts[11:19]} | `{prop}` | {value} | {who} |")
        lines.append("")
    md = "\n".join(lines)
    if args.markdown:
        Path(args.markdown).write_text(md, encoding="utf-8")
    print(md)
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
    s = sub.add_parser("build", help="create the lab workflows, or update them by name")
    s.add_argument("--only", nargs="*", choices=["inherited", "no_show", "fixed"])
    s.add_argument("--off", action="store_true", help="leave the workflows turned off")
    s.set_defaults(func=cmd_build)
    s = sub.add_parser("history", help="who changed the call status and the follow-up flag, when")
    s.add_argument("contact_ids", nargs="+")
    s.add_argument("--markdown", help="also write the table to this file")
    s.set_defaults(func=cmd_history)
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
