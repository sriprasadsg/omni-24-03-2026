# Phase 47: Agent-Scoped Geo Security Detectors - Research

**Researched:** 2026-07-29
**Domain:** Backend alert detectors (haversine impossible-travel + country-code geo-fence) wired into an existing FastAPI/Mongo heartbeat pipeline; admin-gated per-tenant config; minor frontend badge surfacing.
**Confidence:** HIGH — every integration point was read directly from the actual Phase 46 source in this repo (not inferred), and one call was executed live (`python -c "from ueba_service import persist_security_alert"`) to confirm behavior.

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

**Impossible-Travel (GSEC-02)**
- **D-01:** Threshold is a **fixed max speed of ~1000 km/h** (commercial-flight ceiling). Two consecutive check-ins for one `agent_id` whose haversine distance ÷ elapsed time exceeds this raises the alert. Not per-tenant configurable in v3.3 (keep config surface minimal; revisit if tenants ask).
- **D-02:** **Suppress the impossible-travel alert entirely when either endpoint carries the VPN/hosting heuristic flag.** This is the load-bearing GSEC-01→GSEC-02 link — corporate-VPN egress is the dominant false-positive source, and the goal explicitly front-loads killing it. (No downgraded/low-severity alert — full suppression.)

**Geo-Fence (GSEC-03)**
- **D-03:** Allowed regions are a **country-code allowlist (ISO 3166 alpha-2)**. The check-in country is already resolved by `geoip_service` — compare against the tenant's allowlist; not-in-list → alert. No region/state or radius/coordinate fencing in v3.3.
- **D-04:** Alert-only — a violation raises an alert and does nothing to the connection (no reject, no quarantine). Deferred: block enforcement.

**Alert Noise Control (GSEC-02 + GSEC-03)**
- **D-05:** **Dedup per (agent_id, violation_type) on state transition + cooldown window.** Fire one alert when the violation state changes (clean→violating), then suppress repeats within a cooldown window (default **6h**) even if every heartbeat keeps violating. Model the transition/de-noise after Phase 46's `record_location_change` state-machine idea — alert volume tracks violations, not heartbeat frequency.

