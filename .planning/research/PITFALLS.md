# Pitfalls Research — v3.2 Agent Modernization & Remediation Ops

**Domain:** Adding ticket-bridge, SLA/escalation, threaded comments, and CSPM provider checks to an existing multi-tenant GRC platform
**Researched:** 2026-07-20
**Confidence:** HIGH — every pitfall below is verified against actual source in this repo (file/line cited), not generic GRC advice

**Method note:** This is 100% internal codebase archaeology — no external ecosystem research was needed or performed. All findings are drawn from reading `backend/database.py`, `backend/router_registry.py`, `backend/ticketing_service.py`, `backend/tickets_endpoints.py`, `backend/tickets_service.py`, `backend/tickets_escalation_service.py`, `backend/tickets_helpers.py`, `backend/compliance_remediation_service.py`, `backend/compliance_remediation_endpoints.py`, `backend/cloud_checks_service.py`, `backend/cloud_checks_endpoints.py`, `backend/cloud_account_endpoints.py`, `backend/mcp_server.py`, `backend/websocket_manager.py`, `backend/app_startup.py`, `backend/authentication_endpoints.py`, and relevant git history (`e55ba34`, `720a76d`, `772e9058`), plus `.planning/PROJECT.md` and `.planning/HANDOFF.json`.

## Critical Pitfalls

### Pitfall 1: SLA/escalation background sweep silently returns zero results for every tenant

**What goes wrong:**
A new scheduler loop for `compliance_remediation_tasks` (mirroring `tickets_escalation_service.run_escalation_pass`) is written to call `get_database()` and iterate `db.compliance_remediation_tasks.find(...)`. It runs, throws no errors, logs "0 escalated" forever — even with real overdue tasks in the DB.

**Why it happens:**
`get_database()` returns a `TenantIsolatedDatabase`. `compliance_remediation_tasks` is **not** in the exemption allowlist in `database.py` (only `compliance_frameworks`, `compliance_controls`, `ai_governance_frameworks`, `system_features`, `tenants`, `roles`, `response_policies`, `playbooks`, `ip_bans`, `crypto_inventory` are exempt), so it gets wrapped in `TenantIsolatedCollection`. That wrapper's `_inject_tenant_id()` reads `get_tenant_id()` from a **contextvar** (`tenant_context.py`) that is only populated inside an authenticated HTTP request. A background `asyncio` task started from `app_startup.py` has no request context, so `get_tenant_id()` returns `None`, and the fail-closed logic substitutes `tenantId = "NON_EXISTENT_TENANT_ISOLATION_EMERGENCY"` into every query — matching nothing, for every tenant, always. This is a real, live example already fixed correctly for the existing ticket system: `tickets_escalation_service.start_escalation_scheduler` is deliberately called from `app_startup.py:605` with the **raw, unwrapped** `mongodb.db` (`from database import mongodb as _mdb; ... start_escalation_scheduler(_mdb.db)`), never `get_database()`. `run_escalation_pass` itself then does its own per-document handling without tenant filters (it's scanning across all tenants by design, since it's a background sweep, not a request).

**How to avoid:**
Wire the new `compliance_remediation_tasks` SLA scheduler exactly like `tickets_escalation_service`: import `mongodb` from `database.py`, pass `mongodb.db` (raw motor db) into the sweep function, and register it in `app_startup.py` next to the existing `tickets_escalation_service` block — not via `get_database()`/`get_db()`. Do not add `compliance_remediation_tasks` to the `database.py` exemption allowlist as a workaround — that would remove tenant isolation for the collection everywhere else (all request-scoped endpoint access), which is far worse.

