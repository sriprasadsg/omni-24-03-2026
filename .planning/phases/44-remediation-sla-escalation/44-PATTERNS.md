# Phase 44: Remediation SLA & Escalation - Pattern Map

**Mapped:** 2026-07-21
**Files analyzed:** 9 new/modified
**Analogs found:** 9 / 9

## File Classification

| New/Modified File | Role | Data Flow | Closest Analog | Match Quality |
|--------------------|------|-----------|-----------------|----------------|
| `backend/compliance_remediation_sla_service.py` (new) | service | event-driven (batch sweep) | `backend/ticketing_bridge.py` (`run_close_loop_pass`/`start_close_loop_scheduler`) | exact — same collection, same raw-db requirement |
| `backend/compliance_remediation_sla_endpoints.py` (new) | route/controller | request-response + CRUD (settings) | `backend/compliance_evidence_lifecycle_endpoints.py` (STALE-02 GET/PATCH + COC-02 GET) | exact |
| `backend/compliance_remediation_service.py` (modified — `create_task` defaults) | service | CRUD | itself (existing file, add fields to existing insert dict) | n/a — in-place edit |
| `backend/compliance_remediation_endpoints.py` (modified — `TaskUpdate` review) | route/controller | request-response | itself | n/a — in-place edit |
| `backend/database.py` (modified — new indexes) | config | batch | itself, `tickets` compound-index block (lines ~277-278) | exact |
| `backend/app_startup.py` (modified — scheduler registration) | config | event-driven | itself, lines 602-616 (`tickets_escalation_service` / `ticketing_bridge` registration block) | exact |
| `backend/router_registry.py` (modified — router registration) | config | request-response | itself, existing router-registration entries | exact |
| `backend/tests/test_compliance_remediation_sla.py` (new) | test | batch/unit | `backend/tests/test_ticketing_bridge.py` | exact |
| `components/RemediationDashboard.tsx` (modified — SLA column/badge) | component | request-response (render) | itself, `STATUS_COLORS` badge (lines 9-14, 191-194) | exact — in-place edit |
| `components/RemediationTaskModal.tsx` (modified — escalation panel) | component | request-response (lazy fetch) | `components/ChainOfCustodyPanel.tsx` | exact |
| `services/apiService.ts` (modified — `fetchRemediationEscalations`, settings calls) | utility | request-response | itself, `fetchControlAuditLog` / evidence-staleness settings calls | exact |

## Pattern Assignments

### `backend/compliance_remediation_sla_service.py` (service, event-driven sweep)

**Analog:** `backend/ticketing_bridge.py` (`run_close_loop_pass` / `start_close_loop_scheduler`)

**Core sweep pattern** (clone structure verbatim, only query/collection differ):
```python
# Source: backend/ticketing_bridge.py — pattern verified in RESEARCH.md Pattern 1
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

**Do NOT clone** `backend/tickets_helpers.py::_compute_sla()` — hardcodes an hour-scale (`< 3600s`) at-risk cutoff and checks `status in ("resolved", "closed")`; `compliance_remediation_tasks.status` is a 3-value enum with no `"closed"`. Write a new pure function instead — RESEARCH.md's `compute_remediation_sla()` code example (day-scale, configurable `at_risk_window_days`, only `"resolved"` short-circuits) is the correct shape to implement.

**Configurable per-tenant threshold lookup** (clone verbatim from STALE-02, rename type/field):
```python
# Source: backend/evidence_staleness.py:27 (get_staleness_threshold) — RESEARCH.md Pattern 2
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
    return 3  # default (Assumption A1)
```

**Assignee resolution** (clone the *shape*, not the exact resolution order — `resolve_mentions` uses username/email/name; Pitfall 4 recommends email/id/username since `assignee` is a free-text field, not an @mention token):
```python
# Source: backend/control_comments_service.py:28-49 (resolve_mentions) — pattern to adapt
async def resolve_mentions(db, text: str) -> list:
    emails = []
    seen = set()
    for token in extract_mention_tokens(text):
        escaped = re.escape(token)
        user = await db.users.find_one({"username": token})
        if not user:
            user = await db.users.find_one({"email": {"$regex": f"^{escaped}@"}})
        if not user:
            user = await db.users.find_one({"name": {"$regex": f"^{escaped}$", "$options": "i"}})
        if user and user.get("email") and user["email"] not in seen:
            seen.add(user["email"])
            emails.append(user["email"])
    return emails
