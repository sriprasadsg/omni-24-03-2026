# Feature Research

**Domain:** Endpoint/EDR-adjacent fleet management — agent geolocation map, location-based security detections, fleet health observability, location-history audit
**Researched:** 2026-07-29
**Confidence:** MEDIUM (web sources cross-checked across CrowdStrike/Elastic/MaxMind official docs + multiple geofencing/GRC articles — no API-key-gated vendor docs directly verified; codebase-derived findings below are HIGH confidence, read directly from source)

**Scope note:** This is a subsequent-milestone (v3.3) research pass. `publicIp`/`geo` collection (GeoLite2-City), the Public IP + Location row in AgentList/AgentsDashboard, `agent_metrics_history`, heartbeat status (Online/Offline/Error/Quarantined), agent version tracking, the SIEM impossible-travel rule, insider-threat `vpn_geo_anomaly`, the notification service, and `remediation_escalations` are NOT re-researched — they already exist (v3.2 and earlier). This file covers only the 4 new v3.3 feature areas: (1) fleet geo map, (2) location-based security, (3) fleet observability, (4) location history & audit.

**Critical codebase finding, read directly (HIGH confidence) — re-scope before planning:**
Two of the four "target features" named in PROJECT.md's v3.3 section are **already substantially built**, and treating them as net-new will duplicate working code:
- **Offline-agent alerting already exists.** `backend/app_background_tasks.py::monitor_agent_status()` marks agents Offline after 5 minutes of heartbeat silence, broadcasts a websocket `agent_status_change` event, and fires an `agent.offline` in-app notification via `notification_manager`. What's missing is a UI surface (an uptime timeline/percentage view), not the detection or alerting itself.
- **Per-agent version display + fleet upgrade already exists.** `AgentList.tsx` shows and sorts by `agent.version`; `AgentsDashboard.tsx` has a `handleScheduleUpgrade` bulk-upgrade action; `agent_heartbeat_endpoints.py` auto-pushes an update instruction when a reporting agent's version is behind `_LATEST_AGENT_VERSION`. What's missing is a fleet-wide *aggregate* view (e.g., "N agents on 2.1.2, M on 2.1.3" distribution), not per-agent version tracking.
- **`agent_metrics_history` has zero frontend consumption.** `GET /agents/{id}/metrics/history` (in `agent_metrics_endpoints.py`) already returns time-series CPU/mem/disk plus a computed summary (avg/max), ready to chart — but no component reads it. This is a real, table-stakes gap.
- **SIEM impossible-travel (`itdr_service.py::on_login_success`) is USER-authentication-scoped, not agent-scoped.** It tracks `itdr_login_events` (email/ip/country) on human logins, with a 1-hour impossible-travel window. It has no concept of an *agent's* public IP changing. Agent-geo impossible travel is a genuinely new detector — reuse the alert-creation and notification plumbing, not the `itdr_login_events` collection.
- **Insider-threat `vpn_geo_anomaly` is a demo-only risk-factor tag today, not a live rule.** `insider_threat_service.py` defines `vpn_geo_anomaly` in a risk-factor registry and references it only inside `seed_demo_data()` — there is no live detection logic evaluating real login/agent events against it. Treat this as "the taxonomy/weight already exists, the live rule does not" — reuse the risk-factor registry and scoring pipeline, but the actual VPN/geo-anomaly evaluation must be built.
- **GeoIP is City-only — no ASN/VPN/proxy/hosting data exists anywhere in the codebase.** `geoip_service.py` uses only a free MaxMind GeoLite2-City `.mmdb` (country/city/region/lat-long). There is no ASN lookup, no VPN/proxy/hosting flag, no reputation feed of any kind. VPN/proxy/hosting-ASN flagging is 100% new capability requiring a new (likely paid) data source — see Anti-Features and Pitfall-adjacent note below.

## Feature Landscape

### Area 1 — Fleet Geo Map (visualization)

#### Table Stakes