**Warning signs:**
Scheduler logs "0 breached" indefinitely despite manually-verified overdue tasks in Mongo; a quick `db.compliance_remediation_tasks.find({tenantId: "..."})` from a shell shows correct data but the app-level sweep sees nothing; no exceptions anywhere (fail-closed is silent by design — see `database.py:36-37`'s `logging.error("[SECURITY ALERT] ...")` which only fires on `insert_one`/`aggregate`, not on `find`/`update_one`, so even the log signal is easy to miss for reads).

**Feature area:** SLA/escalation for `compliance_remediation_tasks` (feature b).

---

### Pitfall 2: Comment threads on `compliance_controls` leak across tenants (or corrupt shared reference data)

**What goes wrong:**
PROJECT.md's suggestion to "clone `tickets_endpoints.py`'s comment-thread pattern" is read literally: `tickets_service.add_comment()` pushes a comment object directly onto the parent document's `comments[]` array with `$push` (`tickets_service.py:364-369`, `db[self.COL].update_one({"id": ticket_id, "tenantId": tenant_id}, {"$push": {"comments": comment}})`). If a control-comment feature copies this by pushing into `db.compliance_controls`, it will silently write into a **single global document shared by all tenants** — every tenant sees every other tenant's comments on that control, and concurrent writes from different tenants race on the same document.

**Why it happens:**
`compliance_controls` is explicitly in `database.py`'s exemption allowlist (`"compliance_controls"` appears twice, in both `__getattr__` and `__getitem__`) as global reference data — the 30+ seeded frameworks' control definitions are one document per control, read identically by every tenant (`seed_compliance_controls_*.py`). Tickets are tenant-owned documents (one ticket = one tenant), so the embed-and-`$push` pattern is safe there. Controls are *not* tenant-owned documents — cloning the storage pattern without noticing this distinction is the actual trap; the *endpoint shape* (POST comment, GET thread, @mention detection) is fine to clone, the *storage* is not.

**How to avoid:**
Create a new, separate, tenant-scoped collection (e.g. `control_comments`) with documents shaped like `{id, control_id, tenantId, author, text, created_at, edited}` — never write comment data onto `compliance_controls` documents. Add an index `(tenantId, control_id, created_at)` to `database.py`'s index block (there is currently none for this new collection — it doesn't exist yet). Since this is a brand-new collection not in the exemption list, `TenantIsolatedCollection` will auto-scope it correctly for free on every request-path read/write — no manual `tenantId` filter needed in the endpoint (though it doesn't hurt to be explicit for clarity, per the pattern in `compliance_remediation_endpoints.py`).

**Warning signs:**
Any UAT step where Tenant A sees Tenant B's comment text on a control page; any code that does `db.compliance_controls.update_one(..., {"$push": {"comments": ...}})` or `find_one_and_update` targeting `compliance_controls`; a control-comment count that doesn't reset per tenant in manual testing.

**Feature area:** Comment threads on compliance controls (feature c) — this is the single highest-severity pitfall for this milestone.

---

### Pitfall 3: OCI/Alibaba/Cloudflare "add checks" only touches 1 of 4 duplicated provider gates

**What goes wrong:**
A developer adds `cloud_checks_oci.py`, `cloud_checks_alibaba.py`, `cloud_checks_cloudflare.py` (mirroring `cloud_checks_aws.py`/`cloud_checks_azure.py`), imports and concatenates them into `CLOUD_CHECKS` in `cloud_checks_service.py`, ships it — and `POST /api/cloud-checks/run` still fails with `"provider must be one of ('aws', 'azure', 'gcp', 'kubernetes', 'digitalocean', 'microsoft365', 'mongodb_atlas')"` for the 3 new providers, even though account registration (`POST /api/cloud-accounts`) happily accepted `provider: "oci"` already.

**Why it happens:**
This is the exact same class of bug as Phase 25's CHK-01 (documented in PROJECT.md's Key Decisions table: "Provider-allowlist widening ... touches all 4 duplicated gate locations in lockstep, not just the named execution gate"). Verified live in the current tree: `cloud_checks_endpoints.py:73` and `cloud_account_endpoints.py:13` **already** list `"oci", "alibaba", "cloudflare"` in their validation tuples (someone widened the *front-door* gates in anticipation), but `cloud_checks_service.py:37`'s `RUNNABLE_PROVIDERS = ("aws", "azure", "gcp", "kubernetes", "digitalocean", "microsoft365", "mongodb_atlas")` — the gate that actually controls whether `run_checks()` evaluates anything — does **not** include them yet. This is precisely the "currently allowlisted but zero check logic" state PROJECT.md describes. `mcp_server.py:63-65` is the 4th gate but imports `RUNNABLE_PROVIDERS` directly from `cloud_checks_service` rather than duplicating it, so it self-updates once #3 is fixed — but don't assume that of every gate; the two endpoint files hardcode their own tuples/sets independently.

