# Project Research Summary

**Project:** Enterprise OmniAgent — Security & Compliance Portal
**Domain:** Multi-tenant agent geolocation + fleet observability (v3.3)
**Researched:** 2026-07-29
**Confidence:** HIGH (codebase-integration claims verified against source; MEDIUM on external ecosystem/library choices)

## Executive Summary

v3.3 turns the `publicIp` + `geo` data v3.2 landed on agent/asset docs into four surfaces: a fleet geo map, location-based security detectors, fleet observability, and a location-history audit trail. Research against the live codebase shows the milestone is **less greenfield than the brief implies** — two "target features" (offline-agent alerting, agent version tracking) already exist in `app_background_tasks.py::monitor_agent_status()` and `AgentList.tsx`, and `agent_metrics_history` already has a working `GET /agents/{id}/metrics/history` endpoint with **zero frontend consumption**. Those should be scoped as "add the missing UI," not "build."

The genuinely new work is: **VPN/proxy/hosting-ASN classification** (100% new — today's `geoip_service.py` only reads GeoLite2-City, no anonymizer data), **agent-scoped geo security detectors** (the existing SIEM "impossible-travel" is user-login-keyed in `ueba_service`/`itdr_service`, and insider-threat `vpn_geo_anomaly` is demo seed data — neither is a live agent detector), an **append-only `agent_location_history`** audit (cleanly clonable from `remediation_escalations`), and an **offline/air-gapped fleet map** (no map lib exists; `GeographicAttackMap.tsx` is a heatmap-bar mock).

Two risks dominate: (1) the **tenant-isolation background-scheduler bug** this repo has already hit twice (`get_database()` fail-closes to zero results outside an HTTP request — v3.2's SLA sweep and the ticketing escalation loop both had to use raw `mongodb.db`); every new geo/observability sweep must use raw `mongodb.db` from day one. (2) **Privacy/legal** — an immutable, queryable location timeline of (often WFH-home) employee IPs is a materially different GDPR/works-council posture than the current transient `geo` field, and needs review *before* implementation.

## Key Findings

### Recommended Stack

Offline-first throughout — deployments may be air-gapped, so **no runtime external network calls** (no tile servers, no live IP-intel APIs). All map/geo data bundles at build time or ships as a licensed `.mmdb` supplied out-of-band, mirroring the existing `geoip_service.py` model.

**Core technologies:**
- `react-simple-maps@3.0.0` + `d3-geo@3.1.1` + `topojson-client@3.1.0` + `world-atlas@2.0.2` — pure-SVG country/city fleet map, ~50–100 KB bundled TopoJSON, zero tile servers. Right-sized for marker-by-location; MapLibre GL + self-hosted PMTiles is a heavier escalation only if street-level pan/zoom is ever needed.
- `supercluster@8.0.1` — marker clustering for dense fleets.
- `recharts@^3.5.1` — **already installed**; sufficient for metrics-history/uptime charts. No new charting dep.
- **MaxMind GeoIP2 Anonymous IP** `.mmdb` (commercial; fields `is_anonymous_vpn`/`is_hosting_provider`/`is_public_proxy`/`is_residential_proxy`/`is_tor_exit_node`) read with the **same `maxminddb` reader already in `geoip_service.py`**. Free fallback: GeoLite2-ASN (AS-org only, no VPN flag) + `X4BNet/lists_vpn` heuristic ranges. **Product decision required** (paid "detected" vs free "heuristic flag") — affects UI copy.
- MongoDB native time-series collections are available (8.0.26) for any *new* rollup data; leave `agent_metrics_history` untouched.

### Expected Features

**Must have (table stakes):**
- Fleet geo map with markers by city/country, clustering, tenant/status filter, drill-down to agent.
- Agent metrics-history charts (backend already exists — pure frontend gap).
- Per-agent location-history timeline + immutable audit trail.
- Offline-agent alerting surfaced in UI (detection already exists — add aggregate view).

**Should have (competitive):**
- Agent-scoped impossible-travel detection (haversine + time window, `agent_id`-keyed).
- Per-tenant geo-fencing (allowed-region policy + violation alert).
- VPN/proxy/hosting-ASN flagging on agent public IPs.
- Uptime % / heartbeat timeline; agent version-drift surfacing.

**Defer / anti-features:**
- Street-level precise-location map (GeoIP lat/long is a coarse centroid — implying precision is a legal/UX trap).
- Real-time GPS tracking (not available; agents report IP only).

### Architecture Approach

Extend, don't parallel-build. Enrichment slots **inline** where geo already runs.

**Major components:**
1. `agent_asn_service.py` — sibling lazy-`.mmdb` module called at the same spot as `geoip_service.lookup()` in `report_heartbeat()` / registration; adds ASN/VPN flags to the agent doc.
2. `agent_location_history` collection — append-only, cloned from `remediation_escalations`; written only when `public_ip != existing_agent["publicIp"]` (the `existing_agent` doc is already fetched each beat — no extra read).
3. `agent_impossible_travel.py` — clone the haversine/time-window algorithm from `ueba_service.analyze_login()`, keyed by `agent_id` (NOT the email-keyed user path); reuse the existing alert/notification fan-out.
4. `agent_uptime_rollup_loop` + `agent_uptime_daily` — new scheduler cloned from `compliance_remediation_sla_service`'s shape, using **raw `mongodb.db`**; extend `monitor_agent_status()` in place for real-time offline.
5. Fleet-map aggregation endpoint (tenant-scoped, projection-safe) + `react-simple-maps` UI behind a **new** permission/nav slot (not the unrelated seeded `view:geographic_map`).

**Dependency-ordered build:** (1) ASN/VPN enrichment → (2) location-history + change-detection → (3) impossible-travel + geo-fence detectors → (4) offline extension + uptime rollups → (5) map + observability UI.

### Critical Pitfalls

1. **Tenant-isolation scheduler bug (highest-certainty).** `get_database()` fail-closes to zero results in background context — every geo/observability sweep MUST use raw `mongodb.db`. Already hit twice in this repo.
2. **Privacy/legal.** Immutable employee location history = new GDPR/works-council exposure. Legal review is a *pre-implementation gate* for the audit phase, not a post-hoc audit.
3. **False positives near-certain day 1.** Corporate VPN/SASE egress + CGNAT make agents look co-located or "teleporting." No ASN/VPN classification exists yet to suppress on — build enrichment before detectors.
4. **Wrong-shape reuse.** `itdr_service` impossible-travel is email/user-keyed; `vpn_geo_anomaly` is seeded demo data. Clone the algorithm, don't wire agents into user-login collections.
5. **Dormant TTL bug — don't clone.** `agent_metrics_history`'s 30-day TTL index sits on an ISO-string field, not a BSON Date, so it's a silent no-op. New collections must use BSON Date TTL (or an app-level cap).
6. **Air-gapped map breakage.** Any tile-based lib (Leaflet+OSM/Mapbox) fetches external tiles → breaks air-gapped. Commit to bundled TopoJSON+SVG explicitly.

## Implications for Roadmap

Continues numbering from Phase 45 → v3.3 starts at **Phase 46**. Suggested 4 phases:

### Phase 46: Public-IP ASN/VPN Enrichment + Location-History Audit
**Rationale:** Foundation — detectors and map need ASN/VPN flags and a location timeline; both low-risk (inline enrichment + append-only clone). Front-loads the VPN data-source decision and the privacy/legal review gate.
**Delivers:** `agent_asn_service.py` inline enrichment (VPN/hosting/proxy flags on agent docs), append-only `agent_location_history` with cheap change-detection, retention decision routed through the existing retention module.
**Avoids:** false-positive pitfall (enrichment before detectors), TTL-index pitfall (BSON Date), privacy pitfall (legal gate up front).

### Phase 47: Agent-Scoped Geo Security Detectors
**Rationale:** Depends on Phase 46 enrichment + history. Highest new-security value.
**Delivers:** `agent_impossible_travel.py` (`agent_id`-keyed haversine), per-tenant geo-fencing (allowed-region policy + alert), VPN/hosting flags surfaced; reuse existing notification fan-out.
**Avoids:** wrong-shape reuse (new module, not user-login path); needs the data-source decision resolved in 46.

### Phase 48: Fleet Observability UI + Uptime Rollups
**Rationale:** Mostly frontend + one new sweep; backend detection (offline) and metrics endpoint already exist.
**Delivers:** metrics-history charts (`recharts`), heartbeat/uptime timeline + `agent_uptime_daily` rollup loop (raw `mongodb.db`), offline-alert aggregate view, version-drift surfacing.
**Avoids:** scheduler tenant-isolation bug (raw db from day one).

### Phase 49: Fleet Geo Map
**Rationale:** Reads everything from 46–48; last, highest-visibility.
**Delivers:** `react-simple-maps` + bundled `world-atlas` offline SVG map, `supercluster` clustering, tenant/status filters, agent drill-down, new permission/nav slot.
**Uses:** the offline-first map stack; **avoids** air-gapped tile breakage.

### Phase Ordering Rationale
- Strict dependency order (enrichment → history → detectors → observability → map) surfaced identically by the Features and Architecture research.
- Front-loading enrichment + the privacy gate prevents the two dominant risks (false positives, legal) from blocking later phases.
- Map last because it consumes all upstream data.

### Research Flags
Phases likely needing deeper phase-specific research:
- **Phase 46:** VPN/proxy data-source selection (paid GeoIP2 Anonymous IP vs free GeoLite2-ASN + X4BNet) — stakeholder cost/accuracy decision; retention-window legal decision.
- **Phase 49:** confirm bundled-TopoJSON size/UX at country+city zoom (approach decided, sizing not benchmarked).

Standard-pattern phases (lighter research):
- **Phase 48:** established chart/scheduler patterns already in-repo.

## Confidence Assessment

| Area | Confidence | Notes |
|------|------------|-------|
| Stack | MEDIUM-HIGH | Versions verified against npm/PyPI 2026-07-29; offline-map viability cross-checked, not benchmarked |
| Features | HIGH (codebase) / MEDIUM (competitor) | Existing-capability gaps read from source; ecosystem patterns from web |
| Architecture | HIGH | Integration points read from exact source lines in heartbeat/register/scheduler code |
| Pitfalls | HIGH | All grounded in repo source with file/line; scheduler bug corroborated by v3.2's own history |

**Overall confidence:** HIGH for the build plan; MEDIUM on two external decisions (VPN dataset, map bundle sizing).

### Gaps to Address
- **VPN/proxy dataset choice** — resolve in Phase 46 discussion (paid vs free; offline-bundle viability).
- **Location-history retention** — deliberate legal/audit decision, not inherited from the 30-day metrics convention.
- **Geo-fence enforcement point** — block vs alert-only — decide in Phase 47 discussion.
- **Uptime data density** — confirm heartbeat cadence/cap supports desired chart ranges or needs a rollup collection (Phase 48).

## Sources

### Primary (HIGH confidence)
- Codebase: `geoip_service.py`, `agent_heartbeat_endpoints.py`, `agent_registry_endpoints.py`, `agent_metrics_endpoints.py`, `app_background_tasks.py`, `app_startup.py`, `compliance_remediation_sla_service.py`, `ueba_service.py`, `itdr_service.py`, `insider_threat_service.py`, `AgentList.tsx`, `AgentsDashboard.tsx`, `GeographicAttackMap.tsx`, `migrations/002_scale_indexes.py`.

### Secondary (MEDIUM confidence)
- npm/PyPI registries (versions, 2026-07-29); MapLibre / react-simple-maps docs (offline viability); MaxMind GeoIP2 Anonymous IP product docs; MongoDB time-series docs; CrowdStrike/Elastic geofencing & fleet-observability patterns.

---
*Research completed: 2026-07-29*
*Ready for roadmap: yes*
