# Architecture Research — v3.3 Integration

**Domain:** Multi-tenant security/compliance portal (FastAPI + Motor/MongoDB + React/TS) — integrating agent geo & fleet observability into existing architecture
**Researched:** 2026-07-29
**Confidence:** HIGH (grounded directly in the current codebase for all internal-integration claims — every claim is sourced from files read in this repo); MEDIUM only on the fleet-map rendering-library recommendation, which also relies on one external web search (cited below).

## Scope note

This is a subsequent-milestone integration study, not greenfield architecture research. The "standard architecture" (FastAPI + Motor/MongoDB + tenant-isolation wrapper + router-registry + WebSocket + React skeleton) already exists and is not re-litigated. Everything below answers one question: **how do the four v3.3 feature areas — GeoIP/ASN enrichment, location-history audit, location-based security detection, fleet observability/uptime, and a fleet geo map — attach to that existing skeleton**, file by file.

---

## System Overview (new touchpoints only)

```
┌───────────────────────────────────────────────────────────────────────────┐
│  AGENT (Python + Rust)                                                     │
│  register / heartbeat POST { publicIp, meta.current_cpu/memory, ... }     │
└───────────────────────────────────┬───────────────────────────────────────┘
                                     │
┌────────────────────────────────────▼──────────────────────────────────────┐
│  backend/agent_registry_endpoints.py  &  agent_heartbeat_endpoints.py      │
│  (MODIFY — geo-change detection + location-history write slot in here,    │
│   at the exact line geoip_service.lookup() already runs)                  │
├─────────────────────────────────────────────────────────────────────────┤
│  geoip_service.lookup(publicIp)   [EXISTING — unmodified]                 │
│  agent_asn_service.lookup(ip)     [NEW — sibling module, same lazy-mmdb   │
│                                     pattern, for ASN/hosting/VPN flag]     │
│  agent_impossible_travel.py       [NEW — cloned haversine/window pattern  │
│                                     from ueba_service._haversine_km /      │
│                                     itdr_service.IMPOSSIBLE_TRAVEL_HOURS]  │
├─────────────────────────────────────────────────────────────────────────┤
│  Mongo collections (Motor, tenant-isolated via TenantIsolatedDatabase):    │
│  agents                  (EXISTING — publicIp/geo already persisted)      │
│  agent_metrics_history    (EXISTING — capped ring buffer, precedent only)  │
│  agent_location_history   (NEW — append-only, clone remediation_escalations)│
│  agent_uptime_daily       (NEW — daily rollup, written by new scheduler)   │
│  geo_fence_policies       (NEW — per-tenant allowed-region policy)         │
├─────────────────────────────────────────────────────────────────────────┤
│  Background schedulers (registered in backend/app_startup.py):            │
│  monitor_agent_status()             [EXISTING — Online→Offline @ 5 min]   │
│  start_remediation_sla_scheduler()  [EXISTING — pattern to clone]         │
│  agent_uptime_rollup_loop()          [NEW — clone SLA-sweep shape, hourly] │
├─────────────────────────────────────────────────────────────────────────┤
│  Alerting fan-out (all EXISTING, reused not duplicated):                  │
│  websocket_manager.broadcast_agent_status_change / broadcast_security_event│
│  notification_manager.send_notification("agent.offline" | new event types)│
│  notification_service.get_notification_service(db).send_alert(...)        │
├─────────────────────────────────────────────────────────────────────────┤
│  New read endpoints:                                                       │
│  GET /api/agents/{id}/location-history   [NEW]                            │
│  GET /api/agents/fleet-map                [NEW — clustered geo points]     │
│  GET /api/agents/{id}/uptime              [NEW]                            │
├─────────────────────────────────────────────────────────────────────────┤
│  Frontend (React/Vite/Tailwind):                                          │
│  FleetGeoMap.tsx          [NEW — react-simple-maps + bundled TopoJSON]     │
│  AgentLocationHistory.tsx  [NEW — timeline panel inside AgentDetailModal]  │
│  AgentsDashboard.tsx / AgentList.tsx [MODIFY — offline/version-drift       │
│                              badges, "view on map" link]                  │
│  App.tsx / Sidebar.tsx    [MODIFY — new `fleetMap` view + permission;     │
│                              `geographicMap`/`view:geographic_map` already │
│                              exist but point at the unrelated SIEM         │
│                              GeographicAttackMap — do not collide/reuse]   │
└─────────────────────────────────────────────────────────────────────────┘
```