**How to avoid:**
Grep for every literal occurrence of the existing provider list before touching any one of them: `grep -rn "digitalocean.*microsoft365\|microsoft365.*digitalocean\|RUNNABLE_PROVIDERS" backend/*.py`. As of this research, the 4 real locations are: `cloud_checks_service.py:37` (`RUNNABLE_PROVIDERS` — the execution gate, THE one that's currently missing oci/alibaba/cloudflare), `cloud_checks_endpoints.py:73` (already has them), `cloud_account_endpoints.py:13` (already has them), and `mcp_server.py` (imports, doesn't duplicate — safe). Update `RUNNABLE_PROVIDERS` last, after the three new `cloud_checks_<provider>.py` files exist and are wired into `CLOUD_CHECKS`, and re-run `tests/test_cloud_checks_expansion.py` as the template for new provider tests (it directly documents this exact bug class for kubernetes/digitalocean in its docstring).

**Warning signs:**
`POST /api/cloud-accounts` with `provider: "oci"` succeeds (201) but the subsequent `POST /api/cloud-checks/run` or `/api/cloud-accounts/{id}/scan` 400s with a provider-not-supported message; `cloud_checks_service.list_checks(provider="oci")` returns entries but `run_checks(..., "oci", ...)` returns `{"error": "provider must be one of (...)"}`.

**Feature area:** CSPM posture checks for OCI/Alibaba/Cloudflare (feature d).

---

### Pitfall 4: New "simulated" CSPM checks report fake PASS/FAIL without the SIMULATED label

**What goes wrong:**
The new OCI/Alibaba/Cloudflare checks ship reporting confident PASS/FAIL results to tenants, but nothing backs them — no real cloud API calls exist for these providers (same as DigitalOcean, whose "real checks" are not live API calls either).

**Why it happens:**
Look closely at `cloud_checks_service.run_checks()` (`cloud_checks_service.py:65-114`): **none** of the providers, including AWS/Azure/GCP, call a live cloud API in this function. It evaluates checks by matching `check["name"]`/`check["id"]` keywords against previously-**imported** `cloud_findings` documents (from an external scanner ingestion path), and sets `"simulated": not has_real_findings` — i.e. `simulated: true` whenever the tenant hasn't imported any real findings for that account yet, which is the default/common case for a newly-registered account. This mirrors the precedent explicitly logged in PROJECT.md's Key Decisions ("CloudFormation container-scan 'simulated' data is labeled, not fail-closed (Phase 25, CHK-03) ... explicit `simulated` field + SIMULATED badge at 3 dashboard sites, verified via live browser run"). If the new provider check definitions are added but the frontend result-rendering component isn't checked for whether it already reads `result.simulated` generically (likely, since DO/AWS/etc. share one component) vs. needs new per-provider wiring, the SIMULATED badge could silently not render for the 3 new providers specifically, making genuinely-fake results look authoritative — a compliance-integrity issue for a GRC product.

**How to avoid:**
Don't add any new "live API" logic unless that's an explicit, separately-scoped decision — the `simulated` field is already computed automatically and correctly by `run_checks()` for any new provider added to `CLOUD_CHECKS`/`RUNNABLE_PROVIDERS`, since the function is provider-agnostic. The actual verification work is: (1) confirm the 3 dashboard sites that render the SIMULATED badge (per the CHK-03 precedent) render it for these 3 new providers too — grep the frontend for the badge component and confirm it's driven by `result.simulated` generically, not an explicit provider allowlist; (2) verify with a live browser run per account, not just code inspection (CHK-03's own verification note explicitly flags "verified via live browser run, not just code inspection" as the bar that was needed).

**Warning signs:**
A tenant's OCI/Alibaba/Cloudflare posture dashboard shows crisp PASS/FAIL percentages with no SIMULATED indicator anywhere, for an account that has never had findings imported; `cloud_findings` collection has zero documents for that `accountId` yet `cloud_check_results` shows `result: "PASS"` un-badged.

