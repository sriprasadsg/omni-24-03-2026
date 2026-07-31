# Phase 43: Remediation-to-Ticketing Bridge - Research

**Researched:** 2026-07-21
**Domain:** In-process FastAPI/Motor integration bridge (multi-tenant GRC platform) — no new external dependency, no new architecture
**Confidence:** HIGH

## Summary

This phase wires the existing `compliance_remediation_service.py` task lifecycle to the existing `ticketing_service.py` Jira/ServiceNow connectors, and closes the loop when the external ticket resolves. Every piece of infrastructure this phase needs already exists in the codebase in a directly-reusable, unmodified form: `ticketing_service.create_jira_ticket`/`create_servicenow_incident` are plain `httpx`-based async functions (no SDK, no `atlassian-python-api` dependency — that commented-out requirements.txt line is a red herring, confirmed by reading the actual import list), `compliance_remediation_service.update_task()` already dispatches a re-scan whenever `status` is set to `"resolved"` regardless of caller, and `tickets_escalation_service.py`/`scheduled_reports_service.py` both demonstrate proven (though *different*) patterns for a raw-db background polling loop registered in `app_startup.py`.

The single most important research finding: **`backend/integration_service_ticketing.py` is a decoy, not a second candidate.** It is a mixin (`IntegrationServiceTicketingMixin`) on a completely separate `IntegrationService` class used by the generic SIEM/EDR/CMDB integration surface (`integration_endpoints.py`), reading config from an untenanted `integration_configs` collection keyed by `{type, platform}` (no `tenantId` in the config lookup query at all — a latent tenant-isolation gap in that subsystem, out of scope for this phase). It has no `alert`-shaped payload builder, no severity/priority mapping specific to security context, and — critically — its `create_ticket()` signature (`title, description, priority, platform, metadata`) is actually *more* generic/reusable-looking than `ticketing_service.py`'s alert-shaped functions, which could tempt a planner into picking it. Don't: `ticketing_service.py` is the one with tenant-scoped config (`ticketing_configs` keyed by `tenant_id`), the existing `/api/ticketing/*` admin UI (`TicketingIntegration.tsx`) tenants already use to enter Jira/ServiceNow credentials, and the `ticketing_log` audit trail. Building against `integration_service_ticketing.py` would produce a feature invisible to the UI tenants already use to configure ticketing.

The second major finding: there is **no existing close-loop status-polling code anywhere in this codebase** — not in `ticketing_service.py`, not in `integration_service_ticketing.py`, not in `tickets_escalation_service.py`. `_compute_sla()` and the escalation scheduler poll *internal* ticket SLA state, never an *external* Jira/ServiceNow API. This is genuinely new code (two small `httpx GET` functions), not a reuse-and-adapt situation. Jira's `statusCategory.key == "done"` is the correct provider-agnostic closed-check (works across custom workflows); ServiceNow's numeric `state` field is **not** safe to hardcode (values are customizable per instance/version) — use `sysparm_display_value=true` and compare the human-readable label instead, flagged as an Open Question requiring a plan-time decision, not a research gap that blocks planning.

**Primary recommendation:** Build a new `backend/ticketing_bridge.py` module (adapter + orchestration + status-poll functions), leave `ticketing_service.py` and `integration_service_ticketing.py` both untouched, add three fields (`ticket_provider`/`ticket_ref`/`ticket_url`) to `compliance_remediation_tasks` via `$set` (never through the public `TaskUpdate` PATCH model — server-controlled only), and register a fifth `app_startup.py` background loop following the `tickets_escalation_service` raw-db pattern (not the `scheduled_reports_service` `platform-admin` contextvar pattern — see Pitfall 1 below for why).

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| Task→ticket field adapter | API/Backend (`ticketing_bridge.py`) | — | Pure translation logic, no state of its own |
| Jira/ServiceNow ticket creation | API/Backend (`ticketing_service.py`, unmodified) | — | Existing httpx calls to external SaaS APIs |
| Ticket-ref persist-back onto task | Database/Storage | API/Backend | `$set` write via server-controlled path, never client-supplied |
| Provider availability check (D-02) | API/Backend (existing `GET /api/ticketing/config`) | Browser/Client (cache in modal state) | Config already lives server-side; frontend just reads presence of `jira_url`/`snow_instance` |
| Manual "Create Ticket" action | Browser/Client (button + picker) | API/Backend (new endpoint) | User-triggered synchronous action, needs a request/response round trip for the toast |
| Auto-create-on-high/critical | API/Backend (service layer, inside `create_task`) | — | Must fire regardless of which caller invokes `create_task` (tests, other services), not just the HTTP endpoint |
| Close-loop ticket-status polling | API/Backend (new background scheduler) | Database/Storage | No webhook receiver per D-03; cross-tenant sweep needs raw db, not request-scoped tenant context |
| Re-scan dispatch on ticket close | API/Backend (`compliance_remediation_service.update_task`, unmodified) | — | Already fires on any `status="resolved"` write — reuse verbatim, don't reimplement |
| Ticket status/link display on task | Browser/Client (`RemediationTaskModal.tsx`) | — | Read-only render of fields already returned by `GET /tasks` |

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| REM-01 | Compliance admin can create a Jira/ServiceNow ticket from a remediation task, with fields correctly mapped through an explicit adapter (not passed raw) | `ticketing_service.py` read in full — confirmed alert-shaped hardcoding (`hostname`, `process.name`, `process.sha256`, `mitre_technique`); adapter shape specified below in Code Examples; manual "Create Ticket" endpoint + provider picker design specified |
| REM-02 | Closed external ticket auto-resolves the remediation task and triggers the existing re-scan dispatch | `compliance_remediation_service.update_task()` read in full — already dispatches re-scan on `status="resolved"` for ANY caller, including a background scheduler calling it directly with `created_by="system:ticket-poll"`; polling scheduler design (raw-db pattern) + status-check functions (new) specified below |
</phase_requirements>

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| httpx | `>=0.27.0,<1.0.0` (confirmed present, `backend/requirements.txt:42`) | Async HTTP client for Jira/ServiceNow REST calls | Already the exclusive HTTP client used by every function in `ticketing_service.py` — no new dependency needed |
| FastAPI / Motor / Pydantic | Already pinned in `requirements.txt` | Endpoint + async DB + request/response models | Existing stack, no version change required for this phase |