**Config Surface (UI — GSEC-03)**
- **D-06:** Geo-fence allowed-regions + detector on/off live in a **new admin-gated Security settings panel** (separate from Phase 46's PrivacyDashboard — keep security config distinct from privacy). Per-tenant config stored via the existing `system_settings` type-keyed doc pattern (clone of `track_agent_location`), admin-gated GET/PATCH like the 46 toggle endpoints.

### Claude's Discretion
- Alert `alert_type` strings and `severity` values fed to `persist_security_alert` (suggest `impossible_travel` / `geo_fence_violation`; severity `high` / `medium`) — planner/executor choose, consistent with existing UEBA alert taxonomy.
- Exact detector placement in the heartbeat handler (inline alongside 46's `record_location_change`, toggle-gated) — architecture detail for planning.
- Cooldown-window storage mechanism (agent shadow field vs dedicated collection) — planner decides. **Research recommendation below: shadow field on the `agents` doc** (see Architecture Patterns).

### Deferred Ideas (OUT OF SCOPE)
- **Paid MaxMind GeoIP2 Anonymous-IP** upgrade — authoritative VPN/proxy/hosting/Tor classification; upgrades GSEC-01 from heuristic to authoritative if a license is procured.
- **Geo-fence block enforcement** — reject/quarantine out-of-region agents. v3.3 is alert-only.
- **Per-tenant configurable impossible-travel threshold** — revisit if tenants request it; fixed 1000 km/h for now.
- **Region/state or radius geo-fencing** — finer granularity beyond country-code allowlist.

None else — discussion stayed within phase scope.
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| GSEC-01 | Surface the heuristic VPN/proxy/hosting flag on the agent; UI labels it "likely VPN/hosting", never authoritative. | Backend flag already computed by Phase 46's `agent_asn_service.lookup()` and stored on `agent.geo.vpn_heuristic`. **Gap found:** it is rendered only inside `AgentLocationHistory.tsx`'s history rows — the live agent card (`AgentList.tsx`) and `types.ts`'s `GeoLocation` interface do not yet expose/render it. This phase's GSEC-01 work is almost entirely: (1) add `vpn_heuristic`/`asn` to the `GeoLocation` TS interface, (2) render the identical amber badge in `AgentList.tsx`'s agent-card Location row. |
| GSEC-02 | Agent-scoped impossible-travel (haversine + time window, keyed by `agent_id`), reusing the existing alert fan-out. | Haversine reference implementation already exists in `ueba_service.py::_haversine_km` (stdlib `math`, no new dep). Previous-geo/timestamp source, alert fan-out signature, and a **must-fix pre-existing bug** in the fan-out are documented below. |
| GSEC-03 | Per-tenant allowed-region geo-fence (country-code allowlist), alert-only. | `geoip_service.lookup()` already resolves `country_code` (ISO 3166 alpha-2) unconditionally on every heartbeat with a public IP — independent of Phase 46's `track_agent_location` toggle. Config-lookup pattern to clone documented below (`get_sla_at_risk_window`-style tenant→global→default resolution, generalized for a list value). |
</phase_requirements>

## Summary

This phase is almost entirely wiring, not new algorithms: haversine is 6 lines of stdlib `math` (already written once in this exact codebase, in `ueba_service.py`), country-code geo-fencing is a set-membership check against a field `geoip_service` already resolves on every heartbeat, and the "existing alert fan-out" the phase must reuse is `ueba_service.py`'s alert-persistence helper, called identically from five existing heartbeat-telemetry blocks (`shadow_ai`, `ueba_anomaly`, `fim_violation`, `pii_detected`, `runtime_security`).

**Critical finding (verified by direct execution, not inference):** that "existing alert fan-out" is currently **broken**. `agent_heartbeat_endpoints.py` and `agent_heartbeat_alerts_service.py` do `from ueba_service import persist_security_alert` five times, but `ueba_service.py` only defines a *private*, differently-named `_persist_alert(db, alert_type, severity, title, description, metadata)`. Running `python -c "from ueba_service import persist_security_alert"` raises `ImportError` — confirmed live in this repo's venv. Every one of those five call sites wraps the import in `try: ... except ImportError: pass`, so all five have been silently no-oping since they were written; none of shadow-AI, UEBA-anomaly, FIM, PII, or runtime-security alerts have ever actually reached `security_alerts`. GSEC-02/03 **cannot** "reuse the existing alert fan-out" as CONTEXT.md's canonical references assume, because under that name it does not exist. The phase must first make `persist_security_alert` a real, importable public symbol in `ueba_service.py` (the minimal fix: `persist_security_alert = _persist_alert`, or rename the function and update the one internal call site) — this is now in-scope, required plumbing, not optional cleanup, and it also fixes five previously-silent bugs as a side effect.

Two further real design distinctions this phase must get right, both discovered by reading Phase 46's actual state machine rather than assuming it transfers verbatim: (1) the "previous check-in" for impossible-travel must be the **raw** last-heartbeat `agent.geo`/`agent.lastSeen` fields — which are updated on *every* heartbeat unconditionally — not the debounced `locationConfirmed`/`locationPending` shadow fields Phase 46 built to solve a *different* problem (NAT-flip noise in the audit trail); comparing against the debounced state would delay or entirely miss a fast attacker-driven jump. (2) the VPN-suppression signal (D-02) and country-code (D-03) have **different availability**: `geo.country_code`/lat-long populate on every heartbeat regardless of the Phase 46 `track_agent_location` toggle, but `geo.vpn_heuristic` only populates when that toggle is ON — meaning GSEC-03 works independently of Phase 46's toggle, but GSEC-02's false-positive-killing suppression does not.

**Primary recommendation:** Fix `ueba_service.persist_security_alert` first (Wave 0 prerequisite, same class of fix as Phase 30's RAG-tenant-isolation "claimed but never implemented" gap). Then add two small, pure functions (`haversine_impossible_travel(prev, curr) -> bool`, `evaluate_geo_fence(country_code, allowlist) -> bool`) plus a state-transition/cooldown shadow field on the `agents` doc, called inline in `agent_heartbeat_endpoints.py` right after Phase 46's `record_location_change`, gated by a new admin-configurable per-tenant `system_settings` doc cloned from `track_agent_location`.

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| Haversine distance/speed calc | API / Backend | — | Pure function, no I/O; runs inline in the heartbeat handler alongside Phase 46's enrichment |
| Impossible-travel state (dedup/cooldown) | Database / Storage | API / Backend | Shadow field on `agents` doc (Mongo), read/written by the backend heartbeat handler — no new collection needed |
| VPN-heuristic suppression check | API / Backend | Database / Storage | Reads `agent_asn_service.lookup()`'s output already computed this beat + the prior beat's stored `geo.vpn_heuristic` |
| Country-code geo-fence check | API / Backend | Database / Storage | Reads `geoip_service`-resolved `country_code` against a per-tenant allowlist stored in `system_settings` |
| Alert persistence + fan-out | API / Backend | Database / Storage | `ueba_service.persist_security_alert` writes `db.security_alerts` + streaming broker publish + blockchain audit block — must be fixed, then reused verbatim, never duplicated |
| Security settings config (allowlist + detector toggles) | API / Backend | Database / Storage | New admin-gated GET/PATCH endpoints + `system_settings` type-keyed docs, cloned from `agent_location_history_endpoints.py`'s toggle |
| VPN/hosting badge on agent card | Browser / Client | — | `AgentList.tsx` render change + `types.ts` interface extension; read-only, no new state |
| New Security settings panel | Browser / Client | API / Backend | New React component (clone of `PrivacyDashboard.tsx`'s toggle section), calling the new config endpoints |

## Standard Stack

### Core

No new backend or frontend packages are required for this phase.

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| Python stdlib `math` | — (stdlib) | Haversine great-circle distance | Already used for this exact purpose in `ueba_service.py::_haversine_km` in this repo — zero new dependency, zero new attack surface |
| Python stdlib `datetime` | — (stdlib) | Elapsed-time calc, cooldown-window comparison | Same convention as `agent_location_history_service.py`'s `DEBOUNCE_WINDOW`/`timedelta` usage |

### Supporting

Not applicable — no supporting libraries beyond stdlib. `geoip_service.py` and `agent_asn_service.py` (both pre-existing, Phase 46) supply all enrichment inputs this phase consumes; no new reader/parser is introduced.

### Alternatives Considered

| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| stdlib haversine (6-line function) | `geopy.distance.geodesic` / `haversine` PyPI package | Adds a dependency for a formula that already exists, verified working, in this exact codebase (`ueba_service.py`). No justification to add a package. |
| Shadow field on `agents` doc for dedup/cooldown state | Dedicated `geo_security_alert_state` collection | A dedicated collection means 1-2 extra Mongo round-trips per heartbeat (one per violation type) on top of the `existing_agent` doc already fetched at the top of the handler. The shadow-field approach costs zero extra reads (mirrors Phase 46's own D-05 "zero extra reads" precedent for `locationConfirmed`/`locationPending`). Recommended unless the planner has a reason to want the state independently queryable/indexable (e.g., an admin "currently violating" dashboard across all agents — a dedicated collection would support that better, at the cost of the extra reads). |

**Installation:** None — no new packages.

**Version verification:** N/A — no packages to verify.

## Package Legitimacy Audit

Not applicable. This phase introduces zero new backend or frontend packages (see Standard Stack above — everything needed is Python stdlib or already-installed/vendored: `maxminddb`, the bundled X4BNet CIDR snapshot, and React/TypeScript already in `package.json`). No `package-legitimacy check` run was needed.

**Packages removed due to [SLOP] verdict:** none
**Packages flagged as suspicious [SUS]:** none

## Architecture Patterns

### System Architecture Diagram

```
Agent (Rust/Python daemon)
  │  POST /api/agents/{agent_id}/heartbeat   (existing route, agent_heartbeat_endpoints.py)
  ▼
verify_agent_key()  ──▶ set_tenant_id(tenant["id"])   [existing — tenant context for this request/task]
  │
  ▼
existing_agent = db.agents.find_one(...)     [existing — PRE-update read; this IS "previous check-in" state]
  │
  ▼
public_ip present? ──▶ geo = geoip_service.lookup(ip)         [existing, UNGATED — country_code/lat/long always available]
  │
  ▼
track_agent_location toggle ON? ──▶ asn_enrichment = agent_asn_service.lookup(ip)   [existing, GATED — vpn_heuristic only here]
  │                                    geo = {**geo, asn, vpn_heuristic}
  ▼
db.agents.update_one(... new geo/lastSeen ...)   [existing — write happens BEFORE new detectors run]
  │
  ▼
record_location_change(existing_agent, ..., geo, asn_enrichment)   [existing, Phase 46 — NAT-flip debounce for AUDIT TRAIL only]
  │
  ▼  ◀── NEW in this phase, same call site, own toggle ─────────────────────────────
  ├─▶ get_geo_security_settings(db, tenant_id)  → {impossible_travel_enabled, geo_fence_enabled, allowed_country_codes}
  │
  ├─▶ if impossible_travel_enabled:
  │      evaluate_impossible_travel(existing_agent.geo, existing_agent.lastSeen,   ◀── RAW prior beat, NOT locationConfirmed
  │                                  new_geo, now, vpn_flag_prev, vpn_flag_new)
  │        → violating: bool
  │      dedup_and_maybe_alert(existing_agent, agent_id, "impossible_travel", violating)
  │        → if should_fire: persist_security_alert(db, alert_type="impossible_travel", severity="high", ...)
  │
  └─▶ if geo_fence_enabled:
         evaluate_geo_fence(new_geo.country_code, allowed_country_codes) → violating: bool
         dedup_and_maybe_alert(existing_agent, agent_id, "geo_fence_violation", violating)
           → if should_fire: persist_security_alert(db, alert_type="geo_fence_violation", severity="medium", ...)
  │
  ▼
persist_security_alert()  [MUST-FIX: currently ImportError'd no-op — see Pitfall 1]
  ├─▶ db.security_alerts.insert_one(alert)         [existing collection, existing readers: agent_security_endpoints.py, mitre_service.py, ticketing_endpoints.py]
  ├─▶ streaming_service.broker.publish("security_events", ...)   [existing — live dashboard feed]
  └─▶ db.blockchain_audit.insert_one(...)          [existing — immutable audit chain]

Admin browser
  │  GET/PATCH /api/settings/geo-security   (NEW, clone of /api/settings/agent-location-tracking)
  ▼
new Security settings panel (SecuritySettingsDashboard.tsx or similar, NEW)
  │  reads/writes system_settings {type: "geo_security_detectors", tenantId, ...}
  ▼
Admin browser (agent card)
  │  AgentList.tsx renders agent.geo.vpn_heuristic badge  (GSEC-01 — reads the ALREADY-COMPUTED flag, no new backend call)
```

### Recommended Project Structure

```
backend/
├── geo_security_service.py       # NEW — evaluate_impossible_travel(), evaluate_geo_fence(),
│                                  #   dedup_and_maybe_alert(), get_geo_security_settings()
├── geo_security_endpoints.py      # NEW — GET/PATCH /api/settings/geo-security (clone of
│                                  #   agent_location_history_endpoints.py's toggle pair)
├── ueba_service.py                # MODIFIED — add public persist_security_alert name (bugfix)
├── agent_heartbeat_endpoints.py   # MODIFIED — 2 new call sites after record_location_change
├── agent_asn_service.py           # UNCHANGED — vpn_heuristic already exposed
├── geoip_service.py               # UNCHANGED — country_code already exposed
└── tests/
    └── test_geo_security_service.py   # NEW — hermetic unit tests (mirrors test_agent_location_history.py's hand-rolled AsyncMock db)

components/
├── AgentList.tsx                  # MODIFIED — render vpn_heuristic badge on the agent card
├── SecuritySettingsDashboard.tsx  # NEW — geo-fence allowlist + detector toggles (clone of PrivacyDashboard.tsx's toggle section)
└── App.tsx / Sidebar.tsx          # MODIFIED — register + route to the new panel

types.ts                           # MODIFIED — GeoLocation gains vpn_heuristic?/asn? fields
services/apiService.ts             # MODIFIED — getGeoSecuritySettings/setGeoSecuritySettings functions (clone of getAgentLocationTracking/setAgentLocationTracking)
```

### Structure Rationale

- `agent_heartbeat_endpoints.py` is already at ~460+ lines (line 452+ already reached in the `runtime_security` block) — Phase 46 already had to split `agent_heartbeat_alerts_service.py` out to stay under the CLAUDE.md 500-line cap. Adding two multi-branch detectors inline would very likely breach the cap again; put the actual detector logic in a new `geo_security_service.py` sibling module and keep the heartbeat handler's addition to 2 short call-throughs (same pattern Phase 46 used for `record_location_change`).
- One new endpoint file, not folded into `agent_location_history_endpoints.py` — that file's own docstring states its scope is specifically the append-only history resource + its one toggle; the new resource (allowlist + 2 toggles) is a distinct settings surface per D-06.

### Pattern 1: Config lookup — tenant → global → default (clone target: `get_sla_at_risk_window`)

**What:** Per-tenant `system_settings` type-keyed doc, falling back to a global doc, falling back to a hardcoded default.
**When to use:** The new `allowed_country_codes` (list) + `impossible_travel_enabled`/`geo_fence_enabled` (bools) config.
**Example:**
```python
# Source: backend/compliance_remediation_sla_service.py (get_sla_at_risk_window),
# backend/agent_location_history_service.py (get_track_agent_location) — identical
# 3-step resolution order, generalized here for a settings doc with multiple fields.
async def get_geo_security_settings(db, tenant_id) -> dict:
    raw = db._db if hasattr(db, "_db") else db
    defaults = {
        "impossible_travel_enabled": True,
        "geo_fence_enabled": False,   # off by default — an empty allowlist would alert on every check-in
        "allowed_country_codes": [],
    }
    if tenant_id:
        doc = await raw.system_settings.find_one(
            {"type": "geo_security_detectors", "tenantId": tenant_id}
        )
        if doc:
            return {**defaults, **{k: v for k, v in doc.items() if k in defaults}}
    doc = await raw.system_settings.find_one(
        {"type": "geo_security_detectors", "tenantId": {"$exists": False}}
    )
    if doc:
        return {**defaults, **{k: v for k, v in doc.items() if k in defaults}}
    return defaults
```

### Pattern 2: Impossible-travel evaluation — raw previous heartbeat, not the debounced audit-trail state

**What:** Compare the just-resolved `geo` against `existing_agent.get("geo")` (the value written by the *previous* heartbeat, unconditionally, every beat) and `existing_agent.get("lastSeen")` (ISO string) — **not** `existing_agent.get("locationConfirmed")`.
**When to use:** Every heartbeat that has a public IP and resolves a geo, when the `impossible_travel_enabled` toggle is on.
**Why not `locationConfirmed`:** That shadow field only updates after Phase 46's 10-minute NAT-flip debounce confirms a candidate — it exists to solve *audit-trail noise*, a different problem. Using it here would mean a genuinely fast, malicious location jump might not even register as a comparison point until the (unrelated) debounce window elapses, defeating the point of "consecutive check-ins."
**Example:**
```python
# Source: haversine formula lifted verbatim from ueba_service.py::_haversine_km
# (already exists in this codebase for the login-impossible-travel UEBA rule);
# reused here unchanged, imported rather than re-copied.
from ueba_service import _haversine_km  # or promote to a shared util if planner prefers
from datetime import datetime

MAX_SPEED_KMH = 1000  # D-01 — fixed, not tenant-configurable in v3.3

def evaluate_impossible_travel(prev_geo, prev_last_seen_iso, curr_geo, now, prev_vpn, curr_vpn) -> bool:
    if not prev_geo or not curr_geo:
        return False  # first-ever check-in with geo — nothing to compare (Pitfall 3)
    if prev_geo.get("latitude") is None or curr_geo.get("latitude") is None:
        return False  # GeoIP resolved a record with no lat/long (rare, but observed possible)
    if prev_vpn is True or curr_vpn is True:
        return False  # D-02 — full suppression, either endpoint

    prev_dt = datetime.fromisoformat(prev_last_seen_iso.replace("Z", "+00:00"))
    elapsed_hours = (now - prev_dt).total_seconds() / 3600
    if elapsed_hours <= 0:
        return False  # clock skew / out-of-order heartbeat — never divide by zero or negative

    distance_km = _haversine_km(
        prev_geo["latitude"], prev_geo["longitude"],
        curr_geo["latitude"], curr_geo["longitude"],
    )
    return (distance_km / elapsed_hours) > MAX_SPEED_KMH
```

### Pattern 3: State-transition + cooldown dedup shadow field (models Phase 46's `record_location_change`, simplified)

**What:** A 2-state (clean/violating) + `lastAlertedAt` shadow field per violation type, stored directly on the `agents` doc.
**When to use:** Both GSEC-02 and GSEC-03, identically — one shared helper, parameterized by `violation_type`.
**Anti-pattern to avoid:** Do **not** port Phase 46's full 4-branch NAT-flip debounce machine (confirmed/pending candidates, dwell-time promotion) — that machine exists specifically to decide "is this new location real enough to write an immutable audit row," a fundamentally different question from "has this agent's violation state changed and is it outside its cooldown." Reusing the debounce machinery here would be over-engineering: GSEC-02/03 violations are evaluated fresh every heartbeat (cheap, pure boolean checks), so there is no analogous "candidate not yet confirmed" state to track.
**Example:**
```python
# Source: pattern shape modeled on agent_location_history_service.record_location_change's
# state-comparison style, deliberately simplified per the Anti-Pattern note above.
from datetime import datetime, timezone, timedelta

COOLDOWN_WINDOW = timedelta(hours=6)  # D-05 default; Claude's Discretion per CONTEXT.md

async def dedup_and_maybe_alert(raw, agent_id, existing_agent, violation_type: str, violating: bool) -> bool:
    """Returns True iff the caller should fire persist_security_alert now."""
    state = (existing_agent or {}).get("geoSecurityState", {}).get(violation_type, {})
    was_violating = state.get("violating", False)
    last_alerted = state.get("lastAlertedAt")
    now = datetime.now(timezone.utc)

    if not violating:
        if was_violating:
            await raw.agents.update_one(
                {"id": agent_id},
                {"$set": {f"geoSecurityState.{violation_type}.violating": False}},
            )
        return False

    should_fire = (not was_violating) or (
        last_alerted is None or (now - last_alerted) >= COOLDOWN_WINDOW
    )
    if should_fire:
        await raw.agents.update_one(
            {"id": agent_id},
            {"$set": {
                f"geoSecurityState.{violation_type}.violating": True,
                f"geoSecurityState.{violation_type}.lastAlertedAt": now,
            }},
        )
    return should_fire
```
See **Open Questions #1** — whether re-firing after the cooldown elapses on a *still-violating* agent is the intended behavior, or whether D-05 means strictly "one alert per transition, forever, until it clears" (this implementation does the former; flip the `should_fire` condition to drop the `last_alerted` re-check if the latter is confirmed).

### Anti-Patterns to Avoid
- **Building a second alert-persistence path:** the phase's own success criteria (CONTEXT.md `<domain>`) explicitly says "never a parallel alert channel." Fix and reuse `persist_security_alert`; do not write directly to `db.security_alerts` from the new detector module.
- **Re-copying the haversine formula:** `ueba_service._haversine_km` already exists and is correct; import it (or extract to a shared `geo_utils.py` if the planner prefers not to import a "private-feeling" underscore-free helper across modules — either is fine, just don't paste a second copy).
- **Treating `vpn_heuristic is None` as "not VPN" vs. treating it as a crash risk:** it is a real, valid third state (files not installed / toggle off) — must be handled with `is True` / falsy-safe checks, never `if not prev_vpn: suppress` (that would suppress on `None` too, silently changing D-02's semantics) nor a bare `prev_vpn == curr_vpn` boolean XOR that raises on `None`.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Great-circle distance | A new haversine implementation | `ueba_service._haversine_km` (import or extract to shared util) | Already written, already correct, in this exact codebase — zero reason to re-derive |
| Alert persistence + streaming + blockchain audit | A new insert/publish path in the new detector module | `ueba_service.persist_security_alert` (once fixed) | Explicit phase-scope requirement: "reusing the existing alert fan-out... never a parallel alert channel" |
| Per-tenant config resolution | A bespoke lookup | The `system_settings` type-keyed tenant→global→default pattern (`get_sla_at_risk_window`/`get_track_agent_location`) | Established, tested convention already used twice in this codebase for exactly this shape of config |
| Admin-role gating on settings PATCH | A new role-check helper | `_SETTINGS_ADMIN_ROLES`/`_require_admin` pattern from `agent_location_history_endpoints.py` | Identical requirement (admin-only mutation of a tenant setting), already implemented and tested |

**Key insight:** Every piece of this phase's backend surface has a working, already-shipped twin in this exact codebase from Phases 44-46. The only genuinely new logic is ~15 lines of pure boolean-returning functions (impossible-travel check, geo-fence check, dedup/cooldown check); everything else is disciplined cloning.

## Common Pitfalls

### Pitfall 1: `persist_security_alert` does not exist — the "existing alert fan-out" is currently broken
**What goes wrong:** `from ueba_service import persist_security_alert` raises `ImportError`. Confirmed live: `cd backend && venv/bin/python -c "from ueba_service import persist_security_alert"` → `ImportError: cannot import name 'persist_security_alert' from 'ueba_service'`.
**Why it happens:** `ueba_service.py` only defines a private `_persist_alert(db, alert_type, severity, title, description, metadata)` — a different name, never renamed/aliased to the public name five other call sites already assume exists.
**How to avoid:** As a Wave 0 / first-task fix, add `persist_security_alert = _persist_alert` (or rename the function and update its one internal call site at `ueba_service.py:231`) so the name importable elsewhere actually resolves. This is required for GSEC-02/03 to reuse the fan-out at all, and it is a genuine, in-scope bugfix (not scope creep) since it makes five pre-existing, silently-broken alert paths (`shadow_ai`, `ueba_anomaly`, `fim_violation`, `pii_detected`, `runtime_security`) start working too.
**Warning signs:** Any test that imports `persist_security_alert` from `ueba_service` and doesn't stub/patch it will fail at collection/import time until this is fixed.

### Pitfall 2: Confusing the two "previous location" state machines
**What goes wrong:** Using `existing_agent.get("locationConfirmed")` (Phase 46's debounced audit-trail state) as the "previous check-in" for impossible-travel math instead of `existing_agent.get("geo")` + `existing_agent.get("lastSeen")` (the raw prior heartbeat, updated every beat unconditionally).
**Why it happens:** Both live on the same `agents` doc and CONTEXT.md's canonical references point at `agent_location_history_service.py` as the model to follow, inviting the assumption that its state fields are the right input.
**How to avoid:** Use the raw fields. See Architecture Patterns → Pattern 2 above for the concrete reasoning and code.
**Warning signs:** Impossible-travel never fires (or fires only after a ~10-minute delay) even for an obviously fast fake location jump in a test.

### Pitfall 3: First-ever check-in / missing prior geo
**What goes wrong:** `existing_agent` is `None` (new agent registering) or has no `geo` field yet (its first heartbeat with a resolvable public IP) — computing elapsed time or distance against `None` raises or produces nonsense.
**Why it happens:** Same class of bug Phase 46's own state machine had to explicitly branch on ("no confirmed baseline exists yet").
**How to avoid:** Guard explicitly — `if not prev_geo or not curr_geo: return False` before any math (already reflected in the Pattern 2 code example).
**Warning signs:** A `TypeError`/`KeyError` on the very first heartbeat of any newly registered agent.

### Pitfall 4: GeoIP jitter at real heartbeat cadence produces false positives the VPN suppression doesn't cover
**What goes wrong:** The agent heartbeat interval is ~30-60s in this codebase (`backend/live_agent_daemon.py: HEARTBEAT_INTERVAL = 30`; agent-rust mirrors it). At 1000 km/h, the "false positive" distance floor for two *consecutive* heartbeats is only `1000 km/h × (30s/3600) ≈ 8.3 km`. Any CGNAT/mobile-carrier IP reassignment that flips the resolved city between two heartbeats — without the agent actually moving, and without the new IP happening to be in the VPN/hosting range list — can trivially exceed that floor and fire a false impossible-travel alert. D-02's VPN suppression only covers the *corporate-VPN* false-positive class explicitly named in CONTEXT.md; it does not cover CGNAT/mobile-carrier IP churn.
**Why it happens:** GeoIP city-level accuracy is commonly tens of km off, and IP reassignment on cellular/CGNAT networks can happen between two 30-second-apart requests without any physical movement.
**How to avoid:** Flagged as **Open Question #2** below rather than silently patched — the locked decision (D-01) is explicit about "two consecutive check-ins," so any additional floor/smoothing is a scope question for the user/planner, not a unilateral research decision.
**Warning signs:** Impossible-travel alerts clustering around agents on mobile/cellular or CGNAT'd networks with no VPN flag set.

### Pitfall 5: `vpn_heuristic` is a 3-valued signal (`True` / `False` / absent), not boolean
**What goes wrong:** Treating a missing/`None` `vpn_heuristic` (VPN range file not loaded, or `track_agent_location` toggle off so `asn_enrichment` was never computed) as equivalent to `False` in a way that changes suppression semantics, or crashing on `None` in a boolean comparison.
**Why it happens:** `agent_asn_service.lookup()` only sets `result["vpn_heuristic"]` when the X4BNet ranges file loaded successfully; if it's missing, the key is absent from the returned dict entirely (see `agent_asn_service.py::lookup`, lines 193-195).
**How to avoid:** Always check `is True` explicitly for suppression (`if prev_vpn is True or curr_vpn is True: return False`), never truthy/falsy coercion of `None`.
**Warning signs:** A unit test with `vpn_heuristic` omitted from a mocked geo dict silently changes detector behavior from the "flag present and False" case.

### Pitfall 6: GeoLite2-City.mmdb is NOT bundled in this repository
**What goes wrong:** Assuming `geoip_service.lookup()` will return real geo/country data in dev/test/CI. Verified: `backend/data/geoip/` does not exist in this checkout at all (only `backend/data/vpn_ranges/x4bnet_vpn_ipv4.txt` is present, 185KB). The `.mmdb` is licensed and must be supplied out-of-band per `geoip_service.py`'s own docstring.
**Why it happens:** MaxMind GeoLite2 requires a (free but registered) license; it's deliberately not committed to the repo.
**How to avoid:** All hermetic tests must `monkeypatch`/mock `geoip_service.lookup` and `agent_asn_service.lookup` return values directly (exactly as `test_agent_asn_service.py` already does) rather than depending on real `.mmdb` resolution. Do not write a GSEC-03 test that asserts a real country code resolves from a real IP without first confirming the `.mmdb` is present in the test environment.
**Warning signs:** A "smoke test" that calls `geoip_service.lookup("8.8.8.8")` and expects a non-`None` result will fail in this environment today.

### Pitfall 7: `security_alerts` alert docs have no top-level `tenantId` set by `_persist_alert` itself — but it doesn't matter, and don't "fix" it by hand
**What goes wrong:** `_persist_alert`'s alert dict only has `type/severity/title/description/metadata/created_at/status/timestamp` — no explicit `tenantId` key, unlike `agent_security_endpoints.py::_raise_malware_alert` which sets one explicitly. It would be tempting to "fix" this by adding an explicit `tenantId` field when reusing the function.
**Why it's actually fine:** `security_alerts` is **not** in `database.py`'s `TenantIsolatedDatabase` exemption list, so `TenantIsolatedCollection.insert_one()` auto-injects `document["tenantId"]` from the ambient `tenant_context.get_tenant_id()` contextvar on every call — and `verify_agent_key` (the heartbeat auth dependency) already calls `set_tenant_id(tenant["id"])` before the handler body runs. Tenant scoping happens transparently at the DB-wrapper layer; no extra code needed in the new detector module.
**How to avoid:** Don't add redundant manual `tenantId` assignment inside `persist_security_alert`'s call sites — it's already handled. (It's harmless if the planner adds it anyway for defense-in-depth, matching `_raise_malware_alert`'s belt-and-suspenders style, but it is not required.)
**Warning signs:** None operationally — this is here purely so the planner doesn't spend a task "fixing" something that already works.

## Code Examples

### Existing haversine (verbatim source to import/reuse)
```python
# Source: backend/ueba_service.py, lines 109-116 (already in this repo)
def _haversine_km(lat1, lon1, lat2, lon2) -> float:
    """Quick approximate distance between two lat/lon points."""
    import math
    R = 6371
    d_lat = math.radians(lat2 - lat1)
    d_lon = math.radians(lon2 - lon1)
    a = math.sin(d_lat / 2) ** 2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(d_lon / 2) ** 2
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
```

### Existing config-toggle GET/PATCH pair (exact clone target for D-06)
```python
# Source: backend/agent_location_history_endpoints.py, lines 92-129 (already in this repo)
# Clone this pair for GET/PATCH /api/settings/geo-security, swapping:
#   type: "track_agent_location" -> "geo_security_detectors"
#   body: AgentLocationTrackingUpdate(enabled: bool) -> a richer body with
#         impossible_travel_enabled/geo_fence_enabled/allowed_country_codes
```

### Existing amber "likely VPN/hosting" badge (exact clone target for GSEC-01 frontend)
```tsx
// Source: components/AgentLocationHistory.tsx, lines 132-137 (already in this repo)
{entry.vpn_heuristic === true && (
    <span className="ml-2 inline-flex items-center gap-1 bg-amber-100 text-amber-800 dark:bg-amber-900/50 dark:text-amber-300 text-[11px] font-semibold px-2 py-1 rounded-full uppercase tracking-wide">
        <WifiIcon size={10} />
        likely VPN/hosting
    </span>
)}
// GSEC-01 needs the identical badge added to components/AgentList.tsx's agent-card
// Location row (around line 221-229), driven by agent.geo?.vpn_heuristic === true,
// plus the corresponding vpn_heuristic?/asn? fields added to the GeoLocation
// interface in types.ts (currently missing them — see Phase Requirements table).
```

## State of the Art

Not applicable in the usual "library version drift" sense — no external libraries are involved. The one relevant "state of the art" fact is internal: this is the second time this codebase has needed a tenant-scoped `system_settings` toggle (`track_agent_location` was the first, Phase 46) and the third time it's needed the tenant→global→default resolution pattern (`get_sla_at_risk_window`, `get_track_agent_location`, now this phase) — treat that 3-step resolution as the established convention, not something to redesign.

**Deprecated/outdated:** N/A.

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | D-05's cooldown window re-fires an alert after 6h if the agent is *still* violating (rather than firing exactly once per transition, forever, until state clears) | Architecture Patterns → Pattern 3, Open Question #1 | If wrong, the implementation would need to drop the `last_alerted` re-check in `dedup_and_maybe_alert` — a small code change, but changes real alert-volume behavior in production, worth confirming before locking the plan. |
| A2 | Recommended dedup/cooldown storage (shadow field on `agents` doc, not a dedicated collection) is the right tradeoff | Standard Stack → Alternatives Considered | Low risk — CONTEXT.md explicitly leaves this to planner discretion; a dedicated collection is a straightforward, low-cost pivot if the planner wants independently queryable violation state (e.g., a fleet-wide "currently violating" admin view) |

**All claims above are grounded in direct reads of this repo's own source and one live Python execution** — none are external-library or ecosystem claims requiring `[ASSUMED]`/`[CITED]` tags; both entries above are marked because they involve interpreting an intentionally-ambiguous locked decision (D-05) or an explicitly-deferred-to-planner choice, not because the underlying facts are unverified.

## Open Questions (RESOLVED)

> Both resolved during `/gsd-plan-phase` and locked in CONTEXT.md: Q1 → **D-07** (re-fire after cooldown), Q2 → **D-08** (15-min elapsed floor). Implemented in 47-02.

1. **[RESOLVED — D-07: re-fire]** Does the 6h cooldown in D-05 re-fire on a still-violating agent, or is it strictly "one alert per transition, ever"?
   - What we know: D-05's wording ("fire one alert when the violation state changes... then suppress repeats within a cooldown window... even if every heartbeat keeps violating") clearly bounds noise *within* the cooldown window, modeled after Phase 46's state machine (which itself never "re-fires" for an unchanged confirmed state).
   - What's unclear: whether a violation that persists *past* 6 hours should produce a fresh reminder alert (Pattern 3's implementation above) or stay silent until the agent returns to a clean state and violates again.
   - Recommendation: Default to "re-fire after cooldown elapses if still violating" (implemented in Pattern 3) since it matches typical security-alerting UX (a week-long geo-fence violation shouldn't go completely silent after the first alert) — but flag for explicit user confirmation during `/gsd-plan-phase`'s own review, since it's a genuine behavioral choice, not purely an implementation detail.

2. **[RESOLVED — D-08: 15-min elapsed floor]** Should the ~1000 km/h "consecutive check-ins" comparison have any noise floor (minimum elapsed time or minimum distance) given the real ~30-60s heartbeat cadence documented in Pitfall 4?
   - What we know: At 30s intervals, the false-positive distance floor is ~8.3 km, well within normal GeoIP city-level imprecision and CGNAT/mobile-carrier IP churn — a class of false positive D-02's VPN suppression does not address.
   - What's unclear: whether the user wants this addressed now (e.g., a minimum elapsed-time floor before evaluating, or comparing against the last several beats' median location) or is comfortable accepting the noise for v3.3 given it's alert-only (D-04) with no blocking consequence.
   - Recommendation: Surface this explicitly during planning/discuss rather than silently adding an unrequested floor — D-01 is a locked decision and any floor is a modification to it that needs explicit sign-off.

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| `backend/data/vpn_ranges/x4bnet_vpn_ipv4.txt` (X4BNet VPN CIDR snapshot) | GSEC-01 vpn_heuristic flag, GSEC-02 D-02 suppression | ✓ | 185KB snapshot present in this checkout | — |
| `backend/data/geoip/GeoLite2-City.mmdb` | GSEC-03 country_code resolution, GSEC-02 lat/long resolution | ✗ | — (licensed, supplied out-of-band per `geoip_service.py` docstring) | Tests/dev must mock `geoip_service.lookup()`; no fallback for real geo resolution in this environment — this is a pre-existing, Phase-46-inherited gap, not new to this phase |
| `backend/data/geoip/GeoLite2-ASN.mmdb` | ASN org/number enrichment (not required by any GSEC-01/02/03 requirement — only `asn.org`/`asn.number` display fields) | ✗ | — | None needed — `vpn_heuristic` computation is independent of this file (driven solely by the X4BNet ranges file, which is present) |
| `backend/venv/bin/python` + pytest 9.1.1 | Running the phase's test suite | ✓ | pytest 9.1.1 confirmed installed | — |

**Missing dependencies with no fallback:**
- None blocking — the one missing file (GeoLite2-City.mmdb) only blocks *real* geo resolution, which hermetic tests must mock anyway (Pitfall 6); it does not block implementation or testing of this phase's detector logic.

**Missing dependencies with fallback:**
- GeoLite2-City.mmdb / GeoLite2-ASN.mmdb — mock `geoip_service.lookup`/`agent_asn_service.lookup` in all tests (established convention, see `test_agent_asn_service.py`).

## Validation Architecture

### Test Framework

| Property | Value |
|----------|-------|
| Framework | pytest, hermetic `unittest.mock`-based (direct precedent: `backend/tests/test_agent_location_history.py`'s hand-rolled `_mock_db()` + `AsyncMock`, `asyncio.run()` pattern) |
| Config file | `backend/pyproject.toml` |
| Quick run command | `backend/venv/bin/python -m pytest backend/tests/test_geo_security_service.py -q` |
| Full suite command | `backend/venv/bin/python -m pytest backend/tests/ -q` (per project memory: use `backend/venv/bin/python`, not system Python) |

### Phase Requirements → Test Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| — (prerequisite) | `persist_security_alert` is importable from `ueba_service` and calls through to the real alert-persist logic | unit | `pytest backend/tests/test_ueba_service.py -k persist_security_alert -x` | ❌ Wave 0 (new file, or add to existing ueba test file if one exists) |
| GSEC-01 | `GeoLocation` TS interface carries `vpn_heuristic`; `AgentList.tsx` renders the amber badge when true, nothing when false/absent | manual / visual (frontend, no existing TS test harness for this component) | Manual UAT: view an agent with `geo.vpn_heuristic=true` in the agent list | ❌ Wave 0 — manual-only, justified: no existing component-test harness for `AgentList.tsx` in this repo |
| GSEC-02 | Impossible-travel fires when distance/elapsed-time exceeds 1000 km/h between two raw consecutive check-ins | unit | `pytest backend/tests/test_geo_security_service.py -k impossible_travel_positive -x` | ❌ Wave 0 |
| GSEC-02 | Impossible-travel does NOT fire when either endpoint's `vpn_heuristic is True` (D-02) | unit | `pytest backend/tests/test_geo_security_service.py -k vpn_suppression -x` | ❌ Wave 0 |
| GSEC-02 | Impossible-travel does NOT fire on an agent's first-ever check-in (no prior geo) | unit | `pytest backend/tests/test_geo_security_service.py -k first_checkin -x` | ❌ Wave 0 |
| GSEC-02 | `vpn_heuristic` absent/`None` on either side does NOT suppress (only `True` suppresses) | unit | `pytest backend/tests/test_geo_security_service.py -k vpn_none_handling -x` | ❌ Wave 0 |
| GSEC-03 | Geo-fence fires when `country_code` is not in the tenant's `allowed_country_codes` allowlist | unit | `pytest backend/tests/test_geo_security_service.py -k geo_fence_violation -x` | ❌ Wave 0 |
| GSEC-03 | Geo-fence does NOT fire when `country_code` is in the allowlist, or when the detector is toggled off | unit | `pytest backend/tests/test_geo_security_service.py -k geo_fence_clean -x` | ❌ Wave 0 |
| GSEC-02 + GSEC-03 | Dedup: only one alert fires on the clean→violating transition; repeated violating heartbeats within 6h do not re-fire | unit | `pytest backend/tests/test_geo_security_service.py -k dedup_cooldown -x` | ❌ Wave 0 |
| GSEC-02 + GSEC-03 | Config resolution: tenant doc → global doc → hardcoded default, matching `get_sla_at_risk_window`'s contract | unit | `pytest backend/tests/test_geo_security_service.py -k config_resolution -x` | ❌ Wave 0 |
| D-06 | Admin-only PATCH on `/api/settings/geo-security`; non-admin gets 403 | unit | `pytest backend/tests/test_geo_security_endpoints.py -k admin_gate -x` | ❌ Wave 0 |

### Sampling Rate
- **Per task commit:** `backend/venv/bin/python -m pytest backend/tests/test_geo_security_service.py backend/tests/test_geo_security_endpoints.py -q`
- **Per wave merge:** `backend/venv/bin/python -m pytest backend/tests/ -q`
- **Phase gate:** Full suite green before `/gsd-verify-work`; per project memory, the last known-good baseline is **1343 pass / 3 pre-existing fails** (e2e evidence, rust parity, agentic tool_choice) — confirm no *new* failures beyond that baseline, not a byte-identical count. Fixing Pitfall 1 (`persist_security_alert`) may cause previously-silent code paths to start actually inserting into `security_alerts`/publishing to the streaming broker — watch for any existing test that asserted "no alert written" for shadow_ai/fim/pii/runtime_security scenarios purely because the import was silently failing; such a test would need updating, not reverting the fix.

### Wave 0 Gaps
- [ ] `backend/tests/test_geo_security_service.py` — covers impossible-travel, geo-fence, dedup/cooldown, config resolution (new file)
- [ ] `backend/tests/test_geo_security_endpoints.py` — covers admin-gated GET/PATCH (new file)
- [ ] A test asserting `ueba_service.persist_security_alert` is importable and functionally equivalent to `_persist_alert` (new test, or extend an existing `ueba_service` test file if the planner finds one during execution — none was found in this research pass)
- [ ] Framework install: none — pytest already available in `backend/venv`

## Security Domain

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | yes (indirect) | Existing `verify_agent_key` (heartbeat) / `get_current_user` (settings endpoints) dependencies, unchanged by this phase |
| V4 Access Control | yes | New GET/PATCH `/api/settings/geo-security` must reuse `_SETTINGS_ADMIN_ROLES`/`_require_admin` gating verbatim from `agent_location_history_endpoints.py`; tenant scoping on the config doc itself relies on the same `system_settings` tenant/global pattern already proven in Phase 46 |
| V5 Input Validation | yes | `allowed_country_codes` must be validated as a list of 2-letter uppercase ISO 3166 alpha-2 strings via Pydantic (e.g., `constr(pattern=r"^[A-Z]{2}$")` list) at the PATCH boundary — reject malformed codes rather than silently storing garbage that then never matches any real `country_code` |
| V6 Cryptography | no | No new cryptographic material in this phase |
| V13 API / Business Logic | yes | The impossible-travel/geo-fence checks are business-logic gates on an already-authenticated agent-telemetry path; ensure the new detector functions are pure (no side effects beyond the documented shadow-field write + alert call) so they can't be abused to force spurious writes via crafted heartbeat payloads (e.g., a malicious/compromised agent claiming an arbitrary `publicIp` in its payload — note this is a **pre-existing** trust boundary: `agent_heartbeat_endpoints.py` already trusts `payload.get("publicIp")` from the agent without independent verification against the actual TCP peer IP; this phase does not change that trust boundary, but a detector consuming attacker-controlled `publicIp` values means a compromised/malicious agent could spoof its own reported location to *either* trigger nuisance alerts against itself or spoof a "safe" country/IP to evade the geo-fence — worth noting to the user as a residual limitation of IP-self-reported geo, consistent with the milestone's own "Out of Scope: Real-time GPS / precise device location" framing in REQUIREMENTS.md) |

### Known Threat Patterns for this stack

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| Cross-tenant read/write of another tenant's `geo_security_detectors` config via a crafted request | Information Disclosure / Tampering | `TenantIsolatedCollection` auto-injection (already proven for `system_settings` via Phase 46's identical pattern) + explicit `tenant_id` scoping in the GET/PATCH handlers, cloned from `agent_location_history_endpoints.py` |
| Malicious/compromised agent spoofing its own `publicIp` in the heartbeat payload to evade the geo-fence or force nuisance impossible-travel alerts against itself | Spoofing | Pre-existing trust boundary (agent-self-reported IP), unchanged by this phase — documented above as a residual limitation, not newly introduced |
| A silently-broken alert path (Pitfall 1's `persist_security_alert` ImportError) being "fixed" in a way that re-introduces the same bug under a different name in the new detector module | Repudiation (alerts silently never fire) | Add the explicit importability/functional-equivalence test listed in Wave 0 Gaps so a regression is caught by CI, not discovered by absence of alerts in production |

## Sources

### Primary (HIGH confidence — direct file reads + one live execution, this repo)
- `backend/ueba_service.py` — read in full (572 lines); `_persist_alert` signature, `_haversine_km`, alert-type taxonomy (`_RULES` dict), `_UEBA_SUPER_ROLES`
- `backend/agent_heartbeat_endpoints.py` — read lines 1-200 and 320-460; heartbeat handler flow, `existing_agent` fetch order, `persist_security_alert` call sites (all 3 in this file)
- `backend/agent_heartbeat_alerts_service.py` — read in full; `persist_pii_scanner`'s identical `persist_security_alert` call pattern
- `backend/agent_location_history_service.py` — read in full (205 lines); `record_location_change`'s 4-branch state machine, `get_track_agent_location`'s config-resolution pattern
- `backend/agent_location_history_endpoints.py` — read in full; admin-gated GET/PATCH toggle pattern to clone
- `backend/agent_asn_service.py` — read in full (198 lines); `vpn_heuristic` computation independent of the ASN reader, 3-valued nature of the flag
- `backend/geoip_service.py` — read in full (106 lines); `country_code`/lat-long resolution, ungated by the `track_agent_location` toggle
- `backend/database.py` — read lines 1-170; `TenantIsolatedCollection`/`TenantIsolatedDatabase`, exemption list confirming `security_alerts`/`system_settings` are NOT exempt (auto-tenant-scoped)
- `backend/tenant_context.py` — read in full; contextvar-based tenant scoping, confirming `set_tenant_id` in `verify_agent_key` covers the heartbeat path
- `backend/compliance_remediation_sla_service.py` — grep + partial read; `get_sla_at_risk_window`'s config-resolution pattern (second precedent for the same convention)
- `backend/agent_security_endpoints.py` / `backend/mitre_service.py` / `backend/ticketing_endpoints.py` — grepped; confirmed `security_alerts` is the real, actively-read collection (not `db.alerts`, which `ueba_service.get_ueba_alerts` reads from — an unrelated, pre-existing minor inconsistency, out of scope for this phase)
- `components/AgentLocationHistory.tsx` — read in full; exact amber badge markup to clone
- `components/AgentList.tsx` — grepped/read relevant section; confirmed the badge is NOT yet rendered on the live agent card
- `components/PrivacyDashboard.tsx` — read lines 1-100; toggle-panel pattern to clone for the new Security settings panel
- `types.ts` — read `Agent`/`GeoLocation` interfaces; confirmed `vpn_heuristic`/`asn` are missing from `GeoLocation`
- `services/apiService.ts` — read lines 4600-4660; `LocationHistoryEntry`, `getAgentLocationTracking`/`setAgentLocationTracking` exact functions to clone
- `backend/tests/test_agent_location_history.py` / `backend/tests/test_agent_asn_service.py` — read/grepped; hermetic test conventions (hand-rolled `_mock_db()`, `monkeypatch` for env vars and module internals)
- `backend/live_agent_daemon.py` — grepped; confirmed 30s heartbeat interval (Pitfall 4's basis)
- `.planning/phases/46-public-ip-asn-vpn-enrichment-location-history-audit/46-RESEARCH.md` — read structure/format precedent for this document
- Live execution: `cd backend && venv/bin/python -c "from ueba_service import persist_security_alert"` → confirmed `ImportError` (Pitfall 1's evidence)
- `ls backend/data/geoip/ backend/data/vpn_ranges/` — confirmed GeoLite2 `.mmdb` files absent, X4BNet snapshot present (Environment Availability)

### Secondary (MEDIUM confidence)
None — no external documentation lookups were needed for this phase; every question was answerable by reading this repo's own code directly, since GSEC-01/02/03 build entirely on Phase 46's already-implemented enrichment.

### Tertiary (LOW confidence)
None.

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — no new packages; stdlib usage confirmed against an existing, working in-repo example
- Architecture: HIGH — every integration point (heartbeat handler order of operations, config pattern, alert fan-out, badge convention) read directly from source, not inferred from documentation
- Pitfalls: HIGH for Pitfalls 1, 3, 5, 6, 7 (all directly verified by reading code or live execution); MEDIUM for Pitfall 2 (a design recommendation, not a bug, though grounded in reading both state machines fully) and Pitfall 4 (a real numeric consequence of documented heartbeat cadence, but its practical severity in production traffic patterns is not something this research could measure)

**Research date:** 2026-07-29
**Valid until:** 2026-08-29 (30 days — stable internal codebase, no external dependency drift risk; re-verify `persist_security_alert`'s fix status if this phase is delayed and another phase touches `ueba_service.py` in the interim)
