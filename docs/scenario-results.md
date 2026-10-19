# Scenario results

Run 19 Oct 2026 18:51 UTC on the HubSpot developer test account. Contacts act 2.0 min after booking; follow-ups read back after 9.0 min (the workflow delay is 5 min, a stand-in for 2 days).

| Variant | Scenario | Follow-up sent | Wanted | Result |
|---|---|---|---|---|
| inherited | rescheduled | yes | no | **wrong** |
| inherited | completed | yes | no | **wrong** |
| inherited | no_action | yes | yes | correct |
| fixed | rescheduled | no | no | correct |
| fixed | completed | no | no | correct |
| fixed | no_action | yes | yes | correct |

inherited: 2 wrong follow-up(s), fixed: 0 wrong follow-up(s)