**No new packages required for this phase.** `create_jira_ticket`/`create_servicenow_incident` in `ticketing_service.py` import `httpx` directly (`import httpx` inside the function body, `ticketing_service.py:74`, `:211`) — there is **no** `atlassian-python-api` import anywhere in the file `[VERIFIED: backend/ticketing_service.py, read in full]`. The commented-out `# atlassian-python-api>=3.41.0  # Optional: Jira client` line in `requirements.txt:116` is dead weight from an earlier, unused approach — it is not imported by any file that participates in this phase's scope (confirmed via `grep -rn "atlassian" backend/*.py` returning zero import hits). **Do not uncomment or install it.** This resolves CONTEXT.md's flagged open question definitively: `create_jira_ticket` is fully functional today with zero SDK dependency.

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| `ticketing_service.py` (tenant-scoped `ticketing_configs`) | `integration_service_ticketing.py` (`IntegrationServiceTicketingMixin` on `IntegrationService`, untenanted `integration_configs`) | Rejected — see Summary. Not wired to the tenant-facing `TicketingIntegration.tsx` UI; its config lookup has no `tenantId` filter at all (`integration_service.py:_get_integration_config` queries `{"type": ..., "platform": ...}` with no tenant scoping — a pre-existing gap in that subsystem, do not inherit it into this phase) |
| Polling scheduler using raw `mongodb.db` (tickets_escalation_service pattern) | `set_tenant_id("platform-admin")` + `get_database()` (scheduled_reports_service pattern) | Either technically works for a cross-tenant sweep (both bypass per-request tenant scoping), but the raw-db pattern is simpler to reason about and is the pattern ARCHITECTURE.md's SLA-scheduler research (Phase 44, sibling phase) already commits to for the same collection — using the same pattern for both schedulers touching `compliance_remediation_tasks` avoids two different mental models for the same collection |

**Installation:** None — no `pip install` step needed for this phase.

**Version verification:** `httpx` already present and pinned; verified via direct read of `backend/requirements.txt:42`, no registry lookup needed since no new package is introduced.

## Package Legitimacy Audit

**No external packages are installed by this phase.** All ticketing HTTP calls reuse the existing `httpx` dependency already present in `backend/requirements.txt`. The `atlassian-python-api` line remains commented out and untouched — verified not required by any code path this phase touches.

| Package | Registry | Age | Downloads | Source Repo | Verdict | Disposition |
|---------|----------|-----|-----------|-------------|---------|-------------|
| *(none — no new packages)* | — | — | — | — | — | N/A |

**Packages removed due to [SLOP] verdict:** none
**Packages flagged as suspicious [SUS]:** none

## Architecture Patterns

### System Architecture Diagram

```
┌─────────────────────────────────────────────────────────────────────────┐
│ RemediationTaskModal.tsx                                                 │
│   "Create Ticket" button (all priorities) + provider picker              │
│   (shown only if GET /api/ticketing/config has BOTH jira_url AND         │
│    snow_instance present — D-02)                                        │
│         │ POST /tasks/{id}/create-ticket {provider}                      │
│         ▼                                                                │
│ compliance_remediation_endpoints.py  (NEW route)                        │
│         │                                                                │
│         ▼                                                                │
│ ticketing_bridge.create_ticket_for_remediation_task(db, task, tenant_id,│
│                                                       provider_override) │
│    ├─ skip if task.ticket_ref already set (dedup guard)                 │
│    ├─ skip (no-op) if ticketing_service.get_ticketing_config() is None  │
│    ├─ resolve asset hostname (best-effort, "Unknown" fallback)          │
│    ├─ _task_to_alert_shape(task, hostname) → alert-shaped dict          │
│    ├─→ ticketing_service.create_jira_ticket() /                         │
│    │    create_servicenow_incident()      [UNMODIFIED, reused as-is]    │
│    │       └─→ _store_ticket() writes db.ticketing_log                  │
│    │            {alert_id: task["id"], provider, ticket_ref, url}       │
│    │            (task["id"] doubles as the lookup key — no schema       │
│    │             change to ticketing_log needed)                        │
│    └─ db.compliance_remediation_tasks.update_one(                       │
│         {"id": task_id, **tenant_filter},                               │
│         {"$set": {"ticket_provider", "ticket_ref", "ticket_url"}})      │
│                                                                            │
│ compliance_remediation_service.create_task()  (MODIFIED)                │
│    on insert, if priority in (high, critical):                          │
│      try: await ticketing_bridge.create_ticket_for_remediation_task(    │
│              db, task, tenant_id, provider_override=config["provider"]) │
│      except Exception: log warning, continue  (D-04 non-blocking)       │
│                                                                            │
│ app_startup.py  (NEW scheduler block, 5th of its kind)                  │
│    asyncio.create_task(                                                 │
│        ticketing_bridge.start_close_loop_scheduler(raw mongodb.db))     │
│         │ every 900-1800s (15-30 min, D-03)                             │
│         ▼                                                                │
│    ticketing_bridge.run_close_loop_pass(db)                             │
│      raw_db.compliance_remediation_tasks.find(                          │
│        {"status": {"$in": ["open","in_progress"]},                      │
│         "ticket_ref": {"$ne": None}})                                   │
│      for each task:                                                     │
│        ├─ ticketing_bridge.get_jira_issue_status() /                    │
│        │    get_servicenow_incident_status()   [NEW — no prior art]     │
│        └─ if closed:                                                     │
│             compliance_remediation_service.update_task(                 │
│               raw_db, task_id, {"status": "resolved"},                  │
│               {"tenantId": task["tenantId"]},                           │
│               created_by="system:ticket-close-loop")                    │
│               → dispatch_rescan() fires automatically (REM-02, reused,  │
│                 unmodified — this is the entire close-loop payoff)      │
│             broadcast_remediation_update(tenant_id, {...})              │
│               [same WS hook the endpoint uses — replicated here since   │
│                update_task() itself doesn't broadcast]                  │
└─────────────────────────────────────────────────────────────────────────┘
```