| Feature | Why Expected | Complexity | Notes |
|---------|--------------|------------|-------|
| Map view with one marker per agent, colored/shaped by status (Online/Offline/Error/Quarantined) | Baseline for any fleet dashboard with location data; CrowdStrike's own "Active Sensors by Country" WorldMap dashboard is the direct comparable — status-at-a-glance on a map is the expected default, not a premium add-on | MEDIUM | Consume the already-persisted `agent.geo.{latitude,longitude}` + `agent.status`; no new backend endpoint needed beyond the existing agent-list query, just a `lat/lon != null` filter |
| Marker clustering at country/region zoom, expanding to city/individual pins on zoom-in | Every fleet-map competitor surveyed aggregates at low zoom (CrowdStrike aggregates to country level by default) — without clustering, a few hundred agents in one metro area become an unreadable pile of overlapping pins | MEDIUM | Standard client-side library feature (e.g. Leaflet.markercluster / Supercluster) — this is UI-library work, not a new data model |
| Filter by tenant and by status | Multi-tenant platform — an MSP admin needs to scope the map to one client or to "show me everyone offline right now"; this mirrors the existing tenant-scoping already enforced everywhere else in the app | LOW | Same tenant-isolation filter pattern already applied to every other agent-list endpoint; status filter is a simple `$in` query |
| Click-through from marker to agent detail (drill-down) | Table stakes for any ops map — a marker with no click target is a dead end; AgentList/AgentsDashboard already has the target detail view | LOW | Wire marker click → existing agent detail route/modal, no new detail UI needed |
| Self-hosted map tiles (no external tile server dependency) | PROJECT.md explicitly flags air-gapped deployments as a hard requirement — this is this project's own constraint, not a generic table-stake, but it is non-negotiable given the compliance/MSP customer base (some tenants may be in isolated networks) | MEDIUM-HIGH | Standard approach per research: pre-generate/self-host vector or raster tiles (e.g. PMTiles single-file archive, or a raw OSM-extract raster tile directory) served from the app's own static assets, consumed by Leaflet/MapLibre as a normal `tileLayer` — zero runtime call to any public tile CDN. Flag for phase-specific research: tile generation pipeline and file size/licensing of a bundled basemap are non-trivial and deserve their own research pass at planning time |
| Empty/degraded state when an agent has no geo (private IP, GeoIP lookup miss, DB not installed) | `geoip_service.lookup()` already returns `None` silently in these cases — the map must not crash or silently drop agents, it should show them in a "no location" bucket/list | LOW | `geo` is already nullable on the agent doc; map component just needs a defined fallback (list panel) rather than treating it as an error |

#### Differentiators

| Feature | Value Proposition | Complexity | Notes |
|---------|--------------------|------------|-------|
| Live status animation/pulse on markers that just went Online/Offline (websocket-driven) | This codebase already broadcasts `agent_status_change` over websocket (from `monitor_agent_status`) — wiring that existing stream into the map gives a "live ops center" feel most competitors' static dashboards don't have | MEDIUM | Reuse the existing websocket channel; purely additive to the base map, no new backend event needed |
| Heatmap/density overlay (agent concentration by region) as an alternate view to discrete markers | Useful for MSPs with hundreds of endpoints in a few metros where clustering alone still feels noisy | LOW-MEDIUM | Standard library toggle (e.g. Leaflet.heat) layered on the same lat/lon dataset — no new data needed |
| Geo + compliance-posture overlay (color marker by compliance pass-rate, not just online/offline) | Ties the new map into this platform's actual Core Value ("see compliance posture") rather than being a generic IT-ops map — a genuine differentiator vs. pure EDR fleet maps which don't know about compliance | MEDIUM | Requires joining agent geo with the existing per-asset compliance status already computed elsewhere; good v1.x candidate once base map ships |

#### Anti-Features

| Feature | Why Requested | Why Problematic | Alternative |
|---------|---------------|------------------|-------------|
| Real-time street-level/precise-address pinpointing | "More precision looks more powerful" | GeoIP (even paid tiers) is only accurate to city/region for most residential/business IPs — presenting false precision (e.g., pinning to an exact street) is misleading and a compliance/privacy liability for an MSP audience | Show city/region-level accuracy honestly; if higher precision is needed later, it must come from a different signal (e.g. device GPS), which is out of scope for a server-side agent |
| Building a custom in-house tile-rendering/tile-server stack from scratch | Feels like "full control" over air-gapped requirement | Reinventing an OSM tile pipeline (vector tile generation, styling, zoom pyramids) is a multi-week specialty effort with its own licensing/attribution obligations | Use an existing self-hostable tile format (PMTiles/MBTiles) with a pre-built extract; treat this as "bundle & serve a file," not "build a tile server" |
| Live external tile CDN (Mapbox/Google Maps/OSM public tile servers) as the default | Fastest to integrate, best-looking out of the box | Directly violates the stated air-gapped/self-contained requirement; also introduces per-tenant IP/geo data egress to a third party for every map render — a real compliance concern for a compliance-focused product | Self-hosted tiles as table stakes; if online tenants want richer tiles, make an external provider strictly optional/tenant-configurable, never the only path |

### Area 2 — Location-Based Security

#### Table Stakes