# Never raises on unresolved input — mirror this silent-skip behavior for
# unresolved/agent-type assignees (skip assignee notification only, not the
# whole escalation — Pitfall 4).
```

**Escalation notification dispatch** (clone call shape verbatim):
```python
# Source: backend/control_comments_endpoints.py:73-84
for mention_email in await resolve_mentions(db, body.text):
    try:
        svc = get_notification_service(db)
        await svc.send_alert(
            title="You were mentioned in a control comment",
            message=f'{current_user.username} mentioned you: "{body.text[:120]}"',
            severity="info",
            recipients=[mention_email],
            tenant_id=tenant_id,
            channels=[],  # in-app only — no email/sms/slack dispatch
            metadata={"control_id": body.control_id, "event": "mention"},
        )
    except Exception:
        ...  # non-fatal — never let notification failure break the primary write
```
For the SLA scheduler use `get_notification_service(db)` with the raw `db` already passed in (no `get_database()` call inside the scheduler — see Anti-Patterns).

**Tenant-admin recipient lookup** (RESEARCH.md Open Question 1 resolves to this set — use everywhere new in this phase, don't introduce a third variant):
```python
# Source: backend/notification_manager.py:45-47
_ADMIN_ROLES = {"admin", "Admin", "Tenant Admin", "Super Admin", "super_admin", "platform-admin"}
admins_cursor = raw.users.find(
    {"tenantId": tenant_id, "role": {"$in": list(_ADMIN_ROLES)}}
)
```

**Escalation-history insert** (append-only, dedicated collection — clone shape, no update method exists anywhere):
```python
await raw.remediation_escalations.insert_one({
    "task_id": task["id"],
    "tenantId": tenant_id,
    "escalation_level": new_level,
    "days_overdue": days_overdue,
    "notified": resolved_recipient_emails,   # assignee (if resolved) + tenant admins
    "created_at": _now_iso(),
})
```

---

### `backend/compliance_remediation_sla_endpoints.py` (route, request-response + CRUD settings)

**Analog:** `backend/compliance_evidence_lifecycle_endpoints.py` (lines 20-101 for settings GET/PATCH, 108-135 for the audit-log-style read endpoint)

**Admin role set + gate** (clone verbatim — same set as Pattern above, keep in sync per RESEARCH.md Open Question 1; note this file uses a *different, narrower* set (`_SETTINGS_ADMIN_ROLES`) than `notification_manager.py`'s `_ADMIN_ROLES` — RESEARCH.md recommends `notification_manager.py`'s set for *notification delivery* but this file's own `_SETTINGS_ADMIN_ROLES` pattern for *settings-mutation gating*, i.e. use each file's existing convention for its own purpose, don't cross-wire them):
```python
# Source: backend/compliance_evidence_lifecycle_endpoints.py:20-33
_SETTINGS_ADMIN_ROLES = {"Super Admin", "super_admin", "admin", "platform-admin", "Tenant Admin"}

def _require_admin(user) -> None:
    if getattr(user, "role", "") not in _SETTINGS_ADMIN_ROLES:
        raise HTTPException(status_code=403, detail="Admin role required to modify settings")
```

**Pydantic bounds** (clone verbatim, rename field):
```python
# Source: backend/compliance_evidence_lifecycle_endpoints.py:36-37
class StalenessThresholdUpdate(BaseModel):
    thresholdDays: int = Field(ge=1, le=365)
# → new SlaWindowUpdate(BaseModel): windowDays: int = Field(ge=1, le=365)
```

**GET settings endpoint** (no admin gate — non-sensitive config):
```python
# Source: backend/compliance_evidence_lifecycle_endpoints.py:44-59
@router.get("/api/settings/evidence-staleness")
async def get_evidence_staleness(current_user=Depends(get_current_user)):
    try:
        tenant_id = getattr(current_user, "tenant_id", None)
        db = get_database()
        threshold = await get_staleness_threshold(db, tenant_id)
        return {"thresholdDays": threshold}
    except HTTPException:
        raise
    except Exception as e:
        logger.error("get_evidence_staleness error: %s", e)
        raise HTTPException(status_code=500, detail="Internal server error")