### Recommended Project Structure
```
backend/
├── ticketing_bridge.py          # NEW — adapter, orchestration, status-poll, scheduler
├── ticketing_service.py         # UNCHANGED — connectors reused as-is
├── compliance_remediation_service.py    # MODIFIED — auto-create hook in create_task()
├── compliance_remediation_endpoints.py  # MODIFIED — new POST /tasks/{id}/create-ticket route
├── app_startup.py               # MODIFIED — one new scheduler registration block
└── tests/
    └── test_ticketing_bridge.py # NEW — clones test_remediation_workflow.py's _mock_db() pattern
components/
├── RemediationTaskModal.tsx     # MODIFIED — Create Ticket button, provider picker, ticket display
services/
└── apiService.ts                # MODIFIED — createTicketForRemediationTask(), getTicketingConfig()
```

### Pattern 1: Explicit task→alert adapter (REM-01's core requirement)

**What:** A pure function that translates a `compliance_remediation_tasks` document into the `alert`-shaped dict `ticketing_service.create_jira_ticket`/`create_servicenow_incident` already expect, so their `.get()`-based field reads never silently fall through to `"N/A"`.

**When to use:** Every call into `ticketing_service.create_jira_ticket`/`create_servicenow_incident` from this phase — never call them with a raw task dict.

**Example:**
```python
# backend/ticketing_bridge.py — new module
# Adapts a compliance_remediation_tasks doc into the alert shape
# ticketing_service.py's create_jira_ticket/create_servicenow_incident expect.
# Source: field names cross-referenced against ticketing_service.py:71-118,208-244
# (create_jira_ticket, create_servicenow_incident) and
# compliance_remediation_service.py:44-64 (create_task's task dict shape).

async def _task_to_alert_shape(db, task: dict) -> dict:
    hostname = "Unknown"
    asset_id = task.get("asset_id")
    if asset_id:
        try:
            asset = await db.assets.find_one({"id": asset_id})
            hostname = (asset or {}).get("hostname", "Unknown")
        except Exception:
            pass  # best-effort; hostname stays "Unknown", never raises
    return {
        "alert_id": task["id"],                       # doubles as ticketing_log lookup key
        "type": "compliance_remediation",
        "severity": task.get("priority", "medium"),    # vocab already matches JIRA_PRIORITY_MAP/SNOW_URGENCY_MAP keys
        "hostname": hostname,
        "process": {},                                  # not applicable to compliance context — leave empty, template renders "N/A" gracefully for this field only
        "mitre_technique": "N/A",                        # not applicable — explicit, not a silent fallback
        "description": (
            f"Compliance control {task.get('control_id', 'N/A')} failed "
            f"(framework: {task.get('framework_id', 'N/A')}).\n\n"
            f"{task.get('description', '')}"
        ),
        "timestamp": task.get("created_at", ""),
    }
```
`priority` values (`low|medium|high|critical`) already match `JIRA_PRIORITY_MAP`/`SNOW_URGENCY_MAP` keys exactly `[VERIFIED: backend/ticketing_service.py:16-29 vs backend/compliance_remediation_endpoints.py:57]` — no re-mapping table needed.

### Pattern 2: Server-controlled ticket-ref fields (never client-writable)

**What:** `ticket_provider`/`ticket_ref`/`ticket_url` are written exclusively via `db.compliance_remediation_tasks.update_one(..., {"$set": {...}})` from `ticketing_bridge.py`, never accepted as input on the existing `TaskUpdate` Pydantic model (`compliance_remediation_endpoints.py:60-65`).

**When to use:** Always, for this feature. This mirrors the existing `ai_suggestion` persist-back pattern (`compliance_remediation_endpoints.py:162-169`) — same "best-effort `$set` after an external call, from server logic only" shape.

**Why:** If `ticket_ref`/`ticket_url` were added to `TaskUpdate`, any authenticated tenant user could `PATCH /tasks/{id}` with a spoofed ticket link, defeating Success Criterion 2's implicit trust that a displayed ticket link is real.

### Pattern 3: Auto-create provider selection (resolves a gap CONTEXT.md left open)

**What:** D-02 ("admin picks per-ticket if tenant has both configured") only has a UI moment for the **manual** Create Ticket action — there is no human in the loop for **auto-create on high/critical** (D-01). Recommendation: auto-create uses `config["provider"]` (`ticketing_configs.provider`) — the tenant's existing single "active provider" field, already used identically by `auto_create_ticket_for_alert` (`ticketing_service.py:344-362`), `/api/ticketing/test`, and the manual "create from alert" endpoint. This requires zero new schema and is consistent with every other auto-trigger path already in the codebase.

