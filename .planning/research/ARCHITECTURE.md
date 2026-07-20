# Architecture Research — v3.2 Integration

**Domain:** Multi-tenant security/compliance portal (FastAPI + Motor/MongoDB + React/TS) — integrating 4 new remediation-ops features into existing architecture
**Researched:** 2026-07-20
**Confidence:** HIGH (grounded directly in the current codebase, not general domain patterns — every claim below is sourced from files read in this repo)

## Scope note

This is a subsequent-milestone integration study, not greenfield architecture research. The "standard architecture" already exists and is not re-litigated. Everything below answers one question: **how do the four v3.2 features attach to the existing FastAPI/Motor/tenant-isolation/router-registry/WebSocket/React skeleton**, file by file.

---

## System Overview (new touchpoints only)

```
┌───────────────────────────────────────────────────────────────────────────┐
│ compliance_remediation_endpoints.py  (/api/compliance-remediation)         │
│   POST /tasks   PATCH /tasks/{id}   POST /tasks/{id}/suggest               │
│         │                                                                   │
│         ▼                                                                   │
│ compliance_remediation_service.py                                          │
│   create_task() / update_task() ── (a) NEW: fire-and-forget task ──►       │
│                                       ticketing_bridge.create_ticket_for_   │
│                                       remediation_task()                    │
│                                            │                                 │
│                                            ▼                                 │
│                                     ticketing_service.py (REUSED, untouched) │
│                                       create_jira_ticket() /                │
│                                       create_servicenow_incident()          │
│                                            │                                 │
│                                            ▼                                 │
│                                     writes ticket_ref back onto             │
│                                     compliance_remediation_tasks.{ticket_*} │
│                                                                              │
│   update_task() status='resolved' ──► dispatch_rescan()  (unchanged)       │
│                                                                              │
│ (b) NEW: compliance_remediation_sla_service.py                             │
│   start_remediation_sla_scheduler(raw db) — asyncio loop, started from     │
│   app_startup.py next to start_escalation_scheduler/start_report_scheduler │
│   reuses tickets_helpers._compute_sla() (pure fn) on compliance_remediation│
│   _tasks docs; on breach → broadcast_remediation_update() (existing hook)  │
│                                                                              │
│ (c) NEW: control_comments_service.py + control_comments_endpoints.py       │
│   /api/compliance-controls/{control_id}/comments                           │
│   new tenant-scoped collection `control_comments`                          │
│   surfaces inside existing FrameworkDetail.tsx expanded-control row        │
│   (no new Sidebar.tsx nav entry required)                                  │
│                                                                              │
│ (d) NEW: cloud_checks_oci.py / cloud_checks_alibaba.py /                   │
│          cloud_checks_cloudflare.py  (same shape as cloud_checks_aws.py)   │
│   imported into cloud_checks_service.py CLOUD_CHECKS + RUNNABLE_PROVIDERS  │
└───────────────────────────────────────────────────────────────────────────┘
```

---

## Component Responsibilities (new components)

| Component | Responsibility | New or Modified |
|-----------|-----------------|------------------|
| `ticketing_bridge.py` (new, or a function added to `compliance_remediation_service.py`) | Adapts a `compliance_remediation_tasks` doc into the `alert`-shaped dict `ticketing_service.create_jira_ticket`/`create_servicenow_incident` expects; calls it; writes `ticket_provider`/`ticket_ref`/`ticket_url` back onto the task | New |
| `compliance_remediation_service.py` | `create_task`/`update_task` gain an optional post-write call into the ticketing bridge | Modified |
| `compliance_remediation_sla_service.py` (new) | Background sweep of `compliance_remediation_tasks` for `due_date` breach; escalates priority/broadcasts | New (sibling to, not an extension of, `tickets_escalation_service.py`) |
| `tickets_helpers.py` | `_compute_sla()` reused as-is (pure function, no schema coupling beyond `due_date`/`status`) | Unmodified, imported |
| `control_comments_service.py` + `control_comments_endpoints.py` (new) | CRUD for tenant-scoped comment threads keyed by `control_id` | New |
| `cloud_checks_oci.py`, `cloud_checks_alibaba.py`, `cloud_checks_cloudflare.py` (new) | Provider-specific `*_CHECKS` list, same shape as `cloud_checks_aws.py`/`cloud_checks_service.py`'s inline `DO_CHECKS` | New |
| `cloud_checks_service.py` | Import the 3 new check lists into `CLOUD_CHECKS`; add 3 providers to `RUNNABLE_PROVIDERS` | Modified |
| `router_registry.py` | Register `control_comments_endpoints` (and `ticketing_bridge` if it exposes its own router — likely not needed, see below) | Modified |
| `app_startup.py` | Start `compliance_remediation_sla_service.start_remediation_sla_scheduler()` next to the two existing scheduler `asyncio.create_task()` calls | Modified |
| `FrameworkDetail.tsx` | Render a comments panel inside the existing `expandedControlId` row, alongside `ControlEvidenceUploadModal` | Modified |
| `RemediationDashboard.tsx` | Show ticket ref/link and SLA badge on each task row; no new nav entry | Modified |