```

**PATCH settings endpoint** (admin-gated, upsert with tenant/global doc split):
```python
# Source: backend/compliance_evidence_lifecycle_endpoints.py:66-101
@router.patch("/api/settings/evidence-staleness")
async def patch_evidence_staleness(body: StalenessThresholdUpdate, current_user=Depends(get_current_user)):
    try:
        _require_admin(current_user)
        db = get_database()
        raw = db._db if hasattr(db, "_db") else db
        tenant_id = getattr(current_user, "tenant_id", None)
        doc = {"type": "evidence_staleness", "thresholdDays": body.thresholdDays}
        if tenant_id:
            doc["tenantId"] = tenant_id
            await raw.system_settings.update_one(
                {"type": "evidence_staleness", "tenantId": tenant_id}, {"$set": doc}, upsert=True)
        else:
            await raw.system_settings.update_one(
                {"type": "evidence_staleness", "tenantId": {"$exists": False}}, {"$set": doc}, upsert=True)
        return {"thresholdDays": body.thresholdDays}
    except HTTPException:
        raise
    except Exception as e:
        logger.error("patch_evidence_staleness error: %s", e)
        raise HTTPException(status_code=500, detail="Internal server error")
```

**Escalation-history read endpoint** (tenant-scoped, no mutation route defined anywhere — that absence is SLA-02's enforcement):
```python
# Source: backend/compliance_evidence_lifecycle_endpoints.py:108-135 (COC-02 shape) — RESEARCH.md Pattern 3
@router.get("/api/compliance/remediation-tasks/{task_id}/escalations")
async def get_remediation_escalations(task_id: str, current_user=Depends(get_current_user)):
    db = get_database()
    raw = db._db if hasattr(db, "_db") else db
    tenant_id = getattr(current_user, "tenant_id", None)
    query: dict = {"task_id": task_id}
    if tenant_id:
        query["tenantId"] = tenant_id
    entries = await raw.remediation_escalations.find(query, {"_id": 0}).sort("created_at", 1).to_list(length=500)
    return {"task_id": task_id, "entries": entries}
```

---

### `backend/app_startup.py` (config — scheduler registration)

**Analog:** itself, lines 602-616

```python
# Source: backend/app_startup.py:602-616 — exact registration block to clone (new try/except block)
try:
    from tickets_escalation_service import start_escalation_scheduler
    from database import mongodb as _mdb
    asyncio.create_task(start_escalation_scheduler(_mdb.db))
    logger.info("[Tickets] SLA auto-escalation scheduler started")
except Exception as _e:
    logger.warning("[Tickets] Escalation scheduler failed to start: %s", _e)

try:
    from ticketing_bridge import start_close_loop_scheduler
    from database import mongodb as _mdb
    asyncio.create_task(start_close_loop_scheduler(_mdb.db))
    logger.info("[Ticketing] Remediation close-loop scheduler started")
except Exception as _e:
    logger.warning("[Ticketing] Close-loop scheduler failed to start: %s", _e)

# New block — clone shape exactly, must use `_mdb.db` (raw), never get_database()
try:
    from compliance_remediation_sla_service import start_remediation_sla_scheduler
    from database import mongodb as _mdb
    asyncio.create_task(start_remediation_sla_scheduler(_mdb.db))
    logger.info("[Remediation] SLA escalation scheduler started")
except Exception as _e:
    logger.warning("[Remediation] SLA escalation scheduler failed to start: %s", _e)
```

---

### `backend/database.py` (config — indexes)

**Analog:** itself, existing `tickets` compound-index block

```python
# Add alongside the tickets index block (RESEARCH.md Pitfall 3)
await mongodb.db.compliance_remediation_tasks.create_index([("tenantId", 1), ("due_date", 1), ("status", 1)])
await mongodb.db.compliance_remediation_tasks.create_index([("tenantId", 1), ("escalated", 1)])
```

---

### `components/RemediationDashboard.tsx` (component, render)

**Analog:** itself, lines 9-14 (`STATUS_COLORS`) and 191-194 (badge markup)

```tsx
// Source: components/RemediationDashboard.tsx:9-14
const STATUS_COLORS: Record<string, string> = {
    open:        'bg-red-100 text-red-800 dark:bg-red-900/30 dark:text-red-400',
    in_progress: 'bg-yellow-100 text-yellow-800 dark:bg-yellow-900/30 dark:text-yellow-400',
    resolved:    'bg-green-100 text-green-800 dark:bg-green-900/30 dark:text-green-400',
    dismissed:   'bg-gray-100 text-gray-500 dark:bg-gray-700 dark:text-gray-400',
};
// New, same declaration style, placed directly beside STATUS_COLORS:
const SLA_COLORS: Record<string, string> = {
    ok:       'bg-green-100 text-green-800 dark:bg-green-900/30 dark:text-green-400',
    at_risk:  'bg-yellow-100 text-yellow-800 dark:bg-yellow-900/30 dark:text-yellow-400',
    breached: 'bg-red-100 text-red-800 dark:bg-red-900/30 dark:text-red-400',
    none:     'bg-gray-100 text-gray-500 dark:bg-gray-700 dark:text-gray-400',
};
```

```tsx
// Source: components/RemediationDashboard.tsx:192 — badge markup to clone byte-for-byte
<span className={`px-2 py-0.5 text-xs font-semibold rounded-full ${STATUS_COLORS[task.status] ?? STATUS_COLORS.open}`}>
// New SLA badge, same shape:
<span className={`px-2 py-0.5 text-xs font-semibold rounded-full ${SLA_COLORS[task.sla_status] ?? SLA_COLORS.none}`}>
    {(task.sla_status ?? 'none').replace('_', ' ')}