## Component Responsibilities (new/modified only)

| Component | Responsibility | Typical Implementation |
|-----------|----------------|------------------------|
| `geoip_service.lookup()` | Resolve public IP → country/city/lat/lon, offline via bundled `.mmdb` | Already exists, unmodified; called synchronously inline in the request handler |
| `agent_registry_endpoints.py` / `agent_heartbeat_endpoints.py` | Detect geo change per beat, write `agent_location_history`, invoke impossible-travel check | Modify existing handlers at the exact line where `geo = geoip_service.lookup(public_ip)` already runs |
| `agent_location_history` collection | Immutable per-agent geo/IP change audit trail | New collection, append-only inserts only, no updates/deletes — clone `remediation_escalations` shape |
| `agent_uptime_daily` collection | Per-agent daily online-seconds rollup for uptime %, chart-ready | New collection, one upsert per agent per UTC day from the new rollup scheduler |
| `monitor_agent_status()` | Flip Online→Offline after 5 min silence; already broadcasts + notifies | Existing 30-second loop in `app_background_tasks.py` — extend in place, don't clone |
| `agent_uptime_rollup_loop()` (new) | Periodic sweep converting agent status samples into daily uptime rollups | New scheduler, cloned structurally from `compliance_remediation_sla_service.start_remediation_sla_scheduler` (raw-db param, `while True: ...; asyncio.sleep(N)`) |
| `agent_impossible_travel.py` (new module) | Pure function: given two consecutive `(geo, timestamp)` pairs for one agent, decide impossible-travel | Cloned algorithm shape from `ueba_service._haversine_km` + `itdr_service.IMPOSSIBLE_TRAVEL_HOURS`, but keyed by `agentId`, not `email`/`user_id` |
| Fleet map endpoint | Tenant-scoped, projection-safe aggregation of current agent geo points, server-side clustered | New `GET /api/agents/fleet-map`, in a new or existing agent-facing endpoints module |
| `FleetGeoMap.tsx` | Renders agent markers on a bundled, tile-free world map | `react-simple-maps` + `world-atlas` TopoJSON (110m resolution, ~50–100 KB), no external tile server — verified pattern (see Sources) |

## Recommended Project Structure (new/modified files)

```
backend/
├── agent_registry_endpoints.py         # MODIFY — geo-change detect on register
├── agent_heartbeat_endpoints.py        # MODIFY — geo-change detect on heartbeat
├── agent_location_history_service.py   # NEW — change-detection + append-only write, shared by both endpoints above
├── agent_impossible_travel.py          # NEW — pure haversine/window detector, agent-scoped
├── agent_geo_fence_service.py          # NEW — per-tenant allowed-region policy check
├── agent_asn_service.py                # NEW — ASN/hosting/VPN lookup, same lazy-mmdb-reader shape as geoip_service.py
├── agent_uptime_service.py             # NEW — rollup computation + GET /uptime read path
├── agent_fleet_map_endpoints.py         # NEW — GET /api/agents/fleet-map (or fold into agent_metrics_endpoints.py)
├── app_background_tasks.py             # MODIFY — extend monitor_agent_status; add agent_uptime_rollup_loop
├── app_startup.py                      # MODIFY — register the one new scheduler (clone existing try/except block)
├── database.py                         # MODIFY — add indexes for agent_location_history, agent_uptime_daily
└── router_registry.py                  # MODIFY — one _load() line per new endpoints module

components/
├── FleetGeoMap.tsx                     # NEW — map + clustering + tenant/status filter
├── AgentLocationHistory.tsx            # NEW — per-agent timeline, surfaced inside AgentDetailModal.tsx
├── AgentDetailModal.tsx                # MODIFY — add location-history + uptime tabs
├── AgentsDashboard.tsx / AgentList.tsx  # MODIFY — offline badge, version-drift badge, "view on map" link
├── Sidebar.tsx                         # MODIFY — new nav entry for the fleet map (new permission — do not reuse view:geographic_map)
└── App.tsx                             # MODIFY — new view route + Suspense/ErrorBoundary wrapper (mirror geographicMap's existing pattern)
```

