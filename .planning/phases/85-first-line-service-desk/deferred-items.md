# Phase 85 deferred items

## Found during 85-25 (2026-11-09)

- `backend/tests/test_service_desk_lifecycle.py::test_this_fixed_it_resolves_the_ticket_and_only_this_does` fails
  after 14:30 UTC on 2026-11-09: the test confirms the ticket at the fixed moment `NOW = 2026-11-09 14:30 UTC`
  while the ticket's hold started at the real wall clock (`hold_started_at` from the answer run), so
  `total_hold_duration` is negative (-6392 s at 16:16 UTC). It touches `lifecycle.confirm` and the ticket write
  helpers only, not the routes or projection changed by 85-25, so it is out of scope here. Fix: build the
  ticket's hold start from `NOW` (or freeze the clock) in that test. Same class as the Phase 84 wall-clock tests.