**Feature area:** CSPM posture checks for OCI/Alibaba/Cloudflare (feature d).

---

### Pitfall 5: Ticket-bridge naively passes a `compliance_remediation_tasks` doc where `ticketing_service.py` expects an "alert" shape

**What goes wrong:**
`compliance_remediation_service.create_task`/`update_task` calls something like `ticketing_service.create_jira_ticket(task, config)` or `create_servicenow_incident(task, config)` directly, expecting it to "just work" since PROJECT.md says to reuse these connectors. The resulting Jira/ServiceNow ticket has a garbled or blank summary/description, missing severity mapping, and a broken MITRE/process/SHA256 section full of "N/A".

**Why it happens:**
`ticketing_service.py`'s `create_jira_ticket`/`create_servicenow_incident`/`create_zoho_desk_ticket` were built exclusively for **security alerts** and hard-code that shape: they read `alert.get("severity")` (mapped via `JIRA_PRIORITY_MAP`/`SNOW_URGENCY_MAP`, both keyed on `critical/high/medium/low/info`), `alert.get("type")`, `alert.get("hostname")`, `alert.get("process", {}).get("name")`, `alert.get("process", {}).get("sha256")`, `alert.get("mitre_technique")`, `alert.get("alert_id")`. A `compliance_remediation_tasks` document (`compliance_remediation_service.py:44-64`) has none of these fields — it has `title`, `control_id`, `asset_id`, `framework_id`, `status`, `priority` (already `low/medium/high/critical`, matching format — that part's fine), `assignee`, `due_date`, `description`, `agent_id`. PROJECT.md itself flags this precisely: "currently zero overlap; connectors only serve security-alert tickets."

**How to avoid:**
Write an explicit adapter/mapper function (e.g. `_remediation_task_to_alert_shape(task, control_doc, asset_doc)`) that translates a remediation task into the `alert`-shaped dict the connector functions expect before calling them — populate `type` from the control name/framework, `hostname` from the resolved asset, `description` from `task["description"]`, and drop or repurpose the process/SHA256/MITRE fields that don't apply to a compliance context (or extend `create_jira_ticket`'s payload builder to branch on a `source` field so compliance-sourced tickets get compliance-appropriate wording instead of forcing a security-alert template). Also note `_store_ticket()` (`ticketing_service.py:367-375`) writes to `db.ticketing_log` keyed only by `alert_id` — a remediation task's bridge record needs its own linkage field (e.g. `remediation_task_id`) so the UI can look up "which external ticket is this compliance task linked to," which `ticketing_log` doesn't currently support at all.

**Warning signs:**
Jira/ServiceNow tickets created from remediation tasks show `"Process: N/A (PID N/A)"`, `"SHA256: N/A"`, `"MITRE Technique: N/A"` in the description — dead giveaway the security-alert template rendered against a shape it wasn't built for; no way to query "external ticket ref for remediation task X" because `ticketing_log` has no `remediation_task_id` field.

**Feature area:** Remediation-to-ticketing bridge (feature a).

---

### Pitfall 6: Manual `tenant_filter` dict in `compliance_remediation_service` becomes dead code for the ticket-bridge/SLA cross-tenant paths

**What goes wrong:**
`compliance_remediation_endpoints.py`'s `_tenant_filter(user)` returns `{}` for Super Admin roles specifically so a platform-admin view can see tasks across all tenants (`compliance_remediation_endpoints.py:34-41`). But `svc.list_tasks`/`get_task`/`update_task` all call into `db.compliance_remediation_tasks` — which is `get_database()`-wrapped, i.e. `TenantIsolatedCollection`. The wrapper's `_inject_tenant_id()` doesn't care what filter dict the caller built; for any non-`"platform-admin"` value in the **contextvar**, it force-injects `tenantId = effective_tenant_id` into the query regardless. Whether Super Admin's `{}` filter actually returns cross-tenant data or gets silently re-scoped down to one tenant depends entirely on whether `set_tenant_id("platform-admin")` was called somewhere in the request middleware for that role — a fact this endpoint file doesn't control or verify locally. This is the exact class of bug fixed in commit `e55ba34` ("WR-01 read asset_compliance via raw db._db so explicit tenant_id argument is load-bearing") where an explicit tenant_id parameter threaded through a function was silently ignored because the query went through the wrapped collection instead of raw `db._db`.