### Structure Rationale

- **One new service module per concern** (`agent_location_history_service.py`, `agent_impossible_travel.py`, `agent_asn_service.py`, `agent_uptime_service.py`) rather than piling logic into the already-large heartbeat/registry endpoint files — mirrors how `compliance_remediation_sla_service.py` was split out from `compliance_remediation_endpoints.py`, and keeps each file under this project's 500-line cap.
- **Endpoint modules stay thin call-throughs** into the service modules, consistent with the rest of the codebase (`compliance_remediation_sla_endpoints.py` → `compliance_remediation_sla_service.py`).
- **Frontend: extend `AgentDetailModal.tsx` rather than a new page** for location history/uptime — it's per-agent drill-down data, same shape as the existing metrics-history UI; only the fleet map is a new top-level view because it's fleet-wide, not per-agent.

## Architectural Patterns

### Pattern 1: Inline enrichment at register/heartbeat (not a separate enrichment pass)

**What:** GeoIP lookup already happens synchronously inside `report_heartbeat()` / agent registration, right where `publicIp` is extracted from the payload (`backend/agent_heartbeat_endpoints.py:118-124`, mirrored in `agent_registry_endpoints.py:81-87`). ASN/VPN/hosting-provider flagging should slot into that exact same block, not a separate batch job.
**When to use:** Any per-request enrichment that is (a) cheap — a local `.mmdb`/ASN-db lookup, no network call — and (b) needed immediately for the write that follows (geo-change diff, impossible-travel check).
**Trade-offs:** A separate async enrichment pass would decouple latency but introduce a second source of truth and a race between "agent doc written" and "enrichment applied" — unnecessary here since the lookup is already local and sub-millisecond, exactly like `geoip_service.lookup()` today. Keep it inline.

**Example (extending the existing heartbeat block):**
```python
public_ip = payload.get("publicIp") or (payload.get("meta") or {}).get("public_ip")
geo = None
if public_ip:
    update_data["publicIp"] = public_ip
    geo = geoip_service.lookup(public_ip)
    if geo:
        update_data["geo"] = geo
    # NEW: ASN/hosting/VPN flag — same local-db pattern as geoip_service
    asn_info = agent_asn_service.lookup(public_ip)  # new sibling module, same lazy-mmdb-reader shape
    if asn_info:
        update_data["network"] = asn_info  # {"asn": ..., "org": ..., "is_hosting": bool, "is_vpn": bool}
```

### Pattern 2: Cheap geo-change detection to avoid write amplification

**What:** Every heartbeat re-resolves `geo` from `publicIp`, but most beats have the same IP as last time. Compare against the *previously stored* `agents.publicIp` — already fetched a few lines above the geo block via `existing_agent = await db.agents.find_one(...)` — before writing to `agent_location_history`. Only write an audit row when `publicIp` actually changed (plain string compare); do not re-derive/compare geo distance for the gate, since IP-string-equality is the cheap, sufficient signal (a static `.mmdb` maps the same IP to the same geo every time).
**When to use:** Any append-only audit trail fed by a high-frequency heartbeat (60/min, rate-limited via `agent_limiter.limit("60/minute")`).
**Trade-offs:** IP-equality is coarser than geo-equality (a NAT pool rotating IPs within the same city would over-trigger), but it's an O(1) string compare against data already in hand — `existing_agent` is already fetched — versus a geo-field deep-compare that costs the same anyway since geo is derived 1:1 from IP. Accept the coarser signal; flag NAT-pool noise as a phase-specific tuning item if it shows up in practice (e.g., dedup within a rolling window instead of every distinct IP).

