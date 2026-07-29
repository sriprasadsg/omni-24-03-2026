# Phase 44: Remediation SLA & Escalation - Research

**Researched:** 2026-07-21
**Domain:** Backend scheduled sweep + tenant-scoped notification + append-only audit trail, on an existing FastAPI/Motor/MongoDB multi-tenant GRC platform
**Confidence:** HIGH — this is 100% internal codebase archaeology against files that exist today (no external library research needed); every claim below was verified by reading the actual source, not milestone-level research summaries alone.

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions
- **D-01:** Add new fields to the task — `sla_status`, `escalated`, `escalation_level` — rather than reusing/overloading the existing `status` (open/in_progress/resolved) or `priority` fields. Doesn't disturb existing code that already branches on those fields.
- **D-02:** Configurable per-tenant, mirroring the existing evidence-staleness threshold pattern (Phase 7, `STALE-02` — tenant admin sets a threshold via Settings, 1-365 day range precedent). A tenant admin configures the "at risk" window (days before `due_date`); `breached` = past `due_date` regardless of the at-risk setting.
- **D-03:** Notify the task's assignee (re-notify) AND all tenant admins on breach. No "manager of assignee" concept exists in this codebase (confirmed by research) — tenant admins are the closest existing analog to an escalation authority, so they're included by default rather than left out.
- **D-04:** Tiered — `escalation_level` increments at increasing overdue intervals (e.g. day 1 / day 3 / day 7 past due). Matches SLA-01's explicit mention of `escalation_level` as a tracked field; a single fire-and-forget notification risks going unnoticed on a long-overdue compliance task.