| Feature | Why Expected | Complexity | Notes |
|---------|--------------|------------|-------|
| Agent impossible-travel detection (same agent's `publicIp`/`geo` jumps countries faster than physically possible between two heartbeats) | Direct analog to the existing SIEM impossible-travel rule and ITDR's user-login version — expected once agent geo exists, per the milestone's own framing | MEDIUM | **New detector, but reuse the existing alert/notification pipeline.** Do NOT reuse `itdr_login_events` (user-auth-scoped) or duplicate the SIEM rule's login-event query — this needs its own event trail on agent heartbeats (previous geo vs. new geo + elapsed time + implied speed), emitting through the same `_create_alert`-style helper and the existing notification service so it appears in the same alert stream as everything else |
| Per-tenant geo-fencing: allow-list of countries/regions, alert (and optionally block/quarantine) on agent heartbeat from outside the list | Matches the general geofencing/conditional-access pattern (Azure AD, LastPass, DataLocker) — risk-tiered response (alert vs. hard block) is called out across sources as the standard shape, not binary-only | MEDIUM | New: a per-tenant policy doc (`allowed_countries: [...]`, `action: alert|quarantine`) checked on every heartbeat where `geo.country_code` is present; on violation, reuse the existing `agent_quarantine_endpoints.py` quarantine action if `action=quarantine`, and the existing notification service for `action=alert` — don't build a second quarantine mechanism |
| Geo-fence violation alerting surfaced in the same place as other security alerts (SIEM/insider-threat feed), not a siloed new inbox | Consistency with the existing SIEM/insider-threat alert surfaces the milestone explicitly asks to integrate with | LOW | Emit into whatever collection/stream backs the current SIEM alert list (same shape as `itdr_service._create_alert` output) rather than inventing a new alerts collection |
| VPN/proxy/hosting-provider flag shown next to an agent's location (e.g. "connecting via known hosting/VPN network") | Table stakes in identity/fraud tooling generally (MaxMind's own Anonymous IP product exists precisely because this is expected), and relevant here because a "hosting ASN" endpoint is a red flag for a compliance/EDR-adjacent product | MEDIUM-HIGH | **Real gap — no data source exists today.** Requires a new MaxMind add-on DB (GeoIP Anonymous IP, paid) or an alternate ASN/VPN-reputation feed loaded alongside the existing `.mmdb` reader in `geoip_service.py`. Flag explicitly for phase-specific research: licensing cost, air-gapped update/rotation process for a paid `.mmdb`, and false-positive rate on legitimate corporate VPNs (which are common and NOT malicious) all need dedicated research before committing to an implementation approach |

#### Differentiators

| Feature | Value Proposition | Complexity | Notes |
|---------|--------------------|------------|-------|
| Confidence-scored VPN/proxy flagging (not just boolean) surfaced with a "why" (named provider, confidence %) | MaxMind's own higher tier (Anonymous Plus) frames this as the premium differentiator over a bare boolean flag — fewer false positives, more actionable for an analyst | HIGH | Depends entirely on which data source is chosen (only the paid MaxMind Anonymous Plus tier or equivalent commercial feed offers this) — defer until the base VPN/ASN flag (table stakes) ships and the source decision research is done |
| Risk-tiered geo-fence response (step-up verification / quarantine only on repeat or high-severity violation, not every single alert) | Sources explicitly frame graduated risk response as more mature than binary block/allow — reduces alert fatigue for MSP analysts managing many tenants | MEDIUM | Natural v1.x extension once basic alert-on-violation ships and false-positive rate from real usage is known |
| Cross-signal correlation (agent geo-fence violation + user login impossible-travel + insider-threat vpn_geo_anomaly all correlated into one incident, not three separate alerts) | This is the actual "fleet + security convergence" story the milestone implies — genuinely differentiated vs. generic EDR/fleet tools that don't share a compliance platform's existing SIEM/insider-threat surfaces | HIGH | Requires all three underlying detectors to exist first (agent impossible-travel is new, per above); good v2 candidate once each individual detector is proven, not a v1 target |

#### Anti-Features

| Feature | Why Requested | Why Problematic | Alternative |
|---------|---------------|------------------|-------------|
| Auto-block/kill an agent's connection the instant any geo-fence rule fires, with no configurable grace period | "Fail closed" sounds maximally secure | GeoIP has legitimate false-positive triggers (a legitimate corporate VPN egress, a mobile hotspot roaming across a border, an ISP reassigning an IP block) — hard auto-block on first violation will quarantine legitimate endpoints and generate support burden that undermines trust in the whole feature | Default to alert-only with an admin-configurable escalation to quarantine after N violations or on explicit tenant opt-in, matching the existing `agent_quarantine_endpoints.py` action as an available response, not the automatic default |
| Building a brand-new alerts/incidents collection and UI specifically for geo-security events | Feels cleanly scoped to "just this feature" | Directly duplicates the existing SIEM alert feed and insider-threat alert feed the milestone explicitly says to integrate with, not duplicate — creates a second place analysts must check | Emit into the existing SIEM/insider-threat alert surface using the same shape/collection those systems already read from |
| Treating any VPN/proxy hit as an automatic hard-fail/block | "VPN = bad actor" is intuitive | Many legitimate remote-work and MSP-managed endpoints connect over corporate VPNs; blocking on VPN detection alone produces high false-positive noise and would actively break normal remote work for a distributed workforce | Surface VPN/proxy/hosting as an informational flag contributing to a risk score, not a standalone block trigger — pair with the geo-fence/impossible-travel signals rather than acting alone |