**Example:**
```python
prior_ip = existing_agent.get("publicIp") if existing_agent else None
if public_ip and geo and public_ip != prior_ip:
    await agent_location_history_service.record_change(
        db, agent_id=agent_id, tenant_id=_hb_tenant_id,
        old_ip=prior_ip, old_geo=existing_agent.get("geo") if existing_agent else None,
        new_ip=public_ip, new_geo=geo,
    )
    # impossible-travel check only runs on an actual change, not every beat
    await agent_impossible_travel.check(db, agent_id, tenant_id=_hb_tenant_id, new_geo=geo, at=datetime.now(timezone.utc))
```

### Pattern 3: Append-only audit collection (clone `remediation_escalations`)

**What:** `remediation_escalations` is written only via `insert_one` inside `run_sla_pass` (`compliance_remediation_sla_service.py`), never updated or deleted, and queried by `task_id`/`tenantId`. `agent_location_history` should follow the identical shape: `insert_one` only, indexed `[("agent_id", 1), ("timestamp", -1)]` plus `[("tenantId", 1), ("timestamp", -1)]`, fields `{agent_id, tenantId, old_ip, old_geo, new_ip, new_geo, distance_km, timestamp}`.
**When to use:** Any compliance/security-relevant trail where later mutation would undermine the audit guarantee — this is exactly that case (location history is the evidence trail for impossible-travel investigations).
**Trade-offs:** Unbounded growth like `remediation_escalations` (no TTL) is appropriate for a security audit trail, but unlike `agent_metrics_history` (capped at 100 docs/agent) or `agent_telemetry` (30-day TTL index via `database.py`), this collection should **not** get an `expireAfterSeconds` TTL index by default — location history is exactly the kind of record retention/compliance auditors ask for. Confirm retention with the existing `retention_endpoints`/`retention_tiers_endpoints` module rather than hardcoding a TTL.

### Pattern 4: Clone the existing scheduler shape, don't invent a new one

**What:** Every periodic background job in this codebase follows the same three-part shape: (1) a pure `async def run_X_pass(db)` doing one sweep, non-fatal top-level try/except, raw `db` param never resolved internally; (2) `async def start_X_scheduler(db): while True: await run_X_pass(db); await asyncio.sleep(N)`; (3) one `try/except` block added to `run_startup_services()` in `app_startup.py` that imports and `asyncio.create_task(...)`s it, passing the *raw* `mongodb.db` (imported as `from database import mongodb as _mdb`), never the tenant-wrapped `get_database()`. See `compliance_remediation_sla_service.py` / `ticketing_bridge.py` for the canonical example — both explicitly document this "never resolve your own db handle in a background sweep" rule.
**When to use:** The new `agent_uptime_rollup_loop`.
**Trade-offs:** None — this is a strict "don't reinvent" case; the existing pattern already solves tenant-context-free background execution correctly (explicit `tenantId` read from each doc, never ambient `tenant_context`).

**Example:**
```python
# backend/agent_uptime_service.py
async def run_uptime_rollup_pass(db) -> None:
    try:
        now = datetime.now(timezone.utc)
        day_key = now.strftime("%Y-%m-%d")
        async for agent in db.agents.find({}, {"_id": 0, "id": 1, "tenantId": 1, "status": 1}):
            tenant_id = agent.get("tenantId")
            if not tenant_id:
                continue
            await db.agent_uptime_daily.update_one(
                {"agent_id": agent["id"], "day": day_key},
                {"$inc": {"online_samples": 1 if agent.get("status") == "Online" else 0,
                          "total_samples": 1},
                 "$set": {"tenantId": tenant_id}},
                upsert=True,
            )
    except Exception as e:
        logger.error("[Uptime] Rollup pass error: %s", e)

async def start_uptime_rollup_scheduler(db) -> None:
    logger.info("Agent uptime rollup scheduler started (interval=3600s)")
    while True:
        await run_uptime_rollup_pass(db)
        await asyncio.sleep(3600)
```

```python
# backend/app_startup.py — add alongside the existing scheduler block
try:
    from agent_uptime_service import start_uptime_rollup_scheduler
    from database import mongodb as _mdb
    asyncio.create_task(start_uptime_rollup_scheduler(_mdb.db))
    logger.info("[Fleet] Uptime rollup scheduler started")
except Exception as _e:
    logger.warning("[Fleet] Uptime rollup scheduler failed to start: %s", _e)
```

