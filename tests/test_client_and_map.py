import json

import httpx
import pytest

from hslab.client import HubSpot, HubSpotError
from hslab.config import Settings
from hslab.flowmap import overlaps, summarise, to_markdown


def make(handler, **kw):
    client = httpx.Client(transport=httpx.MockTransport(handler), base_url="https://hub.test")
    return HubSpot(Settings(hubspot_access_token="t"), client=client, sleep=lambda s: None, **kw)


def test_retries_on_429_then_succeeds():
    calls = []

    def handler(request):
        calls.append(1)
        if len(calls) < 3:
            return httpx.Response(429, headers={"Retry-After": "1"}, text="slow down")
        return httpx.Response(200, json={"ok": True})

    assert make(handler).get("/x") == {"ok": True}
    assert len(calls) == 3


def test_client_errors_are_not_retried():
    calls = []

    def handler(request):
        calls.append(1)
        return httpx.Response(403, text="missing scope automation")

    with pytest.raises(HubSpotError, match="403"):
        make(handler).get("/automation/v4/flows")
    assert len(calls) == 1


def test_paging_follows_after_cursor():
    def handler(request):
        after = request.url.params.get("after")
        if after is None:
            return httpx.Response(
                200, json={"results": [{"id": "1"}], "paging": {"next": {"after": "2"}}}
            )
        return httpx.Response(200, json={"results": [{"id": "2"}]})

    assert [r["id"] for r in make(handler).paged("/automation/v4/flows")] == ["1", "2"]


def test_empty_token_is_a_clear_error(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    with pytest.raises(HubSpotError, match="HUBSPOT_ACCESS_TOKEN"):
        HubSpot(Settings(hubspot_access_token=""))


FOLLOW_UP = {
    "id": "101",
    "name": "Discovery call follow-up",
    "isEnabled": True,
    "objectTypeId": "0-1",
    "enrollmentCriteria": {
        "type": "LIST_BASED",
        "shouldReEnroll": False,
        "listFilterBranch": {
            "filterBranches": [
                {
                    "filters": [
                        {
                            "property": "discovery_call_status",
                            "operation": {"operator": "IS_ANY_OF", "values": ["booked"]},
                        }
                    ]
                }
            ]
        },
    },
    "actions": [
        {"actionId": "1", "actionTypeId": "0-1", "fields": {"delta": "5", "time_unit": "MINUTES"}},
        {
            "actionId": "2",
            "actionTypeId": "0-5",
            "fields": {"property_name": "follow_up_sent", "value": "true"},
        },
    ],
}

NO_SHOW = {
    "id": "102",
    "name": "No-show nurture",
    "isEnabled": True,
    "objectTypeId": "0-1",
    "enrollmentCriteria": {
        "type": "LIST_BASED",
        "shouldReEnroll": True,
        "filters": [
            {
                "property": "follow_up_sent",
                "operation": {"operator": "IS_EQUAL_TO", "value": "true"},
            }
        ],
    },
    "actions": [
        {
            "actionId": "1",
            "actionTypeId": "0-5",
            "fields": {"property_name": "follow_up_sent", "value": "false"},
        },
    ],
}


def test_summary_reads_writes_and_actions():
    s = summarise(json.loads(json.dumps(FOLLOW_UP)))
    assert s.reads == {"discovery_call_status"}
    assert s.writes == {"follow_up_sent"}
    assert s.actions[0].startswith("1: Delay 5 minutes")
    assert "Set property follow_up_sent" in s.actions[1]
    assert "discovery_call_status IS_ANY_OF booked" in s.enrolment


def test_overlaps_flag_shared_properties():
    notes = overlaps([summarise(FOLLOW_UP), summarise(NO_SHOW)])
    assert any("written by 2 workflows" in n for n in notes)
    assert any("read by No-show nurture" in n for n in notes)
    md = to_markdown([summarise(FOLLOW_UP), summarise(NO_SHOW)])
    assert "## Shared properties" in md and "Discovery call follow-up" in md
