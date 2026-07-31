# Phase 44: Remediation SLA & Escalation - Context

**Gathered:** 2026-07-20
**Status:** Ready for planning

<domain>
## Phase Boundary

Compute SLA status from a remediation task's `due_date`, automatically escalate breaches, and keep an immutable audit trail of every escalation — scoped to `compliance_remediation_tasks` only. The existing `tickets_escalation_service.py` is a different domain/schema (generic support tickets), not reusable as-is; only its pure `_compute_sla()` helper is reused. Depends on Phase 43 (both mutate the same `compliance_remediation_tasks` document — sequenced to avoid schema races).

</domain>

<decisions>
## Implementation Decisions

### SLA schema (captured during batch plan-phase attempt, 2026-07-20)
- **D-01:** Add new fields to the task — `sla_status`, `escalated`, `escalation_level` — rather than reusing/overloading the existing `status` (open/in_progress/resolved) or `priority` fields. Doesn't disturb existing code that already branches on those fields.

### SLA threshold definition
- **D-02:** Configurable per-tenant, mirroring the existing evidence-staleness threshold pattern (Phase 7, `STALE-02` — tenant admin sets a threshold via Settings, 1-365 day range precedent). A tenant admin configures the "at risk" window (days before `due_date`); `breached` = past `due_date` regardless of the at-risk setting.

### Escalation target
- **D-03:** Notify the task's assignee (re-notify) AND all tenant admins on breach. No "manager of assignee" concept exists in this codebase (confirmed by research) — tenant admins are the closest existing analog to an escalation authority, so they're included by default rather than left out.

### Escalation tiers/repeat behavior
- **D-04:** Tiered — `escalation_level` increments at increasing overdue intervals (e.g. day 1 / day 3 / day 7 past due). Matches SLA-01's explicit mention of `escalation_level` as a tracked field; a single fire-and-forget notification risks going unnoticed on a long-overdue compliance task.

### Claude's Discretion
- D-02, D-03, D-04 were explicitly deferred by the user ("You decide") — rationale above is Claude's, following "reuse existing precedent (staleness threshold, admin-as-escalation-authority), avoid silent single-notification loss" as the guiding principle.
- Exact tier day-boundaries (1/3/7 is a starting point, not locked — confirm reasonable defaults during planning).
- Default per-tenant "at risk" window value if not yet configured (mirror STALE-02's default, e.g. a small number of days).

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Milestone research (v3.2)
- `.planning/research/ARCHITECTURE.md` — new sibling module `compliance_remediation_sla_service.py` (not an extension of `tickets_escalation_service.py`), reuses only the pure `_compute_sla()` helper from `tickets_helpers.py`; background sweep uses the raw unwrapped `mongodb.db`, registered in `app_startup.py` alongside existing schedulers
- `.planning/research/PITFALLS.md` — **critical:** a scheduler built with `get_database()` instead of raw `mongodb.db` silently fail-closes to zero results forever (no tenant context in a background `asyncio` task) — this is the single highest-risk pitfall flagged for the whole v3.2 milestone; also flags the missing compound index `(tenantId, due_date, status)` and the "assuming `tickets`-shaped schema fields exist on `compliance_remediation_tasks` that don't" pitfall
- `.planning/research/SUMMARY.md` — explicitly names this phase's open product decisions (schema-extension shape, resolved as D-01) as needing discuss-phase input, which this session provided

### Prior-phase decisions
- `.planning/phases/07-evidence-lifecycle-staleness-chain-of-custody/*` — the STALE-02 configurable-threshold precedent informing D-02 (check the actual implementation for the settings-field pattern to replicate)

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `tickets_helpers.py::_compute_sla()` — pure function, reusable as-is per ARCHITECTURE.md (works off any dict with `due_date`/`status`).
- `tickets_escalation_service.py`/`scheduled_reports_service.py` — scheduler registration pattern to clone for the new `compliance_remediation_sla_service.py` background loop.
- Existing per-tenant Settings threshold pattern (STALE-02) — clone for the new SLA "at risk" window setting (D-02).
- Existing in-app notification system — delivery target for escalation notifications (D-03), consistent with Phase 42's decision for comment @mentions.

### Established Patterns
- Raw unwrapped `mongodb.db` required for any background scheduler — `TenantIsolatedCollection`'s fail-closed contextvar has no tenant context outside a request.
- Compound index `(tenantId, due_date, status)` does not yet exist on `compliance_remediation_tasks` — must be added for this phase to scale.

### Integration Points
- `app_startup.py` — where the new SLA scheduler registers, alongside `tickets_escalation_service.py`'s existing registration.
- Remediation task view (frontend) — needs to display `sla_status`/`escalation_level`, and an append-only escalation-history panel per SLA-02.

</code_context>

<specifics>
## Specific Ideas

None beyond the decisions captured above.

</specifics>

<deferred>
## Deferred Ideas

None — discussion stayed within phase scope.

</deferred>

---

*Phase: 44-remediation-sla-escalation*
*Context gathered: 2026-07-20*