## Data Flow

### Request Flow — heartbeat → geo → history → detection → alert

```
Agent heartbeat POST /api/agents/{id}/heartbeat
    ↓
report_heartbeat() — existing_agent fetched, geo = geoip_service.lookup(publicIp)
    ↓
[NEW] compare public_ip vs existing_agent.publicIp
    ↓ (changed)                                    ↓ (unchanged)
agent_location_history_service.record_change()      no-op — no extra write
    ↓
agent_impossible_travel.check(prev_geo, new_geo, dt)
    ↓ (flagged)
websocket_manager.broadcast_security_event() + notification_manager.send_notification("agent.geo_anomaly", ...)
    ↓
Frontend: notification bell (existing) + AgentLocationHistory.tsx timeline (new) refresh via socketService (existing)
```

### Fleet Map Read Flow

```
FleetGeoMap.tsx mount
    ↓
GET /api/agents/fleet-map?tenantId=&status=  (tenant-scoped via get_current_user, same auth dependency as agent_metrics_endpoints.py)
    ↓
Aggregation: db.agents.find({...tenant filter...}, {"_id":0,"id":1,"hostname":1,"geo":1,"status":1,"tenantId":1})
    ↓ (server-side clustering: round lat/lon to ~1 decimal, group + count)
JSON: [{lat, lon, count, city, country, status_breakdown}]
    ↓
react-simple-maps renders markers against bundled TopoJSON — no tile-server round-trip
```

### Key Data Flows

1. **Geo enrichment** stays exactly where it is today (inline in register/heartbeat) — the only new work is a cheap before/after diff and a conditional audit write, not a new pipeline stage.
2. **Detection**: two independent detectors coexist by design. The existing user-login impossible-travel logic (`ueba_service.analyze_login()`, `itdr_service.on_login_success()`, both keyed by `email`/`user_id`, both writing to `login_events`/`itdr_login_events`) is untouched. A new agent-scoped detector (`agent_impossible_travel.py`, keyed by `agent_id`) is added alongside it, reusing the same haversine math and the same alert fan-out (`websocket_manager`, `notification_manager`) so operators see both in one alerting surface without the two entity types (users vs. endpoints) being conflated in one collection.
3. **Alerting fan-out**: every new alert (impossible travel, offline, geo-fence violation) goes through the existing `notification_manager.send_notification(event_type, payload, tenant_id)` + `websocket_manager.broadcast_*` combo — no new notification transport is introduced.

## Scaling Considerations

| Scale | Architecture Adjustments |
|-------|--------------------------|
| Small fleet (≤500 agents/tenant) | Everything above works unmodified: a raw `find()` over `agents` for the fleet-map endpoint and the uptime rollup's per-agent loop are both fine at this size. |
| Medium fleet (500–5,000 agents/tenant) | Add a `[("tenantId",1),("geo.country_code",1)]` index on `agents` for the fleet-map query; server-side clustering (round-lat/lon groupby) becomes necessary rather than optional — return clusters, not raw points, once markers exceed a few hundred. |
| Large fleet (5,000+ agents/tenant, or many tenants) | Rework the uptime rollup sweep from a Python per-agent loop to a Mongo `$group` aggregation pipeline; consider a bounded retention window (e.g., 13 months) for `agent_uptime_daily` — kept separate from the *never-expiring* `agent_location_history` audit trail. |

### Scaling Priorities

1. **First bottleneck:** the per-agent Python loop in `run_uptime_rollup_pass` (`async for agent in db.agents.find(...)`) — fine at hundreds of agents, becomes the first thing to convert to a Mongo aggregation pipeline as fleets grow.
2. **Second bottleneck:** `agent_location_history` unbounded growth for very churny agent populations (e.g., laptops roaming daily) — mitigated first by the change-detection dedup in Pattern 2 (already prevents most write amplification) before reaching for a TTL, since this is an audit trail and shouldn't silently expire.

## Anti-Patterns

### Anti-Pattern 1: Building a second, parallel impossible-travel rule inside `siem_rules`

