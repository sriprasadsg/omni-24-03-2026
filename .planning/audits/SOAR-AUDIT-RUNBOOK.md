---
purpose: scoped feature audit
target: SOAR (Security Orchestration, Automation and Response)
written: 2026-08-25
status: not yet executed
---

# SOAR Feature Audit — Runbook

## Why this exists

User asked broadly "are there any features not working, like SOAR and other
features?" No time/budget left in the session that raised the question to do
a real audit — this scopes one down to something a fresh session can execute
directly instead of re-deriving context.

## Why SOAR specifically, and what to actually check

This session found a real, previously-undetected bug in the cloud/SaaS
provider integrations (Phase 32): three "SIEM poll" functions had unit tests
that asserted hardcoded fake data as *correct* behavior — the tests passed,
CI was green, but the feature fabricated findings in production. The tests
didn't catch it because they mocked the exact thing that was fake.

SOAR is a good next audit target for the same failure mode: it has real
implementation files and a passing test suite (`test_soar_and_ml.py`, part of
every full-suite run this session, no failures), but that only proves the
code does what its own mocks say it does — not that the connectors make real
calls, or that a playbook actually executes an action against a real target
system.

**The audit question isn't "do the tests pass" (already known: yes). It's:
do the connectors and playbook execution actually call out to real systems,
or do any of them silently fabricate/simulate results the way the cloud
providers did?**

## Files to read first

- `backend/soar_engine.py` — core playbook execution
- `backend/soar_endpoints.py` — API surface
- `backend/soar_connectors_security.py`, `soar_connectors_cloud.py`,
  `soar_connectors_messaging.py` — the actual outbound integration points
  (most likely place for a fabrication bug, same shape as the cloud-provider
  one: a `_make_*_client()` that returns a mock, or a hardcoded response list)
- `backend/soar_integrations.py`
- `backend/tests/test_soar_and_ml.py` — read what it actually mocks; a test
  that patches the connector's real-call function (not just its own service
  layer) and asserts a fixed count is the same smell that hid the Phase 32 bug
- Frontend: `components/SOARDashboard.tsx` — what does it display, and does
  that data come from a real execution path or a seeded/demo one?

## Method (same as the Phase 32 investigation)

1. For each connector file, find every "make client" / "call API" function.
   Check: does it actually import and use a real SDK/HTTP client, or does it
   return a mock/hardcoded object? (grep for `mock`, `Mock`, `TODO`,
   `simulated`, `# fake`, hardcoded response literals — same signals that
   found the cloud-provider bug.)
2. For each, check whether the test file mocks the connector's *outbound
   call* (legitimate — proves the surrounding logic works) or mocks
   *something further downstream than where the real bug would be* (i.e.,
   does the test actually exercise the code that would be broken, or does it
   patch around it).
3. Check whether SOAR playbooks that claim to take real remediation actions
   (block IP, disable account, isolate host, etc.) actually dispatch to a
   real target (agent instruction queue / API call) or just write a DB
   record and call it done.
4. Cross-reference against any existing `*-REVIEW.md` for whatever phase
   built SOAR — search `.planning/phases/*/*-REVIEW.md` for "soar" to see if
   a prior code review already flagged something here that was never
   circled back to (this is exactly how the Phase 32 bug was found — a
   2026-07-27 review had flagged it and it sat unfixed for a month).

## Expected output

A findings list in the same shape as `32-REVIEW.md`: file:line, what's
fabricated vs real, severity, suggested fix — not a full remediation in the
same pass unless the findings are small and clearly scoped (mirror how
Phase 32's critical fix was a small, well-evidenced change once the bug was
actually found).

## Not in scope for this pass

- Other features the user mentioned as "and other features" — this runbook
  is SOAR only. If SOAR turns out clean, the same method (grep for
  mock-shaped client constructors + hardcoded response literals, check what
  the tests actually exercise) is reusable for auditing another feature next.