**How to avoid:**
For any new cross-tenant view added by this milestone (e.g. an MSP-wide "all overdue remediation tasks across managed tenants" escalation dashboard, or a platform-admin ticket-bridge audit view), don't rely on the `TenantIsolatedCollection`'s contextvar-driven Super Admin bypass working out of the box — verify explicitly (test with a platform-admin token) or use the same `db._db` raw-unwrap pattern used elsewhere in this codebase (`compliance_evidence_lifecycle_endpoints.py:78,116,150`, `program_service.py`'s `db._db.asset_compliance`) so the manually-built `tenant_filter` dict is what actually scopes the query, not a contextvar side-channel.

**Warning signs:**
A platform-admin/Super Admin user querying remediation tasks or escalation status sees only their own tenant's data (or zero data) despite the endpoint code appearing to special-case their role; a unit test mocks `db.compliance_remediation_tasks` directly and passes (because the mock doesn't reproduce the wrapper's contextvar override) while the live endpoint behaves differently.

**Feature area:** SLA/escalation (feature b) and remediation-to-ticketing bridge (feature a), specifically any cross-tenant/admin views.

---

### Pitfall 7: New routers/endpoints built but never registered in `router_registry.py`

**What goes wrong:**
New endpoint modules for the ticket-bridge trigger (e.g. `remediation_ticketing_endpoints.py`), SLA config (`compliance_remediation_sla_endpoints.py`), or control comments (`control_comments_endpoints.py`) are written, tested in isolation, and 404 on every route once deployed.

**Why it happens:**
Verified recurring in this codebase's history (Phase 28, Phase 30 per milestone context) and the mechanism is fragile-by-design: `router_registry.py`'s `_load()` wraps every import in try/except and only re-raises for the small `_REQUIRED_ROUTERS` frozenset (currently `compliance_status_endpoints`, `compliance_evidence_lifecycle_endpoints`, `compliance_bulk_evidence_endpoints`, `compliance_score_endpoints`, `evidence_review_endpoints`, `cloud_account_endpoints`) — everything else, including the entire 60+ entry `_OPTIONAL` list at the bottom, silently logs an ERROR and continues if the *module itself* fails to import, but more relevantly here: a module that's simply never *listed* in either the explicit `_load()` calls or `_OPTIONAL` tuple list is never imported at all, and there's no lint/test that catches "orphaned endpoint file with no registration."

**How to avoid:**
For each new endpoint file created this milestone, add it either as an explicit `_load(app, "module_name", "router")` call (compliance/remediation feature area is registered around `router_registry.py:169` — `compliance_remediation_endpoints` already lives there, so siblings should go nearby) or append to the `_OPTIONAL` list. Since `cloud_account_endpoints` is already in `_REQUIRED_ROUTERS` (CR-02 precedent — a `RuntimeError` at import time for missing `CLOUD_CREDENTIALS_KEY` must hard-fail startup, not be swallowed), evaluate whether any new CSPM provider file has an equivalent "must not silently vanish" import-time guard and needs the same required-router treatment. After registering, hit the route once against a running server — a passing unit test on the router object alone does not prove it's mounted.

**Warning signs:**
Endpoint works when the router's `TestClient(app_module.router)` is exercised directly in a unit test, but 404s through the real running app; `grep <new_module_name> router_registry.py` returns nothing.

**Feature area:** All four (a, b, c, d) — applies to every new endpoint file this milestone introduces.

---

### Pitfall 8: New frontend UI built but never wired into `App.tsx`/`Sidebar.tsx`

**What goes wrong:**
A new SLA-breach badge/filter on the remediation task list, a comment-thread panel on the control detail view, an OCI/Alibaba/Cloudflare posture card, or a "linked external ticket" indicator on remediation tasks gets fully built and works in isolated Storybook/dev-server testing, but is unreachable from the actual app because no route/nav entry points to it.

**Why it happens:**
Documented as recurring "repeatedly across v2.0 phases — 5 dashboards found stranded in one audit" in the milestone context. This codebase's existing remediation UI already lives inline inside `AssetComplianceList.tsx` (per HANDOFF task 3: "Fix compliance dashboard Suggested Actions/Findings icons") rather than as a dedicated top-level page — meaning the natural (and easy to skip) integration point for new remediation/SLA/comment UI is *editing an existing component*, not registering a new route, which is easy to forget precisely because it doesn't look like "adding a page."

**How to avoid:**
Before considering any of the 4 features' frontend work done, explicitly trace: comment-thread UI → which control-detail component renders it and is that component reachable from `Sidebar.tsx` nav; SLA/escalation badges → confirm they render inside the same `AssetComplianceList.tsx`/remediation task list the existing workflow already uses (don't build a parallel, disconnected view); CSPM provider cards for OCI/Alibaba/Cloudflare → confirm the existing cloud-posture dashboard's provider-icon/filter list (wherever DigitalOcean's icon/label lives) is extended to include the 3 new providers, not just the backend data.

