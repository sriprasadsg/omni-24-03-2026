# Phase 46: Public-IP ASN/VPN Enrichment + Location-History Audit - Pattern Map

**Mapped:** 2026-07-29
**Files analyzed:** 12 (new + modified)
**Analogs found:** 12 / 12

## File Classification

| New/Modified File | Role | Data Flow | Closest Analog | Match Quality |
|--------------------|------|-----------|-----------------|----------------|
| `backend/agent_asn_service.py` (NEW) | service | transform (lazy-loaded lookup) | `backend/geoip_service.py` | exact |
| `backend/agent_location_history_service.py` (NEW) | service | event-driven (change-detection + append-only write) | `backend/compliance_remediation_sla_service.py` (`run_sla_pass` write path + `get_sla_at_risk_window` toggle lookup) | exact |
| `backend/agent_location_history_endpoints.py` (NEW) | route | request-response (GET-only, tenant-scoped) | `backend/compliance_remediation_sla_endpoints.py` (`get_remediation_escalations`) | exact |
| `backend/agent_heartbeat_endpoints.py` (MODIFY, lines ~116-130) | controller | request-response, inline enrichment hook | itself (existing `geoip_service.lookup()` call site) | exact — extend in place |
| `backend/agent_registry_endpoints.py` (MODIFY, lines ~80-88) | controller | request-response, inline enrichment hook | itself (existing `geoip_service.lookup()` call site) | exact — extend in place |
| `backend/retention_service.py` (MODIFY — add `cleanup_agent_location_history`) | service | batch (delete_many sweep) | itself (`cleanup_audit_logs`/`cleanup_system_metrics`/`cleanup_notifications`) | exact — clone sibling method |
| `backend/retention_endpoints.py` (MODIFY — add `agent_location_history` to `_POLICY_DEFAULTS`) | route/config | CRUD (policy seed) | itself (`_POLICY_DEFAULTS` dict + `/run` wiring) | exact — extend in place |
| `backend/migrations/003_agent_location_history_indexes.py` (NEW) | migration | batch | `backend/migrations/002_scale_indexes.py` | role-match |
| `components/AgentLocationHistory.tsx` (NEW) | component | request-response (lazy fetch-on-expand) | `components/EscalationHistoryPanel.tsx` | exact |
| `components/AgentDetailModal.tsx` (MODIFY — mount new panel) | component | request-response | itself (existing tab-mount pattern) + `components/RemediationTaskModal.tsx` (mount line) | role-match |
| `services/apiService.ts` (MODIFY — add `fetchAgentLocationHistory`) | service (client) | request-response | `services/apiService.ts` `fetchRemediationEscalations` (line 4596) | exact |
| `backend/tests/test_agent_location_history.py` / `test_agent_asn_service.py` / `test_retention_agent_location_history.py` (NEW) | test | — | `backend/tests/test_compliance_remediation_sla.py` | exact |

## Pattern Assignments

### `backend/agent_asn_service.py` (service, transform)

**Analog:** `backend/geoip_service.py` (full file, 106 lines — read in full)

**Module docstring / imports pattern** (lines 1-17):
```python
"""GeoIP resolution for agent public (WAN) IPs.

Uses a local MaxMind GeoLite2-City database (`.mmdb`) — no per-lookup outbound
calls, works air-gapped. ... When the DB is absent (or the IP is
private/reserved) lookups return None and callers simply store no geo.
"""
from __future__ import annotations

import ipaddress
import logging
import os
import threading
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

_DEFAULT_DB_PATH = os.path.join(os.path.dirname(__file__), "data", "geoip", "GeoLite2-City.mmdb")

_reader = None
_reader_lock = threading.Lock()
_load_attempted = False
_warned_missing = False
```
Mirror as `_DEFAULT_ASN_DB_PATH = ...GeoLite2-ASN.mmdb`; env var `GEOIP_ASN_DB_PATH` per D-11.