---

## New vs Modified Files — full list

**New backend files:**
- `backend/ticketing_bridge.py` — adapter + orchestration for (a). Keep this as its own module rather than bloating `compliance_remediation_service.py`; `ticketing_service.py` stays untouched (0 changes to its 383 lines, confirming "reuse don't rebuild").
- `backend/compliance_remediation_sla_service.py` — (b) scheduler + breach-detection logic, scoped to `compliance_remediation_tasks`.
- `backend/control_comments_service.py` — (c) DB logic for `control_comments`.
- `backend/control_comments_endpoints.py` — (c) FastAPI router, prefix `/api/compliance-controls` or `/api/control-comments` (see naming note below).
- `backend/cloud_checks_oci.py`, `backend/cloud_checks_alibaba.py`, `backend/cloud_checks_cloudflare.py` — (d) check definitions, one file per provider matching the AWS/Azure/GCP pattern (DigitalOcean is the *inline-list* exception inside `cloud_checks_service.py`; new providers should follow the dedicated-module pattern like AWS/Azure/GCP/K8s/M365/Mongo Atlas, not the DO inline shortcut — cleaner for 3 providers with real content).

**New frontend files:**
- `components/ControlCommentsPanel.tsx` (or similar) — mounted inside `FrameworkDetail.tsx`'s expanded control row.
- Ticket-bridge and SLA UI are additions to the *existing* `RemediationDashboard.tsx`, not new files.

**Modified backend files:**
- `backend/compliance_remediation_service.py` — `create_task()` and `update_task()` call the new ticketing bridge (see Pattern 1 below for sync-vs-async decision); `dispatch_rescan()` untouched.
- `backend/cloud_checks_service.py` — add 3 imports, extend `CLOUD_CHECKS`, extend `RUNNABLE_PROVIDERS` tuple (line 37).
- `backend/router_registry.py` — one new `_load(app, "control_comments_endpoints", "router")` line. `ticketing_bridge.py` and `compliance_remediation_sla_service.py` do **not** need router registration — bridge is called in-process by `compliance_remediation_service.py`, and the SLA service is a background task started from `app_startup.py`, not an HTTP surface (unless you also want a manual "run escalation now" endpoint — optional, low priority).
- `backend/app_startup.py` — one new `try/except` + `asyncio.create_task(...)` block, copy-pasted structurally from the `tickets_escalation_service` block (lines 602–608).
- `backend/database.py` — **no change needed.** `control_comments` and any ticket-ref fields on `compliance_remediation_tasks` are plain tenant-scoped writes through the existing `TenantIsolatedCollection` wrapper; see Pitfall note below for why this is *not* the Phase 39 auditor situation.

**Modified frontend files:**
- `components/FrameworkDetail.tsx` — mount `ControlCommentsPanel` in the expanded-row area (already has `expandedControlId` state and a slot pattern used by `ControlEvidenceUploadModal`).
- `components/RemediationDashboard.tsx` — add ticket-ref display + SLA badge to the task list; call new `api.createTicketForRemediationTask` / read `ticket_url` off the task object already returned by `GET /tasks`.
- `services/apiService.ts` (or wherever `getRemediationTasks`/`updateRemediationTask` live) — add thin wrappers for the new comment endpoints.

**Not modified (confirmed by reading):**
- `ticketing_service.py` — 0 lines changed. This is the point of "reuse, don't rebuild."
- `tickets_escalation_service.py` — 0 lines changed. It is genuinely a different domain (generic `db.tickets`, hardcoded query/update targets, its own priority-ladder/history schema). Extending it in place (e.g. adding an `if collection == "compliance_remediation_tasks"` branch) would couple two unrelated feature domains into one file and is explicitly the wrong move per the milestone brief.
- `mcp_server_endpoints.py` / `mcp_server.py` — no provider allowlist found in the MCP `run_cloud_check` tool path (it delegates straight to `cloud_checks_service.run_checks()`), so unlike the Phase 25 decision log entry (which named 4 lockstep gate locations), only **3** gates need widening for (d), not 4 — see Pitfalls.

---

## Architectural Patterns

### Pattern (a): Remediation-to-Ticketing Bridge — synchronous call, not event-driven

**What:** `compliance_remediation_service.create_task()` (and optionally `update_task()` on priority escalation) calls `ticketing_bridge.create_ticket_for_remediation_task(db, task, config)` **synchronously, in-request**, immediately after the task document is persisted — not via a queue, pub/sub, or polling worker.

**Why sync, not event-driven:** This codebase has no message bus / task queue (no Celery, no Redis Streams, no outbox table) anywhere in the backend — every cross-service call in `compliance_remediation_endpoints.py` (`dispatch_rescan`, AI-suggest, WebSocket broadcast) is a direct in-process `await` inside the endpoint's request/response cycle, wrapped in `try/except` so a downstream failure doesn't fail the parent write. Introducing an event bus for one bridge would be new infrastructure for a single call site — inconsistent with everything else in the file and unjustified by scale (remediation task creation is a low-frequency, human-triggered action, not a hot path).

