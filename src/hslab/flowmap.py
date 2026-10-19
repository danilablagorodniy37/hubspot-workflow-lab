"""Export every workflow as JSON and write a one-page map: what enrols a record, what each workflow
does, which properties it reads and writes, and where two workflows touch the same property.

The Workflows API v4 is in beta; the parser walks the JSON generically instead of trusting one
schema, so a field it does not know shows up in the raw export rather than breaking the map.
"""

from __future__ import annotations

import json
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .client import HubSpot

ACTION_NAMES = {
    "0-1": "Delay",
    "0-3": "Create task",
    "0-4": "Send marketing email",
    "0-5": "Set property",
    "0-8": "Send internal email",
    "0-9": "Send in-app notification",
    "0-14": "Create record",
    "0-35": "Delay until date",
}

READ_KEYS = ("property", "propertyName")
WRITE_KEYS = ("property_name", "targetProperty", "propertyName")


@dataclass
class FlowSummary:
    id: str
    name: str
    enabled: bool
    object_type: str
    enrolment: str
    re_enrol: bool | None
    actions: list[str] = field(default_factory=list)
    reads: set[str] = field(default_factory=set)
    writes: set[str] = field(default_factory=set)


def _walk(node: Any):
    if isinstance(node, dict):
        yield node
        for v in node.values():
            yield from _walk(v)
    elif isinstance(node, list):
        for v in node:
            yield from _walk(v)


def _filters(criteria: Any) -> list[str]:
    out = []
    for d in _walk(criteria):
        prop = next((d[k] for k in READ_KEYS if isinstance(d.get(k), str)), None)
        op = d.get("operation") or d
        operator = op.get("operator") if isinstance(op, dict) else None
        if prop and operator:
            values = op.get("values") or ([op["value"]] if "value" in op else [])
            out.append(f"{prop} {operator} {', '.join(map(str, values))}".strip())
    return out


def summarise(flow: dict) -> FlowSummary:
    crit = flow.get("enrollmentCriteria") or {}
    filters = _filters(crit)
    enrolment = f"{crit.get('type', '?')}: " + (
        "; ".join(filters) if filters else "(no property filters)"
    )
    s = FlowSummary(
        id=str(flow.get("id", "?")),
        name=flow.get("name", "(unnamed)"),
        enabled=bool(flow.get("isEnabled")),
        object_type=str(flow.get("objectTypeId", "?")),
        enrolment=enrolment,
        re_enrol=crit.get("shouldReEnroll"),
    )
    for d in _walk(crit):
        for k in READ_KEYS:
            if isinstance(d.get(k), str):
                s.reads.add(d[k])
    for action in flow.get("actions") or []:
        type_id = str(action.get("actionTypeId", action.get("type", "?")))
        label = ACTION_NAMES.get(type_id, f"action {type_id}")
        fields = action.get("fields") or {}
        written = [fields[k] for k in WRITE_KEYS if isinstance(fields.get(k), str)]
        detail = ""
        if type_id == "0-1":
            detail = f" {fields.get('delta', '?')} {str(fields.get('time_unit', '')).lower()}"
        if written:
            detail += " " + ", ".join(written)
            s.writes.update(written)
        if action.get("type") in ("LIST_BRANCH", "STATIC_BRANCH") or "listBranches" in action:
            label = "If/then branch"
            for d in _walk(action):
                for k in READ_KEYS:
                    if isinstance(d.get(k), str):
                        s.reads.add(d[k])
        s.actions.append(f"{action.get('actionId', '?')}: {label}{detail}")
    return s


def overlaps(summaries: list[FlowSummary]) -> list[str]:
    writers: dict[str, list[str]] = defaultdict(list)
    readers: dict[str, list[str]] = defaultdict(list)
    for s in summaries:
        for p in s.writes:
            writers[p].append(s.name)
        for p in s.reads:
            readers[p].append(s.name)
    notes = []
    for p, ws in sorted(writers.items()):
        if len(ws) > 1:
            notes.append(f"`{p}` is written by {len(ws)} workflows: {', '.join(sorted(ws))}")
        for reader in sorted(set(readers.get(p, []))):
            others = sorted(set(ws) - {reader})
            if others:
                notes.append(f"`{p}` is written by {', '.join(others)} and read by {reader}")
    return notes


def fetch_all(hs: HubSpot) -> list[dict]:
    listing = list(hs.paged("/automation/v4/flows"))
    return [hs.get(f"/automation/v4/flows/{f['id']}") for f in listing]


def export(flows: list[dict], directory: str | Path) -> list[Path]:
    out_dir = Path(directory)
    out_dir.mkdir(parents=True, exist_ok=True)
    paths = []
    for f in flows:
        slug = "".join(c if c.isalnum() else "-" for c in f.get("name", "flow").lower()).strip("-")
        p = out_dir / f"{slug or 'flow'}.json"
        p.write_text(json.dumps(f, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        paths.append(p)
    return paths


def to_markdown(summaries: list[FlowSummary]) -> str:
    lines = [
        "# Workflow map",
        "",
        "Generated by `hslab map` from the Workflows API v4. One section per workflow, then",
        "the places where two workflows read or write the same property: that is where changes",
        "break things.",
        "",
        "| Workflow | On | Enrols when | Re-enrol | Reads | Writes |",
        "|---|---|---|---|---|---|",
    ]
    for s in summaries:
        lines.append(
            f"| {s.name} | {'yes' if s.enabled else 'no'} | {s.enrolment} | {s.re_enrol} | "
            f"{', '.join(sorted(s.reads)) or '-'} | {', '.join(sorted(s.writes)) or '-'} |"
        )
    for s in summaries:
        lines += ["", f"## {s.name} (id {s.id})", ""] + [f"- {a}" for a in s.actions]
    notes = overlaps(summaries)
    lines += ["", "## Shared properties", ""] + ([f"- {n}" for n in notes] or ["- none"])
    return "\n".join(lines) + "\n"