**Lazy singleton reader pattern** (lines 27-58):
```python
def _db_path() -> str:
    return os.getenv("GEOIP_DB_PATH", _DEFAULT_DB_PATH)

def _get_reader():
    """Lazily open the .mmdb reader once. Returns None if unavailable."""
    global _reader, _load_attempted, _warned_missing
    if _reader is not None:
        return _reader
    if _load_attempted:
        return _reader  # already tried and failed; don't retry every call
    with _reader_lock:
        if _reader is not None or _load_attempted:
            return _reader
        _load_attempted = True
        path = _db_path()
        if not os.path.isfile(path):
            if not _warned_missing:
                logger.warning("... database not found at %s ...", path)
                _warned_missing = True
            return None
        try:
            import maxminddb
            _reader = maxminddb.open_database(path)
            logger.info("... database loaded from %s", path)
        except Exception as exc:  # noqa: BLE001 — never let geo break the request
            logger.warning("Failed to open ... database %s: %s", path, exc)
            _reader = None
        return _reader
```
Clone verbatim, single-attempt-then-cache-None-forever semantics — do not retry every call.

**`_is_public` reuse** (lines 61-67):
```python
def _is_public(ip: str) -> bool:
    try:
        addr = ipaddress.ip_address(ip)
    except ValueError:
        return False
    return not (addr.is_private or addr.is_loopback or addr.is_link_local
                or addr.is_multicast or addr.is_reserved or addr.is_unspecified)
```
Either `import geoip_service` and call `geoip_service._is_public(ip)`, or duplicate this 6-line function (planner's call per RESEARCH.md — duplicating is arguably cleaner since the name is private-by-convention).

**`lookup()` never-raises contract** (lines 70-87):
```python
def lookup(ip: Optional[str]) -> Optional[Dict[str, Any]]:
    """... Never raises — any failure yields None."""
    if not ip or not _is_public(ip):
        return None
    reader = _get_reader()
    if reader is None:
        return None
    try:
        rec = reader.get(ip)
    except Exception as exc:  # noqa: BLE001
        logger.debug("... lookup failed for %s: %s", ip, exc)
        return None
    if not rec:
        return None
```
Same shape for the ASN reader; then read `autonomous_system_number`/`autonomous_system_organization` per RESEARCH.md Assumptions Log A1 (LOW confidence — verify against a real `.mmdb` before locking field names). The X4BNet CIDR-range `bisect` lookup has a full skeleton already drafted in RESEARCH.md's "Code Examples" section — copy it directly, it already follows this exact lazy-singleton shape (`_load_vpn_ranges()`/`_is_known_vpn_range()`).

---

### `backend/agent_location_history_service.py` (service, event-driven)

**Analog A — append-only write:** `backend/compliance_remediation_sla_service.py` lines 268-275 (`run_sla_pass`)
```python
await db.remediation_escalations.insert_one({
    "task_id": task["id"],
    "tenantId": tenant_id,
    "escalation_level": new_level,
    "days_overdue": days_overdue,
    "notified": recipients,
    "created_at": _now_iso(),
})
```
Clone shape for `agent_location_history.insert_one({...})` — but **store `timestamp` as a native `datetime` object, not `.isoformat()`** (Anti-Pattern in RESEARCH.md: `_now_iso()` here returns a string; that pattern must NOT be copied for the new collection — use `datetime.now(timezone.utc)` directly so Motor serializes a genuine BSON Date).

**Analog B — per-tenant toggle lookup:** `backend/compliance_remediation_sla_service.py` lines 112-152 (`get_sla_at_risk_window`)
```python
async def get_sla_at_risk_window(db, tenant_id) -> int:
    raw = db._db if hasattr(db, "_db") else db
    if tenant_id:
        doc = await raw.system_settings.find_one(
            {"type": "remediation_sla_at_risk", "tenantId": tenant_id}
        )
        if doc and isinstance(doc.get("windowDays"), int):
            return _safe_window(doc["windowDays"])
    doc = await raw.system_settings.find_one(
        {"type": "remediation_sla_at_risk", "tenantId": {"$exists": False}}
    )
    if doc and isinstance(doc.get("windowDays"), int):
        return _safe_window(doc["windowDays"])
    return _DEFAULT_AT_RISK_WINDOW_DAYS
```
Clone verbatim as `get_track_agent_location(db, tenant_id) -> bool`, renaming `type` to `"track_agent_location"`, field to `"enabled"`, default `True` per D-02. RESEARCH.md already provides the exact renamed function body — use it as-is.

**NAT-flip de-noise state machine:** No direct analog exists in the codebase for this specific logic (RESEARCH.md rates this MEDIUM confidence — original design, not found verbatim elsewhere). Use the 4-branch state-machine design in RESEARCH.md's "Pitfall 1" section verbatim: two new agent-doc fields `locationConfirmed {publicIp, geo, confirmedAt}` and `locationPending {publicIp, geo, firstSeenAt}`, compared/promoted alongside the existing `db.agents.update_one(...)` call — never mutates a written history row.

---

### `backend/agent_location_history_endpoints.py` (route, request-response)

**Analog:** `backend/compliance_remediation_sla_endpoints.py` lines 45-80 (`get_remediation_escalations`)
```python
@router.get("/api/compliance/remediation-tasks/{task_id}/escalations")
async def get_remediation_escalations(
    task_id: str,
    current_user=Depends(get_current_user),
):
    try:
        db = get_database()
        raw = db._db if hasattr(db, "_db") else db
        tenant_id = getattr(current_user, "tenant_id", None)

        query: dict = {"task_id": task_id}
        if tenant_id:
            query["tenantId"] = tenant_id

        entries = await raw.remediation_escalations.find(
            query, {"_id": 0}
        ).sort("created_at", 1).to_list(length=500)

        # Belt-and-braces (T-44-06): re-check tenantId in application code too.
        if tenant_id:
            entries = [e for e in entries if e.get("tenantId") == tenant_id]

        return {"task_id": task_id, "entries": entries}
    except HTTPException:
        raise
    except Exception as e:
        logger.error("get_remediation_escalations error: %s", e)
        raise HTTPException(status_code=500, detail="Internal server error")
```
Clone verbatim for `GET /api/agents/{agent_id}/location-history`, substituting `agent_id` for `task_id`, sorting by `timestamp` ascending, and computing dwell time in this handler at read-time (never stored per-row — see RESEARCH.md Pitfall 2: `dwell = timestamp(i+1) - timestamp(i)`; last row uses `now - timestamp(last)`). **No PATCH/PUT/DELETE route** — the immutability guarantee is the absence of any mutation route for this resource, exactly like `remediation_escalations`.

**Admin-gated settings PATCH template** (for the `track_agent_location` toggle endpoint), lines 1-35 and 108-144 of the same file:
```python
_SETTINGS_ADMIN_ROLES = {"Super Admin", "super_admin", "admin", "platform-admin", "Tenant Admin"}

def _require_admin(user) -> None:
    if getattr(user, "role", "") not in _SETTINGS_ADMIN_ROLES:
        raise HTTPException(status_code=403, detail="Admin role required to modify settings")

class SlaWindowUpdate(BaseModel):
    windowDays: int = Field(ge=1, le=365)

@router.patch("/api/settings/remediation-sla")
async def patch_remediation_sla_settings(body: SlaWindowUpdate, current_user=Depends(get_current_user)):
    try:
        _require_admin(current_user)
        db = get_database()
        raw = db._db if hasattr(db, "_db") else db
        tenant_id = getattr(current_user, "tenant_id", None)
        doc = {"type": "remediation_sla_at_risk", "windowDays": body.windowDays}
        if tenant_id:
            doc["tenantId"] = tenant_id
            await raw.system_settings.update_one(
                {"type": "remediation_sla_at_risk", "tenantId": tenant_id},
                {"$set": doc}, upsert=True,
            )
        else:
            await raw.system_settings.update_one(
                {"type": "remediation_sla_at_risk", "tenantId": {"$exists": False}},
                {"$set": doc}, upsert=True,
            )
        return {"windowDays": body.windowDays}
    except HTTPException:
        raise
    except Exception as e:
        logger.error("patch_remediation_sla_settings error: %s", e)
        raise HTTPException(status_code=500, detail="Internal server error")
```
Clone for `PATCH /api/settings/agent-location-tracking` with `{"enabled": bool}` body, gated by the same admin-role set.

---

### `backend/agent_heartbeat_endpoints.py` (MODIFY, lines 116-130)

**Existing block to extend:**
```python
public_ip = payload.get("publicIp") or (payload.get("meta") or {}).get("public_ip")
geo = None
if public_ip:
    update_data["publicIp"] = public_ip
    geo = geoip_service.lookup(public_ip)
    if geo:
        update_data["geo"] = geo

await db.agents.update_one(
    _hb_agent_filter,
    {"$set": update_data, "$setOnInsert": {"registeredAt": datetime.now(timezone.utc).isoformat()}},
    upsert=True
)
```
`existing_agent` is already fetched at line 59 (`existing_agent = await db.agents.find_one(_hb_agent_filter)`) — this is the zero-extra-read baseline D-05 references. Insert the ASN/VPN + location-history calls between the `geo = geoip_service.lookup(...)` block and the `await db.agents.update_one(...)` call, gated on `get_track_agent_location(db, tenant_id)`.

---

### `backend/agent_registry_endpoints.py` (MODIFY, lines 80-89)

**Existing block to extend:**
```python
existing_agent = await db.agents.find_one({"hostname": hostname, "tenantId": tenant["id"]})
...
public_ip = data.get("publicIp") or reg_meta.get("public_ip")
geo = None
if public_ip:
    agent_data["publicIp"] = public_ip
    geo = geoip_service.lookup(public_ip)
    if geo:
        agent_data["geo"] = geo

await db.agents.update_one({"id": agent_id}, {"$set": agent_data}, upsert=True)
```
`set_tenant_id(tenant["id"])` at line 34 confirms tenant context is populated before any `get_database()`-backed call — safe to reuse the toggle-lookup helper here. Same extension shape as the heartbeat handler; first-ever registration has no prior entry to diff against, so it should always write an initial `agent_location_history` row when the toggle is ON.

---

### `backend/retention_service.py` (MODIFY — add cleanup method)

**Analog:** its own existing sibling methods (lines 10-35)
```python
async def cleanup_notifications(self, retention_days: int = 30) -> int:
    """Delete notifications older than retention_days"""
    cutoff = datetime.now(timezone.utc) - timedelta(days=retention_days)
    result = await self.db.notifications.delete_many({
        "sent_at": {"$lt": cutoff.isoformat()}
    })
    return result.deleted_count

async def run_cleanup(self, policies: dict = None) -> dict:
    p = policies or {}
    audit_deleted   = await self.cleanup_audit_logs(p.get("audit_logs", 90))
    metrics_deleted = await self.cleanup_system_metrics(p.get("metrics", 30))
    notif_deleted   = await self.cleanup_notifications(p.get("notifications", 30))
    report = {
        "audit_logs_deleted":   audit_deleted,
        "metrics_deleted":      metrics_deleted,
        "notifications_deleted": notif_deleted,
        "status": "completed",
    }
    return report
```
Add `cleanup_agent_location_history(self, retention_days: int = 365) -> int` following the same shape, but compare against a native `datetime` cutoff object directly (`{"timestamp": {"$lt": cutoff}}`) rather than `.isoformat()`, since D-01/Anti-Pattern requires the new collection's `timestamp` field to be a real BSON Date. Wire the new method's result into `run_cleanup()`'s returned dict.

---

### `backend/retention_endpoints.py` (MODIFY — add policy default)

**Analog:** existing `_POLICY_DEFAULTS` dict (lines 17-23)
```python
_POLICY_DEFAULTS = {
    "audit_logs":       {"retention_days": 90,  "description": "Retain audit logs for 90 days"},
    "metrics":          {"retention_days": 30,  "description": "Retain metrics for 30 days"},
    "notifications":    {"retention_days": 30,  "description": "Retain notifications for 30 days"},
    "security_events":  {"retention_days": 180, "description": "Retain security events for 180 days"},
    "alerts":           {"retention_days": 365, "description": "Retain alerts for 365 days"},
}
```
Add `"agent_location_history": {"retention_days": 365, "description": "Retain agent location-history audit records for 365 days"}`. **Note:** `security_events`/`alerts` are seeded here but have no cleanup implementation in `retention_service.py` — do not repeat that gap; the `cleanup_agent_location_history()` method (above) must actually be wired into `run_cleanup()`, not just seeded as a policy doc.

---

### `components/AgentLocationHistory.tsx` (component, request-response)

**Analog:** `components/EscalationHistoryPanel.tsx` (full file, 125 lines — read in full)

**Imports + interface shape** (lines 1-13):
```tsx
import React, { useState } from 'react';
import { HistoryIcon, ChevronDownIcon, AlertTriangleIcon } from './icons';
import * as api from '../services/apiService';

interface EscalationHistoryPanelProps {
    taskId: string;
}

interface EscalationEntry {
    escalation_level: number;
    created_at: string;
    notified: string[];
}
```
Rename to `AgentLocationHistoryProps { agentId: string }` and a `LocationHistoryEntry` interface (`publicIp`, `geo`, `vpn_heuristic`, `timestamp`).

**Lazy-expand-on-toggle fetch pattern** (lines 38-60):
```tsx
export const EscalationHistoryPanel: React.FC<EscalationHistoryPanelProps> = ({ taskId }) => {
    const [isExpanded, setIsExpanded] = useState(false);
    const [entries, setEntries] = useState<EscalationEntry[]>([]);
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
                setError('Failed to load escalation history. Retry by collapsing and expanding this panel.');
            } finally {
                setLoading(false);
            }
        }
        setIsExpanded(prev => !prev);
    };
```
Clone verbatim structure, swap `api.fetchRemediationEscalations` for `api.fetchAgentLocationHistory`.

**Collapsible header + row-render shape** (lines 62-124): clone directly — header with `HistoryIcon`/count badge/`ChevronDownIcon`, loading spinner, empty-state message, then a `.map()` over entries rendering an icon + two lines of text. For location rows, render (per D-09): flag emoji + city/country, public IP, VPN/hosting badge text ("likely VPN/hosting" — never "detected"), timestamp, dwell time. **Read-only — no edit/delete affordance anywhere** (D-10), matching this analog's own "no destructive control" comment at line 37.

**Reusable helpers:** `flagEmoji(code)` and `formatGeo(geo)` already exist in `components/AgentList.tsx` lines 78-86:
```tsx
const flagEmoji = (code?: string): string => {
    if (!code || code.length !== 2) return '';
    const cc = code.toUpperCase();
    if (!/^[A-Z]{2}$/.test(cc)) return '';
    return String.fromCodePoint(...[...cc].map(c => 0x1f1e6 + c.charCodeAt(0) - 65));
};

const formatGeo = (geo?: { city?: string; region?: string; country?: string }): string =>
    [geo?.city, geo?.region, geo?.country].filter(Boolean).join(', ');
```
These are currently module-private in `AgentList.tsx` — either export them from there and import into the new panel, or extract to a shared util (e.g. `utils/geoFormat.ts`) rather than duplicating.

---

### `components/AgentDetailModal.tsx` (MODIFY — mount point)

**Analog for mount style:** `components/RemediationTaskModal.tsx` line 377
```tsx
{task?.id && <EscalationHistoryPanel taskId={task.id} />}
```
`AgentDetailModal.tsx` is tab-based (`activeTab: 'overview' | 'runtime' | 'compliance' | ...`). Per RESEARCH.md's "Frontend Integration" section, D-08's literal instruction ("same shape/placement as `EscalationHistoryPanel`") means embedding `<AgentLocationHistory agentId={agent.id} />` as a collapsible panel **inside the existing Overview tab's content**, not as a new seventh tab — flag this choice explicitly in the plan since it's a genuine design decision, not a pure clone.

---

### `services/apiService.ts` (MODIFY — add client fetch function)

**Analog:** `fetchRemediationEscalations` (lines 4596-4604)
```typescript
export const fetchRemediationEscalations = async (taskId: string): Promise<{ task_id: string; entries: { escalation_level: number; created_at: string; notified: string[] }[] }> => {
    try {
        const res = await authFetch(`${API_BASE}/compliance/remediation-tasks/${taskId}/escalations`);
        if (!res.ok) return { task_id: taskId, entries: [] };
        return await res.json();
    } catch {
        return { task_id: taskId, entries: [] };
    }
};
```
Clone verbatim as `fetchAgentLocationHistory(agentId)` hitting `${API_BASE}/agents/${agentId}/location-history`, returning `{ agent_id, entries }`. Same fail-safe empty-array-on-error shape — never throws to the caller.

---

## Shared Patterns

### Lazy singleton `.mmdb`/data-file reader
**Source:** `backend/geoip_service.py` lines 21-58
**Apply to:** `agent_asn_service.py`'s GeoLite2-ASN reader AND its X4BNet CIDR-range loader (same thread-locked, single-attempt-then-cache pattern, duplicated for two independent lazy resources in one module).

### Append-only audit collection + no-mutation-route enforcement
**Source:** `backend/compliance_remediation_sla_service.py` (write, lines 268-275) + `backend/compliance_remediation_sla_endpoints.py` (read, lines 45-80)
**Apply to:** `agent_location_history_service.py` (write) + `agent_location_history_endpoints.py` (read). Immutability is enforced purely by the *absence* of PATCH/PUT/DELETE routes — verify no such route exists for `/api/agents/{agent_id}/location-history` during plan-checking, exactly as SLA-02 verifies for `remediation_escalations`.

### Per-tenant toggle via `system_settings` (tenant → global → default)
**Source:** `backend/compliance_remediation_sla_service.py` lines 112-152 (`get_sla_at_risk_window`)
**Apply to:** new `get_track_agent_location(db, tenant_id) -> bool` in `agent_location_history_service.py`, gating both the location-history write and the `agent_asn_service.lookup()` call — but explicitly NOT gating the existing `geoip_service.lookup()` city/country enrichment call (out of scope regression risk called out in RESEARCH.md).

### Belt-and-braces tenant re-filter on reads
**Source:** `backend/compliance_remediation_sla_endpoints.py` lines 70-73
```python
if tenant_id:
    entries = [e for e in entries if e.get("tenantId") == tenant_id]
```
**Apply to:** the new `GET /api/agents/{agent_id}/location-history` endpoint — never trust the Mongo query filter alone.

### Admin-gated settings PATCH
**Source:** `backend/compliance_remediation_sla_endpoints.py` lines 24-34, 108-144 (`_SETTINGS_ADMIN_ROLES`, `_require_admin`, `patch_remediation_sla_settings`)
**Apply to:** the `track_agent_location` toggle PATCH endpoint.

### BSON Date vs ISO-string timestamp (critical anti-pattern to avoid)
**Source (what NOT to copy):** `backend/agent_heartbeat_endpoints.py:181` writes `agent_metrics_history.timestamp` as `.isoformat()` (string), and `backend/migrations/002_scale_indexes.py:53-58` creates a TTL index on it that is a silent no-op because MongoDB TTL only expires `Date`-typed fields.
**Apply to:** `agent_location_history.timestamp` MUST be inserted as a native Python `datetime` object (`datetime.now(timezone.utc)`, no `.isoformat()`), so Motor serializes a genuine BSON Date — required for both the `cleanup_agent_location_history()` `$lt` comparison and any future TTL index.

### Lazy fetch-on-expand read-only history panel (frontend)
**Source:** `components/EscalationHistoryPanel.tsx` (full file)
**Apply to:** `components/AgentLocationHistory.tsx` — identical `isExpanded`/`fetched`/`loading`/`error` state shape, identical collapsible header, identical "no destructive control" constraint.

## No Analog Found

| File | Role | Data Flow | Reason |
|------|------|-----------|--------|
| NAT-flip de-noise state machine (inside `agent_location_history_service.py`) | logic | event-driven | No existing debounce/de-dup-within-a-time-window pattern elsewhere in this codebase — RESEARCH.md's "Pitfall 1" section provides an original 4-branch design (`locationConfirmed`/`locationPending` shadow fields) to follow instead of a codebase analog |
| X4BNet CIDR bundled-snapshot parsing/format | data | file-I/O | No existing bundled-CIDR-file pattern in this repo; RESEARCH.md provides a full code skeleton (`_load_vpn_ranges`/`_is_known_vpn_range` using stdlib `bisect`) as the closest thing to an analog — verify against a real downloaded X4BNet file before implementation (Assumptions Log A2) |
| `backend/migrations/003_agent_location_history_indexes.py` (NEW) | migration | batch | Only a partial analog (`002_scale_indexes.py`) exists — same file *shape* (create_index calls) but no prior migration created indexes for a brand-new append-only collection specifically; follow `002_scale_indexes.py`'s convention for compound-index syntax, but the actual index list (agent_id+tenantId+timestamp) is new |

## Metadata

**Analog search scope:** `backend/*.py` (geoip_service, compliance_remediation_sla_*, retention_*, agent_heartbeat_endpoints, agent_registry_endpoints, migrations/002_scale_indexes.py), `components/*.tsx` (EscalationHistoryPanel, RemediationTaskModal, AgentList, AgentDetailModal), `services/apiService.ts`
**Files scanned:** 12 read in full or targeted range, cross-referenced against RESEARCH.md's own file/line citations (all of which were independently verified by reading the cited files directly in this session)
**Pattern extraction date:** 2026-07-29
