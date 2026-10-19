"""Create the lab's workflows through the Workflows API v4 (beta).

Three workflows, as a client might hand them over:
- "Discovery call follow-up (inherited)": books -> fixed delay -> follow-up. Fires even when the
  contact rescheduled or already had the call during the delay. This is the bug.
- "No-show nurture (inherited)": also writes follow_up_sent, so the two workflows share a property.
- "Discovery call follow-up (fixed)": same trigger, but contacts that are no longer 'booked' are
  unenrolled, and an if/then branch re-checks the status right before the follow-up.

The delay is 5 minutes so the scenarios finish in one sitting; in production it would be 2 days.
"""

from __future__ import annotations

from .client import HubSpot

DELAY_MINUTES = "5"


def _prop_filter(prop: str, values: list[str]) -> dict:
    return {
        "filterType": "PROPERTY",
        "property": prop,
        "operation": {
            "operator": "IS_ANY_OF",
            "values": values,
            "operationType": "ENUMERATION",
            "includeObjectsWithNoValueSet": False,
        },
    }


def _branch(filters: list[dict]) -> dict:
    return {
        "filterBranchType": "OR",
        "filterBranchOperator": "OR",
        "filters": [],
        "filterBranches": [
            {
                "filterBranchType": "AND",
                "filterBranchOperator": "AND",
                "filterBranches": [],
                "filters": filters,
            }
        ],
    }


def _enrolment(filters: list[dict], unenrol: bool) -> dict:
    return {
        "type": "LIST_BASED",
        "shouldReEnroll": False,
        "unEnrollObjectsNotMeetingCriteria": unenrol,
        "reEnrollmentTriggersFilterBranches": [],
        "listFilterBranch": _branch(filters),
    }


def _delay(action_id: str, next_id: str) -> dict:
    return {
        "type": "SINGLE_CONNECTION",
        "actionId": action_id,
        "actionTypeVersion": 0,
        "actionTypeId": "0-1",
        "connection": {"edgeType": "STANDARD", "nextActionId": next_id},
        "fields": {"delta": DELAY_MINUTES, "time_unit": "MINUTES"},
    }


def _set(action_id: str, prop: str, value: str, next_id: str | None) -> dict:
    a = {
        "type": "SINGLE_CONNECTION",
        "actionId": action_id,
        "actionTypeVersion": 0,
        "actionTypeId": "0-5",
        "fields": {"property_name": prop, "value": {"staticValue": value, "type": "STATIC_VALUE"}},
    }
    if next_id:
        a["connection"] = {"edgeType": "STANDARD", "nextActionId": next_id}
    return a


def _task(action_id: str, subject: str, next_id: str | None = None) -> dict:
    a = {
        "type": "SINGLE_CONNECTION",
        "actionId": action_id,
        "actionTypeVersion": 0,
        "actionTypeId": "0-3",
        "fields": {
            "task_type": "TODO",
            "subject": subject,
            "body": f"<p>{subject}. Created by the workflow lab.</p>",
            "priority": "NONE",
            "associations": [
                {
                    "target": {"associationCategory": "HUBSPOT_DEFINED", "associationTypeId": 10},
                    "value": {"type": "ENROLLED_OBJECT"},
                }
            ],
            "use_explicit_associations": "true",
        },
    }
    if next_id:
        a["connection"] = {"edgeType": "STANDARD", "nextActionId": next_id}
    return a


def _flow(name: str, enrolment: dict, actions: list[dict], start: str, next_available: str) -> dict:
    return {
        "isEnabled": True,
        "flowType": "WORKFLOW",
        "name": name,
        "type": "CONTACT_FLOW",
        "objectTypeId": "0-1",
        "startActionId": start,
        "nextAvailableActionId": next_available,
        "actions": actions,
        "enrollmentCriteria": enrolment,
        "timeWindows": [],
        "blockedDates": [],
        "customProperties": {},
        "suppressionListIds": [],
        "canEnrollFromSalesforce": False,
        "crmObjectCreationStatus": "COMPLETE",
    }


def inherited_follow_up() -> dict:
    return _flow(
        "Discovery call follow-up (inherited)",
        _enrolment(
            [
                _prop_filter("discovery_call_status", ["booked"]),
                _prop_filter("lab_variant", ["inherited"]),
            ],
            unenrol=False,
        ),
        [
            _delay("1", "2"),
            _set("2", "follow_up_sent", "true", "3"),
            _task("3", "Send the discovery call follow-up"),
        ],
        start="1",
        next_available="4",
    )


def no_show_nurture() -> dict:
    return _flow(
        "No-show nurture (inherited)",
        _enrolment([_prop_filter("discovery_call_status", ["no_show"])], unenrol=False),
        [
            _set("1", "follow_up_sent", "false", "2"),
            _task("2", "Offer the contact a new discovery call slot"),
        ],
        start="1",
        next_available="3",
    )


def fixed_follow_up() -> dict:
    still_booked = _branch([_prop_filter("discovery_call_status", ["booked"])])
    return _flow(
        "Discovery call follow-up (fixed)",
        _enrolment(
            [
                _prop_filter("discovery_call_status", ["booked"]),
                _prop_filter("lab_variant", ["fixed"]),
            ],
            unenrol=True,
        ),
        [
            _delay("1", "2"),
            {
                "type": "LIST_BRANCH",
                "actionId": "2",
                "listBranches": [
                    {
                        "branchName": "Still booked",
                        "filterBranch": still_booked,
                        "connection": {"edgeType": "STANDARD", "nextActionId": "3"},
                    }
                ],
                "defaultBranchName": "Rescheduled, completed or cancelled: no follow-up",
            },
            _set("3", "follow_up_sent", "true", "4"),
            _task("4", "Send the discovery call follow-up"),
        ],
        start="1",
        next_available="5",
    )


SPECS = {"inherited": inherited_follow_up, "no_show": no_show_nurture, "fixed": fixed_follow_up}


def apply(hs: HubSpot, which: list[str], enable: bool | None = None) -> dict[str, str]:
    """Create each workflow, or update it in place if one with the same name exists."""
    by_name = {}
    for item in hs.paged("/automation/v4/flows"):
        full = hs.get(f"/automation/v4/flows/{item['id']}")
        by_name[full.get("name")] = full
    result = {}
    for key in which:
        spec = SPECS[key]()
        if enable is not None:
            spec["isEnabled"] = enable
        current = by_name.get(spec["name"])
        if current:
            spec["revisionId"] = current["revisionId"]
            out = hs.request("PUT", f"/automation/v4/flows/{current['id']}", json=spec)
            result[key] = f"updated {out['id']} rev {out.get('revisionId')}"
        else:
            out = hs.post("/automation/v4/flows", spec)
            result[key] = f"created {out['id']}"
    return result