### Area 3 — Fleet Observability

#### Table Stakes

| Feature | Why Expected | Complexity | Notes |
|---------|--------------|------------|-------|
| Per-agent CPU/mem/disk history chart (time-series, selectable window e.g. 1h/24h/7d) | Elastic Fleet's own agent detail view shows exactly this (CPU/mem/last-checkin over time) — the direct fleet-management comparable; and this codebase's own backend endpoint already computes it | LOW-MEDIUM | **Zero backend work needed.** `GET /agents/{id}/metrics/history` already returns time-series + summary stats (avg/max per metric). Purely a frontend charting task — reuse `recharts` (already a project dependency, used elsewhere in dashboards) rather than adding a new charting library |
| Heartbeat/uptime timeline (visual bar/strip showing Online/Offline/Error segments over time) + an uptime % figure | Standard fleet-health primitive (Elastic's "agent activity" chronological log is the direct analog); auditors and MSP ops both want "how reliable has this endpoint been," not just current status | MEDIUM | New: requires persisting/deriving status transitions over time. `agent.status` is currently overwritten in place with no history — either add a lightweight `agent_status_history` collection (append a record on each transition, mirroring the append-only pattern already used elsewhere) or derive uptime % from `agent_metrics_history`/heartbeat timestamps as a cheaper first cut. Flag as needing a design decision at planning time: true state-transition log (more accurate, more storage) vs. heartbeat-gap inference (cheaper, less precise) |
| Offline-agent alerting | Already exists — see the codebase finding at the top of this document | — | **Reuse `monitor_agent_status()` as-is.** Only gap: surfacing it in a fleet-wide "currently offline" list/widget on the new observability view; the detection+notification backend needs no changes |
| Agent version-drift surfacing at the fleet level (e.g. "14 agents on 2.1.2, 3 on 2.1.1, 1 on 1.9.0 — needs upgrade") | Table stakes for any managed-fleet tool — CrowdStrike's own docs call out monitoring sensor version/RFM status across the fleet as a named capability | LOW-MEDIUM | Per-agent version already displayed and sortable in `AgentList.tsx`; `_LATEST_AGENT_VERSION` already known server-side. This is an aggregation task (`GROUP BY version`) plus a simple bar/summary widget — not a new tracking mechanism. Wire it to the existing `handleScheduleUpgrade` action so drift → one-click remediation |
| Per-agent health "at a glance" badge (e.g. resource-pressure warning when CPU/mem/disk consistently high) | Table stakes once history data is charted — a raw chart without a threshold-based summary forces the operator to eyeball it every time | LOW | Compute from the existing `summary` object (`cpu_avg`/`cpu_max` etc.) already returned by `get_agent_metrics_history` — no new backend logic, just a frontend threshold/badge |

#### Differentiators

| Feature | Value Proposition | Complexity | Notes |
|---------|--------------------|------------|-------|
| Fleet-wide health rollup dashboard (single view: uptime % distribution, version drift %, resource-pressure count, offline count — across all agents/tenants for an MSP admin) | Elastic/CrowdStrike expose this per-agent or per-policy-group; an MSP-wide rollup across *all* tenant fleets in one glance is a genuine differentiator for the MSP-operator persona this platform is built around | MEDIUM | Straightforward aggregation over already-existing per-agent data (metrics history, status, version) — no new collections, just a summary endpoint/view |
| Predictive/trend-based alerting (e.g. "disk usage trending toward full in ~5 days" rather than only threshold-crossing) | Goes beyond reactive alerting most fleet tools ship by default | HIGH | Defer — requires trend/regression logic on `agent_metrics_history`; not needed for a credible v1, real scope-creep risk if pulled forward |

#### Anti-Features

| Feature | Why Requested | Why Problematic | Alternative |
|---------|---------------|------------------|-------------|
| Sub-minute/near-real-time metrics streaming and charting | "More real-time = better observability" | Heartbeat interval is already ~30s and `agent_metrics_history` is capped at ~1-min granularity/48h retention server-side (`to_list(length=2880)`) — building a faster streaming pipeline than the data source itself supports is wasted effort | Chart at the existing granularity; if finer resolution is genuinely needed later, that's a heartbeat-interval/storage-retention change, not a frontend problem |
| A second, parallel status-tracking system independent of `agent.status`/`monitor_agent_status()` | "The uptime timeline needs its own source of truth" | Duplicates the existing offline-detection logic and risks the two statuses disagreeing (e.g. timeline says Online while `agent.status` says Offline) | Derive the uptime timeline directly from `agent.status` transitions (via a new lightweight history collection or heartbeat-gap inference) — single source of truth for "is this agent up" |

### Area 4 — Location History & Audit

#### Table Stakes

| Feature | Why Expected | Complexity | Notes |
|---------|--------------|------------|-------|
| Per-agent public-IP/geo change timeline (chronological list: old geo → new geo, timestamp) | Direct analog to any audit-trail feature in this codebase (compliance `status_history`, remediation `escalation_history`) — once geo changes are security-relevant (Area 2), auditors will expect to see the history, not just the current value | LOW-MEDIUM | New: append an entry each time a heartbeat's resolved `geo` differs from the agent doc's stored `geo` (compare before overwrite in `agent_heartbeat_endpoints.py`), rather than only ever overwriting in place as today |
| Immutable, append-only storage (no update/delete on history entries) | Explicitly named in the milestone; matches the proven `remediation_escalations` pattern in this exact codebase | LOW | **Clone `remediation_escalations` directly**: a dedicated collection (e.g. `agent_geo_history`), `insert_one`-only access pattern, no update/delete endpoints exposed — same shape as the SLA escalation audit trail already shipped in v3.2 |
| Read-only, tenant-scoped GET endpoint to view an agent's history | Matches the existing pattern for `remediation_escalations` (tenant-scoped GET, admin-gated where relevant) | LOW | Clone `compliance_remediation_sla_endpoints.py`'s read-only GET shape and tenant-isolation logic verbatim |
| History entry includes enough context to explain the change (previous geo, new geo, previous/new public IP, timestamp, and — if available — which heartbeat/agent version triggered it) | Auditors need the "why/what changed" narrative, not just a bare diff; this is the same expectation already met by `status_history`'s `changedBy`/`changedAt`/`previous_status` shape | LOW | Mirror the `status_history` field shape (`previous_value`/`new_value`/`changed_at`) rather than inventing a new schema convention |

#### Differentiators

| Feature | Value Proposition | Complexity | Notes |
|---------|--------------------|------------|-------|
| Location-history entries cross-linked to any security alert they triggered (e.g. "this geo change also fired an impossible-travel alert — view it") | Ties the audit trail into Area 2's detections, giving auditors and analysts a single narrative instead of two disconnected records | LOW-MEDIUM | Simple foreign-key style reference (`alert_id`) stored on the history entry when the geo-change coincides with a fired detection — cheap once both features exist, sequence Area 2 before this enhancement |
| Exportable per-agent or per-tenant location-history report (PDF/Excel) alongside the existing compliance audit exports | Consistent with this platform's existing audit-export capability (`compliance_reporting_pdf.py`/`compliance_reporting_excel.py`) — MSPs already export compliance evidence packages and would expect location history to be exportable the same way for an audit | MEDIUM | Reuse the existing PDF/Excel generation infrastructure and STATUS_LEGEND-style convention rather than building new export plumbing; good v1.x follow-on, not required for initial ship |

#### Anti-Features

| Feature | Why Requested | Why Problematic | Alternative |
|---------|---------------|------------------|-------------|
| Allowing admin edit/delete of history entries (e.g. "clean up noisy/incorrect geo blips") | Feels like reasonable data hygiene | Directly breaks the "immutable, append-only" requirement explicitly stated in the milestone and undermines the entire audit value proposition (an editable audit trail isn't an audit trail) | If a geo entry is genuinely wrong (bad GeoIP data), append a corrective/annotation entry — never mutate or remove the original, same principle already applied to `status_history`/`remediation_escalations` |
| Recording every single heartbeat as a history entry regardless of whether geo actually changed | "More data is more audit-proof" | Heartbeats arrive every ~30s; logging every one when geo is unchanged 99%+ of the time bloats the collection for zero audit value and makes the real change events harder to find in the noise | Only append when the resolved geo (or public IP) differs from the currently stored value — a diff-triggered log, exactly like why `status_history` only appends on an actual status change, not every read |
| A generic "audit everything" polymorphic history collection shared across agents, controls, remediation tasks, etc. | DRY instinct — "we already have three append-only history patterns, unify them" | Increases blast radius of any schema change and mixes very different access-control/retention needs (agent geo history vs. compliance status history) into one collection; this is the same anti-pattern already explicitly rejected for comments in the v3.2 research | A dedicated `agent_geo_history` collection, matching the existing convention of one purpose-built append-only collection per audit concern (`remediation_escalations`, `status_history` embedded on assets, and now this) |

## Feature Dependencies

```
Fleet geo map (Area 1)
    └──requires──> agent.geo / agent.publicIp fields (already built, v3.2)
    └──requires──> self-hosted tile bundle/pipeline (new — flagged for phase research)
    └──enhances──> Location-based security (Area 2) UI can plot geo-fence violations on the same map, optional

Location-based security (Area 2)
    └──requires──> agent.geo / agent.publicIp on each heartbeat (already built, v3.2)
    └──requires (new)──> agent-level geo-change event trail (new — needed for impossible-travel comparison; not the same store as Area 4's audit, though both come from the same heartbeat-diff logic)
    └──requires (new, VPN/ASN flag only)──> a new ASN/VPN/hosting IP data source (GeoIP Anonymous IP or equivalent) — geoip_service.py has no such source today
    └──integrates-with, does-not-duplicate──> existing SIEM impossible-travel rule (itdr_service.py, user-login-scoped) and insider-threat vpn_geo_anomaly (risk-factor taxonomy only, no live rule yet)
    └──reuses──> existing agent_quarantine_endpoints.py quarantine action, existing notification service

Fleet observability (Area 3)
    └──requires──> agent_metrics_history + GET /agents/{id}/metrics/history (already built, zero backend work)
    └──requires (new)──> agent status-transition history (for accurate uptime %, timeline) OR heartbeat-gap inference (cheaper alternative)
    └──reuses──> monitor_agent_status() offline detection + notification (already built, do not rebuild)
    └──reuses──> per-agent version field + handleScheduleUpgrade action (already built; version-drift is new aggregation only)

Location history & audit (Area 4)
    └──requires──> agent.geo / agent.publicIp on each heartbeat (already built, v3.2)
    └──pattern-clones──> remediation_escalations append-only shape (already built, proven, v3.2)
    └──enhances──> Location-based security (Area 2) via optional alert_id cross-link
```

### Dependency Notes

- **Areas 2 and 4 share a root cause (heartbeat geo-diff) but must NOT share a collection.** Both need "did this agent's geo/IP change since last heartbeat" logic in `agent_heartbeat_endpoints.py`, but Area 2's need is transient (compare-then-decide-alert) while Area 4's need is a permanent immutable log. Compute the diff once per heartbeat and fan out to both: fire the Area 2 detector check, and separately append to the Area 4 `agent_geo_history` collection — do not make one read from the other's store.
- **Area 2's VPN/ASN flagging is the single highest-uncertainty item in this milestone.** No existing data source, no existing code path, and the cost/licensing/air-gapped-update-cadence tradeoffs of a paid MaxMind add-on (or an alternative feed) need dedicated phase-specific research before a plan can commit to an approach. Flagged explicitly, per PROJECT.md's own request.
- **Area 3's uptime-timeline design decision (true state-transition log vs. heartbeat-gap inference) should be made once, early, and reused if Area 4's audit trail needs a parallel "was this agent online" concept later** — but they remain separate collections; do not conflate agent *presence* history with agent *location* history even though both are time-series-of-agent-state.
- **Area 1 (map) is consumable-only for Areas 2/3/4 data** (it can overlay geo-fence violations or offline status as optional layers) but has zero hard dependency on them — it can ship as soon as the tile-serving approach is chosen, independent of the other three areas.
- **Reuse-vs-build guidance for existing SIEM/insider-threat overlap, stated explicitly per the downstream consumer's request:**
  - SIEM impossible-travel (`itdr_service.py`) → **reuse the alert-creation pattern (`_create_alert`) and severity/notification conventions only.** Do not extend `itdr_login_events` to also carry agent heartbeats — build a parallel, agent-scoped event trail and detector function.
  - Insider-threat `vpn_geo_anomaly` → **reuse the risk-factor id/weight/category registry.** The live rule itself does not exist (`seed_demo_data` only) — Area 2's actual VPN+geo-anomaly detection logic is new code that should emit into whatever collection the insider-threat feed already reads for real (non-demo) risk events, not a new inbox.
  - `remediation_escalations` → **clone the append-only collection + read-only endpoint pattern wholesale** for Area 4; this is the single cleanest and lowest-risk reuse in the whole milestone.
  - `agent_metrics_history` / heartbeat status / version tracking → **reuse as-is, build UI only** (Area 3); resist any temptation to add parallel metrics collection or a second offline-detection mechanism.

## MVP Definition

### Launch With (v1 — this milestone)

- [ ] Fleet geo map: markers by status, clustering, tenant/status filters, click-through to agent detail, self-hosted tiles — table stakes for Area 1
- [ ] Agent-scoped impossible-travel detector (new, parallel to but not duplicating the user-login ITDR rule), emitting into the existing SIEM/insider-threat alert surface
- [ ] Per-tenant geo-fencing policy (allowed countries/regions) with alert-only default response, reusing existing quarantine action as an available (not automatic) escalation
- [ ] Per-agent CPU/mem/disk history chart consuming the already-built `GET /agents/{id}/metrics/history` endpoint — pure frontend work
- [ ] Uptime timeline + uptime % (requires the new status-transition history or heartbeat-gap-inference decision)
- [ ] Fleet-level version-drift summary widget, wired to the existing `handleScheduleUpgrade` action
- [ ] Per-agent public-IP/geo change timeline in a new immutable `agent_geo_history` collection, cloned from the `remediation_escalations` append-only/read-only pattern

### Add After Validation (v1.x)

- [ ] VPN/proxy/hosting-ASN flagging — trigger: once a data-source decision (paid MaxMind Anonymous IP/Plus vs. alternative feed) is researched and approved; explicitly the highest-uncertainty item, sequence it after the rest of Area 2 ships
- [ ] Geo + compliance-posture overlay on the fleet map — trigger: once the base map is live and stable
- [ ] Fleet-wide MSP rollup dashboard (uptime/version-drift/resource-pressure across all tenants) — trigger: once per-tenant observability views are proven
- [ ] Exportable location-history report (PDF/Excel) — trigger: once the base audit trail is live and an auditor/MSP asks for exportability, consistent with existing compliance export patterns
- [ ] Cross-linking geo-history entries to the security alerts they triggered — trigger: once both Area 2 and Area 4 are independently live

### Future Consideration (v2+)

- [ ] Risk-tiered/graduated geo-fence response (step-up verification before quarantine) — defer: needs real false-positive data from v1's alert-only rollout first
- [ ] Cross-signal correlation (agent geo-fence + user impossible-travel + insider-threat vpn_geo_anomaly merged into one incident) — defer: each underlying detector needs to prove out independently first
- [ ] Predictive/trend-based resource alerting on `agent_metrics_history` — defer: reactive threshold alerting is the credible v1 bar; trend modeling is real scope creep for this milestone
- [ ] Confidence-scored VPN/proxy flagging (named provider + %) — defer: only available via the highest commercial tier of a VPN-detection feed; revisit after the boolean flag ships and proves valuable

## Feature Prioritization Matrix

| Feature | User Value | Implementation Cost | Priority |
|---------|------------|----------------------|----------|
| Fleet geo map (markers, clustering, filters, drill-down) | HIGH | MEDIUM | P1 |
| Self-hosted tile pipeline for air-gapped map | HIGH (blocking for map) | MEDIUM-HIGH | P1 (flag for dedicated research) |
| Agent impossible-travel detector | HIGH | MEDIUM | P1 |
| Per-tenant geo-fencing (alert-only default) | HIGH | MEDIUM | P1 |
| Per-agent metrics history chart (frontend only) | HIGH | LOW-MEDIUM | P1 |
| Uptime timeline + uptime % | HIGH | MEDIUM | P1 |
| Fleet version-drift summary widget | MEDIUM-HIGH | LOW-MEDIUM | P1 |
| Location-history append-only audit trail | HIGH | LOW-MEDIUM | P1 |
| VPN/proxy/hosting-ASN flagging | MEDIUM-HIGH | MEDIUM-HIGH (new data source) | P2 |
| Geo + compliance-posture map overlay | MEDIUM | MEDIUM | P2 |
| MSP-wide fleet rollup dashboard | MEDIUM | MEDIUM | P2 |
| Exportable location-history report | LOW-MEDIUM | MEDIUM | P2 |
| Risk-tiered geo-fence escalation | MEDIUM | MEDIUM | P3 |
| Cross-signal correlated incidents | MEDIUM | HIGH | P3 |
| Predictive resource-trend alerting | LOW (for this milestone) | HIGH | P3 |
| Confidence-scored VPN provider naming | LOW-MEDIUM | HIGH | P3 |

**Priority key:**
- P1: Must have for launch (v3.3 milestone scope)
- P2: Should have, add when possible (v1.x)
- P3: Nice to have, future consideration (v2+)

## Competitor Feature Analysis

| Feature | CrowdStrike Falcon | Elastic Fleet | This Project's Approach |
|---------|---------------------|---------------|---------------------------|
| Geo map | Pre-built WorldMap dashboard, "Active Sensors by Country," Grouping Tags for org/location | Not geo-focused (Fleet is agent-policy-centric, not location-centric) | Country/city marker map with clustering + status color, on top of already-collected `geo`/`publicIp` — closer to CrowdStrike's model than Elastic's |
| Geo-based security detection | Correlates device geolocation with geopolitical/CTI events; no publicly documented per-agent geofencing/impossible-travel product feature found in sources | Not a security-detection product in this sense | Agent-scoped impossible-travel + per-tenant geofencing, integrated with this platform's own existing SIEM/insider-threat surfaces — a genuine differentiator vs. both comparables, which don't combine fleet-geo with security detection in one product |
| VPN/proxy/ASN flagging | Not documented in sources reviewed as a fleet-map feature | Not applicable | New capability via a MaxMind Anonymous IP/Plus-class data source — matches the general fraud/identity-tooling pattern (MaxMind, IPQualityScore) rather than an EDR-specific precedent, since none was found |
| Fleet health/observability | Sensor version/RFM status monitoring, device search by dozens of properties | Agent detail view: CPU/mem, last-checkin, chronological agent-activity log; offline-alerting is a documented, common ask (Kibana community threads) | Per-agent metrics-history chart (data already exists) + uptime timeline/% + version-drift aggregate — directly modeled on Elastic's agent-detail + activity-log shape, reusing already-built offline-detection instead of rebuilding it |
| Location/audit history | Not documented as a standalone audit feature in sources reviewed | Chronological "Agent activity" log exists for policy/config operations, not geo specifically | Purpose-built immutable `agent_geo_history`, cloned from this project's own proven `remediation_escalations` pattern — a project-specific reuse decision, not modeled on either competitor |

## Sources

- [Manage Your Fleet | CrowdStrike Developer Center](https://developer.crowdstrike.com/accomplish/manage-your-fleet/)
- [Geopolitical Intelligence from EDR Sensor Location Data](https://t3l3m3try.medium.com/geopolitical-intelligence-from-edr-sensor-location-data-33b29313d118)
- [Fleet | Deploy CrowdStrike with Fleet](https://fleetdm.com/guides/deploying-crowdstrike-with-fleet)
- [Monitor Elastic Agents | Elastic Docs](https://www.elastic.co/docs/reference/fleet/monitor-elastic-agent)
- [How to Alert When Elastic Agent Goes Offline? — Kibana Discuss](https://discuss.elastic.co/t/how-to-alert-when-elastic-agent-goes-offline/379222)
- [Elastic Fleet: Alert on Agent Status — Kibana Discuss](https://discuss.elastic.co/t/elastic-fleet-alert-on-agent-status/333502)
- [Geofencing for Access Control: Setting Digital Boundaries](https://faisalyahya.com/access-control/geofencing-for-access-control-setting-digital-boundaries/)
- [Geofencing in Cybersecurity: Setup, Use Cases & Troubleshooting](https://www.thelasttech.com/post/geofencing-in-cybersecurity)
- [Strengthening Your Security Perimeter: Geofencing in Conditional Access Policies](https://www.r3-it.com/blog/geofencing-conditional-access-policies/)
- [Geofencing: IAM Policy — LastPass](https://www.lastpass.com/features/security-policies/geofencing)
- [GeoIP® Anonymous IP database | MaxMind](https://www.maxmind.com/en/geoip-anonymous-ip-database)
- [GeoIP® Anonymous Plus database | MaxMind](https://www.maxmind.com/en/geoip-anonymous-plus-database)
- [Proxy detection and anonymous IP | MaxMind Support](https://support.maxmind.com/knowledge-base/articles/anonymizer-and-proxy-data-maxmind)
- [GeoIP Anonymous IP binary database fields | MaxMind Developer Portal](https://dev.maxmind.com/geoip/docs/databases/anonymous-ip/binary/)
- [Protomaps — Self Hosted Maps and Map Tiles](https://thejeshgn.com/2021/05/25/protomaps-self-hosted-maps-and-map-tiles/)
- [Offline Maps with Leaflet.js](https://xerocrypt.github.io/articles/offline-maps.html)
- [Offline Geospatial Maps: Building a No-Internet Tile Server](https://dev.to/ben_var_551c679bfe4787c4f/offline-geospatial-maps-building-a-no-internet-tile-server-10gh)
- Codebase read directly (HIGH confidence, not web-sourced): `backend/geoip_service.py`, `backend/agent_heartbeat_endpoints.py`, `backend/agent_metrics_endpoints.py`, `backend/app_background_tasks.py`, `backend/itdr_service.py`, `backend/insider_threat_service.py`, `backend/agent_quarantine_endpoints.py`, `backend/compliance_remediation_sla_service.py`, `backend/compliance_remediation_sla_endpoints.py`, `components/AgentList.tsx`, `components/AgentsDashboard.tsx`, `package.json` (recharts dependency)

---
*Feature research for: agent geo & fleet-observability platform features (v3.3 milestone)*
*Researched: 2026-07-29*