**What people do:** Add a new row to the `siem_rules` seed catalog (`backend/siem_endpoints.py:_SEED_RULES`) named "Agent Impossible Travel" and expect it to "just work" because a rule with that name already exists ("Impossible Travel — Simultaneous Login from Two Geographies").
**Why it's wrong:** `siem_rules` in this codebase is a **catalog of rule *descriptions*** (severity/description/remediation text shown in the UI), seeded once at startup — it is not a live execution engine wired to agent heartbeats. The actual executable impossible-travel logic lives in `ueba_service.analyze_login()` and `itdr_service.on_login_success()`, both scoped to **user login events** (`email`/`user_id`, `login_events`/`itdr_login_events` collections), not agents. Writing a catalog row with no executor behind it produces a UI entry that never fires. Likewise, `insider_threat_service.RISK_INDICATORS`'s `vpn_geo_anomaly` entry is a static weight used only by `seed_demo_data()` — there is no live indicator-evaluation pipeline to "integrate" with either.
**Do this instead:** Write a real, small, agent-scoped detector module (`agent_impossible_travel.py`) that reuses the haversine/time-window *algorithm* already proven in `ueba_service._haversine_km` and `itdr_service.IMPOSSIBLE_TRAVEL_HOURS`, but key it by `agent_id` and feed it from the heartbeat handler. Optionally add one `siem_rules` catalog entry purely for UI/severity-labeling consistency with the existing "Impossible Travel" rule card, but the detection itself must be code, not a seeded document.

### Anti-Pattern 2: Forcing agent geo events into `login_events` / `itdr_login_events`

**What people do:** Insert a synthetic "login" document into `login_events` for every agent heartbeat so the existing UEBA/ITDR pipelines "automatically" pick it up.
**Why it's wrong:** Those collections are semantically user-authentication events (`user_id`, `login_success`) consumed by RBAC/session-risk features elsewhere; conflating an endpoint's public-IP change with a "login" corrupts that semantics and risk-scores real users based on their fleet's roaming, not their own behavior.
**Do this instead:** Keep `agent_location_history` a distinct, agent-keyed collection; share only the *alerting mechanism* (`notification_manager`/`websocket_manager`), not the *event collection*, with the user-login detectors.

### Anti-Pattern 3: Building a tile-serving map stack for an air-gapped deployment

**What people do:** Reach for Leaflet/Mapbox GL with an OSM/Mapbox tile URL because that's the default tutorial setup.
**Why it's wrong:** Tile servers require outbound internet access at render time; this platform explicitly ships to air-gapped environments (the same constraint `geoip_service.py` already solves by bundling a local `.mmdb` instead of calling a geo API). A tile-based map silently breaks (blank grey map) offline.
**Do this instead:** `react-simple-maps` + a bundled `world-atlas` TopoJSON asset (~50–100 KB, checked into the frontend bundle, no network fetch) renders an SVG world outline and plots lat/lon markers with zero external calls — the same "ship the reference data locally" philosophy as `geoip_service.py`'s `.mmdb`. This is also consistent with the codebase's own precedent: `GeographicAttackMap.tsx` (the existing SIEM threat-origin view, reachable today via the `geographicMap` nav item) already avoids any cartographic tile dependency by using a country-list/heatmap-bar visualization instead of markers-on-a-map — confirming "no external map tiles, ever" is an established constraint here, not a new one.

## Integration Points

### External Services

| Service | Integration Pattern | Notes |
|---------|---------------------|-------|
| MaxMind GeoLite2-City `.mmdb` | Already integrated via `geoip_service.py`; ASN/hosting-provider flagging needs a sibling `.mmdb` (GeoLite2-ASN or the commercial GeoIP2-ISP variant) loaded the same lazy-singleton way | No new external service — same "bring your own `.mmdb`" model, same env-var convention (`GEOIP_DB_PATH` → add `GEOIP_ASN_DB_PATH`) |
| `world-atlas` TopoJSON (npm package) | Bundled at build time into the frontend, not fetched at runtime | One-time `npm install world-atlas react-simple-maps d3-geo`; verify license (public-domain/ISC, Natural Earth-derived) before bundling |

### Internal Boundaries