**When to use:** `create_ticket_for_remediation_task(..., provider_override=None)` — when `provider_override` is `None` (auto-create path), fall back to `config.get("provider")`; when explicitly passed (manual Create Ticket action, D-02), use it directly.

### Pattern 4: Background scheduler — raw db, not `get_database()`

**What:** `ticketing_bridge.start_close_loop_scheduler(db)` must be called with the **raw, unwrapped** `mongodb.db` from `app_startup.py`, exactly like `tickets_escalation_service.start_escalation_scheduler(_mdb.db)` (`app_startup.py:602-606`) — never `get_database()`.

**Why:** `compliance_remediation_tasks` is **not** in `database.py`'s tenant-isolation exemption list (`database.py:122-134`, confirmed by direct read — the list contains `compliance_frameworks`, `compliance_controls`, `ai_governance_frameworks`, `system_features`, `tenants`, `roles`, `response_policies`, `playbooks`, `ip_bans`, `crypto_inventory` — `compliance_remediation_tasks` is absent). A background `asyncio` task has no request-scoped tenant contextvar, so `get_database()`'s wrapper would inject the fail-closed sentinel `tenantId = "NON_EXISTENT_TENANT_ISOLATION_EMERGENCY"` into every query, silently matching zero documents forever, with no exception raised (see Pitfall 1 below — this is a documented, previously-hit class of bug in this exact codebase).

**Example (scheduler registration, `app_startup.py`):**
```python
try:
    from ticketing_bridge import start_close_loop_scheduler
    from database import mongodb as _mdb
    asyncio.create_task(start_close_loop_scheduler(_mdb.db))
    logger.info("[Ticketing] Remediation close-loop scheduler started")
except Exception as _e:
    logger.warning("[Ticketing] Close-loop scheduler failed to start: %s", _e)
```
This is structurally identical to the existing `tickets_escalation_service` block (`app_startup.py:602-608`) — 5th instance of the same established pattern (after tickets, syslog polling×4, reports).

### Anti-Patterns to Avoid
- **Calling `create_jira_ticket(task, config)` directly with a raw task dict:** Silently produces "Process: N/A (PID N/A)", "SHA256: N/A", "MITRE Technique: N/A" in the ticket body — see Pattern 1.
- **Registering the close-loop scheduler via `get_database()`:** Silently returns zero results forever, no exception (see Pattern 4 / Pitfall 1).
- **Extending `tickets_escalation_service.py` in place for the close-loop poll:** Different domain (SLA-breach escalation on internal tickets vs. external-ticket-status polling) — write `ticketing_bridge.py`'s own loop instead. Do not add an `if collection == ...` branch to the existing service.
- **Adding `ticket_provider`/`ticket_ref`/`ticket_url` to the `TaskUpdate` Pydantic model:** Makes the ticket link client-spoofable (see Pattern 2).
- **Hardcoding ServiceNow numeric `state` codes (e.g. `6`, `7`) as "closed":** Values are customizable per instance/version — confirmed ambiguous even across ServiceNow's own community documentation (see Open Questions).

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Jira/ServiceNow ticket creation HTTP calls, auth headers, priority mapping | A parallel `create_jira_ticket_for_remediation()` duplicate | `ticketing_service.create_jira_ticket`/`create_servicenow_incident`, unmodified, called with an adapted payload | Already handles auth (`Basic` header construction), priority mapping, and `_store_ticket` audit logging — duplicating it doubles maintenance surface for zero functional gain |
| Re-scan dispatch on task resolution | A second "dispatch rescan on ticket close" code path | `compliance_remediation_service.update_task(db, task_id, {"status": "resolved"}, tenant_filter, created_by=...)` — already dispatches rescan on any `status="resolved"` write | This is the literal mechanism REM-02 asks for ("triggers the existing re-scan dispatch, matching manual-resolution behavior") — calling the same function IS "matching," not "reimplementing to match" |
| Background scheduler loop shape (interval sleep, try/except-per-pass) | A bespoke `while True` loop with different error handling | Structurally clone `tickets_escalation_service.start_escalation_scheduler`'s shape (`while True: await pass_fn(db); await asyncio.sleep(N)`, pass function wraps its whole body in `try/except Exception: logger.error(...)`) | Proven pattern in this exact codebase, already running in production-equivalent code for 300s-interval sweeps |
| Provider-configured-check UI logic | A new backend endpoint just to answer "does this tenant have Jira and/or ServiceNow configured" | The existing `GET /api/ticketing/config` (already returns `jira_url`, `snow_instance` unmasked — only tokens/passwords are masked) | Zero new backend surface needed; frontend derives `hasJira`/`hasServiceNow` booleans from fields already returned |

**Key insight:** Every piece of "hard" work in this phase (auth headers, priority maps, re-scan dispatch, scheduler loop shape, provider-config storage) already exists and is directly reusable. The only genuinely new logic is the adapter function (Pattern 1) and the two ticket-status-check functions (no prior art — see Open Questions).

## Common Pitfalls

> Pitfalls 1, 3, 5, 6, 7 below are the subset of `.planning/research/PITFALLS.md` (milestone-level research) that apply specifically to Feature (a) — Remediation-to-Ticketing Bridge. Full milestone pitfalls document also covers features (b)/(c)/(d) (Phases 42/44), not reproduced here except where directly relevant.

