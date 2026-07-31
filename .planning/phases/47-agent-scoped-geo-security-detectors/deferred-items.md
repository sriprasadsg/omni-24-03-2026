# Deferred Items — Phase 47

## 1. `backend/ueba_service.py` exceeds CLAUDE.md's 500-line cap (pre-existing)

- **Found during:** 47-01, Task 2.
- **Detail:** `ueba_service.py` was already 572 lines before this plan touched it (confirmed in 47-RESEARCH.md's Sources section: "read in full (572 lines)"). Plan 47-01's minimal, non-breaking fix (`persist_security_alert = _persist_alert` plus an explanatory comment) added 12 lines, bringing it to 584.
- **Why not fixed here:** 47-01's `<prohibitions>` explicitly scope this plan to the alias only ("MUST NOT rename `_persist_alert`... MUST NOT write a second/parallel alert-insert path"). Splitting `ueba_service.py` to get under the 500-line cap is an unrelated structural refactor, out of scope for a Wave-0 prerequisite bugfix plan, and risks destabilizing the five now-reactivated alert call sites this plan intentionally leaves untouched.
- **Recommendation:** If a future phase touches `ueba_service.py` again, consider splitting the alert-persistence helper (`_persist_alert`/`persist_security_alert`) into a small `alert_persistence_service.py` sibling module, mirroring the `agent_heartbeat_alerts_service.py` split Phase 46 already did for a similar reason.
