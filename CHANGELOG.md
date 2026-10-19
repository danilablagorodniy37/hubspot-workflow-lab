# Changelog

## 0.1.0 (19 Oct 2026)

First release, built and measured on a HubSpot developer test account.

- `hslab setup`: the lab's contact properties, 30 contacts and 10 deals (idempotent).
- `hslab build`: four workflows through the Workflows API v4 (beta): the inherited discovery-call follow-up, a no-show nurture, a disabled old copy, and the fixed follow-up (unenrol when no longer booked, plus a "Still booked" branch before the follow-up).
- `hslab map`: every workflow exported as JSON and a map of triggers, re-enrolment, unenrolment and the properties each one reads and writes; flags the four workflows that write `follow_up_sent`.
- `hslab scenarios`: six scripted contacts on the live workflows. Inherited: 2 wrong follow-ups out of 3. Fixed: 0.
- `hslab history`: property history showing the inherited workflow setting the flag three minutes after the contact rescheduled.
- CI: lint, format, secret scan, tests, exported workflows parse as JSON.