**Failure isolation:** Ticket creation failure must **not** fail task creation. Follow the exact pattern already used for `dispatch_rescan`'s WebSocket push (lines 156–169 of `compliance_remediation_service.py`) and the endpoint's broadcast (lines 110–123 of `compliance_remediation_endpoints.py`): wrap in `try/except Exception`, log at `warning`, continue. A tenant with a misconfigured Jira token must still be able to create/update remediation tasks.

**Where the ticket ID gets stored:** Add three fields to the `compliance_remediation_tasks` document schema (in `compliance_remediation_service.create_task`'s `task` dict, or via a post-create `update_one`):
- `ticket_provider`: `"jira" | "servicenow" | None`
- `ticket_ref`: the Jira key / ServiceNow number (`data.get("key")` / `data.get("number")` — see `ticketing_service.create_jira_ticket`/`create_servicenow_incident` return shapes)
- `ticket_url`: the browsable URL, already computed by `ticketing_service` internally and returned in its `{"success": True, "url": ...}` payload

Write path: `ticketing_bridge.create_ticket_for_remediation_task()` calls `ticketing_service.create_jira_ticket(fake_alert, config)`, gets back `{"success": True, "ticket_key": "SEC-123", "url": "..."}`, then does `await db.compliance_remediation_tasks.update_one({"id": task["id"], **tenant_filter}, {"$set": {"ticket_provider": "jira", "ticket_ref": ticket_key, "ticket_url": url}})`. This mirrors the existing `ai_suggestion` persist-back pattern at the bottom of `suggest_remediation()` (lines 162–169 of `compliance_remediation_endpoints.py`) almost exactly — same "best-effort `$set` after an external call" shape.

**Adapter requirement — this is the part that isn't obvious:** `ticketing_service.create_jira_ticket(alert, config)` and `create_servicenow_incident(alert, config)` are hardcoded to read `alert.get("type")`, `alert.get("hostname")`, `alert.get("process", {}).get("name")`, `alert.get("mitre_technique")`, `alert.get("severity")`, `alert.get("alert_id")`, `alert.get("description")`. A `compliance_remediation_tasks` document has none of `hostname`/`process`/`mitre_technique` — it has `title`, `control_id`, `asset_id`, `priority`, `description`. Calling `create_jira_ticket(task, config)` directly would silently produce garbage tickets ("Process: N/A", "MITRE Technique: N/A", hostname "Unknown Host") rather than erroring — Python dict `.get()` swallows the mismatch. The bridge function must build an `alert`-shaped dict first:

```python
async def _task_to_alert_shape(db, task: dict) -> dict:
    hostname = "Unknown"
    if task.get("asset_id"):
        asset = await db.assets.find_one({"id": task["asset_id"]})
        hostname = (asset or {}).get("hostname", "Unknown")
    return {
        "alert_id": task["id"],
        "type": "compliance_remediation",
        "severity": task.get("priority", "medium"),   # priority already shares the same 4-value vocabulary as JIRA_PRIORITY_MAP
        "hostname": hostname,
        "process": {},
        "mitre_technique": "N/A",
        "description": f"Control {task.get('control_id','')} failed. {task.get('description','')}",
    }
```

`priority` on remediation tasks (`low|medium|high|critical`) already matches `JIRA_PRIORITY_MAP`/`SNOW_URGENCY_MAP` keys exactly — no re-mapping needed there.

**Config lookup:** reuse `ticketing_service.get_ticketing_config(tenant_id)` unchanged — same tenant-scoped `ticketing_configs` collection the alert-ticketing flow already uses. There's no separate "compliance ticketing config" — one config per tenant, shared across both alert-triggered and remediation-triggered tickets. If a tenant hasn't configured ticketing, `create_task`/`update_task` should skip the bridge call entirely (config lookup returns `None` → no-op, same short-circuit already in `auto_create_ticket_for_alert`).

**Trigger condition:** Recommend ticket creation on `create_task` only when `priority in ("high", "critical")` (mirrors `auto_create_severity` semantics already used for alerts) — or make it fully manual via a `POST /tasks/{id}/create-ticket` endpoint if the milestone wants explicit user control rather than automatic creation. Either is architecturally identical (same bridge function, different call site); this is a product decision, not an architecture one — flag for the roadmap/plan phase rather than deciding here.

### Pattern (b): SLA/Escalation — new dedicated service, reuse the pure SLA math only

**What:** `compliance_remediation_sla_service.py` is a **new, separate module**, not a modification of `tickets_escalation_service.py`. It has its own `run_remediation_sla_pass(db)` and `start_remediation_sla_scheduler(db)`, structurally copied from `tickets_escalation_service.py`'s two functions but pointed at `db.compliance_remediation_tasks` instead of `db.tickets`.

**What IS reused:** `tickets_helpers._compute_sla(ticket: dict) -> dict` is a pure function — it reads `due_date`, `status`, `total_hold_duration`, `hold_started_at` off any dict via `.get()` with safe defaults, injects `sla_status`/`sla_remaining_minutes`, and returns the same dict. `compliance_remediation_tasks` already has `due_date` and `status` fields (no hold-duration concept, which is fine — `.get("total_hold_duration", 0)` defaults to 0). **Import and call `_compute_sla()` directly** rather than reimplementing SLA math — this is the one genuinely reusable piece, confirmed by reading the function: it has zero coupling to the `tickets` collection schema beyond the fields already present on a remediation task.

**What is NOT reused:** `run_escalation_pass()` itself is hardcoded to `db.tickets.find(...)` / `db.tickets.update_one(...)`, a ticket-specific `_PRIORITY_LADDER`/`_bump_priority()`/`_history_entry()` trio that assumes a `history` array field remediation tasks don't have, and an `escalated`/`escalation_level` schema. Branching this function by collection name would be a worse coupling than just writing ~40 lines of new, parallel logic — the milestone brief's instinct ("different domain, not reusable as-is") is correct after reading the code.

**New escalation semantics for remediation tasks:** Priority bump (reuse `_bump_priority()` from `tickets_escalation_service` — it's a tiny pure function, fine to import) plus `await broadcast_remediation_update(tenant_id, {...})` on breach, using the **existing** WebSocket hook rather than inventing a new broadcast function. Store `escalated`/`escalated_at`/`escalation_level` fields on the task doc, mirroring the tickets schema loosely (consistency of vocabulary across the codebase, not code reuse).

**Where the scheduler lives — confirmed prior art:** `app_startup.py` is the single place all three background loops (`start_finops_scheduler`, `start_escalation_scheduler`, `start_report_scheduler`) get started, each in its own `try/except` block calling `asyncio.create_task(...)`, logged with a `[Domain] ... started` info line on success and a `warning` on failure to import. Add a fourth block:

```python
try:
    from compliance_remediation_sla_service import start_remediation_sla_scheduler
    from database import mongodb as _mdb
    asyncio.create_task(start_remediation_sla_scheduler(_mdb.db))
    logger.info("[Compliance] Remediation SLA scheduler started")
except Exception as _e:
    logger.warning("[Compliance] Remediation SLA scheduler failed to start: %s", _e)
```

**Important detail on tenant scoping for the scheduler itself:** note that `start_escalation_scheduler(_mdb.db)` and `start_report_scheduler()` are passed the **raw, unwrapped** `mongodb.db` (or call `get_database()` after `set_tenant_id("platform-admin")`), because a background sweep must scan *across all tenants* in one query, not one tenant at a time — the `TenantIsolatedCollection` wrapper would silently scope every query to a single (or no) tenant via the context-var, which is wrong for a global sweep. The new remediation SLA scheduler must follow the same raw-`db` convention (`db.compliance_remediation_tasks.find({"status": {"$in": ["open","in_progress"]}, "escalated": False})` — no `tenantId` filter, since the task documents already carry `tenantId` per-document, and the scheduler only needs it for the per-task WebSocket broadcast target, not for query scoping). This is a legitimate, already-precedented use of the raw-`db` escape hatch — distinct from the Phase 39 pitfall (see below).

**Interval:** match the existing 300s (5 min) cadence used by both `tickets_escalation_service` and `scheduled_reports_service` — no reason to deviate, and it keeps operational/monitoring expectations consistent.

### Pattern (c): Comment Threads on Compliance Controls — new tenant-scoped collection, NOT embedded

**What:** A new `control_comments` collection, one document per comment: `{id, control_id, tenantId, author, text, created_at, mentions?}`. **Do not** clone the *storage* mechanics of `tickets_endpoints.py`'s comment pattern (`$push` into a `comments` array embedded on the parent document) — only clone its *endpoint shape* (`POST /{parent_id}/comments`, `@mentions` regex + notification hook).

**Why not embedded, despite the milestone brief saying "clone tickets_endpoints.py's pattern":** Tickets (`db.tickets`) are tenant-owned documents — each ticket belongs to exactly one tenant, so `$push`-ing a comment into the ticket doc is safe. Compliance **controls** (`db.compliance_controls`) are on the tenant-isolation **exemption allowlist** in `database.py` (`TenantIsolatedDatabase.__getattr__`/`__getitem__`, lines 122–135) — they are global reference data shared across every tenant (SOC 2 CC6.1 is the same document for tenant A and tenant B). Embedding tenant-specific comments into a shared, globally-exempted document would mean **every tenant sees every other tenant's comments** on that control — a cross-tenant data leak by construction, not a bug to catch later. This is the single most important integration finding for (c): the "clone the pattern" instruction in the milestone brief is right about the *endpoint/response shape*, wrong if taken to mean "embed the same way" — a dedicated tenant-scoped collection is structurally required here, not a style preference.

**Tenant isolation exemption list treatment — answer: no exemption needed.** `control_comments` should go through the **default** `TenantIsolatedCollection` path (i.e., must **not** be added to the exemption list in `database.py`). Each comment write auto-gets `tenantId` injected by `TenantIsolatedCollection.insert_one()`; each read auto-filters by the caller's `tenantId`. This is structurally identical to how `compliance_remediation_tasks` already works today (`control_id` references a *global* `compliance_controls` document, but the *task*/*comment* about that control is tenant-private) — proven, already-shipped precedent in this exact codebase, not a new pattern. No `db._db` unwrap is needed (that escape hatch, used in Phase 39, was specifically for a collection needing `global OR tenant` `$or` scoping — comments need neither; they are purely tenant-scoped, full stop).

**Minimal endpoint surface** (`control_comments_endpoints.py`, prefix `/api/compliance-controls/{control_id}/comments` — or `/api/control-comments?control_id=` if the codebase's existing endpoint-prefix conventions favor query-param filtering over path nesting for this kind of resource; `compliance_remediation_endpoints.py` uses query params (`?control_id=`) for filtering, so prefer consistency: `GET /api/control-comments?control_id=X` + `POST /api/control-comments`):
- `POST /api/control-comments` — body `{control_id, text}`; author/tenant derived from `get_current_user` exactly like `compliance_remediation_endpoints._tenant_filter`.
- `GET /api/control-comments?control_id=X` — list, tenant-scoped, sorted by `created_at`.
- `DELETE /api/control-comments/{comment_id}` — author or admin only (mirror the manual-evidence delete RBAC precedent from v1.0: "owner/admin delete").

No `PATCH`/edit needed for MVP — comment threads in GRC tools are typically append-only audit trails, which also sidesteps a whole class of "who can edit whose comment" RBAC questions. (Flag this as a product decision for the roadmap, but architecturally, append-only is the lower-risk default and matches how `tickets_service.add_comment` works today — it has no edit endpoint either, only `add_comment`.)

**Frontend integration — no Sidebar.tsx entry required.** Unlike a full new dashboard (which would need `App.tsx`'s lazy-import + view-switch + `Sidebar.tsx` nav item, per the milestone's stated "unreachable" gotcha), comment threads are a sub-panel of an *already-reachable* view. `FrameworkDetail.tsx` already has `expandedControlId` state (line 42) and mounts `ControlEvidenceUploadModal` in that expanded-row context. Add a `ControlCommentsPanel` component mounted the same way. This sidesteps the "new dashboard never wired into nav" failure mode entirely because there is no new top-level view.

### Pattern (d): New CSPM Provider — dedicated check-definition module, 3 (not 4) gates to widen

**What:** For each of OCI, Alibaba, Cloudflare: a new `cloud_checks_<provider>.py` file exporting a `<PROVIDER>_CHECKS: List[Dict[str, Any]]` list, each entry shaped exactly like an `AWS_CHECKS`/`AZURE_CHECKS` entry (`id`, `name`, `description`, `provider`, `service`, `severity`, `frameworks`, `remediation`) — copy the dict shape from `cloud_checks_aws.py` verbatim, just change `id` prefixes (`oci-*`, `alibaba-*`, `cf-*`) and provider-relevant `service`/`frameworks` values.

**Why a dedicated module, not inline like DigitalOcean:** `DO_CHECKS` is defined *inline* inside `cloud_checks_service.py` (lines 17–28) rather than as a separate module — this looks like it was a shortcut for a small (10-check) list. For OCI/Alibaba/Cloudflare, matching the dominant pattern (AWS/Azure/GCP/K8s/M365/MongoDB-Atlas — 6 of 7 existing providers use dedicated modules, only DO is inline) keeps `cloud_checks_service.py` from growing unboundedly and matches the CLAUDE.md "keep files under 500 lines" rule (`cloud_checks_service.py` is currently 150 lines — inlining 3 more provider lists at DO's scale would roughly double it; separate files keep it thin).

**Exact changes required (confirmed by reading, all 3 in `cloud_checks_service.py` unless noted):**
1. `cloud_checks_service.py` line 9–14: add `from cloud_checks_oci import OCI_CHECKS`, `from cloud_checks_alibaba import ALIBABA_CHECKS`, `from cloud_checks_cloudflare import CLOUDFLARE_CHECKS`.
2. `cloud_checks_service.py` line 31: extend `CLOUD_CHECKS = AWS_CHECKS + AZURE_CHECKS + GCP_CHECKS + K8S_CHECKS + DO_CHECKS + M365_CHECKS + MONGODB_ATLAS_CHECKS + OCI_CHECKS + ALIBABA_CHECKS + CLOUDFLARE_CHECKS`.
3. `cloud_checks_service.py` line 37: extend `RUNNABLE_PROVIDERS = (..., "oci", "alibaba", "cloudflare")`. **This is the load-bearing change** — `run_checks()` (line 67) hard-rejects any provider not in this tuple with `{"error": f"provider must be one of {RUNNABLE_PROVIDERS}", "ran": 0}`, which is exactly the "allowlisted but zero check logic" symptom described in the milestone brief: `cloud_checks_endpoints.py`'s `/run` payload validation (line 73) already accepts `oci`/`alibaba`/`cloudflare`, so a request currently passes endpoint validation and then dies one layer down in the service with a 400.
4. `cloud_checks_endpoints.py` line 73 — **already includes** `oci`, `alibaba`, `cloudflare` in its inline provider tuple; **no change needed here**, contrary to first assumption — it was pre-widened, only `RUNNABLE_PROVIDERS` lags.
5. `cloud_account_endpoints.py` line 13 `_VALID_PROVIDERS` — **already includes** all three; **no change needed here either**. Account *registration* already works end-to-end for these providers; only *check execution* is blocked.

So the real gap is narrower than "widen 2 allowlists" — it's **one line** (`RUNNABLE_PROVIDERS`) plus **three new check-definition files**. The milestone brief's framing ("nothing implements checks for them") is accurate; the *allowlist* framing undersells how much is already done. **Do not** waste a phase auditing/touching `cloud_checks_endpoints.py` or `cloud_account_endpoints.py`'s allowlists — verify with a quick `grep` at plan time that they still contain all three (they do as of this research date), then move straight to writing the check modules + the `RUNNABLE_PROVIDERS` line.

6. **`mcp_server_endpoints.py`/`mcp_server.py`** — the milestone's own Key Decisions log (Phase 25 entry) names this as a 4th lockstep gate location from a prior provider-widening. Reading the current `mcp_server.py`/`mcp_rest_endpoints.py` `run_cloud_check` tool definitions found **no provider allowlist** in the MCP layer today — it appears to delegate provider validation entirely to `cloud_checks_service.run_checks()` (which will now correctly accept the new providers once `RUNNABLE_PROVIDERS` is widened). Treat this as **resolved by inheritance**, not a 4th file to touch — but a plan-phase implementer should still grep `mcp_server.py`/`mcp_rest_endpoints.py` for a hardcoded provider list before assuming this, since MCP tool schemas sometimes duplicate enums for LLM-facing parameter descriptions (cosmetic, non-blocking if missed, but worth a 30-second check).

**`run_checks()` behavior for providers with no real scanner yet:** Note `run_checks()` (cloud_checks_service.py lines 65–114) works purely off *previously-imported* `cloud_findings` documents (`db.cloud_findings.find({"accountId":..., "tenantId":...})`) — it does not itself call out to any cloud provider API. This means OCI/Alibaba/Cloudflare checks will behave exactly like DigitalOcean's did before real findings existed: `has_real_findings = False` → every check gets `"simulated": True` and defaults to `PASS` (no matching findings = pass). This matches the **existing, already-shipped** "labeled simulated data" precedent (Key Decision: "CloudFormation container-scan 'simulated' data is labeled, not fail-closed" — Phase 25, CHK-03) — no new design decision needed, just confirm the 3 dashboard `SIMULATED` badge sites (already built for the DO/CloudFormation case) render correctly for these 3 new providers too (should be automatic, since the badge logic keys off the `simulated` field generically, not a provider allowlist — verify this assumption in the plan/execute phase, don't just assume).

---

## Data Flow

### Ticket bridge (feature a)

```
POST /api/compliance-remediation/tasks
    → compliance_remediation_service.create_task()
        → insert compliance_remediation_tasks doc
        → [NEW] await ticketing_bridge.create_ticket_for_remediation_task(db, task, tenant_id)
              → ticketing_service.get_ticketing_config(tenant_id)   [existing, unmodified]
              → build alert-shaped dict from task + asset lookup
              → ticketing_service.create_jira_ticket() / create_servicenow_incident()  [existing, unmodified]
              → db.compliance_remediation_tasks.update_one(..., {"$set": {ticket_provider, ticket_ref, ticket_url}})
        → return task (now includes ticket_* fields if bridge succeeded)
```

### SLA escalation (feature b)

```
app_startup.py (on boot)
    → asyncio.create_task(compliance_remediation_sla_service.start_remediation_sla_scheduler(raw_db))
        → every 300s:
            → raw_db.compliance_remediation_tasks.find({"status": {"$in":["open","in_progress"]}, "escalated": False})
            → for each task: tickets_helpers._compute_sla(task)   [existing, unmodified, imported]
            → if breached: bump priority, $set escalated fields, await broadcast_remediation_update(task["tenantId"], {...})  [existing WS hook]
```

### Comment threads (feature c)

```
FrameworkDetail.tsx (expandedControlId set)
    → ControlCommentsPanel mounts
        → GET /api/control-comments?control_id=X   (tenant-scoped via TenantIsolatedCollection, default path)
    → user submits comment
        → POST /api/control-comments {control_id, text}
            → control_comments_service.add_comment()
                → db.control_comments.insert_one({id, control_id, tenantId, author, text, created_at})
                  [tenantId auto-injected by TenantIsolatedCollection.insert_one — no exemption listing]
```

### CSPM check execution (feature d)

```
POST /api/cloud-checks/run {accountId, provider: "oci"}
    → cloud_checks_endpoints.run_checks()   [already accepts "oci" — no change]
        → cloud_checks_service.run_checks(account_id, "oci", tenant_id)
            → provider in RUNNABLE_PROVIDERS?  [NEW: "oci" now included]
            → provider_checks = [c for c in CLOUD_CHECKS if c["provider"]=="oci"]   [NEW: OCI_CHECKS now contributes entries]
            → evaluate against db.cloud_findings (empty until a real OCI scanner exists → all PASS, simulated=True)
            → upsert db.cloud_check_results
```

---

## Integration Points

### Internal boundaries

| Boundary | Communication | Notes |
|----------|---------------|-------|
| `compliance_remediation_service` ↔ `ticketing_service` | Direct in-process `await` call (adapter function in between) | No new infra; must be non-fatal on ticketing failure (try/except, same as existing `dispatch_rescan` WS push) |
| `compliance_remediation_sla_service` ↔ `compliance_remediation_tasks` | Raw (unwrapped) `db` access, background loop | Matches existing `tickets_escalation_service`/`scheduled_reports_service` convention for cross-tenant sweeps — this is sanctioned, not a tenant-isolation violation |
| `control_comments_service` ↔ `compliance_controls` (global) | `control_id` is a loose foreign key, no join enforced at write time (matches `compliance_remediation_tasks.control_id` precedent — no FK validation exists there either) | Comments collection itself stays fully tenant-scoped (default `TenantIsolatedCollection` path) |
| `cloud_checks_service` ↔ new provider check modules | Static import + list concatenation | Zero runtime coupling; each provider module is a flat data file, no logic |
| New schedulers ↔ `app_startup.py` | `asyncio.create_task()` in a `try/except` block at server boot | 4th instance of an established pattern — no new mechanism |
| New endpoints ↔ `router_registry.py` | `_load(app, "module_name", "router")` | Only `control_comments_endpoints` needs this; the SLA scheduler and ticketing bridge are not separate routers |

### External services (unchanged by this milestone)

| Service | Integration Pattern | Notes |
|---------|---------------------|-------|
| Jira / ServiceNow | `ticketing_service.py`'s existing `httpx` calls | Reused as-is for remediation tickets; no new provider onboarding |
| OCI / Alibaba / Cloudflare cloud APIs | **Not called yet** — `run_checks()` only evaluates pre-imported `cloud_findings`, it has no live-scan capability for any provider | Real OCI/Alibaba/Cloudflare *scanning* (vs. check *definitions*) is out of scope for this milestone per the brief; don't scope-creep into building live scanners |

---

## Anti-Patterns (specific to this integration)

### Anti-Pattern 1: Extending `tickets_escalation_service.py` in place

**What people might do:** Add an `if collection_name == "compliance_remediation_tasks"` branch, or a `collection` parameter, to `run_escalation_pass()`/`start_escalation_scheduler()` to "avoid duplication."
**Why it's wrong:** The function's priority-ladder, history-entry shape, and `escalated`/`escalation_level` field semantics are ticket-domain-specific; forcing a second, structurally different domain through the same function couples two unrelated features and makes both harder to change independently. The milestone brief's instinct to treat this as "a different domain" is correct.
**Instead:** New module, reuse only the pure `_compute_sla()` helper.

### Anti-Pattern 2: Embedding comments on `compliance_controls`

**What people might do:** `$push` comments into the shared `compliance_controls` document, copying `tickets_service.add_comment`'s storage mechanics literally, because the milestone brief says "clone the pattern."
**Why it's wrong:** `compliance_controls` is on the tenant-isolation exemption allowlist (global reference data). Any tenant-specific data embedded there leaks across every tenant.
**Instead:** New `control_comments` collection, tenant-scoped via the default (non-exempted) `TenantIsolatedCollection` path — clone the endpoint *shape*, not the storage mechanism.

### Anti-Pattern 3: Calling `ticketing_service.create_jira_ticket(task, config)` directly with no adapter

**What people might do:** Pass the remediation task dict straight into the existing ticketing functions since "they already exist, just reuse them."
**Why it's wrong:** Field-name mismatch (`hostname`, `process`, `mitre_technique` vs. `title`, `control_id`, `asset_id`) is silently absorbed by `.get()` defaults, producing tickets with "Unknown Host" / "Process: N/A" / "MITRE Technique: N/A" instead of an error — a correctness bug that won't surface until someone reads a live Jira ticket.
**Instead:** A thin adapter function that maps remediation-task fields into the alert shape before calling the existing (unmodified) ticketing functions.

### Anti-Pattern 4: Assuming all 4 Phase-25-style gate locations need touching for new cloud providers

**What people might do:** Following the Key Decisions log entry literally, spend effort updating `cloud_checks_service.py`, `cloud_checks_endpoints.py`, `cloud_account_endpoints.py`, and `mcp_server_endpoints.py` in lockstep for OCI/Alibaba/Cloudflare, as was necessary in Phase 25.
**Why it's wrong here:** Verified by reading current code — `cloud_checks_endpoints.py` and `cloud_account_endpoints.py` already include all three providers in their allowlists (this was apparently done in the same widening pass referenced by the Phase 25 decision, or later). Only `RUNNABLE_PROVIDERS` in `cloud_checks_service.py` is stale. Re-touching already-correct allowlists is wasted plan/review time, and touching `mcp_server_endpoints.py` speculatively (it has no gate to touch) risks introducing an unnecessary diff.
**Instead:** Grep the 3 allowlist locations first, at plan time, to confirm current state before scoping the phase — don't assume the historical decision log describes today's code unchanged.

---

## Suggested Build Order

**Independent, can run first / in parallel (already scoped, zero overlap with the 4 features below):**
1. Rust agent 2.1.0 dependency modernization (`agent-install/omni-agent-rs` — the shipping tree) — pure dependency/lockfile work in a separate language toolchain, no backend/frontend coupling.
2. 401 auth-session bug investigation — orthogonal to remediation-ops; touches `authentication_service.py`/session/token handling, not any of the 4 files families above.

These two can be dispatched to a separate workstream/agent entirely and don't block or get blocked by anything below.

**Remediation-ops features — recommended sequencing (dependency-driven, not arbitrary):**

3. **(d) CSPM checks for OCI/Alibaba/Cloudflare** — do this first among the 4. It is the most isolated (new data-only modules + one `RUNNABLE_PROVIDERS` line), has zero shared surface with (a)/(b)/(c), and de-risks nothing else, but also risks nothing else — good warm-up / parallelizable slot. Verify the 2 allowlists are already correct before writing any check module (5-minute grep, per Anti-Pattern 4).

4. **(c) Comment threads on compliance controls** — second. Also fully isolated from (a)/(b) (new collection, new router, new frontend sub-panel). The only shared context with (a)/(b) is "both attach to compliance-domain data," but no code dependency. Doing this before (a)/(b) means the tenant-isolation "no exemption needed" pattern gets validated (and can be pointed to as precedent) before the SLA scheduler work, which also needs a clear head on the raw-`db` vs. wrapped-`db` distinction.

5. **(a) Remediation-to-ticketing bridge** — third. Depends on nothing above, but should land before (b) because (b)'s escalation logic will likely want to *also* trigger/update a ticket on breach (a natural product follow-on even if not explicitly in scope) — building the bridge first means (b) can optionally hook into it later without rework. If (b) truly won't touch tickets, this ordering constraint relaxes and (a)/(b) become swappable.

6. **(b) SLA/escalation for remediation tasks** — fourth, after (a). Needs `compliance_remediation_tasks` to have stabilized its schema for this milestone (both (a) and (b) add new fields to the same document — `ticket_*` from (a), `escalated`/`escalation_level`/`sla_status` from (b) — sequencing avoids two features racing to define the task schema shape in parallel plans/reviews).

**Rationale for (d), (c) before (a), (b):** (d) and (c) are structurally trivial and fully additive (new files, one new allowlist line, no shared schema). (a) and (b) both mutate the same `compliance_remediation_tasks` document and both need the SLA-scheduler-vs-request-cycle distinction (raw `db` for background sweeps, wrapped `db` for endpoints) to be applied correctly — sequencing them last, with (a) before (b), minimizes schema churn and lets whoever plans (b) reference a real, shipped example of the raw-`db` scheduler pattern from (a)'s sibling work in this same milestone (well — (a) doesn't need a scheduler; more precisely, (b) can reference the *existing* `tickets_escalation_service`/`scheduled_reports_service` prior art either way, so this ordering benefit is secondary — the primary reason for (a) before (b) is simply "shared document, avoid concurrent-phase schema conflicts").

**Everything in this milestone is backend-then-frontend within each feature**, not backend-milestone-then-frontend-milestone: each of (a)/(b)/(c)/(d) should ship its backend + the specific frontend touch-point (ticket badge, SLA badge, comments panel, provider dropdown activation) in the same phase, since none of the frontend changes are large enough to warrant their own phase, and shipping backend-only for any of these leaves it unverifiable via UAT.

---

## Sources

- Direct code reads (this repository, `feat/rust-agent-2.1.0-and-fixes` branch, 2026-07-20): `backend/compliance_remediation_service.py`, `backend/compliance_remediation_endpoints.py`, `backend/ticketing_service.py`, `backend/ticketing_endpoints.py`, `backend/tickets_escalation_service.py`, `backend/tickets_helpers.py`, `backend/tickets_endpoints.py` (comments section), `backend/tickets_models.py`, `backend/scheduled_reports_service.py`, `backend/app_startup.py`, `backend/router_registry.py`, `backend/database.py`, `backend/cloud_checks_service.py`, `backend/cloud_checks_endpoints.py`, `backend/cloud_account_endpoints.py`, `backend/cloud_checks_aws.py`, `App.tsx`, `components/Sidebar.tsx`, `components/RemediationDashboard.tsx`, `components/ComplianceDashboard.tsx`, `components/FrameworkDetail.tsx`.
- `.planning/PROJECT.md` (v3.2 milestone section) and `.planning/HANDOFF.json` (tasks 10/11 status, confirming independence of Rust/auth work from the 4 remediation-ops features).

---
*Architecture research for: Enterprise OmniAgent v3.2 milestone integration*
*Researched: 2026-07-20*
