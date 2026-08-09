# Phase 46: Public-IP ASN/VPN Enrichment + Location-History Audit - Research

**Researched:** 2026-07-29
**Domain:** Multi-tenant FastAPI/MongoDB agent telemetry — append-only audit collection + inline offline-`.mmdb` enrichment
**Confidence:** HIGH (all integration-point claims verified directly against this repo's source, file/line cited below); LOW on the two external data-format claims (GeoLite2-ASN field names, X4BNet file layout — plain `WebSearch` only, not fetched from a live `.mmdb`/repo checkout, and not run through an authoritative-source seam this session — see Assumptions Log).

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

**Retention & Privacy Posture**
- **D-01:** Location-history retention = **365 days**, routed through the **existing retention module** (do NOT hardcode a TTL; do NOT inherit the 30-day `agent_metrics_history` convention).
- **D-02:** Per-tenant **`track_agent_location` toggle** (default **ON**) — a tenant can disable agent location tracking for works-council/GDPR reasons. When OFF, no location-history rows are written and enrichment is skipped for that tenant.
- **D-03:** Add a short **disclosure note** in the relevant settings surface explaining what is tracked and why (employee-device IP/geo).
- **D-04:** Retention/privacy is a **pre-implementation gate** — this decision must be reflected before data starts accumulating (per PITFALLS.md Pitfall 5/2).

**Change Detection (what writes a row)**
- **D-05:** Write a new `agent_location_history` row when **`publicIp` OR resolved city/country changes** vs the last recorded entry — compared against the `existing_agent` doc already fetched on heartbeat (no extra read).
- **D-06:** **De-noise NAT flip-flop** — a public IP that recurs within a short window (~10 min) collapses to one row rather than writing a row on every flip. Exact window is a planning/tuning detail.
- **D-07:** Volume tracks **IP/geo changes, not heartbeat frequency** (success criterion 3).

**Location-History Timeline (GAUD-02)**
- **D-08:** New **`AgentLocationHistory` panel in the agent detail view** — same shape/placement as the existing `EscalationHistoryPanel` in `RemediationTaskModal`.
- **D-09:** Each row shows: **country flag + city/country**, **public IP**, **VPN/hosting badge** (heuristic — labelled "likely VPN/hosting", never "detected"), **timestamp**, and **dwell time** (how long the agent stayed at that location).
- **D-10:** Read-only — no edit/delete UI (matches the append-only API).

**ASN/VPN Data Packaging**
- **D-11:** **GeoLite2-ASN.mmdb** loaded via a new **`GEOIP_ASN_DB_PATH`** env var, mirroring the existing City DB pattern in `geoip_service.py` (supplied out-of-band; graceful degradation when absent).
- **D-12:** **X4BNet** public-VPN IP-range lists shipped as a **bundled snapshot in the repo**, refreshed at release time (works air-gapped; no runtime fetch).
- **D-13:** Enrichment stored on the agent doc under **`geo.asn`** (AS number + org name) and **`geo.vpn_heuristic`** (boolean/label). Enrichment runs **inline** at the same spot as `geoip_service.lookup()` in the heartbeat/register handlers (new sibling module, e.g. `agent_asn_service.py`).

### Claude's Discretion
- Exact NAT-flip de-dup window value, index shapes, and the precise `agent_location_history` document schema (planner/executor decide, following the `remediation_escalations` shape).
- Whether ASN + VPN enrichment lands in one `agent_asn_service.py` module or two — implementation detail.

### Deferred Ideas (OUT OF SCOPE)
- **Paid MaxMind GeoIP2 Anonymous IP** upgrade (authoritative VPN/proxy/Tor) — Future Requirement; upgrades GSEC-01 if a license is procured.
- **Geo-fence blocking** and **impossible-travel** — Phase 47.
- **Native MongoDB time-series** migration for history if 365d/volume outgrows the approach — Future Requirement.
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| GAUD-01 | Every change to an agent's public IP / geo is recorded in an immutable, append-only location-history collection (change detected cheaply against the already-fetched agent doc on heartbeat; append-only pattern cloned from `remediation_escalations`). | See "Integration Point 1" (exact heartbeat/register lines), "Pattern: Append-only collection clone", "Common Pitfall: NAT-flip de-noise needs more than the existing_agent compare", "Retention Module Integration" (365-day routing). |
| GAUD-02 | An admin can view a per-agent location-history timeline (chronological IP/geo changes with timestamps). | See "Integration Point 5" (GET endpoint pattern), "Frontend Integration" (`EscalationHistoryPanel` clone, `apiService.ts` pattern, mount point). |
</phase_requirements>

## Summary

This phase is a disciplined *clone-and-extend* exercise, not new architecture — every piece has a direct, already-working precedent in this repo. The append-only audit collection clones `remediation_escalations` (`compliance_remediation_sla_service.py` write path / `compliance_remediation_sla_endpoints.py` GET-only read path with zero PATCH/DELETE routes). The ASN/VPN enrichment clones `geoip_service.py`'s lazy-`.mmdb`-reader singleton, adding a `GEOIP_ASN_DB_PATH` env var and a new `agent_asn_service.py` sibling module, called from the exact same block in `agent_heartbeat_endpoints.py`/`agent_registry_endpoints.py` where `geoip_service.lookup()` already runs today (both files read).

Two things in this phase are **not** simple clones and need explicit design decisions the planner must lock down: (1) the "existing retention module" that D-01 says to route 365-day retention through is a **manual-trigger-only, 3-collection-hardcoded** cleanup (`retention_service.py`/`retention_endpoints.py`) with **no automatic scheduler today** — extending it to cover `agent_location_history` is a real code change, not a config toggle, and the planner should decide whether to also add an automatic sweep (following the proven raw-`mongodb.db` scheduler pattern) or accept manual-trigger-only parity with the existing precedent; (2) the NAT flip-flop de-noise window (D-06) cannot be implemented by only comparing against `existing_agent.publicIp`, because that field is overwritten every heartbeat regardless of whether a history row was written — a naive implementation satisfies D-05 but not D-06. A concrete design is given below (Common Pitfall section) using a small pending/candidate shadow field on the agent doc, not by mutating any `agent_location_history` row.

**Primary recommendation:** Clone `remediation_escalations`'/`geoip_service.py`'s exact patterns file-for-file (append-only insert, lazy-mmdb-reader, tenant-then-global-then-default `system_settings` doc for the per-tenant toggle) and treat the retention-module gap and the NAT-flip de-noise design as the two genuinely new pieces of engineering in this phase.

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| ASN/VPN IP enrichment | API / Backend | — | Local `.mmdb`/bundled-CIDR lookup, no network call; must run inline in the same request handler as the existing GeoIP lookup (agent auth already sets tenant context there) |
| Location-history change detection + write | API / Backend | Database / Storage | Detection logic lives in the heartbeat/register request handler (has `existing_agent` in hand); the write target is a new Mongo collection |
| Location-history retention enforcement | API / Backend | Database / Storage | Existing retention module is an admin-triggered API endpoint (`POST /api/retention/run`) that calls into `RetentionService`, which issues `delete_many` against Mongo — no separate service tier |
| Per-tenant `track_agent_location` toggle | API / Backend | Database / Storage | Read/write via a `system_settings` doc (tenant → global → default), the exact `get_sla_at_risk_window()` shape; gates both the write and enrichment call sites in the backend request handlers |
| Location-history timeline read | API / Backend | Frontend Server (SSR: none — pure SPA) | Tenant-scoped GET endpoint, consumed by a React panel — no SSR tier in this stack |
| Timeline panel UI | Browser / Client | — | `AgentLocationHistory.tsx`, a lazy-fetch-on-expand React panel mounted inside `AgentDetailModal.tsx`, cloning `EscalationHistoryPanel.tsx` |
| Disclosure note (privacy) | Browser / Client | — | Static copy in a settings surface (no dynamic backend data needed beyond the toggle state itself) |

## Standard Stack

### Core

No new backend or frontend packages are required for this phase.

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| `maxminddb` | `>=2.5.0` (already pinned in `backend/requirements.txt:138`) [VERIFIED: backend/requirements.txt] | Reads any MaxMind-format `.mmdb` file, including GeoLite2-ASN — same reader `geoip_service.py` already uses for GeoLite2-City | Zero new dependency; MaxMind DB binary format is generic across City/ASN/Anonymous-IP variants [CITED: dev.maxmind.com/geoip/docs/databases/asn/] |
| `ipaddress` (stdlib) | Python 3.12 stdlib (project runs `backend/venv/lib/python3.12`) [VERIFIED: backend/venv path] | Parses X4BNet CIDR ranges and performs private/public IP classification — `geoip_service.py._is_public()` already uses it | Already the established pattern in this codebase (`geoip_service.py:11,61-67`); avoids a new CIDR-matching dependency |

### Supporting

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| `bisect` (stdlib) | Python 3.12 stdlib | O(log n) membership test against a sorted list of X4BNet CIDR integer ranges, built once at lazy-load time (mirrors `geoip_service._get_reader()`'s lazy-singleton shape) | Recommended over a new pip package (`pytricia`/`python-radix`) — those packages' current maintenance status was not verified this session, and a hand-rolled sorted-range + `bisect` lookup is well within this codebase's existing "no new dependency for a solved-by-stdlib problem" convention (see geoip_service.py itself, which chose raw `maxminddb` over the heavier `geoip2` wrapper library) |

### Alternatives Considered

| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| Hand-rolled sorted-range + `bisect` CIDR lookup | `pytricia` / `python-radix` (PRadix) | Faster for very large range sets (100k+ CIDRs) via a real radix trie; X4BNet's combined VPN+datacenter lists are in the low thousands of CIDRs, well within `bisect`'s comfortable range, so the added dependency isn't justified for this phase's data volume |
| GeoLite2-ASN (free, AS-org name only) | MaxMind GeoIP2 Anonymous IP (paid, `is_anonymous_vpn`/`is_hosting_provider`/etc.) | Explicitly deferred per CONTEXT.md — Future Requirement gated on a MaxMind license; do not build for it in this phase |
| Raw `maxminddb` reader (matches `geoip_service.py`) | `geoip2` wrapper library (`geoip2.database.Reader(...).asn(ip)`) | `geoip2` is not in `requirements.txt` today; introducing it just for ASN lookups would create two different access patterns for the same MaxMind DB family in this codebase. Use the raw reader's `.get(ip)` dict, exactly like `geoip_service.py` does, and read `autonomous_system_number`/`autonomous_system_organization` keys directly [CITED: github.com/maxmind/GeoIP2-python — confirms these are the field names geoip2 itself surfaces from the same underlying mmdb record] |

**Installation:**
```bash
# No new packages required — maxminddb already pinned, ipaddress/bisect are stdlib.
```

**Version verification:** `maxminddb>=2.5.0` already verified present in `backend/requirements.txt:138` [VERIFIED: backend/requirements.txt] — no registry lookup needed since nothing new is being added.

## Package Legitimacy Audit

No external packages are being newly introduced in this phase (backend or frontend). `maxminddb` is an existing, already-vetted dependency; `ipaddress`/`bisect` are Python stdlib. X4BNet's `lists_vpn` is a data snapshot (CIDR text files), not an installable package, and is vendored into the repo rather than pulled via a package manager — no npm/PyPI/crates legitimacy check applies to it, but note it below anyway for supply-chain awareness.

| Package / Asset | Registry | Age | Downloads | Source Repo | Verdict | Disposition |
|------------------|----------|-----|-----------|--------------|---------|-------------|
| `maxminddb` | PyPI (already installed) | N/A — pre-existing dependency | N/A | github.com/maxmind/MaxMind-DB-Reader-python | OK | Approved (no change) |
| X4BNet `lists_vpn` snapshot | N/A — vendored data file, not a package | N/A | N/A | github.com/X4BNet/lists_vpn [ASSUMED — repo existence/file layout from plain WebSearch this session, not fetched; confirm the exact `output/vpn/ipv4.txt` path and license before vendoring, see Assumptions Log A2] | N/A (data, not code) | Vendor as a static file under `backend/data/vpn_ranges/`; re-verify the source repo URL/commit hash at each refresh, since this is untrusted third-party data loaded at runtime |

**Packages removed due to [SLOP] verdict:** none
**Packages flagged as suspicious [SUS]:** none

## Architecture Patterns

### System Architecture Diagram

```
Agent heartbeat/register  POST /api/agents/{id}/heartbeat | POST /api/agents/register
        │
        ▼
existing_agent = await db.agents.find_one(...)   [ALREADY HAPPENS — no extra read]
        │
        ▼
public_ip = payload.get("publicIp") ...
        │
        ├──► geoip_service.lookup(public_ip)          [EXISTING — city/country/lat/lon]
        │
        ├──► agent_asn_service.lookup(public_ip)       [NEW — ASN + heuristic VPN flag]
        │        │
        │        ├─ GeoLite2-ASN.mmdb (GEOIP_ASN_DB_PATH, lazy singleton)
        │        └─ X4BNet bundled CIDR ranges (lazy-loaded sorted-range set)
        │
        ▼
track_agent_location toggle check (system_settings: tenant → global → default=ON)
        │
   ON   │   OFF → skip below, still update agents.publicIp/geo/geo.asn as today
        ▼
Change-detection: public_ip/city/country vs existing_agent, PLUS NAT-flip de-noise
against a short-lived pending-candidate shadow field (see Common Pitfalls)
        │
        ├─ no real change / still bouncing within window → no history write
        │
        ▼ confirmed change
agent_location_history.insert_one({...})   [NEW — append-only, clone remediation_escalations]
        │
        ▼
db.agents.update_one(... publicIp/geo/geo.asn/geo.vpn_heuristic ...)   [unchanged shape]

──────────────────────────────────────────────────────────────────────

Frontend read path:
AgentDetailModal.tsx mount → AgentLocationHistory.tsx (clone EscalationHistoryPanel.tsx)
        │
        ▼ (lazy, on-expand)
apiService.fetchAgentLocationHistory(agentId)
        │
        ▼
GET /api/agents/{agent_id}/location-history   [NEW — tenant-scoped, GET-only]
        │
        ▼
db.agent_location_history.find({agent_id, tenantId}).sort(timestamp, 1)
        │
        ▼
Rows rendered: flag + city/country, public IP, VPN/hosting badge, timestamp, dwell time
(dwell time computed at read time — see Common Pitfalls, never stored per-row)

──────────────────────────────────────────────────────────────────────

Retention (365d, D-01):
POST /api/retention/run (admin-triggered, existing endpoint)
        │
        ▼
RetentionService.run_cleanup(policies)  [MODIFY — add agent_location_history entry]
        │
        ▼
delete_many({"timestamp": {"$lt": cutoff}})  — timestamp stored as BSON Date (not ISO string)
```

### Recommended Project Structure

```
backend/
├── agent_heartbeat_endpoints.py          # MODIFY — call agent_asn_service + location-history hook, lines ~116-124
├── agent_registry_endpoints.py           # MODIFY — same hook, lines ~80-87
├── agent_asn_service.py                  # NEW — GeoLite2-ASN + X4BNet lazy-loaded lookup, mirrors geoip_service.py
├── agent_location_history_service.py     # NEW — change-detection + de-noise + append-only write, shared by both endpoint files above
├── agent_location_history_endpoints.py   # NEW — GET /api/agents/{id}/location-history (or fold into agent_metrics_endpoints.py — planner's call)
├── data/
│   ├── geoip/                            # EXISTING dir — GeoLite2-City.mmdb goes here
│   └── vpn_ranges/                       # NEW — bundled X4BNet CIDR snapshot (e.g. x4bnet_vpn_ipv4.txt)
├── retention_service.py                  # MODIFY — add cleanup_agent_location_history(), wire into run_cleanup()
├── retention_endpoints.py                # MODIFY — add "agent_location_history" to _POLICY_DEFAULTS (365 days)
├── database.py                           # MODIFY — no new exemption entry (agents/agent_location_history stay tenant-isolated); add create_index calls
├── migrations/
│   └── 003_agent_location_history_indexes.py   # NEW — compound indexes, following 002_scale_indexes.py's convention
├── agent_endpoints.py                    # MODIFY — include_router(agent_location_history_endpoints.router) if a new file is chosen
└── router_registry.py                    # MODIFY — one _load() line, only if the new endpoints file is registered standalone (not folded into agent_endpoints.py)

components/
├── AgentLocationHistory.tsx              # NEW — clone of EscalationHistoryPanel.tsx
├── AgentDetailModal.tsx                  # MODIFY — mount the new panel (see Frontend Integration below for tab-vs-embedded decision)
└── (disclosure note surface — e.g. PrivacyDashboard.tsx or SettingsDashboard's relevant tab — planner to confirm exact surface)

services/
└── apiService.ts                         # MODIFY — add fetchAgentLocationHistory(), clone fetchRemediationEscalations() shape (line ~4596)
```

### Structure Rationale

- One new service module per concern (`agent_asn_service.py`, `agent_location_history_service.py`) rather than growing the already-large `agent_heartbeat_endpoints.py` (517 lines) or `agent_registry_endpoints.py` (360 lines) further — both are already close to the CLAUDE.md 500-line cap once the new call sites are added; keeping the actual logic in sibling service modules avoids breaching it.
- Endpoint files stay thin call-throughs into the service modules, exactly like `compliance_remediation_sla_endpoints.py` → `compliance_remediation_sla_service.py`.

### Integration Point 1 — Heartbeat geo-enrichment block (exact lines)

`backend/agent_heartbeat_endpoints.py`:
- `existing_agent = await db.agents.find_one(_hb_agent_filter)` — **line 59** (already fetched, this is the "no extra read" fetch D-05 references).
- The geo/publicIp block to extend is **lines 116-124**:
```python
public_ip = payload.get("publicIp") or (payload.get("meta") or {}).get("public_ip")
geo = None
if public_ip:
    update_data["publicIp"] = public_ip
    geo = geoip_service.lookup(public_ip)
    if geo:
        update_data["geo"] = geo
```
Insert `agent_asn_service.lookup(public_ip)` immediately after the `geoip_service.lookup()` call, and the location-history change-detection/write call after that (needs `existing_agent` from line 59 and the freshly computed `public_ip`/`geo`). The `await db.agents.update_one(...)` at **line 126-130** is where `update_data` (now including `geo.asn`/`geo.vpn_heuristic`) actually persists.

### Integration Point 2 — Registration geo-enrichment block (exact lines)

`backend/agent_registry_endpoints.py`:
- `existing_agent = await db.agents.find_one({"hostname": hostname, "tenantId": tenant["id"]})` — **line 41**.
- `set_tenant_id(tenant["id"])` — **line 34**, confirming tenant context is populated before any `get_database()`-backed call in this handler (safe to use `get_database()` here, unlike a background sweep — see Common Pitfalls).
- The geo/publicIp block to extend is **lines 80-87**:
```python
public_ip = data.get("publicIp") or reg_meta.get("public_ip")
geo = None
if public_ip:
    agent_data["publicIp"] = public_ip
    geo = geoip_service.lookup(public_ip)
    if geo:
        agent_data["geo"] = geo
```
Same extension shape as Integration Point 1. Note registration is a much lower-frequency path (`10/minute` rate limit vs. heartbeat's `60/minute`) — first-ever registration should also write an initial `agent_location_history` row (there is no "prior" entry to diff against on first-seen).

### Integration Point 3 — `geoip_service.py`'s exact template to mirror for `agent_asn_service.py`

Read in full (`backend/geoip_service.py`, 106 lines). The reusable shape:
- `_DEFAULT_DB_PATH` = `os.path.join(os.path.dirname(__file__), "data", "geoip", "GeoLite2-City.mmdb")` (line 19) → mirror as `os.path.join(os.path.dirname(__file__), "data", "geoip", "GeoLite2-ASN.mmdb")`.
- `_db_path()` reads `os.getenv("GEOIP_DB_PATH", _DEFAULT_DB_PATH)` (lines 27-28) → mirror as `os.getenv("GEOIP_ASN_DB_PATH", _DEFAULT_ASN_DB_PATH)` per D-11.
- `_get_reader()` (lines 31-58): thread-locked, lazy, single-attempt-then-cache-None-forever singleton — do not retry every call on repeated failure. Clone this exactly for the ASN reader.
- `_is_public(ip)` (lines 61-67): reuse directly — do not reimplement; `agent_asn_service.py` should `import geoip_service` and call `geoip_service._is_public(ip)`, or duplicate the 6-line function if avoiding a private-name cross-module import is preferred (planner's call; duplicating is arguably cleaner since `_is_public` is name-mangled-private by convention).
- `lookup(ip)` (lines 70-105): parses `rec.get("country")`/`rec.get("city")`/etc.; for ASN, the raw dict returned by `reader.get(ip)` on a GeoLite2-ASN mmdb is claimed (by web search, see Assumptions Log A1) to have keys `autonomous_system_number` (int) and `autonomous_system_organization` (str) directly at the top level (not nested under a `country`/`city` sub-dict — ASN records are flatter than City records) [ASSUMED — verify against an actual downloaded GeoLite2-ASN.mmdb or the official MaxMind binary-format doc before implementation; this session's check was a plain WebSearch, classified LOW confidence by this project's own source-hierarchy tooling, not a fetch of an authoritative page].

### Pattern: Append-only audit collection (clone `remediation_escalations`)

**What:** `remediation_escalations` is written only via `insert_one` inside `run_sla_pass` (`compliance_remediation_sla_service.py:268-275`), never updated or deleted anywhere in the codebase. Its GET endpoint (`compliance_remediation_sla_endpoints.py:45-80`) is the exact template for the new location-history read:
```python
@router.get("/api/compliance/remediation-tasks/{task_id}/escalations")
async def get_remediation_escalations(task_id: str, current_user=Depends(get_current_user)):
    db = get_database()
    raw = db._db if hasattr(db, "_db") else db
    tenant_id = getattr(current_user, "tenant_id", None)
    query: dict = {"task_id": task_id}
    if tenant_id:
        query["tenantId"] = tenant_id
    entries = await raw.remediation_escalations.find(query, {"_id": 0}).sort("created_at", 1).to_list(length=500)
    if tenant_id:
        entries = [e for e in entries if e.get("tenantId") == tenant_id]   # belt-and-braces re-check
    return {"task_id": task_id, "entries": entries}
```
Clone this verbatim for `GET /api/agents/{agent_id}/location-history`, substituting `agent_id` for `task_id` and adding the same "belt-and-braces" application-level re-filter after the query (T-44-06's pattern — never trust the query filter alone). **The immutability guarantee is the absence of any PATCH/PUT/DELETE route for this resource anywhere in the codebase** — do not add one, and grep for the resource path in plan-checker/verification to confirm none exists (mirrors SLA-02's own verification gate).

**When to use:** Any compliance/security-relevant trail where later mutation would undermine the audit guarantee.

### Pattern: Per-tenant toggle via `system_settings` (clone `get_sla_at_risk_window`)

`compliance_remediation_sla_service.get_sla_at_risk_window()` (lines 112-152) is the exact template for `track_agent_location`:
```python
async def get_track_agent_location(db, tenant_id) -> bool:
    raw = db._db if hasattr(db, "_db") else db
    if tenant_id:
        doc = await raw.system_settings.find_one({"type": "track_agent_location", "tenantId": tenant_id})
        if doc and isinstance(doc.get("enabled"), bool):
            return doc["enabled"]
    doc = await raw.system_settings.find_one({"type": "track_agent_location", "tenantId": {"$exists": False}})
    if doc and isinstance(doc.get("enabled"), bool):
        return doc["enabled"]
    return True  # D-02: default ON
```
Lookup order: per-tenant doc → global doc → hardcoded default (`True`). PATCH endpoint should mirror `compliance_remediation_sla_endpoints.py`'s `patch_remediation_sla_settings` (admin-gated via a `_SETTINGS_ADMIN_ROLES`-equivalent set, `upsert=True` on the tenant-scoped doc).

**Gate both** the location-history write and the `agent_asn_service.lookup()` call on this toggle when OFF, per D-02's literal wording ("no location-history rows are written and enrichment is skipped"). **Do not gate the pre-existing `geoip_service.lookup()` city/country enrichment** — that's out of this phase's scope (landed in v3.2) and disabling it would be an undocumented regression to existing behavior nobody asked for. Flag this scope boundary explicitly in the plan so a reviewer doesn't assume the toggle should also blank out `agent.geo`.

### Anti-Patterns to Avoid

- **Writing a history row on every heartbeat instead of on-change:** Row count would scale 1:1 with heartbeat volume × fleet size, directly violating D-07 (volume tracks changes, not heartbeat frequency) and PITFALLS.md's own "Technical Debt Patterns" table entry for this exact anti-pattern.
- **Cloning the `agent_metrics_history` TTL pattern (ISO string + `expireAfterSeconds` index):** `agent_heartbeat_endpoints.py:181` writes `agent_metrics_history.timestamp` as `datetime.now(timezone.utc).isoformat()` (a BSON string), and `migrations/002_scale_indexes.py:53-58` creates a TTL index on that field — since MongoDB TTL indexes only expire `Date`-typed fields, that TTL index is a silent no-op today (PITFALLS.md Pitfall 6, confirmed by direct inspection of both files this session). `agent_location_history.timestamp` must be stored as a native Python `datetime` object (Motor/pymongo serializes this to a genuine BSON Date automatically — do not call `.isoformat()` on it before insertion), even though this phase's retention mechanism is an app-level `delete_many` sweep rather than a TTL index (see Retention Module Integration below) — storing a real Date keeps the `$lt`/`$gte` comparison correct regardless of which enforcement mechanism is used, and leaves the door open for a future TTL index without a backfill migration.
- **Assuming the toggle-off state should also suppress the existing v3.2 `geo` field:** see the toggle pattern note directly above.

## Retention Module Integration (D-01) — the "existing module" is manual-trigger-only and hardcoded to 3 collections

**Files read:** `backend/retention_service.py` (53 lines), `backend/retention_endpoints.py` (106 lines), `backend/retention_tiers_endpoints.py` (161 lines).

There are **two, unrelated** "retention" surfaces in this codebase — the planner must pick the right one and understand its actual current behavior, which is more limited than "route through the existing retention module" implies:

1. **`retention_endpoints.py` / `retention_service.py` (`/api/retention/*`)** — this is the module CONTEXT.md's D-01 refers to. It is:
   - **Not tenant-scoped** — `_POLICY_DEFAULTS` is a single hardcoded dict (`audit_logs`, `metrics`, `notifications`, `security_events`, `alerts`) seeded once, platform-wide, into `db.retention_policies`.
   - **Only 3 of those 5 seeded collections actually have a cleanup implementation** — `RetentionService.run_cleanup()` (lines 37-49) calls `cleanup_audit_logs`, `cleanup_system_metrics`, `cleanup_notifications` only. `security_events` and `alerts` have policy *documents* but no corresponding cleanup method — they are configured but never actually purged. This is a genuine pre-existing gap in the module, not something this phase needs to fix, but the planner should not assume "add a policy doc" alone is sufficient — a `cleanup_agent_location_history()` method must also be added and wired into `run_cleanup()`.
   - **Has no automatic scheduler** — confirmed via `grep -n "retention" app_startup.py app_background_tasks.py` returning zero scheduler references. `POST /api/retention/run` is only invoked when an admin calls it (or a future automation calls it) — there is currently no periodic background sweep anywhere in this codebase that runs retention automatically. **This is a genuine open question for the planner**: either (a) accept manual-trigger-only retention enforcement, matching the existing precedent's actual (not documented) behavior, or (b) add a new scheduler cloned from the proven `compliance_remediation_sla_service` shape (raw `mongodb.db`, `while True: await run_X(); await asyncio.sleep(N)`, registered in `app_startup.py`) that calls `RetentionService.run_cleanup()` on an interval. Given D-04 frames retention as a compliance-relevant, pre-implementation-gated decision, an automatic sweep is the safer choice to actually enforce the 365-day policy without relying on an admin remembering to click a button — flag this as a decision for the plan (not silently defaulting to manual-only).
   - Uses **string ISO comparison** (`{"timestamp": {"$lt": cutoff.isoformat()}}`) against existing collections, which works today only because those collections happen to write consistently-formatted UTC ISO strings. This is a different pitfall shape than the TTL-index Date-type issue (Pitfall 6) — it is not "broken," but it is fragile and inconsistent with recommending a native Date field for the new collection. Add `cleanup_agent_location_history(retention_days=365)` using a real `datetime` cutoff compared against a BSON Date `timestamp` field (`{"timestamp": {"$lt": cutoff}}` — this works correctly and identically for both a string-typed and Date-typed field cutoff in Mongo's query language *as long as the field's actual BSON type is consistent*; store Date, compare with a `datetime` object, not `.isoformat()`).

2. **`retention_tiers_endpoints.py` (`/api/retention-tiers/*`)** — a separate, tenant-scoped CRUD surface for user-defined named policies (`tier`, `retention_days`, `legal_hold`) stored in `retention_policies` docs with a `tenantId`/`id`. **This module performs no enforcement at all** — it is pure policy bookkeeping (create/update/delete/legal-hold-toggle), never calling any cleanup. Do not confuse this with #1; it is not "the existing retention module" D-01 means, though it could optionally be used later to let a tenant view/adjust the 365-day window per D-01's spirit — out of scope for this phase unless explicitly requested.

**Recommendation:** Add `"agent_location_history": {"retention_days": 365, "description": "Retain agent location-history audit records for 365 days"}` to `_POLICY_DEFAULTS` in `retention_endpoints.py`, add `cleanup_agent_location_history()` to `RetentionService` (delete_many on a Date-typed `timestamp` field, no `tenantId` filter needed since retention is a platform-wide sweep exactly like the other 3 existing cleanup methods), and wire it into `run_cleanup()`'s returned report dict. Explicitly decide (and document in the plan) whether an automatic scheduler is added or whether manual-trigger parity with the existing precedent is accepted for this phase.

## Common Pitfalls

### Pitfall 1: NAT-flip de-noise (D-06) cannot be implemented by only comparing against `existing_agent.publicIp`

**What goes wrong:** The natural first implementation is "if `public_ip != existing_agent.get('publicIp')`, write a history row." This correctly satisfies D-05 (write on change) but **not** D-06 (de-noise flip-flops within ~10 minutes) — because `agents.publicIp` gets unconditionally overwritten to the newest value on *every* heartbeat (existing behavior, `agent_heartbeat_endpoints.py:121`/`agent_registry_endpoints.py:84`, unchanged by this phase). If an agent's IP bounces A → B → A within the 10-minute window, the second heartbeat sees `existing_agent.publicIp == A` and thinks nothing changed (correct, no row), but the *first* flip (A → B) already wrote a row, and then the third real heartbeat back at B (if the bounce continues) would look like *another* new change relative to the now-stored A. A single "prior value" field cannot distinguish "flip-flop" from "two genuine changes in quick succession" — you need to know not just the last value, but the last *committed* audit value and how long it's been stable.

**Why it happens:** `agents.publicIp` serves double duty today — it's both "last-seen raw value" (used everywhere else in the codebase that reads `agent.publicIp`) and would become the change-detection baseline. Overloading one field for both purposes loses the information needed to de-noise.

**How to avoid:** Keep the existing `agents.publicIp`/`agents.geo` fields exactly as they are today (many other things may read them as "last observed" — do not change their write-every-heartbeat semantics). Add two **new**, phase-owned fields used only by the location-history logic:
- `agents.locationConfirmed` — `{publicIp, geo, confirmedAt}`: the last value that was actually promoted to a written `agent_location_history` row (the "committed" baseline for change-detection, separate from the raw last-seen `publicIp`).
- `agents.locationPending` — `{publicIp, geo, firstSeenAt}`: a candidate value currently being observed, not yet committed.

Per-heartbeat logic (only runs when `public_ip` is present and the toggle is ON):
1. If `public_ip`/`geo` equals `locationConfirmed`'s values → no-op (agent is at its confirmed location; this is the common case, most heartbeats hit this branch).
2. Else if `public_ip`/`geo` equals `locationPending`'s values and `now - locationPending.firstSeenAt >= debounce_window` (~10 min, tunable) → **promote**: insert the `agent_location_history` row, set `locationConfirmed = locationPending`, clear `locationPending`.
3. Else if `public_ip`/`geo` equals `locationPending`'s values but the window hasn't elapsed yet → no-op, keep waiting.
4. Else (a genuinely new candidate different from both `locationConfirmed` and any current `locationPending`) → reset `locationPending = {publicIp, geo, firstSeenAt: now}` (discard whatever was pending before — this is what collapses A→B→A: B never accumulates enough dwell time to promote before the agent flips back to A, which matches `locationConfirmed` and short-circuits at step 1 with the pending state simply discarded).

This never mutates a written `agent_location_history` row (preserves immutability/D-10) and never blocks/delays the heartbeat response — it's a same-request state-machine update alongside the existing `db.agents.update_one(...)` call. The debounce window value is Claude's Discretion per CONTEXT.md; ~10 minutes matches the stated NAT-lease-flip timescale.

**Warning signs:** A history row appears, then a nearly-identical reverse-direction row appears less than the debounce window later, for the same agent — that's the de-noise failing to collapse a flip-flop.

### Pitfall 2: "Dwell time" (D-09) must be computed at read time, not stored per-row

**What goes wrong:** Storing a `dwell_seconds` field directly on each `agent_location_history` row at write time is tempting but wrong for the *most recent* row — that agent may still be at that location, so any stored dwell value goes stale the instant it's written and would need constant updates, which violates append-only immutability (D-10) and the whole point of the collection.

**How to avoid:** Compute dwell time in the GET endpoint (or the frontend) as a derived value: for row *i* (sorted ascending by timestamp), `dwell = timestamp(i+1) - timestamp(i)`; for the last/most-recent row, `dwell = now - timestamp(last)`. Never persist this field.

### Pitfall 3: Reusing `db.agents.find_one` tenant-scoping without the same "belt-and-braces" pattern SLA-02 already established

**What goes wrong:** The new GET endpoint might filter only by `{"agent_id": agent_id, "tenantId": tenant_id}` in the Mongo query and trust that alone.

**How to avoid:** `compliance_remediation_sla_endpoints.py:70-73` re-filters the result list in application code after the query (`entries = [e for e in entries if e.get("tenantId") == tenant_id]`) — this exact belt-and-braces re-check (T-44-06's mitigation) should be cloned for the new endpoint, not skipped as "redundant."

### Pitfall 4: `security_events`/`alerts` retention policy docs exist but have no cleanup implementation — don't assume "seed a policy doc" is sufficient for `agent_location_history` either

Already covered in detail above (Retention Module Integration) — restated here because it's the kind of "looks done but isn't" gap this project's own PITFALLS.md warns about generally.

## Code Examples

### ASN/VPN lookup module skeleton (mirrors `geoip_service.py` exactly)

```python
# backend/agent_asn_service.py — Source: pattern cloned from backend/geoip_service.py (this repo)
from __future__ import annotations
import ipaddress
import logging
import os
import threading
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

_DEFAULT_ASN_DB_PATH = os.path.join(os.path.dirname(__file__), "data", "geoip", "GeoLite2-ASN.mmdb")
_VPN_RANGES_PATH = os.path.join(os.path.dirname(__file__), "data", "vpn_ranges", "x4bnet_vpn_ipv4.txt")

_reader = None
_reader_lock = threading.Lock()
_load_attempted = False

_vpn_ranges: Optional[list] = None  # sorted list of (start_int, end_int) tuples
_vpn_lock = threading.Lock()
_vpn_load_attempted = False


def _get_reader():
    global _reader, _load_attempted
    if _reader is not None or _load_attempted:
        return _reader
    with _reader_lock:
        if _reader is not None or _load_attempted:
            return _reader
        _load_attempted = True
        path = os.getenv("GEOIP_ASN_DB_PATH", _DEFAULT_ASN_DB_PATH)
        if not os.path.isfile(path):
            logger.warning("GeoLite2-ASN database not found at %s — ASN enrichment disabled.", path)
            return None
        try:
            import maxminddb
            _reader = maxminddb.open_database(path)
        except Exception as exc:
            logger.warning("Failed to open GeoLite2-ASN database %s: %s", path, exc)
        return _reader


def _load_vpn_ranges() -> list:
    global _vpn_ranges, _vpn_load_attempted
    if _vpn_ranges is not None or _vpn_load_attempted:
        return _vpn_ranges or []
    with _vpn_lock:
        if _vpn_ranges is not None or _vpn_load_attempted:
            return _vpn_ranges or []
        _vpn_load_attempted = True
        ranges = []
        try:
            with open(_VPN_RANGES_PATH) as f:
                for line in f:
                    line = line.strip()
                    if not line or line.startswith("#"):
                        continue
                    net = ipaddress.ip_network(line, strict=False)
                    ranges.append((int(net.network_address), int(net.broadcast_address)))
            ranges.sort()
        except FileNotFoundError:
            logger.warning("X4BNet VPN range snapshot not found at %s — VPN heuristic disabled.", _VPN_RANGES_PATH)
        _vpn_ranges = ranges
        return ranges


def _is_known_vpn_range(ip: str) -> bool:
    import bisect
    ranges = _load_vpn_ranges()
    if not ranges:
        return False
    ip_int = int(ipaddress.ip_address(ip))
    idx = bisect.bisect_right(ranges, (ip_int, float("inf"))) - 1
    if idx < 0:
        return False
    start, end = ranges[idx]
    return start <= ip_int <= end


def lookup(ip: Optional[str]) -> Optional[Dict[str, Any]]:
    """Returns {"asn": {number, org}, "vpn_heuristic": bool} or None. Never raises."""
    import geoip_service
    if not ip or not geoip_service._is_public(ip):
        return None
    result: Dict[str, Any] = {}
    reader = _get_reader()
    if reader is not None:
        try:
            rec = reader.get(ip)
            if rec:
                result["asn"] = {
                    "number": rec.get("autonomous_system_number"),
                    "org": rec.get("autonomous_system_organization"),
                }
        except Exception as exc:
            logger.debug("ASN lookup failed for %s: %s", ip, exc)
    result["vpn_heuristic"] = _is_known_vpn_range(ip)
    return result or None
```

### Frontend location-history panel (clone `EscalationHistoryPanel.tsx`)

```tsx
// components/AgentLocationHistory.tsx — Source: components/EscalationHistoryPanel.tsx (this repo, cloned shape)
// Reuses flagEmoji/formatGeo helpers already defined in components/AgentList.tsx — extract
// them to a shared util if both files need them, rather than duplicating.
import React, { useState } from 'react';
import { HistoryIcon, ChevronDownIcon, GlobeIcon } from './icons';
import * as api from '../services/apiService';

interface LocationHistoryEntry {
    publicIp: string;
    geo?: { city?: string; region?: string; country?: string; country_code?: string };
    vpn_heuristic?: boolean;
    timestamp: string;   // ISO string over the wire; dwell computed client-side
}

// Same lazy-expand-on-toggle, read-only shape as EscalationHistoryPanel — no edit/delete
// affordance anywhere (D-10).
export const AgentLocationHistory: React.FC<{ agentId: string }> = ({ agentId }) => {
    const [isExpanded, setIsExpanded] = useState(false);
    const [entries, setEntries] = useState<LocationHistoryEntry[]>([]);
    const [loading, setLoading] = useState(false);
    const [fetched, setFetched] = useState(false);

    const handleToggle = async () => {
        if (!isExpanded && !fetched) {
            setLoading(true);
            try {
                const data = await api.fetchAgentLocationHistory(agentId);
                setEntries(data.entries ?? []);
                setFetched(true);
            } finally {
                setLoading(false);
            }
        }
        setIsExpanded(prev => !prev);
    };
    // ... render loop identical in structure to EscalationHistoryPanel.tsx,
    // computing dwell = next.timestamp - this.timestamp (or now - last.timestamp)
    // client-side per Common Pitfall 2 — never trust a stored dwell field.
    return null; // full JSX omitted — clone EscalationHistoryPanel.tsx's structure
};
```

### `apiService.ts` client function (clone `fetchRemediationEscalations`)

```typescript
// Source: services/apiService.ts:4596 (this repo, cloned shape)
export const fetchAgentLocationHistory = async (agentId: string): Promise<{ agent_id: string; entries: LocationHistoryEntry[] }> => {
    try {
        const res = await authFetch(`${API_BASE}/agents/${agentId}/location-history`);
        if (!res.ok) return { agent_id: agentId, entries: [] };
        return await res.json();
    } catch {
        return { agent_id: agentId, entries: [] };
    }
};
```

## Frontend Integration — mount point decision

`AgentDetailModal.tsx` (read this session) is a **tab-based** modal (`activeTab: 'overview' | 'runtime' | 'compliance' | 'health' | 'software' | 'patching' | 'instructions'`, lines 183, 617-645), whereas `EscalationHistoryPanel` in `RemediationTaskModal.tsx` is an **embedded collapsible panel within a single-view modal** (no tabs — `RemediationTaskModal.tsx:377`, `{task?.id && <EscalationHistoryPanel taskId={task.id} />}`). D-08 says "same shape/placement as `EscalationHistoryPanel`," which literally means: embed `AgentLocationHistory` as a collapsible panel **inside the existing `overview` tab's content** (alongside where `agent.publicIp`/`agent.geo` are presumably already rendered, per `AgentOverviewTab.tsx`), not as a new seventh tab. Recommend embedding in the Overview tab; a new tab is a defensible alternative given the modal's own established multi-tab convention, but it deviates from D-08's literal "clone the panel" instruction — flag this choice explicitly in the plan rather than silently picking one.

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| `GeoLite2-City.mmdb` (existing) | `geoip_service.py` city/country enrichment | ✗ (not present in this checkout — `backend/data/geoip/` has no `.mmdb` file) | — | Already gracefully degrades (`geoip_service.lookup()` returns `None`); confirms this is the expected out-of-band-supply state in dev |
| `GeoLite2-ASN.mmdb` (new) | `agent_asn_service.py` ASN lookup | ✗ (new dependency, out-of-band supply per D-11) | — | Graceful degrade — `result["asn"]` simply absent, `vpn_heuristic` can still work from the X4BNet list alone |
| X4BNet VPN range snapshot | `agent_asn_service.py` heuristic VPN flag | ✗ (must be added to the repo this phase, per D-12) | — | Graceful degrade — `_is_known_vpn_range()` returns `False` for everything if the file is missing, matching the "no runtime fetch" requirement |
| `maxminddb` Python package | Both ASN and City lookups | ✓ | `>=2.5.0` [VERIFIED: backend/requirements.txt:138] | — |

**Missing dependencies with no fallback:** none — every new dependency in this phase already has an established graceful-degrade precedent to follow.
**Missing dependencies with fallback:** `GeoLite2-ASN.mmdb` (supplied out-of-band at deploy time, exactly like the existing City DB) and the X4BNet snapshot (bundled into the repo as a build-time asset, not fetched at runtime).

## Validation Architecture

### Test Framework

| Property | Value |
|----------|-------|
| Framework | pytest, hermetic `unittest.mock`-based (see `backend/tests/test_compliance_remediation_sla.py` as the direct precedent for this phase's shape) |
| Config file | `backend/pyproject.toml` |
| Quick run command | `backend/venv/bin/python -m pytest backend/tests/test_agent_location_history.py -q` |
| Full suite command | `backend/venv/bin/python -m pytest backend/tests/ -q` (per project memory: use `backend/venv/bin/python`, not system Python — the venv has pytest and deps installed; system Python does not) |

### Phase Requirements → Test Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| GAUD-01 | Change-detection writes exactly one row on a real `publicIp`/geo change | unit | `pytest backend/tests/test_agent_location_history.py -k change_detection -x` | ❌ Wave 0 |
| GAUD-01 | NAT flip-flop (A→B→A within debounce window) never promotes to a written row | unit | `pytest backend/tests/test_agent_location_history.py -k denoise -x` | ❌ Wave 0 |
| GAUD-01 | Two genuine changes further apart than the debounce window each write a row | unit | `pytest backend/tests/test_agent_location_history.py -k denoise -x` | ❌ Wave 0 |
| GAUD-01 | No PATCH/PUT/DELETE route exists for the location-history resource (immutability) | unit | `pytest backend/tests/test_agent_location_history.py -k immutability -x` | ❌ Wave 0 |
| GAUD-01 | `track_agent_location=false` suppresses both the write and the ASN/VPN enrichment call, but not the existing `geo` city/country enrichment | unit | `pytest backend/tests/test_agent_location_history.py -k toggle -x` | ❌ Wave 0 |
| GAUD-01 | `agent_location_history.timestamp` is a real BSON Date, not a string (regression guard against Pitfall 6) | unit | `pytest backend/tests/test_agent_location_history.py -k bson_date -x` | ❌ Wave 0 |
| GAUD-01 | Retention: a synthetic 366-day-old row is deleted by `cleanup_agent_location_history`, a 1-day-old row is not | integration (real Mongo, not mocked — per PITFALLS.md's own recommendation for TTL/expiry claims) | `pytest backend/tests/test_retention_agent_location_history.py -x` | ❌ Wave 0 |
| GAUD-02 | Tenant-scoped GET returns only the calling tenant's entries, sorted ascending | unit | `pytest backend/tests/test_agent_location_history.py -k tenant_scope -x` | ❌ Wave 0 |
| GAUD-02 | ASN/VPN lookup gracefully returns `None`/`False` when the `.mmdb`/snapshot file is absent | unit | `pytest backend/tests/test_agent_asn_service.py -x` | ❌ Wave 0 |

### Sampling Rate
- **Per task commit:** `backend/venv/bin/python -m pytest backend/tests/test_agent_location_history.py backend/tests/test_agent_asn_service.py -q`
- **Per wave merge:** `backend/venv/bin/python -m pytest backend/tests/ -q`
- **Phase gate:** Full suite green before `/gsd-verify-work`; per project memory, the last known-good baseline is **1343 pass / 3 pre-existing fails** (e2e evidence, rust parity, agentic tool_choice) — confirm no *new* failures, not a byte-identical count.

### Wave 0 Gaps
- [ ] `backend/tests/test_agent_location_history.py` — covers GAUD-01 (change-detection, de-noise, immutability, toggle gating, BSON Date type)
- [ ] `backend/tests/test_agent_asn_service.py` — covers the ASN/VPN lookup module's graceful-degrade behavior
- [ ] `backend/tests/test_retention_agent_location_history.py` — covers the 365-day retention sweep against a real (non-mocked) Mongo instance, per PITFALLS.md's explicit recommendation to verify TTL/expiry claims against real data rather than mocks
- [ ] Framework install: none — pytest + mongomock/real Mongo already available in this environment

## Security Domain

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-------------------|
| V2 Authentication | yes (indirect) | Existing `verify_agent_key`/`get_current_user` dependencies, unchanged by this phase |
| V4 Access Control | yes | New GET endpoint must reuse the exact tenant-scoping + belt-and-braces re-filter pattern from `compliance_remediation_sla_endpoints.py` (Pitfall 3 above); admin-only gating on the `track_agent_location` PATCH, mirroring `_SETTINGS_ADMIN_ROLES` |
| V5 Input Validation | yes | `windowDays`-equivalent config values (if a settings endpoint is added) should use Pydantic `Field(ge=..., le=...)` bounds exactly like `SlaWindowUpdate` |
| V6 Cryptography | no | No new cryptographic material in this phase |
| V9/V14 Data Protection & Config (ASVS 5.0 numbering may vary) | yes | This is fundamentally a data-retention/privacy-classification phase — D-04's pre-implementation privacy gate is itself the ASVS-relevant control; no PII beyond IP/geo is newly collected |

### Known Threat Patterns for this stack

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| Cross-tenant read of another tenant's location-history via a crafted `agent_id` | Information Disclosure | Tenant-scoped query + belt-and-braces application-level re-filter (cloned from SLA-02's proven pattern) |
| Background sweep (if an automatic retention scheduler is added) silently detecting/deleting nothing because it used `get_database()` instead of raw `mongodb.db` | Denial of Service (silent) | Follow Pattern 4 from `.planning/research/ARCHITECTURE.md` exactly — raw `mongodb.db` passed at scheduler registration, per-document `tenantId` handling |
| Untrusted third-party X4BNet data injected into the bundled snapshot at a future refresh | Tampering | Pin/verify the source repo commit hash when refreshing the bundled file; treat it as vendored third-party data requiring the same scrutiny as any dependency update |

## Assumptions Log

> This project's `classify-confidence` seam rates plain `WebSearch` (no authoritative-doc fetch, no cross-check) as **LOW** confidence, not MEDIUM — both external-data claims below were sourced this way and must be tagged `[ASSUMED]` regardless of how confidently the search summarized them. Confirm both before implementation locks in field names or file paths.

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | GeoLite2-ASN `.mmdb` records expose `autonomous_system_number`/`autonomous_system_organization` as flat top-level keys (not nested) | "Integration Point 3", `agent_asn_service.py` code example | If the actual field names or nesting differ, `agent_asn_service.lookup()` silently returns `None` for the ASN sub-object (caught by the existing "never raises" try/except pattern) rather than crashing — low blast radius, but `geo.asn` would silently stay empty on every agent, undetected without a real `.mmdb` test |
| A2 | X4BNet `lists_vpn` repo layout — `output/vpn/ipv4.txt` (strict VPN) vs `output/datacenter/ipv4.txt` (VPN+datacenter), plain CIDR-per-line text, GitHub-Actions auto-rebuilt | "Standard Stack" / "Package Legitimacy Audit" / `agent_asn_service.py` code example (`_load_vpn_ranges()` parsing) | If the file's actual line format differs (e.g., includes IPv6, comments in a different style, or a JSON wrapper instead of plain text), the bundled-snapshot loader would need adjustment before `_is_known_vpn_range()` works at all — verify by actually downloading the file before writing the parser, not by trusting this citation |

**If this table is empty:** N/A — see above; confirm A1/A2 against a real downloaded artifact during implementation, ideally as the first task in the relevant wave (fail fast if the format assumption is wrong).

## Sources

### Primary (HIGH confidence — direct codebase inspection this session)
- `backend/geoip_service.py` (full file, 106 lines) — lazy-mmdb-reader template
- `backend/agent_heartbeat_endpoints.py` (full file, 517 lines) — exact heartbeat integration lines
- `backend/agent_registry_endpoints.py` (full file, 360 lines) — exact registration integration lines
- `backend/compliance_remediation_sla_service.py` (full file, 316 lines) — append-only write pattern, `system_settings` toggle lookup pattern
- `backend/compliance_remediation_sla_endpoints.py` (full file, 144 lines) — GET-only immutable read pattern, belt-and-braces tenant re-filter
- `backend/retention_service.py` (full file, 53 lines) / `backend/retention_endpoints.py` (full file, 106 lines) / `backend/retention_tiers_endpoints.py` (full file, 161 lines) — retention module's actual (limited) current behavior
- `backend/database.py` (lines 1-260+) — `TenantIsolatedDatabase` exemption list (confirms `agents` is not exempt), index-creation block
- `backend/migrations/002_scale_indexes.py` (full file, 61 lines) — TTL index Date-type requirement, confirmed silent-no-op on `agent_metrics_history`
- `backend/agent_metrics_endpoints.py` (lines 1-140) — tenant-scoped GET-by-agent-id read pattern to clone
- `backend/agent_endpoints.py` / `backend/router_registry.py` — router aggregation/registration pattern
- `components/EscalationHistoryPanel.tsx` (full file, 125 lines) / `components/RemediationTaskModal.tsx` (mount line) — frontend panel clone template
- `components/AgentList.tsx` (lines 60-160) — `flagEmoji`/`formatGeo` helpers
- `components/AgentDetailModal.tsx` (lines 1-650) — tab structure, mount-point decision
- `services/apiService.ts` (lines 4585-4605, 1007+) — client function clone template
- `.planning/research/SUMMARY.md`, `ARCHITECTURE.md`, `PITFALLS.md`, `STACK.md` — milestone-level research this phase builds on (not re-derived)

### Tertiary (LOW confidence — plain WebSearch only this session; see Assumptions Log A1/A2)
- [MaxMind GeoLite ASN binary database fields](https://dev.maxmind.com/geoip/docs/databases/asn/binary/) — claims `autonomous_system_number`/`autonomous_system_organization` field names (A1)
- [MaxMind GeoIP2-python](https://github.com/maxmind/GeoIP2-python) — same field names via the wrapper library's API surface, secondhand via search summary, not fetched (A1)
- [X4BNet/lists_vpn README](https://github.com/X4BNet/lists_vpn/blob/main/README.md) — claims `output/vpn/ipv4.txt` vs `output/datacenter/ipv4.txt` distinction and CIDR-notation format (A2)

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — no new packages, everything already verified present in `requirements.txt`
- Architecture/integration points: HIGH — every claim grounded in exact file/line citations from this session's reads
- Retention module gap: HIGH — directly read all 3 relevant files; confirmed no scheduler via grep
- NAT-flip de-noise design: MEDIUM — this is original design reasoning (not found verbatim in any source), grounded in the codebase's actual field semantics but not verified against a reference implementation elsewhere
- ASN/X4BNet external data-format specifics: LOW — plain WebSearch only this session (project's own `classify-confidence` seam rates unauthenticated web search as LOW, not MEDIUM); tagged `[ASSUMED]`, see Assumptions Log A1/A2 — confirm against a real downloaded artifact before implementation locks in field names or file paths

**Research date:** 2026-07-29
**Valid until:** 30 days (stable internal patterns); re-verify GeoLite2-ASN/X4BNet field-format claims (Assumptions Log A1/A2) against an actual downloaded `.mmdb`/snapshot file before implementation — do not treat this session's WebSearch summaries as locked fact