### Pitfall 1: Close-loop scheduler silently returns zero results for every tenant
**What goes wrong:** A scheduler using `get_database()`/`get_db()` inside a background `asyncio.create_task` runs forever, logs no errors, finds zero overdue-to-close tickets — even with real closed tickets linked to real tasks in Mongo.
**Why it happens:** `compliance_remediation_tasks` is not in `database.py`'s exemption allowlist, so it's wrapped by `TenantIsolatedCollection`. That wrapper reads `tenant_id` from a **contextvar** populated only inside an authenticated HTTP request. A bare `asyncio` task has no request context → `get_tenant_id()` returns `None` → fail-closed sentinel `tenantId = "NON_EXISTENT_TENANT_ISOLATION_EMERGENCY"` gets injected into every query → matches nothing, silently, forever.
**How to avoid:** Register the scheduler with the raw `mongodb.db` object exactly like `tickets_escalation_service` (see Pattern 4 above). Do **not** add `compliance_remediation_tasks` to the exemption allowlist as a workaround — that would remove tenant isolation from the collection's request-scoped access paths too.
**Warning signs:** Scheduler logs "0 closed" indefinitely despite a manually-verified closed Jira ticket linked to a task; no exceptions anywhere (`database.py`'s `[SECURITY ALERT]` log only fires on `insert_one`/`aggregate`, not `find`, so even the log signal is easy to miss).

### Pitfall 3 (renumbered from milestone doc — router registration)
**What goes wrong:** The new `POST /tasks/{id}/create-ticket` route is added to `compliance_remediation_endpoints.py` (an *existing*, already-registered router — `router_registry.py:169`), so this specific pitfall does not apply to the manual-create route. It **does** apply if a planner instead creates a separate new endpoint file (e.g. `ticketing_bridge_endpoints.py`) for this route — that file would need its own `router_registry.py` line and would silently 404 without it.
**How to avoid:** Prefer adding the route directly to the existing `compliance_remediation_endpoints.py` router (no new file, no new registration needed) rather than creating a new endpoints module for a single route.

### Pitfall 5: Adapter omission (already covered above as the primary REM-01 risk — see Pattern 1 and Anti-Patterns)

### Pitfall 6: Manual `tenant_filter` dict silently overridden by contextvar for cross-tenant/admin views
**What goes wrong:** If a future admin-facing "all pending tickets across tenants" view is added, a `{}`-based Super Admin filter can be silently re-scoped to one tenant by the `TenantIsolatedCollection` wrapper's contextvar, regardless of the filter dict the endpoint code built.
**Relevance to this phase:** Low — this phase's endpoints (`create-ticket`) are tenant-scoped like every other route in `compliance_remediation_endpoints.py`, using the existing `_tenant_filter(user)` helper unchanged. Only relevant if the plan adds a platform-admin cross-tenant ticket-bridge audit view (not required by REM-01/REM-02 as scoped).

### Pitfall 7: New routers/endpoints never registered in `router_registry.py`
**Relevance to this phase:** Low risk if the new route is added to `compliance_remediation_endpoints.py` (already registered, `router_registry.py:169`). Confirm no new endpoint *file* is introduced, or add its registration explicitly if one is.

### Pitfall (new, specific to this phase): ServiceNow "closed" state is not a stable numeric constant
**What goes wrong:** Code hardcodes `incident.state in (6, 7)` (or any specific numeric pair) as "closed/resolved" and works in one ServiceNow instance/version but silently never detects closure in another.
**Why it happens:** ServiceNow's `incident.state` choice-list numeric values are configurable per instance and have changed across ServiceNow releases — community documentation itself shows conflicting numeric mappings (verified via direct search this session: one source lists 6=Resolved/7=Closed, another lists 6=Canceled/7=Awaiting Problem for the same table). There is no universal numeric constant safe to hardcode.
**How to avoid:** Request the incident with `sysparm_display_value=true` (or `=all`) and compare the **label** (`"Closed"`/`"Resolved"`) case-insensitively, not the raw numeric `state` value. Document this explicitly in the implementation, and flag it as a per-tenant-instance risk in a code comment — a tenant with a heavily customized ServiceNow workflow could still use different terminal-state labels, which is an acceptable, documented v1 limitation (not a blocker), matching the "best-effort, non-blocking" philosophy already locked in D-04.
**Warning signs:** A ticket visibly closed in the tenant's ServiceNow instance never triggers `status="resolved"` on the linked remediation task.

## Code Examples

### Ticket status check — Jira (new, no prior art in this codebase)
```python
# Source: Jira Cloud Platform REST API v3 status/statusCategory semantics
# https://developer.atlassian.com/cloud/jira/platform/rest/v3/api-group-workflow-statuses/
# statusCategory.key is a normalized 3-value field ("new" | "indeterminate" | "done")
# that is stable across custom workflows with arbitrary status names — this is the
# correct provider-agnostic "is this issue done" check, NOT string-matching on
# status.name (which varies per Jira project's custom workflow).
async def get_jira_issue_status(ticket_key: str, config: dict) -> dict:
    import httpx, base64
    jira_url = config.get("jira_url", "").rstrip("/")
    auth = base64.b64encode(
        f"{config['jira_email']}:{config['jira_api_token']}".encode()
    ).decode()
    headers = {"Authorization": f"Basic {auth}", "Accept": "application/json"}
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(
                f"{jira_url}/rest/api/3/issue/{ticket_key}?fields=status", headers=headers
            )
            data = resp.json()
            category = data.get("fields", {}).get("status", {}).get("statusCategory", {}).get("key", "")
            return {"success": True, "closed": category == "done"}
    except Exception as e:
        return {"success": False, "closed": False, "error": str(e)}
```

### Ticket status check — ServiceNow (new, no prior art; label-based per Pitfall above)
```python
# ServiceNow Table API — sysparm_display_value=true returns human-readable
# state labels instead of instance-specific numeric codes.
# https://www.servicenow.com/docs/bundle/yokohama-api-reference/page/integrate/inbound-rest/concept/c_TableAPI.html
_SNOW_CLOSED_LABELS = {"closed", "resolved"}

async def get_servicenow_incident_status(sys_id: str, config: dict) -> dict:
    import httpx
    instance = config.get("snow_instance", "").rstrip("/")
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(
                f"https://{instance}.service-now.com/api/now/table/incident/{sys_id}"
                f"?sysparm_fields=state&sysparm_display_value=true",
                auth=(config.get("snow_username"), config.get("snow_password")),
                headers={"Accept": "application/json"},
            )
            data = resp.json().get("result", {})
            state_label = str(data.get("state", "")).strip().lower()
            return {"success": True, "closed": state_label in _SNOW_CLOSED_LABELS}
    except Exception as e:
        return {"success": False, "closed": False, "error": str(e)}
```

### Close-loop pass (new, mirrors `run_escalation_pass` shape)
```python
# backend/ticketing_bridge.py
async def run_close_loop_pass(db) -> None:
    """Background sweep: poll linked external tickets, resolve tasks whose ticket closed."""
    try:
        query = {
            "status": {"$in": ["open", "in_progress"]},
            "ticket_ref": {"$ne": None},
        }
        cursor = db.compliance_remediation_tasks.find(query, {"_id": 0})
        async for task in cursor:
            tenant_id = task.get("tenantId", "")
            config = await get_ticketing_config(tenant_id)   # ticketing_service, unmodified
            if not config:
                continue
            provider = task.get("ticket_provider")
            if provider == "jira":
                result = await get_jira_issue_status(task["ticket_ref"], config)
            elif provider == "servicenow":
                result = await get_servicenow_incident_status(task["ticket_ref"], config)
            else:
                continue
            if result.get("closed"):
                import compliance_remediation_service as svc
                updated = await svc.update_task(
                    db, task["id"], {"status": "resolved"},
                    {"tenantId": tenant_id}, created_by="system:ticket-close-loop",
                )
                if updated:
                    try:
                        from websocket_manager import broadcast_remediation_update
                        await broadcast_remediation_update(tenant_id, {
                            "task_id": task["id"], "status": "resolved",
                            "control_id": updated.get("control_id"),
                        })
                    except Exception:
                        pass  # non-fatal, matches D-04 philosophy
    except Exception as exc:
        logger.error("Close-loop pass failed: %s", exc)


async def start_close_loop_scheduler(db) -> None:
    """Loop every 15-30 min (D-03) polling linked external tickets for closure."""
    logger.info("Ticketing close-loop scheduler started (interval=1200s)")
    while True:
        await run_close_loop_pass(db)
        await asyncio.sleep(1200)  # 20 min — mid-range of D-03's 15-30 min guidance
```

## State of the Art

No externally-facing "state of the art" shift applies here — this is a pure internal-integration phase. The one relevant convention shift worth noting:

| Old Approach (this codebase, pre-Phase-43) | Current Approach (this phase) | When Changed | Impact |
|--------------------------------------------|-------------------------------|---------------|--------|
| `ticketing_service.py` connectors serve only security-alert tickets (1 call site: `edr_alerts`/`security_alerts`) | Same connectors serve a second call site (compliance remediation tasks) via an adapter, with zero changes to the connectors themselves | This phase | `ticketing_log`/`ticketing_configs` become shared infrastructure across two feature domains — any future connector bug-fix or new-provider addition benefits both call sites automatically |

**Deprecated/outdated:** None. Nothing in this phase's scope replaces or deprecates existing functionality.

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | Jira `statusCategory.key == "done"` is the correct provider-agnostic "issue closed" check | Code Examples, Common Pitfalls | If a tenant's custom Jira workflow doesn't map its terminal status to the "Done" category (rare but possible on old/misconfigured workflows), the close-loop would never fire for that tenant's tickets. Low risk — this is standard, well-documented Jira behavior, not an edge case; confidence is MEDIUM (web-search-cross-checked against Atlassian's own developer docs, not directly tested against a live Jira instance this session) |
| A2 | ServiceNow's numeric `state` codes are NOT safe to hardcode; display-value label comparison is the safer approach | Common Pitfalls, Code Examples | If display-value localization ever returns non-English labels for a tenant's ServiceNow locale settings, the `_SNOW_CLOSED_LABELS` set would need i18n handling — not addressed in this phase, flagged as an Open Question below, LOW risk for a v1 (English-labeled) deployment assumption |
| A3 | Auto-create (D-01) should use `config["provider"]` as the fallback when both Jira and ServiceNow are configured, since D-02's provider-picker only has a UI moment for the manual action | Architecture Patterns (Pattern 3) | If the user actually wants a different resolution (e.g. always prefer Jira for auto-create, or skip auto-create entirely when both are configured and ambiguous), this is a product decision CONTEXT.md didn't fully close — flag for discuss-phase/plan confirmation if the planner or user wants to revisit; the recommended default is low-risk since it reuses an existing, already-live field with an established single-responsibility precedent |
| A4 | 20-minute close-loop poll interval (mid-point of D-03's 15-30 min range) is an acceptable default | Code Examples | Purely a tuning knob explicitly left to "Claude's Discretion" per CONTEXT.md — no risk beyond needing adjustment if operational experience suggests otherwise |

## Open Questions

1. **ServiceNow terminal-state label set for non-English/heavily-customized instances**
   - What we know: Default OOB ServiceNow English labels for terminal incident states are "Resolved" and "Closed".
   - What's unclear: Whether any tenant customizes incident state labels or runs a non-English locale.
   - Recommendation: Ship with the English-label check (`{"closed", "resolved"}`); document as a known v1 limitation in the code comment (already reflected in the Code Examples above) rather than building a per-tenant configurable terminal-state list — that's scope creep against D-04's "best-effort" philosophy for a corner case with no reported demand.

2. **Should `create_ticket_for_remediation_task`'s dedup guard check `ticket_ref` presence, or also allow re-linking after a prior ticket was itself closed/abandoned?**
   - What we know: FEATURES.md's table-stakes list calls for a dedup guard ("check for an existing open linked ticket before creating a new one on repeat trigger").
   - What's unclear: Whether a tenant should be able to create a *second* ticket for the same task after the first one's close-loop already resolved the task (e.g., task reopened, needs a new ticket).
   - Recommendation: Simplest correct v1 behavior — the manual "Create Ticket" button is available whenever `ticket_ref` is unset (i.e., after close-loop resolution clears nothing, since resolution doesn't unset `ticket_ref` — the link to the *original* ticket remains visible for audit purposes). If a task is reopened (status moved back to `open`/`in_progress` manually), `ticket_ref` still points at the old (closed) ticket; the manual button should be disabled/hidden while `ticket_ref` is set, requiring the admin to explicitly understand a new ticket means abandoning the audit trail to the old one. Flag this UX nuance for the planner to make an explicit micro-decision on (e.g. "Create Ticket" button hidden whenever `ticket_ref` is truthy, full stop, simplest and lowest-risk).

## Environment Availability

No external tool/runtime dependency probing is needed for this phase — Jira/ServiceNow are per-tenant SaaS credentials entered via the existing `/api/ticketing/config` UI, not a local dev-environment dependency. `httpx` (the only relevant "dependency") is already confirmed present (see Standard Stack). Skipping this section's full table format since there is nothing to probe locally.

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest (via `backend/venv/bin/python -m pytest`) |
| Config file | none dedicated — plain `test_*.py` files under `backend/tests/` |
| Quick run command | `cd backend && venv/bin/python -m pytest tests/test_ticketing_bridge.py tests/test_remediation_workflow.py tests/test_tickets.py -q` |
| Full suite command | `cd backend && venv/bin/python -m pytest -q` (per project memory: 932+/0 green baseline as of 2026-07-14, re-verify current count before this phase's plan-gate) |

### Phase Requirements → Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| REM-01 | `_task_to_alert_shape` maps task fields correctly (control_id/priority/description present, no "N/A" leakage for mappable fields) | unit | `pytest tests/test_ticketing_bridge.py -k adapter -x` | ❌ Wave 0 |
| REM-01 | `create_ticket_for_remediation_task` calls `ticketing_service.create_jira_ticket`/`create_servicenow_incident` with adapted payload and `$set`s `ticket_provider`/`ticket_ref`/`ticket_url` on success | unit | `pytest tests/test_ticketing_bridge.py -k create_ticket -x` | ❌ Wave 0 |
| REM-01 | `create_ticket_for_remediation_task` is a no-op (returns without error) when `get_ticketing_config` returns `None` | unit | `pytest tests/test_ticketing_bridge.py -k no_config -x` | ❌ Wave 0 |
| REM-01 | Dedup guard: no second ticket created when `ticket_ref` already set on the task | unit | `pytest tests/test_ticketing_bridge.py -k dedup -x` | ❌ Wave 0 |
| REM-01 | Ticket-creation exception inside `create_task`'s auto-create hook does not propagate — task creation still succeeds (D-04) | unit | `pytest tests/test_remediation_workflow.py -k autocreate_nonfatal -x` | ❌ Wave 0 |
| REM-01 | `POST /tasks/{id}/create-ticket` endpoint: 200 with ticket fields on success, non-blocking-but-visible error response on connector failure | integration | `pytest tests/test_ticketing_bridge.py -k endpoint -x` | ❌ Wave 0 |
| REM-02 | `get_jira_issue_status`/`get_servicenow_incident_status` correctly classify `closed`/`open` from mocked HTTP responses | unit | `pytest tests/test_ticketing_bridge.py -k status_check -x` | ❌ Wave 0 |
| REM-02 | `run_close_loop_pass` calls `update_task(..., {"status": "resolved"}, ...)` when the linked ticket is closed, and that call's own re-scan dispatch fires (assert `dispatch_rescan`/`agent_instructions.insert_one` invoked) | unit | `pytest tests/test_ticketing_bridge.py -k close_loop_dispatch -x` | ❌ Wave 0 |
| REM-02 | `run_close_loop_pass` skips tasks with no `ticket_ref`, and skips (does not crash) when a tenant's ticketing config was removed after ticket creation | unit | `pytest tests/test_ticketing_bridge.py -k close_loop_skip -x` | ❌ Wave 0 |
| REM-02 | Scheduler registered with raw `mongodb.db`, not `get_database()` (regression guard against Pitfall 1) | unit | `pytest tests/test_ticketing_bridge.py -k raw_db_registration -x` | ❌ Wave 0 |

### Sampling Rate
- **Per task commit:** the quick-run command above, scoped to the file(s) touched.
- **Per wave merge:** full `tests/test_ticketing_bridge.py` + `tests/test_remediation_workflow.py` + `tests/test_tickets.py`.
- **Phase gate:** full backend suite green before `/gsd-verify-work`.

### Wave 0 Gaps
- [ ] `backend/tests/test_ticketing_bridge.py` — new file, covers REM-01/REM-02 per the table above. Clone the `_mock_db()` factory pattern from `tests/test_remediation_workflow.py` (MagicMock collections with `AsyncMock` methods) and extend it with a mocked `db.ticketing_configs`/`db.ticketing_log` collection.
- [ ] `backend/tests/test_remediation_workflow.py` — extend existing file's `_mock_db()` with a `db.compliance_remediation_tasks` scenario for the auto-create-on-high-priority hook inside `create_task` (currently the file only covers create/list/update/dispatch, not the new ticketing side-effect).
- Framework install: none — `pytest`/`unittest.mock` already present in `backend/venv`.

## Security Domain

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | no | No new auth surface — reuses `get_current_user` on all new/modified endpoints |
| V3 Session Management | no | Unaffected |
| V4 Access Control | yes | New `POST /tasks/{id}/create-ticket` route must reuse `_tenant_filter(user)` exactly as the existing `PATCH /tasks/{id}` does — same tenant-scoping precondition, no new role check needed beyond what the existing remediation endpoints already require |
| V5 Input Validation | yes | `provider` field on the manual create-ticket request must be validated against a `Literal["jira", "servicenow"]` (Pydantic), rejecting arbitrary strings before they reach `create_ticket_for_remediation_task`'s branch logic |
| V6 Cryptography | no | No new cryptographic material — reuses existing `ticketing_configs` credential storage as-is (Jira API token / ServiceNow password fields are stored in Mongo, matching the existing pattern for that collection; not introducing a new secrets-handling surface) |

### Known Threat Patterns for this stack

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| Client-supplied `ticket_ref`/`ticket_url` spoofing via `PATCH /tasks/{id}` | Tampering | `ticket_provider`/`ticket_ref`/`ticket_url` are never added to the `TaskUpdate` Pydantic model — only written server-side via `ticketing_bridge.py`'s internal `$set` (Pattern 2 above) |
| Cross-tenant ticket-status leakage via the close-loop scheduler | Information Disclosure | Raw-db scheduler queries `compliance_remediation_tasks` globally but resolves per-task `tenantId` from the document itself before calling `get_ticketing_config(tenant_id)` and before the `update_task(..., {"tenantId": tenant_id})` call — never a blanket cross-tenant write |
| Manual create-ticket endpoint used to enumerate/probe a tenant's other tenants' tasks via `task_id` guessing | Information Disclosure | Existing `_tenant_filter(user)` precondition on the route (same as every other `/tasks/{id}` route) — a 404 (not 403) is returned for a task_id outside the caller's tenant scope, matching existing endpoint behavior, no new information leak introduced |
| SSRF via a malicious `jira_url`/`snow_instance` value pointed at an internal service | Tampering / SSRF | Out of scope for this phase to newly mitigate — `ticketing_service.py`'s existing `create_jira_ticket`/`create_servicenow_incident` already have this theoretical exposure (admin-supplied URL, httpx GET/POST) and this phase reuses those functions unmodified rather than introducing a new instance of the pattern; note `backend/tests/test_ssrf_guards.py` exists in this codebase for other integrations — if a plan-checker or security-auditor flags this, it's a pre-existing condition of `ticketing_service.py`, not new exposure from Phase 43 |

## Sources

### Primary (HIGH confidence)
- Direct code reads (this repository, `feat/rust-agent-2.1.0-and-fixes` branch, 2026-07-21): `backend/ticketing_service.py` (full file, 384 lines), `backend/integration_service_ticketing.py` (full file, 212 lines), `backend/integration_service.py` (header/class definition), `backend/compliance_remediation_service.py` (full file, 172 lines), `backend/compliance_remediation_endpoints.py` (full file, 172 lines), `backend/ticketing_endpoints.py` (full file, 136 lines), `backend/tickets_escalation_service.py` (full file, 100 lines), `backend/scheduled_reports_service.py` (scheduler section, lines 1-80, 470-499), `backend/app_startup.py` (scheduler registration block, lines 580-641), `backend/router_registry.py` (registration lines 150-207), `backend/database.py` (`TenantIsolatedDatabase` exemption list, lines 110-154), `backend/tests/test_remediation_workflow.py` (mock-db pattern), `backend/tests/test_tickets.py` (mock-cursor pattern), `components/RemediationDashboard.tsx` (full file), `components/RemediationTaskModal.tsx` (full file), `components/TicketingIntegration.tsx` (full file), `components/Sidebar.tsx` (nav entries), `types.ts` (`RemediationTask` interface), `services/apiService.ts` (existing remediation/ticket wrapper functions), `backend/requirements.txt` (httpx pin, atlassian-python-api comment)
- `.planning/research/ARCHITECTURE.md`, `.planning/research/PITFALLS.md`, `.planning/research/FEATURES.md` (v3.2 milestone-level research, HIGH confidence, grounded in this same codebase)

### Secondary (MEDIUM confidence)
- [Jira Cloud Platform REST API — statuses/statusCategory](https://developer.atlassian.com/cloud/jira/platform/rest/v3/api-group-workflow-statuses/) — `statusCategory.key` semantics, cross-checked via WebSearch this session
- [ServiceNow Table API (Yokohama release docs)](https://www.servicenow.com/docs/bundle/yokohama-api-reference/page/integrate/inbound-rest/concept/c_TableAPI.html) — confirms `sysparm_display_value` parameter exists; used to justify the label-based (not numeric-code-based) closed-check

### Tertiary (LOW confidence)
- ServiceNow community forum threads on `incident.state` numeric values — explicitly conflicting across threads (one source: 6=Resolved/7=Closed; another: 6=Canceled/7=Awaiting Problem), which is *why* this research recommends the display-value label approach rather than trusting any specific numeric mapping

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — no new packages, all reused code read in full and verified by direct import inspection
- Architecture: HIGH — every integration point traced to actual file/line in this repository, cross-validated against the already-completed milestone-level ARCHITECTURE.md/PITFALLS.md
- Pitfalls: HIGH for the reused-pattern pitfalls (directly sourced from this codebase's own history/comments); MEDIUM for the two new status-check functions (no in-repo prior art, cross-checked against official provider docs via WebSearch but not tested against a live Jira/ServiceNow instance this session)

**Research date:** 2026-07-21
**Valid until:** 30 days (stable internal integration, no fast-moving external dependency)
