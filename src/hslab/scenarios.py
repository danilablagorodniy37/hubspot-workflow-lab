"""Scripted scenarios against the real workflows: book a call, then reschedule, complete or do
nothing during the delay, and read back whether the follow-up fired.

Each run creates fresh contacts (one per variant and scenario) so enrolment history is clean, and
compares the outcome with what the business wants: a follow-up only when nothing happened.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from .client import HubSpot

SCENARIOS = ("rescheduled", "completed", "no_action")
VARIANTS = ("inherited", "fixed")
# What the business wants: a follow-up only if the contact did nothing after booking.
EXPECTED = {"rescheduled": False, "completed": False, "no_action": True}


@dataclass
class Outcome:
    variant: str
    scenario: str
    contact_id: str
    follow_up_sent: bool
    expected: bool

    @property
    def ok(self) -> bool:
        return self.follow_up_sent == self.expected


def _ms(dt: datetime) -> str:
    return str(int(dt.timestamp() * 1000))


def book(hs: HubSpot, run: str, variant: str, scenario: str, call_in: timedelta) -> str:
    email = f"lab-{run}-{variant}-{scenario}@example.com"
    props = {
        "email": email,
        "firstname": "Lab",
        "lastname": f"{variant} {scenario}",
        "lab_variant": variant,
        "lab_scenario": f"{run}:{scenario}",
        "follow_up_sent": "false",
        "discovery_call_date": _ms(datetime.now(UTC) + call_in),
        "discovery_call_status": "booked",
    }
    out = hs.post(
        "/crm/v3/objects/contacts/batch/upsert",
        {"inputs": [{"id": email, "idProperty": "email", "properties": props}]},
    )
    return out["results"][0]["id"]


def act(hs: HubSpot, contact_id: str, scenario: str, new_call_in: timedelta) -> None:
    if scenario == "rescheduled":
        props = {
            "discovery_call_status": "rescheduled",
            "discovery_call_date": _ms(datetime.now(UTC) + new_call_in),
        }
    elif scenario == "completed":
        props = {"discovery_call_status": "completed"}
    else:
        return
    hs.patch(f"/crm/v3/objects/contacts/{contact_id}", {"properties": props})


def read_sent(hs: HubSpot, contact_id: str) -> bool:
    data = hs.get(f"/crm/v3/objects/contacts/{contact_id}", properties="follow_up_sent")
    return str(data.get("properties", {}).get("follow_up_sent", "")).lower() == "true"


def run(
    hs: HubSpot,
    act_after: timedelta = timedelta(minutes=2),
    check_after: timedelta = timedelta(minutes=9),
    sleep=time.sleep,
    log=print,
) -> list[Outcome]:
    run_id = datetime.now(UTC).strftime("%m%d%H%M")
    booked: dict[tuple[str, str], str] = {}
    for v in VARIANTS:
        for s in SCENARIOS:
            booked[(v, s)] = book(hs, run_id, v, s, call_in=timedelta(days=2))
            log(f"booked {v}/{s}: contact {booked[(v, s)]}")
    log(f"waiting {act_after} before the contacts act")
    sleep(act_after.total_seconds())
    for (_variant, s), cid in booked.items():
        act(hs, cid, s, new_call_in=timedelta(days=5))
    log(f"waiting {check_after - act_after} for the workflow delays to pass")
    sleep((check_after - act_after).total_seconds())
    outcomes = [
        Outcome(v, s, cid, read_sent(hs, cid), EXPECTED[s]) for (v, s), cid in booked.items()
    ]
    return outcomes


def to_markdown(outcomes: list[Outcome], run_note: str = "") -> str:
    lines = [
        "# Scenario results",
        "",
        run_note,
        "",
        "| Variant | Scenario | Follow-up sent | Wanted | Result |",
        "|---|---|---|---|---|",
    ]
    for o in outcomes:
        lines.append(
            f"| {o.variant} | {o.scenario} | {'yes' if o.follow_up_sent else 'no'} | "
            f"{'yes' if o.expected else 'no'} | {'correct' if o.ok else '**wrong**'} |"
        )
    wrong = {v: sum(1 for o in outcomes if o.variant == v and not o.ok) for v in VARIANTS}
    lines += ["", ", ".join(f"{v}: {n} wrong follow-up(s)" for v, n in wrong.items())]
    return "\n".join(lines) + "\n"