</span>
```

UI-SPEC additions: new `<th>SLA</th>` header between `Status`/`Actions`; new `<td>` between existing status `<td>` and actions `<td>`; empty-state `colSpan={6}` → `colSpan={7}`. Guard `task.sla_status` possibly `undefined` — always fall back to `none`.

---

### `components/RemediationTaskModal.tsx` (component, lazy-fetch panel)

**Analog:** `components/ChainOfCustodyPanel.tsx` (full structural clone)

**Toggle/fetch-on-expand pattern** (clone exactly, swap API call and copy):
```tsx
// Source: components/ChainOfCustodyPanel.tsx:30-52
const [isExpanded, setIsExpanded] = useState(false);
const [entries, setEntries] = useState<any[]>([]);
const [loading, setLoading] = useState(false);
const [error, setError] = useState<string | null>(null);
const [fetched, setFetched] = useState(false);

const handleToggle = async () => {
    if (!isExpanded && !fetched) {
        setLoading(true);
        setError(null);
        try {
            const data = await api.fetchRemediationEscalations(taskId);
            setEntries(data.entries ?? []);
            setFetched(true);
        } catch {
            setError('Failed to load escalation history');
        } finally {
            setLoading(false);
        }
    }
    setIsExpanded(prev => !prev);
};
```

**Header/toggle bar markup** (clone exactly, swap icon/copy per UI-SPEC — `HistoryIcon` not `ClockIcon`, "Escalation History" not "Chain of Custody"):
```tsx
// Source: components/ChainOfCustodyPanel.tsx:54-73
<div className="mt-4">
    <div
        className="flex items-center justify-between px-4 py-2 bg-gray-100 dark:bg-gray-700/50 rounded-t-md border border-gray-200 dark:border-gray-700 cursor-pointer"
        onClick={handleToggle}
        role="button"
        tabIndex={0}
        onKeyDown={e => { if (e.key === 'Enter' || e.key === ' ') handleToggle(); }}
        aria-label={isExpanded ? 'Collapse escalation history panel' : 'Expand escalation history panel'}
    >
        <span className="text-sm font-semibold text-gray-700 dark:text-gray-300 flex items-center gap-1.5">
            <HistoryIcon size={14} />
            Escalation History
            <span className="text-xs font-normal text-gray-400">({entries.length} events)</span>
        </span>
        <ChevronDownIcon size={14} className={`text-gray-500 transition-transform ${isExpanded ? 'rotate-180' : ''}`} />
    </div>
    {isExpanded && ( /* body — see below */ )}
