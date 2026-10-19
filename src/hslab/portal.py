"""Set up the 'inherited' portal: a property group, the properties the workflows use, test records.

Everything is idempotent: properties that exist are left alone, contacts are upserted by email,
deals are created only for contacts that do not have one yet.
"""

from __future__ import annotations

import random

from .client import HubSpot, HubSpotError

GROUP = "workflow_lab"

STATUS_OPTIONS = ["Booked", "Rescheduled", "Completed", "No show", "Cancelled"]

PROPERTIES: list[dict] = [
    {
        "name": "discovery_call_status",
        "label": "Discovery call status",
        "type": "enumeration",
        "fieldType": "select",
        "options": [
            {"label": s, "value": s.lower().replace(" ", "_"), "displayOrder": i}
            for i, s in enumerate(STATUS_OPTIONS)
        ],
    },
    {
        "name": "discovery_call_date",
        "label": "Discovery call date",
        "type": "datetime",
        "fieldType": "date",
    },
    {
        "name": "follow_up_sent",
        "label": "Follow-up sent",
        "type": "bool",
        "fieldType": "booleancheckbox",
        "options": [
            {"label": "Yes", "value": "true", "displayOrder": 0},
            {"label": "No", "value": "false", "displayOrder": 1},
        ],
    },
    {
        "name": "follow_up_sent_at",
        "label": "Follow-up sent at",
        "type": "datetime",
        "fieldType": "date",
    },
    {
        "name": "lab_variant",
        "label": "Lab variant",
        "type": "enumeration",
        "fieldType": "select",
        "options": [
            {"label": "Inherited", "value": "inherited", "displayOrder": 0},
            {"label": "Fixed", "value": "fixed", "displayOrder": 1},
        ],
    },
    {"name": "lab_scenario", "label": "Lab scenario", "type": "string", "fieldType": "text"},
]

FIRST = ["Amelia", "Tom", "Priya", "Olu", "Sophie", "Marek", "Grace", "Ravi", "Hannah", "Liam"]
LAST = [
    "Hughes",
    "Patel",
    "Okafor",
    "Nowak",
    "Khan",
    "Bennett",
    "Walsh",
    "Rossi",
    "Clarke",
    "Singh",
]
MATTERS = ["Probate", "Lease dispute", "Employment claim", "Conveyancing", "Will and LPA"]


def ensure_properties(hs: HubSpot) -> list[str]:
    created = []
    try:
        hs.post(
            "/crm/v3/properties/contacts/groups",
            {"name": GROUP, "label": "Workflow lab", "displayOrder": -1},
        )
        created.append(f"group {GROUP}")
    except HubSpotError as e:
        if e.status != 409:
            raise
    for prop in PROPERTIES:
        try:
            hs.post("/crm/v3/properties/contacts", prop | {"groupName": GROUP})
            created.append(prop["name"])
        except HubSpotError as e:
            if e.status != 409:
                raise
    return created


def seed_contacts(hs: HubSpot, count: int = 30, seed: int = 20261020) -> list[str]:
    """Upsert `count` fictional contacts by email; returns their ids."""
    rng = random.Random(seed)
    inputs = []
    for i in range(count):
        first, last = rng.choice(FIRST), rng.choice(LAST)
        email = f"{first}.{last}.{i}@example.com".lower()
        inputs.append(
            {
                "id": email,
                "idProperty": "email",
                "properties": {
                    "email": email,
                    "firstname": first,
                    "lastname": last,
                    "lifecyclestage": rng.choice(["lead", "marketingqualifiedlead", "opportunity"]),
                    "lab_scenario": "seed",
                },
            }
        )
    out = hs.post("/crm/v3/objects/contacts/batch/upsert", {"inputs": inputs})
    return [r["id"] for r in out.get("results", [])]


def seed_deals(hs: HubSpot, contact_ids: list[str], count: int = 10, seed: int = 20261020) -> int:
    rng = random.Random(seed)
    existing = hs.search(
        "deals",
        [{"propertyName": "dealname", "operator": "CONTAINS_TOKEN", "value": "lab"}],
        ["dealname"],
    )
    if len(existing) >= count:
        return 0
    inputs = []
    for cid in contact_ids[: count - len(existing)]:
        inputs.append(
            {
                "properties": {
                    "dealname": f"[lab] {rng.choice(MATTERS)} #{cid}",
                    "pipeline": "default",
                    "dealstage": "appointmentscheduled",
                    "amount": str(rng.choice([450, 900, 1500, 2400])),
                },
                "associations": [
                    {
                        "to": {"id": cid},
                        "types": [
                            {"associationCategory": "HUBSPOT_DEFINED", "associationTypeId": 3}
                        ],
                    }
                ],
            }
        )
    if inputs:
        hs.post("/crm/v3/objects/deals/batch/create", {"inputs": inputs})
    return len(inputs)