| Boundary | Communication | Notes |
|----------|---------------|-------|
| `agent_heartbeat_endpoints.py` / `agent_registry_endpoints.py` ↔ `agent_location_history_service.py` | Direct async function call, same request | Both existing endpoint files already do a `find_one` on `agents` before the geo block — no extra DB round-trip needed to get "prior" state |
| `agent_location_history_service.py` ↔ `agent_impossible_travel.py` | Direct async function call, chained only on an actual IP change | Impossible-travel check must read the *previous* `agent_location_history` row (or `existing_agent.geo`) for "last known position" — do not maintain a third mirror of this state |
| Detectors ↔ alerting | `notification_manager.send_notification(event_type, payload, tenant_id)` + `websocket_manager.broadcast_security_event` / a new `broadcast_agent_geo_alert` following the exact shape of the existing `broadcast_agent_status_change` | Reuse, do not add a third alerting transport |
| `agent_uptime_rollup_loop` ↔ `monitor_agent_status` | Independent schedulers, both reading `agents.status`/`lastSeen`; no direct call between them | Keep them separate — `monitor_agent_status` runs every 30s for near-real-time offline flips; the uptime rollup runs hourly for aggregation. Merging them would either slow down offline detection or make the rollup needlessly expensive. |
| Frontend `FleetGeoMap.tsx` ↔ backend | New REST endpoint, refreshed on demand | Reuse `socketService`'s existing agent-status-change event to trigger a re-fetch rather than opening a new socket channel just for map updates |

## Suggested Build Order

1. **ASN/VPN enrichment sibling to `geoip_service.py`** (new `.mmdb`-backed lookup) — no dependents; do first so later phases can flag `is_vpn`/`is_hosting` on both new alerts and the fleet map.
2. **Location-history audit** (`agent_location_history` collection + change-detection in the heartbeat/register handlers) — everything downstream (impossible-travel, fleet map "last moved" data) reads this.
3. **Agent-scoped impossible-travel + geo-fence detectors** — depend on #2 for "previous known geo"; wire into existing `notification_manager`/`websocket_manager`.
4. **Offline-agent alerting extension + uptime rollups** — mostly independent of #1–3; extend `monitor_agent_status` in place, add the new `agent_uptime_rollup_loop` scheduler per Pattern 4.
5. **Fleet map + observability UI** (map endpoint, `FleetGeoMap.tsx`, location-history/uptime panels in `AgentDetailModal.tsx`) — last, since it's a read-only aggregation over everything built in #1–4, and is where the new-permission/nav-slot decision (distinct from the pre-existing but unrelated `view:geographic_map`) gets finalized.

## Sources

- Direct codebase inspection (HIGH confidence, no external source needed): `backend/agent_heartbeat_endpoints.py`, `backend/agent_registry_endpoints.py`, `backend/geoip_service.py`, `backend/app_startup.py`, `backend/app_background_tasks.py`, `backend/database.py`, `backend/router_registry.py`, `backend/compliance_remediation_sla_service.py`, `backend/ticketing_bridge.py`, `backend/ueba_service.py`, `backend/itdr_service.py`, `backend/insider_threat_service.py`, `backend/siem_endpoints.py`, `backend/notification_service.py`, `backend/notification_manager.py`, `backend/websocket_manager.py`, `backend/agent_metrics_endpoints.py`, `components/GeographicAttackMap.tsx`, `components/Sidebar.tsx`, `components/AgentsDashboard.tsx`, `App.tsx`
- [react-simple-maps](https://www.react-simple-maps.io/) / [GitHub: zcreativelabs/react-simple-maps](https://github.com/zcreativelabs/react-simple-maps) — MEDIUM confidence (single web search, corroborated by the codebase's own tile-free precedent in `GeographicAttackMap.tsx`)
- [Interactive world map result view in React with D3 and TopoJSON](https://medium.com/nexl-engineering/interactive-world-map-result-view-in-react-with-d3-and-topojson-e6f5cf6092fb) — MEDIUM confidence, pattern confirmation only

---
*Architecture research for: v3.3 — Agent Geo & Fleet Observability*
*Researched: 2026-07-29*