**Warning signs:**
A UAT pass that only exercises the API (curl/Postman) reports success, but a live browser click-through can't find the feature anywhere in the nav; grep for the new component name in `App.tsx`/`Sidebar.tsx`/the relevant parent dashboard component returns nothing.

**Feature area:** All four (a, b, c, d) — verify with a live browser click-through, not just API tests, per this codebase's own established verification bar (CHK-03 precedent above).

---

### Pitfall 9: `compliance_remediation_tasks` has no index to support an SLA breach sweep at scale

**What goes wrong:**
The SLA/escalation scheduler works fine in dev/testing with a handful of tasks, then becomes a slow, full-collection-scan query once a tenant has thousands of remediation tasks across many frameworks/controls, run every N minutes forever.

**Why it happens:**
`database.py`'s index-creation block (`connect_to_mongo()`) has explicit compound indexes for the `tickets` collection supporting exactly this kind of sweep — `tickets.create_index([("tenantId", 1), ("due_date", 1), ("status", 1)])` and `tickets.create_index([("tenantId", 1), ("escalated", 1)])` (`database.py:277-278`) — because `tickets_escalation_service` already needed this at scale. There is currently **no equivalent index for `compliance_remediation_tasks`** anywhere in `database.py`'s index list. A naive `db.compliance_remediation_tasks.find({"status": {"$in": [...]}, ...})` sweep across all tenants (mirroring `run_escalation_pass`'s `db.tickets.find(query)`) will do a full collection scan every cycle without one.

**How to avoid:**
Add `compliance_remediation_tasks.create_index([("tenantId", 1), ("due_date", 1), ("status", 1)])` and, if an `escalated`/`escalation_level` field is added to the task schema (it doesn't exist yet — see Pitfall 10), a matching `(tenantId, escalated)` index, in the same `database.py` block, using the `tickets` indexes as the direct template.

**Feature area:** SLA/escalation (feature b).

---

### Pitfall 10: `compliance_remediation_tasks` schema has no `history`/`escalated`/`escalation_level`/`sla_status` fields — SLA logic can't just "port over" from `tickets_escalation_service`

**What goes wrong:**
Code is written assuming `compliance_remediation_tasks` documents already carry the same shape as `tickets` (which has `history[]`, `escalated`, `escalation_level`, computed `sla_status`, `total_hold_duration`/`hold_started_at` for pause-aware SLA math) because `tickets_escalation_service.py` is used as the direct template. It isn't — `compliance_remediation_service.create_task` (`compliance_remediation_service.py:44-64`) only sets `id, title, control_id, asset_id, framework_id, status, priority, assignee, assignee_type, due_date, description, resolution_notes, agent_id, ai_suggestion, tenantId, created_by, created_at, updated_at`. There is no `history` array, no `escalated` boolean, no `escalation_level`, and `TaskUpdate`'s Pydantic model (`compliance_remediation_endpoints.py:60-65`) doesn't accept those fields either — even if the service layer tried to `$set` them, and even if it succeeded, `status` is constrained to `Literal["open", "in_progress", "resolved"]` with no "escalated"/"overdue" state, unlike `tickets`' 6-state machine with explicit `_VALID_TRANSITIONS`.

**How to avoid:**
Treat `tickets_escalation_service.py`/`tickets_helpers.py` (`_compute_sla`, `_sla_due`, `_bump_priority`, `_history_entry`) as a **pattern reference**, not reusable code — port the *logic shape* (priority ladder bump on breach, `at_risk`/`breached`/`ok` SLA status computation, an appended history entry per auto-escalation) into new functions scoped to `compliance_remediation_tasks`, and extend the task schema (`compliance_remediation_service.create_task`) and Pydantic models to add whatever new fields (`history`, `escalated`, `escalation_level`) the new logic needs before wiring the scheduler — don't assume the fields exist. Decide explicitly whether "escalated" bumps `priority` only (as tickets does) or needs a new `status` value, since the current status enum has no room for one.

**Feature area:** SLA/escalation (feature b).

---

## Integration Gotchas

| Integration | Common Mistake | Correct Approach |
|-------------|----------------|-------------------|
| Jira/ServiceNow via `ticketing_service.py` | Pass a `compliance_remediation_tasks` doc straight into `create_jira_ticket()`/`create_servicenow_incident()`, which expect an "alert" shape (`severity`, `hostname`, `process.name`, `process.sha256`, `mitre_technique`, `alert_id`) | Write an explicit task→alert-shape adapter; extend `_store_ticket`/`ticketing_log` with a `remediation_task_id` field so the bridge is queryable in both directions |
| `TenantIsolatedCollection` (any new collection) | Assume `get_database()` auto-scopes correctly in a background `asyncio` task with no request context | Background sweeps must use the raw, unwrapped `mongodb.db` (see `tickets_escalation_service` + `app_startup.py:603-608`), never `get_database()` |
| `compliance_controls` (global-exempt collection) | Clone `tickets_service.add_comment`'s `$push` pattern directly onto the control document | New tenant-scoped `control_comments` collection, joined by `control_id` — never write tenant data into the shared global control document |
| Cloud provider allowlists (4 duplicated locations) | Update `cloud_checks_service.py`'s `RUNNABLE_PROVIDERS` and assume the front-door gates (`cloud_checks_endpoints.py`, `cloud_account_endpoints.py`) are in sync | Grep for the current provider tuple/set literal across all `.py` files before and after any change; `mcp_server.py` imports `RUNNABLE_PROVIDERS` (safe), the two endpoint files hardcode their own copies (not safe to assume) |
| `websocket_manager.broadcast_*` (reused for comment/SLA real-time push) | Iterate `connected_clients[tenant_id]` directly while emitting (mutation-during-iteration risk) | Snapshot with `list(connected_clients[tenant_id])` first — `broadcast_remediation_update` already does this correctly; `broadcast_network_traffic` does not (pre-existing inconsistency, don't copy that one) |

## "Looks Done But Isn't" Checklist

- [ ] **Ticket-bridge:** External ticket actually contains compliance-relevant text (control ID, framework, asset, remediation description) — not "Process: N/A, SHA256: N/A" leftover from the security-alert template.
- [ ] **Ticket-bridge:** `ticketing_log` (or its successor) can answer "what external ticket, if any, is linked to remediation task X" — not just "what alert created ticket Y."
- [ ] **SLA/escalation:** Scheduler is registered with the **raw** `mongodb.db`, not `get_database()` — verify by checking `app_startup.py` registers it the same way as `tickets_escalation_service`.
- [ ] **SLA/escalation:** A compound index exists on `compliance_remediation_tasks` for `(tenantId, due_date, status)` before the scheduler ships, not added reactively after a slow-query alert.
- [ ] **SLA/escalation:** Escalated/overdue state is visible in the frontend remediation task list, not just computed server-side and logged.
- [ ] **Comment threads:** Comments are stored in a new tenant-scoped collection, confirmed via code review that `compliance_controls` (or any exempted global collection) is never the write target.
- [ ] **Comment threads:** Cross-tenant isolation verified with two different tenant logins on the same control ID, not just a single-tenant smoke test.
- [ ] **CSPM providers:** `POST /api/cloud-checks/run` (or `/api/cloud-accounts/{id}/scan`) actually succeeds for `oci`/`alibaba`/`cloudflare` — registration succeeding is not sufficient proof.
- [ ] **CSPM providers:** SIMULATED badge renders for the 3 new providers on a freshly-registered account with no imported findings, verified via live browser run.
- [ ] **All four features:** New backend router is present in `router_registry.py`; new frontend component is reachable from `Sidebar.tsx`/`App.tsx` nav or an existing wired page — verified by a live click-through, not just passing unit/API tests.
- [ ] **All four features:** Any new `@limiter.limit(...)`-decorated endpoint includes the `response: Response` parameter (slowapi requirement) — verified by hitting the route through the real app, since unit tests that bypass the middleware stack won't catch its absence.

## Pitfall-to-Feature Mapping

| Pitfall | Feature Area | Verification |
|---------|---------------|--------------|
| Background sweep returns zero (fail-closed tenant filter) | SLA/escalation (b) | Confirm scheduler registration uses raw `mongodb.db`; manually seed an overdue task and confirm the sweep picks it up in a live run |
| Comment thread on global `compliance_controls` doc | Comment threads (c) | Two-tenant isolation test on the same `control_id`; code review confirms no write to `compliance_controls` |
| Provider allowlist widened in 1 of 4 gates | CSPM providers (d) | `run_checks()`/`/scan` succeeds end-to-end for oci/alibaba/cloudflare, not just registration |
| Simulated CSPM results unlabeled | CSPM providers (d) | Live browser run against a freshly-registered account, SIMULATED badge visible |
| Ticket-bridge alert-shape mismatch | Ticket-bridge (a) | Inspect actual created Jira/ServiceNow ticket body for compliance-relevant content |
| Manual tenant_filter dict silently overridden by contextvar | Ticket-bridge (a) + SLA (b), cross-tenant views | Test with an actual platform-admin/Super Admin token against a multi-tenant dataset |
| Router never registered | All | `grep <module> router_registry.py`; hit the live route |
| Frontend built but unwired | All | Live browser click-through from nav, not API test |
| No index for SLA sweep at scale | SLA/escalation (b) | `explain()` the sweep query against a multi-thousand-task collection |
| Schema fields assumed present (`history`, `escalated`, etc.) | SLA/escalation (b) | Confirm `compliance_remediation_service.create_task`/`TaskUpdate` model include the new fields before the scheduler writes to them |

## Sources

- `backend/database.py` (TenantIsolatedCollection, exemption allowlist, index block)
- `backend/router_registry.py` (`_REQUIRED_ROUTERS`, `_load()`, `_OPTIONAL` list)
- `backend/ticketing_service.py` (Jira/ServiceNow/Zoho/webhook connector shape)
- `backend/tickets_endpoints.py`, `backend/tickets_service.py`, `backend/tickets_helpers.py`, `backend/tickets_escalation_service.py` (comment-thread pattern, SLA computation, escalation scheduler)
- `backend/compliance_remediation_service.py`, `backend/compliance_remediation_endpoints.py` (current remediation task schema and tenant-filter handling)
- `backend/cloud_checks_service.py`, `backend/cloud_checks_endpoints.py`, `backend/cloud_account_endpoints.py`, `backend/mcp_server.py`, `backend/tests/test_cloud_checks_expansion.py` (provider allowlist duplication, simulated-data convention)
- `backend/websocket_manager.py` (broadcast snapshot pattern)
- `backend/app_startup.py` (scheduler registration pattern)
- `backend/authentication_endpoints.py` (rate-limiter `response: Response` pattern, refresh-token rotation)
- Git history: `e55ba34` (WR-01 raw `db._db` fix), `720a76d` (auditor global-framework 404 fix)
- `.planning/PROJECT.md` (v3.2 milestone scope, Key Decisions table — Phase 25 CHK-01/CHK-03 precedents)
- `.planning/HANDOFF.json` (task 10/11 status)

---
*Pitfalls research for: Enterprise OmniAgent v3.2 — Agent Modernization & Remediation Ops*
*Researched: 2026-07-20*