### Claude's Discretion
- D-02, D-03, D-04 were explicitly deferred by the user ("You decide") — rationale is Claude's, following "reuse existing precedent (staleness threshold, admin-as-escalation-authority), avoid silent single-notification loss" as the guiding principle.
- Exact tier day-boundaries (1/3/7 is a starting point, not locked — confirm reasonable defaults during planning).
- Default per-tenant "at risk" window value if not yet configured (mirror STALE-02's default, e.g. a small number of days).

### Deferred Ideas (OUT OF SCOPE)
None — discussion stayed within phase scope.
</user_constraints>

## Project Constraints (from CLAUDE.md)

- Keep files under 500 lines — the new `compliance_remediation_sla_service.py`, `compliance_remediation_sla_endpoints.py`, and `test_compliance_remediation_sla.py` must each stay under this limit; split if the sweep logic + settings lookup + escalation-history logic grows too large for one file.
- Validate input at system boundaries — the at-risk-window PATCH endpoint must use Pydantic `Field(ge=1, le=365)` bounds (cloned from `StalenessThresholdUpdate`), not manual range checks.
- Never create documentation files unless explicitly requested — no extra `.md` files beyond what GSD's own workflow produces.
- Prefer editing existing files over creating new ones — `RemediationDashboard.tsx` and `RemediationTaskModal.tsx` must be edited in place (Pitfall 6), not replaced with new components.
- Never commit secrets/credentials/.env files — not applicable to this phase's scope (no new secrets introduced).

## Summary

This phase adds SLA computation, tiered auto-escalation, and an immutable escalation history to `compliance_remediation_tasks`. The milestone-level `ARCHITECTURE.md` says to reuse `tickets_helpers._compute_sla()` "as-is" — **direct code inspection shows this is wrong and `PITFALLS.md` Pitfall 10 already corrects it**: `_compute_sla()` hardcodes an `at_risk` cutoff of "< 1 hour remaining" (tickets are hour-scale SLAs) and checks `ticket.get("status") in ("resolved", "closed")`, but `compliance_remediation_tasks.status` is a 3-value enum (`open`/`in_progress`/`resolved`, no `closed`). D-02 requires a **configurable, per-tenant, day-scale** at-risk window — structurally incompatible with the hour-scale hardcoded constant. **Port the logic shape (due-date parsing, hold-aware math is NOT needed here since remediation tasks have no hold/pause concept), not the function itself.**

The strongest implementation precedent is not `tickets_escalation_service.py` (older, different collection, different tenant-scoping story) but **`ticketing_bridge.py`'s `run_close_loop_pass`/`start_close_loop_scheduler`** — the immediately preceding Phase 43 plan, operating on the exact same `compliance_remediation_tasks` collection, with the exact same raw-`mongodb.db`-required, per-document `tenantId`-extraction pattern this phase needs. Clone that file's structure, not `tickets_escalation_service.py`'s.

For D-02 (configurable per-tenant threshold), `evidence_staleness.py` + `compliance_evidence_lifecycle_endpoints.py` (Phase 7, STALE-02) is an exact, ready-to-clone template: a `system_settings` collection document keyed by `{"type": "<name>", "tenantId": <id>}` with a global (`tenantId` absent) fallback and a hardcoded final default, a `GET`/`PATCH` endpoint pair, Pydantic `Field(ge=1, le=365)` bounds, and an admin-role gate on the PATCH only.

For SLA-02 (immutable, append-only history), the codebase has **two competing precedents**: `tickets_escalation_service.py` appends to a `history[]` array field via `$push` (mutable field, immutable only by convention), while the two most recent audit-trail features — Phase 7's `evidence_audit_log` and Phase 42's `control_comments` — both use a **dedicated collection** with no update/delete route ("absence IS the enforcement," per `control_comments`' own comment). Recommend the dedicated-collection pattern: it is the codebase's converging convention for anything described as "immutable" and "viewable by a compliance admin" (matches SLA-02's wording almost verbatim to COC-02's), and it is queryable/indexable independently of the 16MB embedded-document ceiling that `$push`-to-array patterns risk at scale.

**Primary recommendation:** New sibling module `compliance_remediation_sla_service.py`, cloned structurally from `ticketing_bridge.py`'s scheduler pair; a new `remediation_escalations` collection cloned from `evidence_audit_log`'s shape and read-endpoint pattern; SLA/at-risk settings cloned from `evidence_staleness.py`'s `system_settings` pattern; escalation notification cloned from `control_comments_endpoints.py`'s `get_notification_service(db).send_alert(...)` call shape, with tenant-admin recipients resolved via the `db.users.find({"tenantId": ..., "role": {"$in": ADMIN_ROLES}})` pattern already used in `notification_manager.py`.

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| SLA status computation (ok/at_risk/breached) | API / Backend | — | Pure function of `due_date` + tenant setting; must be computed both on-read (task view) and on-sweep (scheduler) — same function, two call sites |
| Per-tenant "at risk" window setting | Database / Storage | API / Backend | `system_settings` doc, read/written via a settings endpoint, mirroring STALE-02 |
| Breach detection + escalation trigger | API / Backend | Database / Storage | Background `asyncio` scheduler sweep against raw `mongodb.db`, not request-scoped |
| Escalation notification delivery | API / Backend | — | `notification_service.NotificationService.send_alert()`, in-app channel only (mirrors CMT-01's `channels=[]` in-app-only precedent) |
| Escalation history persistence | Database / Storage | API / Backend | New `remediation_escalations` collection; read-only endpoint, no mutation route |
| SLA badge / escalation panel display | Browser / Client | Frontend Server (SSR N/A — this app is CSR React, no SSR tier) | `RemediationDashboard.tsx` table + `RemediationTaskModal.tsx` detail panel |

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| SLA-01 | SLA status (ok/at_risk/breached) computed from `due_date`; breach triggers escalation notification | New `compute_remediation_sla()` pure function (Code Examples); background sweep cloned from `ticketing_bridge.run_close_loop_pass`; notification via `control_comments_endpoints.py`'s `send_alert` call shape |
| SLA-02 | Immutable, append-only escalation history, viewable by a compliance admin | New `remediation_escalations` collection cloned from `evidence_audit_log` + `compliance_evidence_lifecycle_endpoints.py`'s CoC read-endpoint pattern; no PATCH/DELETE route = enforcement |
</phase_requirements>

## Standard Stack

### Core
This phase adds **no new third-party dependencies** — it is 100% internal code following existing FastAPI + Motor (async MongoDB driver) + Pydantic patterns already present in the codebase.

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| motor (already installed) | existing pinned version | Async MongoDB driver for the new collection/scheduler | Already used by every other service module in `backend/` |
| pydantic (already installed) | existing pinned version | `TaskUpdate`/settings request models, `Field(ge=1, le=365)` bounds | Matches `StalenessThresholdUpdate` precedent exactly |

### Supporting
None — no new packages required.

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| New `remediation_escalations` collection | `$push` to a `history[]` array on the task doc (tickets-style) | Array approach matches the *older* `tickets_escalation_service` precedent but not the two most recent "immutable audit trail" features in this codebase; also risks the 16MB doc-size ceiling and can't be indexed/queried independently |
| Reusing `_compute_sla()` unmodified | Writing a new `compute_remediation_sla()` | `_compute_sla()`'s hour-scale hardcoded threshold and `("resolved","closed")` status check are structurally wrong for this phase's day-scale, 3-status-enum requirement — confirmed by direct code read, not assumption |

## Package Legitimacy Audit

Not applicable — this phase installs no external packages.

## Architecture Patterns

### System Architecture Diagram

```
[Background asyncio task, app_startup.py]
        │  registered next to tickets_escalation_service /
        │  ticketing_bridge close-loop scheduler (raw mongodb.db)
        ▼
[compliance_remediation_sla_service.start_remediation_sla_scheduler(db)]
        │  loop every 300s (matches Phase 43's 5-min cadence)
        ▼
[run_sla_pass(db)]
        │  db.compliance_remediation_tasks.find(
        │      {"status": {"$in": ["open","in_progress"]}})
        │  — no tenantId filter at query level (raw db, all-tenant sweep by design)
        ▼
   for each task:
        │  tenant_id = task["tenantId"]           ← per-doc tenant extraction
        │  window = get_sla_at_risk_window(db, tenant_id)   ← STALE-02-style lookup
        │  compute_remediation_sla(task, window)   ← pure fn, sets sla_status
        ▼
   ┌─────────────────────────────┬─────────────────────────────────┐
   │ sla_status == "at_risk"     │ sla_status == "breached"         │
   │ (no escalation trigger —    │ escalation_level = f(days_overdue)│
   │  SLA-01 only requires       │ if new level > current:          │
   │  breach to trigger)         │   $set sla_status/escalated/level │
   │                             │   on compliance_remediation_tasks │
   │                             │   insert_one → remediation_escalations (new collection, append-only)
   │                             │   send_alert() → assignee + tenant admins (in-app, channels=[])
   │                             │   broadcast_remediation_update() → websocket (tenant-scoped)
   └─────────────────────────────┴─────────────────────────────────┘

[Frontend: RemediationDashboard.tsx]        [Frontend: RemediationTaskModal.tsx]
   task.sla_status → new SLA_COLORS badge      escalation history panel, cloned from
   (clone STATUS_COLORS pattern, line 9-14)    ChainOfCustodyPanel.tsx's lazy-expand
                                                fetch-on-toggle pattern
```

### Recommended Project Structure
```
backend/
├── compliance_remediation_sla_service.py   # NEW — pure compute_remediation_sla() + run_sla_pass()/scheduler
├── compliance_remediation_sla_endpoints.py # NEW — GET/PATCH at-risk-window setting, GET escalation history
├── compliance_remediation_service.py       # MODIFIED — create_task() gains sla_status/escalated/escalation_level defaults
├── compliance_remediation_endpoints.py     # MODIFIED — TaskUpdate model, if SLA fields need manual override (likely not — system-managed only)
├── database.py                             # MODIFIED — new indexes (see Pitfall 1)
├── app_startup.py                          # MODIFIED — register new scheduler
├── router_registry.py                      # MODIFIED — register new endpoints router (Pitfall 7 in PITFALLS.md)
└── tests/
    └── test_compliance_remediation_sla.py  # NEW — clone test_ticketing_bridge.py's shape

components/
├── RemediationDashboard.tsx                # MODIFIED — SLA_COLORS badge in task table
└── RemediationTaskModal.tsx                # MODIFIED — escalation history panel (clone ChainOfCustodyPanel.tsx)

services/apiService.ts                      # MODIFIED — fetchRemediationEscalations(taskId), settings get/patch calls
```

### Pattern 1: Raw-db background sweep with per-document tenant extraction
**What:** Scheduler receives `db` (raw `mongodb.db`, Motor client) as a passed-in parameter, never resolves it itself via `get_database()`.
**When to use:** Any `asyncio.create_task()`-started loop in `app_startup.py` — there is no HTTP request context, so `TenantIsolatedDatabase`'s contextvar-based tenant resolution silently fails closed (see Common Pitfalls).
**Example:**
```python
# Source: backend/ticketing_bridge.py (Phase 43, verified by direct read — same collection)
async def run_sla_pass(db) -> None:
    try:
        query = {"status": {"$in": ["open", "in_progress"]}}
        cursor = db.compliance_remediation_tasks.find(query, {"_id": 0})
        async for task in cursor:
            tenant_id = task.get("tenantId", "")
            if not tenant_id:
                continue
            # ... per-task SLA compute + escalate, scoped by extracted tenant_id
    except Exception as exc:
        logger.error("SLA pass failed: %s", exc)


async def start_remediation_sla_scheduler(db) -> None:
    logger.info("Remediation SLA scheduler started (interval=300s)")
    while True:
        await run_sla_pass(db)
        await asyncio.sleep(300)
```

### Pattern 2: Per-tenant configurable threshold with global fallback and hardcoded final default
**What:** `system_settings` collection, doc shape `{"type": "<setting_name>", "tenantId": <id>, <valueField>: <value>}`; lookup tries tenant-scoped doc, then global doc (`tenantId` absent via `$exists: False`), then a hardcoded constant.
**When to use:** D-02's per-tenant "at risk" window — clone verbatim from `evidence_staleness.get_staleness_threshold()`.
**Example:**
```python
# Source: backend/evidence_staleness.py (Phase 7, STALE-02) — clone exactly, rename type/field
async def get_sla_at_risk_window(db, tenant_id) -> int:
    def _safe(raw_val: int) -> int:
        return max(1, raw_val)
    raw = db._db if hasattr(db, "_db") else db
    if tenant_id:
        doc = await raw.system_settings.find_one(
            {"type": "remediation_sla_at_risk", "tenantId": tenant_id}
        )
        if doc and isinstance(doc.get("windowDays"), int):
            return _safe(doc["windowDays"])
    doc = await raw.system_settings.find_one(
        {"type": "remediation_sla_at_risk", "tenantId": {"$exists": False}}
    )
    if doc and isinstance(doc.get("windowDays"), int):
        return _safe(doc["windowDays"])
    return 3  # default — see Open Questions for justification
```
**Note:** the sweep passes raw `db` (already unwrapped `mongodb.db`), so `db._db if hasattr(db, "_db") else db` is defensive but the `hasattr` branch will never trigger inside the scheduler — it only matters if this same function is also called from a request-scoped endpoint (`GET /api/settings/remediation-sla`), where `db` **will** be a `TenantIsolatedDatabase` wrapper. Keep the guard for that dual call-site reason, exactly as `evidence_staleness.py` does.

### Pattern 3: Dedicated append-only audit-trail collection with no mutation route
**What:** A separate collection (not an array field), written only via `insert_one`, read via a tenant-scoped `GET` endpoint sorted by timestamp, with **no** corresponding `PATCH`/`DELETE`/`PUT` route registered anywhere.
**When to use:** SLA-02's "immutable, append-only... viewable by a compliance admin" — this is the exact phrasing pattern `evidence_audit_log` (COC-02) and `control_comments` (CMT-01, D-03) both already satisfy this way.
**Example:**
```python
# Source: backend/compliance_evidence_lifecycle_endpoints.py:108-135 (Phase 7, COC-02) — read-endpoint template
@router.get("/api/compliance/remediation-tasks/{task_id}/escalations")
async def get_remediation_escalations(task_id: str, current_user=Depends(get_current_user)):
    db = get_database()
    raw = db._db if hasattr(db, "_db") else db
    tenant_id = getattr(current_user, "tenant_id", None)
    query: dict = {"task_id": task_id}
    if tenant_id:
        query["tenantId"] = tenant_id
    entries = await raw.remediation_escalations.find(
        query, {"_id": 0}
    ).sort("created_at", 1).to_list(length=500)
    return {"task_id": task_id, "entries": entries}
# No PATCH/DELETE route is defined anywhere for remediation_escalations — absence IS the enforcement
# (verbatim rationale from control_comments_endpoints.py:70-71, D-03).
```

### Anti-Patterns to Avoid
- **Calling `get_database()` inside the scheduler or the pure `compute_remediation_sla()` function:** breaks the raw-db requirement; only endpoint handlers (request-scoped, have a `current_user`) should call `get_database()`.
- **Reusing `_compute_sla()` unmodified:** silently wrong `at_risk` semantics (hour-scale, not day-scale) and status-check mismatch (`"closed"` never exists on remediation tasks). Write a new function; port logic shape only.
- **`$push`-ing escalation entries onto the task document:** inconsistent with the two most recent "immutable audit trail" precedents in this codebase (both use dedicated collections); also risks large-document growth at scale.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Per-tenant configurable setting storage/lookup | A new settings abstraction | `system_settings` collection + tenant-then-global-then-default lookup (clone `evidence_staleness.get_staleness_threshold`) | Exact precedent already exists, already tested, already has an admin-gated PATCH pattern |
| Multi-channel/in-app notification delivery | A new notification dispatch path | `notification_service.get_notification_service(db).send_alert(...)` with `channels=[]` for in-app-only | Already used identically for Phase 42's @mention notifications; `channels=[]` is explicitly documented (notification_service.py:42-48) to mean in-app-only, not "no notification" |
| Tenant-admin user lookup | A bespoke admin-role query | `db.users.find({"tenantId": tenant_id, "role": {"$in": ADMIN_ROLES}})` | Exact pattern in `notification_manager.py:44-49`; reuse the role-set constant (or a near-identical one — see Common Pitfalls for the two slightly different existing sets) |

**Key insight:** every piece of this phase already has a close (often near-identical field-name) precedent somewhere in `backend/`. The risk in this phase is not missing library knowledge — it's copying the *wrong* precedent (`tickets_escalation_service.py`) instead of the *closer, more recent* one (`ticketing_bridge.py`, same collection).

## Common Pitfalls

### Pitfall 1: Background sweep silently returns zero results for every tenant (confirmed critical, from PITFALLS.md Pitfall 1 — re-verified against current code)
**What goes wrong:** New scheduler calls `get_database()` and iterates `db.compliance_remediation_tasks.find(...)`; runs with no errors, logs "0 escalated" forever, even with real overdue tasks.
**Why it happens:** `compliance_remediation_tasks` is not in `database.py`'s tenant-isolation exemption allowlist, so `get_database()` wraps it in `TenantIsolatedCollection`, whose `_inject_tenant_id()` reads a request-scoped contextvar that is `None` outside an HTTP request — the fail-closed substitution (`tenantId = "NON_EXISTENT_TENANT_ISOLATION_EMERGENCY"`) matches nothing.
**How to avoid:** `from database import mongodb as _mdb; asyncio.create_task(start_remediation_sla_scheduler(_mdb.db))` in `app_startup.py`, exactly like `tickets_escalation_service` (line 605) and `ticketing_bridge.start_close_loop_scheduler` (line 613).
**Warning signs:** Scheduler logs show "0 tasks escalated" indefinitely in a tenant known to have overdue tasks; a unit test that mocks `db.compliance_remediation_tasks` directly passes (mock doesn't reproduce the contextvar override) while the live endpoint/scheduler misbehaves.

### Pitfall 2: `_compute_sla()` reused unmodified produces wrong SLA status for remediation tasks
**What goes wrong:** A task 2 days from `due_date` (well within a 3-day "at risk" tenant setting) reports `sla_status: "ok"` because `_compute_sla()`'s at-risk cutoff is hardcoded to `< 3600` seconds (1 hour) remaining, not a configurable day count. A `resolved` remediation task with `status="resolved"` is correctly excluded, but a task that somehow reaches a non-enumerated status would fall through the `("resolved","closed")` check silently.
**Why it happens:** `_compute_sla()` was written for `tickets` (hour-scale SLA, 6-state status machine including `"closed"`), not `compliance_remediation_tasks` (day-scale SLA, 3-state enum).
**How to avoid:** Write `compute_remediation_sla(task, at_risk_window_days)` as a new pure function in `compliance_remediation_sla_service.py`; only port the due-date-parsing defensive try/except shape from `_compute_sla()`, not the threshold logic.
**Warning signs:** A test asserting `at_risk` at day-scale distances from `due_date` fails against an unmodified `_compute_sla()` import.

### Pitfall 3: `compliance_remediation_tasks` has no supporting index — confirmed absent (verified via `grep create_index database.py`, zero matches for this collection)
**What goes wrong:** The sweep query (`{"status": {"$in": [...]}}`) does a full collection scan every 5-minute cycle; fine in dev, slow at scale (thousands of tasks per tenant).
**Why it happens:** `database.py`'s `connect_to_mongo()` index block has compound indexes for `tickets` (`(tenantId,1),(due_date,1),(status,1)` and `(tenantId,1),(escalated,1)`, lines 277-278) but nothing at all for `compliance_remediation_tasks`.
**How to avoid:** Add, in the same `database.py` block, using the `tickets` indexes as direct template:
```python
await mongodb.db.compliance_remediation_tasks.create_index([("tenantId", 1), ("due_date", 1), ("status", 1)])
await mongodb.db.compliance_remediation_tasks.create_index([("tenantId", 1), ("escalated", 1)])
```
**Warning signs:** `explain()` on the sweep query shows `COLLSCAN` instead of `IXSCAN` against a multi-thousand-task collection.

### Pitfall 4: Assignee resolution to an email is not guaranteed — `assignee` is free text, and `assignee_type` may be `"agent"`
**What goes wrong:** D-03 says "notify the task's assignee"; naively calling `send_alert(recipients=[task["assignee"]])` sends to whatever string is in that field — which per `RemediationTaskModal.tsx:243` is user-entered free text ("User ID or email"), not a validated foreign key, and when `assignee_type == "agent"`, the value is an Agent ID with no human inbox at all.
**Why it happens:** `compliance_remediation_service.create_task` stores `assignee`/`assignee_type` verbatim from the request body with no lookup against `db.users`.
**How to avoid:** Resolve `assignee` the same way `control_comments_service.resolve_mentions` resolves @mention tokens — try `db.users.find_one({"email": assignee})`, fall back to `{"id": assignee}` or `{"username": assignee}`; skip assignee notification (not the whole escalation) if `assignee_type == "agent"` or resolution fails, and never raise on an unresolved assignee (mirrors `resolve_mentions`' silent-skip-on-typo behavior).
**Warning signs:** `send_alert` called with a non-email string in `recipients`; escalation processing raises/crashes when a task has `assignee_type: "agent"`.

### Pitfall 5: New endpoints module never registered in `router_registry.py`
**What goes wrong:** `compliance_remediation_sla_endpoints.py` is written and tested in isolation but 404s once deployed.
**Why it happens:** Documented recurring pattern in this codebase (PITFALLS.md Pitfall 7) — every new endpoint module requires an explicit registration step that's easy to skip.
**How to avoid:** Add the new router to `router_registry.py` in the same commit that creates the endpoints file; verify with a live `curl`/integration test, not just a unit test that imports the module directly.

### Pitfall 6: New frontend badge/panel built but not wired into the actual remediation view
**What goes wrong:** SLA badge and escalation-history panel get built and pass isolated component tests, but the live `RemediationDashboard.tsx`/`RemediationTaskModal.tsx` never renders them, exactly the "5 dashboards stranded" pattern flagged in PITFALLS.md Pitfall 8.
**Why it happens:** `RemediationDashboard.tsx` currently has no `sla_status` column at all (verified: full-file read shows only Task/Control/Assignee/Due Date/Status/Actions columns); it's easy to build a new standalone component instead of editing this existing table.
**How to avoid:** Edit `RemediationDashboard.tsx`'s existing `<table>` (add an SLA column, clone `STATUS_COLORS`/badge pattern at lines 9-14, 191-194) and `RemediationTaskModal.tsx` (add escalation panel near the existing ticket-badge block at lines 280-302), not a new page/route.

## Code Examples

### SLA computation (new, day-scale, configurable)
```python
# New file: backend/compliance_remediation_sla_service.py
from datetime import datetime, timezone
from typing import Any, Dict

_TIER_DAYS = [1, 3, 7]  # escalation_level 1/2/3 at 1/3/7 days past due — see Open Questions


def compute_remediation_sla(task: Dict[str, Any], at_risk_window_days: int) -> Dict[str, Any]:
    """Pure function — computes sla_status without persisting. Mirrors
    tickets_helpers._compute_sla()'s defensive parsing shape, NOT its
    hour-scale threshold or resolved/closed status check (PITFALLS.md
    Pitfall 10 — those don't apply to compliance_remediation_tasks)."""
    if task.get("status") == "resolved":
        task["sla_status"] = "ok"  # resolved tasks are not SLA-tracked
        return task

    due = task.get("due_date")
    if not due:
        task["sla_status"] = "none"
        return task
    try:
        due_str = str(due).replace("Z", "+00:00")
        due_dt = datetime.fromisoformat(due_str)
        if due_dt.tzinfo is None:
            due_dt = due_dt.replace(tzinfo=timezone.utc)
    except (ValueError, TypeError):
        task["sla_status"] = "none"
        return task

    now = datetime.now(timezone.utc)
    days_remaining = (due_dt - now).total_seconds() / 86400

    if now > due_dt:
        task["sla_status"] = "breached"
    elif days_remaining <= at_risk_window_days:
        task["sla_status"] = "at_risk"
    else:
        task["sla_status"] = "ok"
    return task


def compute_escalation_level(days_overdue: float) -> int:
    """Tiered level per D-04 — 1/3/7 days past due."""
    level = 0
    for i, threshold in enumerate(_TIER_DAYS, start=1):
        if days_overdue >= threshold:
            level = i
    return level
```

## State of the Art

Not applicable — this is internal architectural consistency, not an external-ecosystem-drift domain. No table.

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | Default per-tenant "at risk" window = 3 days (mirroring STALE-02's default-of-7 shape but scaled down since remediation SLAs are typically shorter-fuse than evidence staleness) | Pattern 2 code example | Low — it's a documented, easily-changed constant with an admin PATCH override; wrong default doesn't break correctness, only initial UX |
| A2 | Escalation tier boundaries = 1/3/7 days past due (D-04's own suggested starting point, not contradicted by any code found) | Code Examples, `_TIER_DAYS` | Low — CONTEXT.md explicitly says "confirm reasonable defaults during planning," so this is expected to be a judgment call; easily tunable constant |
| A3 | Tenant-admin role set for escalation notification should be `{"admin","Admin","Tenant Admin","Super Admin","super_admin","platform-admin"}` (notification_manager.py's set) rather than `compliance_evidence_lifecycle_endpoints.py`'s slightly different `_SETTINGS_ADMIN_ROLES` set (missing capitalized `"Admin"`) | Don't Hand-Roll, Pitfall 4 | Medium — if the wrong/narrower set is used, some tenant admins won't be notified on breach; recommend the planner pick ONE canonical set and use it everywhere new in this phase (don't introduce a third variant) |
| A4 | Assignee resolution should try `email` exact match, then `id`, then `username` (adapted from `resolve_mentions`' 3-step resolution order) | Pitfall 4 | Medium — if resolution order differs from what's assumed here, some assignees silently won't be notified; low blast radius since it's non-fatal by design (mirrors `resolve_mentions`) |

**None of these are compliance/security/retention claims requiring the heavier confirmation bar — all are tunable implementation constants already flagged as discretionary in CONTEXT.md or low-risk resolution-order choices.**

## Open Questions (RESOLVED)

1. **Exact tenant-admin role-set constant to use**
   - What we know: two near-identical but not-identical role sets exist in the codebase (`notification_manager.py`'s `_ADMIN_ROLES` vs `compliance_evidence_lifecycle_endpoints.py`'s `_SETTINGS_ADMIN_ROLES`).
   - What's unclear: whether there's a canonical third location that should be imported instead of duplicated a third time.
   - Recommendation: planner should pick `notification_manager.py`'s set (includes both `"admin"` and `"Admin"` casings) since it's the set already used specifically for admin *notification* delivery (closest semantic match to this phase's need), not settings-mutation gating.
   - RESOLVED: 44-02's `<read_first>` explicitly directs using `notification_manager.py`'s `_ADMIN_ROLES` per the recommendation.

2. **Should `escalation_level` reset if a task moves from `breached` back to `ok`/`at_risk`** (e.g., due_date is extended by an edit)?
   - What we know: `TaskUpdate`'s Pydantic model currently only accepts `status`/other existing fields; whether `due_date` is editable post-creation wasn't traced in this session.
   - What's unclear: reset-on-due-date-extension behavior isn't specified in CONTEXT.md's D-01–D-04.
   - Recommendation: treat as out of scope unless `due_date` editing already exists — flag for the planner to confirm via a quick grep of `TaskUpdate`'s field list before committing to reset-vs-no-reset semantics.
   - RESOLVED: 44-01 Task 3 confirms `TaskUpdate`'s field list and scopes reset semantics accordingly — out of scope per the recommendation.

## Environment Availability

Not applicable — this phase adds no new external tool/service/runtime dependency. All work is against the existing FastAPI/Motor/MongoDB stack already running in this environment (confirmed via direct file reads of `backend/database.py`, `backend/app_startup.py`).

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest (`pytest.ini`, asyncio mode `auto` via pytest-asyncio) |
| Config file | `pytest.ini` (repo root of `backend/`) |
| Quick run command | `backend/venv/bin/python -m pytest backend/tests/test_compliance_remediation_sla.py -v` (per project memory: always use `backend/venv/bin/python`, not system python) |
| Full suite command | `backend/venv/bin/python -m pytest backend/tests -q` |

### Phase Requirements → Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| SLA-01 | `compute_remediation_sla()` returns ok/at_risk/breached correctly at day-scale boundaries | unit | `pytest backend/tests/test_compliance_remediation_sla.py -k compute_sla -x` | ❌ Wave 0 |
| SLA-01 | `run_sla_pass` escalates a breached task and calls `send_alert` for assignee + tenant admins | unit (mocked db, mirrors `test_ticketing_bridge.py`'s `_mock_db()` factory) | `pytest backend/tests/test_compliance_remediation_sla.py -k run_sla_pass -x` | ❌ Wave 0 |
| SLA-01 | Scheduler registration uses raw `mongodb.db`, never `get_database` | unit (regression guard, clone `test_raw_db_registration_never_uses_get_database`) | `pytest backend/tests/test_compliance_remediation_sla.py -k raw_db_registration -x` | ❌ Wave 0 |
| SLA-02 | Escalation entries are insert-only; no PATCH/DELETE route exists for `remediation_escalations` | unit + route-absence check | `pytest backend/tests/test_compliance_remediation_sla.py -k escalation_history -x` | ❌ Wave 0 |
| SLA-02 | Escalation history is tenant-scoped (cross-tenant read returns empty) | integration | `pytest backend/tests/test_compliance_remediation_sla.py -k tenant_scope -x` | ❌ Wave 0 |

### Sampling Rate
- **Per task commit:** `backend/venv/bin/python -m pytest backend/tests/test_compliance_remediation_sla.py -v`
- **Per wave merge:** `backend/venv/bin/python -m pytest backend/tests -q`
- **Phase gate:** Full suite green before `/gsd-verify-work`

### Wave 0 Gaps
- [ ] `backend/tests/test_compliance_remediation_sla.py` — new file, clone `test_ticketing_bridge.py`'s `_mock_db()` fixture factory and file-level docstring-as-test-index convention (covers SLA-01, SLA-02)
- [ ] No shared fixtures needed beyond the existing `_mock_db()` pattern already established in `test_remediation_workflow.py`/`test_ticketing_bridge.py`
- [ ] Framework install: none — pytest + pytest-asyncio already installed and configured

## Security Domain

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | no | Not touched by this phase — scheduler is a background task, not a new auth surface |
| V3 Session Management | no | N/A |
| V4 Access Control | yes | Tenant scoping on every read (escalation-history GET endpoint, settings GET/PATCH) via `current_user.tenant_id`; admin-role gate on the settings PATCH, cloned from `_require_admin`/`_SETTINGS_ADMIN_ROLES` |
| V5 Input Validation | yes | Pydantic `Field(ge=1, le=365)`-style bound on the at-risk-window PATCH body, cloned from `StalenessThresholdUpdate` |
| V6 Cryptography | no | N/A — no new secrets/crypto surface |

### Known Threat Patterns for this stack

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| Cross-tenant escalation-history read (tenant B reads tenant A's escalations by guessing a `task_id`) | Information Disclosure | Always AND the query with `{"tenantId": tenant_id}` at read time, mirroring `get_evidence_audit_log`'s pattern — never rely solely on the background sweep having been tenant-correct at write time |
| Background sweep processes a task with no `tenantId` field (malformed/legacy doc) | Tampering (data integrity) | `if not tenant_id: continue` guard before any escalation/notification logic, as shown in Pattern 1 |
| Notification recipient injection via unresolved/malformed `assignee` free-text field | Spoofing (notification goes to wrong/attacker-controlled address if assignee field isn't validated as email-shaped before use) | Resolve `assignee` against `db.users` before using it as a `send_alert` recipient (never pass the raw free-text field directly as an email address) — see Pitfall 4 |

## Sources

### Primary (HIGH confidence — direct codebase reads, this session)
- `backend/tickets_helpers.py` — full read, `_compute_sla()` exact behavior
- `backend/tickets_escalation_service.py` — full read, older escalation pattern (array `$push`, hour-scale)
- `backend/ticketing_bridge.py` — full read, closest precedent (Phase 43, same collection)
- `backend/compliance_remediation_service.py` — full read, exact current task schema
- `backend/evidence_staleness.py` — full read, STALE-02 threshold-lookup pattern
- `backend/compliance_evidence_lifecycle_endpoints.py` — full read, STALE-02 endpoints + COC-02 audit-log read endpoint
- `backend/control_comments_service.py`, `backend/control_comments_endpoints.py` — full/partial read, @mention resolution + `send_alert` call shape
- `backend/notification_service.py`, `backend/notification_manager.py` — partial read, `send_alert` signature + tenant-admin lookup pattern
- `backend/app_startup.py` (lines 590-660) — scheduler registration block, exact precedent locations
- `backend/database.py` (`create_index` grep) — confirmed absence of any `compliance_remediation_tasks` index
- `backend/compliance_remediation_endpoints.py` — `TaskUpdate` Pydantic model, confirmed 3-value status enum
- `components/RemediationDashboard.tsx` — full read, no existing SLA column
- `components/RemediationTaskModal.tsx` — partial read, Phase 43 ticket-badge location + free-text assignee field
- `components/ChainOfCustodyPanel.tsx` — partial read, lazy-expand panel pattern to clone
- `backend/tests/test_ticketing_bridge.py` — partial read, test file shape/docstring-index convention

### Secondary (MEDIUM confidence)
- `.planning/research/PITFALLS.md` (v3.2 milestone research) — Pitfalls 1, 6, 7, 8, 9, 10 all directly relevant and re-verified against current code in this session (all confirmed accurate)
- `.planning/research/ARCHITECTURE.md` (v3.2 milestone research) — directionally correct on module naming/placement, but its "`_compute_sla()` reused as-is" claim is superseded by this session's direct verification + PITFALLS.md's own Pitfall 10

### Tertiary (LOW confidence)
- None — no WebSearch was needed for this phase; entirely internal-codebase research.

## Metadata

**Confidence breakdown:**
- Standard Stack: HIGH — no new dependencies, all patterns verified against existing installed code
- Architecture: HIGH — every pattern cited was read directly from the file it's attributed to in this session
- Pitfalls: HIGH — cross-verified milestone `PITFALLS.md` claims against current source, all confirmed still accurate; added 2 new pitfalls (assignee resolution, frontend wiring specifics) not covered at milestone-research depth

**Research date:** 2026-07-21
**Valid until:** Effectively indefinite for the internal patterns cited (stable, no external dependency drift risk) — re-verify only if Phase 43's `ticketing_bridge.py` or the `compliance_remediation_tasks` schema changes before this phase executes.
