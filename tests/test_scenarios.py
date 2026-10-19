from datetime import timedelta

from hslab.scenarios import EXPECTED, run, to_markdown


class FakeHubSpot:
    """Simulates the two workflows: 'inherited' sends a follow-up to everyone booked; 'fixed'
    only if the contact is still booked when the delay ends."""

    def __init__(self):
        self.contacts = {}

    def post(self, path, body):
        assert path.endswith("/batch/upsert")
        item = body["inputs"][0]
        cid = str(len(self.contacts) + 1)
        self.contacts[cid] = dict(item["properties"])
        return {"results": [{"id": cid}]}

    def patch(self, path, body):
        cid = path.rsplit("/", 1)[-1]
        self.contacts[cid].update(body["properties"])

    def get(self, path, **params):
        cid = path.rsplit("/", 1)[-1]
        c = self.contacts[cid]
        sent = c["lab_variant"] == "inherited" or c["discovery_call_status"] == "booked"
        return {"properties": {"follow_up_sent": "true" if sent else "false"}}


def test_inherited_variant_shows_the_bug_and_fixed_variant_does_not():
    outcomes = run(
        FakeHubSpot(),
        timedelta(seconds=0),
        timedelta(seconds=0),
        sleep=lambda s: None,
        log=lambda m: None,
    )
    by = {(o.variant, o.scenario): o for o in outcomes}
    assert len(outcomes) == 6
    assert not by[("inherited", "rescheduled")].ok and not by[("inherited", "completed")].ok
    assert by[("inherited", "no_action")].ok
    assert all(by[("fixed", s)].ok for s in EXPECTED)
    md = to_markdown(outcomes, "test run")
    assert "inherited: 2 wrong follow-up(s), fixed: 0 wrong follow-up(s)" in md