</div>
```

**Body: loading / error / empty / entries** (clone structure, swap copy per UI-SPEC):
```tsx
// Source: components/ChainOfCustodyPanel.tsx:75-94 — loading spinner unchanged;
// error copy → "Failed to load escalation history. Retry by collapsing and expanding this panel."
// empty copy → "No escalations recorded for this task."
{!loading && !error && entries.length === 0 && (
    <p className="px-4 py-6 text-center text-xs text-gray-400 italic">
        No escalations recorded for this task.
    </p>
)}
{!loading && !error && entries.map((entry, idx) => (
    <div key={`esc-${idx}`} className="px-4 py-3">
        <div className="flex items-start gap-2">
            <div className="flex-shrink-0 mt-0.5">
                <AlertTriangleIcon size={14} className="text-red-500 dark:text-red-400" />
            </div>
            <div className="min-w-0">
                <p className="text-xs font-semibold text-gray-800 dark:text-gray-200">
                    Tier {entry.escalation_level} escalation
                </p>
                <p className="text-xs text-gray-400 dark:text-gray-500 mt-0.5">
                    {formatTimestamp(entry.created_at)} UTC &middot; Notified: {(entry.notified ?? []).join(', ')}
                </p>
            </div>
        </div>
    </div>
))}
```

Import source per UI-SPEC: `HistoryIcon`, `ChevronDownIcon`, `AlertTriangleIcon` from local `./icons` (matching `ChainOfCustodyPanel.tsx`'s single-source icon convention), NOT `lucide-react`. Placement: after Ticketing block `</div>` (~line 358), before `{/* Buttons */}` (~line 361). Render only when `task?.id` is set (never in create mode).

---

## Shared Patterns

### Raw-db requirement for background schedulers
**Source:** `backend/app_startup.py:602-616`, `backend/ticketing_bridge.py`
**Apply to:** `compliance_remediation_sla_service.py`'s `run_sla_pass`/`start_remediation_sla_scheduler`
`db` must be `mongodb.db` (raw Motor client), passed in from `app_startup.py` at registration time — never call `get_database()` inside the scheduler or inside `compute_remediation_sla()`. `get_database()` wraps collections in `TenantIsolatedCollection`, which fail-closes to zero results outside an HTTP request context (Pitfall 1, highest-risk item flagged for this phase).

### Per-tenant configurable setting (tenant → global → hardcoded default)
**Source:** `backend/evidence_staleness.py:27`, `backend/compliance_evidence_lifecycle_endpoints.py:20-101`
**Apply to:** `compliance_remediation_sla_service.get_sla_at_risk_window` + `compliance_remediation_sla_endpoints.py`'s GET/PATCH pair
`system_settings` collection, doc shape `{"type": "<name>", "tenantId": <id or absent>, <field>: <value>}`. PATCH is admin-gated via `_require_admin`/`_SETTINGS_ADMIN_ROLES`; GET is not.

### Admin-role notification recipient set
**Source:** `backend/notification_manager.py:45-47`
**Apply to:** escalation notification dispatch in `compliance_remediation_sla_service.py` (tenant-admin recipients on breach)
Use `_ADMIN_ROLES = {"admin", "Admin", "Tenant Admin", "Super Admin", "super_admin", "platform-admin"}` — this set (not `_SETTINGS_ADMIN_ROLES`) per RESEARCH.md Open Question 1, since it's the set already used for admin *notification* delivery.

### In-app-only notification dispatch
**Source:** `backend/control_comments_endpoints.py:73-84`
**Apply to:** escalation notifications to assignee + tenant admins
`get_notification_service(db).send_alert(title=..., message=..., severity=..., recipients=[...], tenant_id=..., channels=[], metadata={...})` — `channels=[]` means in-app-only, not "no notification."

### Append-only audit-trail collection (no mutation route)
**Source:** `backend/compliance_evidence_lifecycle_endpoints.py:108-135` (evidence_audit_log), `backend/control_comments_service.py` comment at lines 3-7
**Apply to:** `remediation_escalations` collection
Dedicated collection, `insert_one` only, tenant-scoped `find()` on read. No PATCH/DELETE/PUT route registered anywhere for this collection — absence of the route IS the immutability enforcement (verbatim rationale already used twice in this codebase).

### Cross-tenant read guard
**Source:** `backend/compliance_evidence_lifecycle_endpoints.py` GET audit-log pattern
**Apply to:** `GET /api/compliance/remediation-tasks/{task_id}/escalations`
Always AND the query with `{"tenantId": tenant_id}` at read time — never rely solely on the write-time sweep having been tenant-correct.

## No Analog Found

None — every file in scope has a strong (exact or role-match) analog in the codebase; RESEARCH.md's own "Don't Hand-Roll" table confirms this (every piece of this phase already has a close precedent somewhere in `backend/`).

## Metadata

**Analog search scope:** `backend/` (service, endpoints, app_startup, database, tests), `components/` (RemediationDashboard, RemediationTaskModal, ChainOfCustodyPanel), `services/apiService.ts`
**Files scanned/read this session:** `backend/app_startup.py` (lines 595-620), `backend/control_comments_service.py` (full), `backend/control_comments_endpoints.py` (lines 55-85), `backend/compliance_evidence_lifecycle_endpoints.py` (lines 20-135), `backend/notification_manager.py` (grep), `components/RemediationDashboard.tsx` (lines 1-20), `components/ChainOfCustodyPanel.tsx` (lines 1-135) — plus all files RESEARCH.md already read in depth (cited above, not re-read)
**Pattern extraction date:** 2026-07-21
