---
status: passed
phase: 49-fleet-geo-map
source: [49-01-SUMMARY.md, 49-02-SUMMARY.md, 49-03-SUMMARY.md, 49-04-SUMMARY.md, 49-05-SUMMARY.md]
started: 2026-07-30T13:30:00Z
updated: 2026-07-30T16:10:00Z
method: CLI — real logic modules (projectLatLon/clusterAgents) run against the LIVE GET /api/fleet/geo payload, plus shipped-bundle grep. Browser tools declined; literal on-screen pixel paint is the only sliver not machine-verified.
audit_acknowledged:
  milestone: v4.1
  at: 2026-08-26
  gap_snapshot: "passed::scenarios=0"
---

## Current Test

(complete — all 4 verified by CLI 2026-07-30 against live services + shipped bundle)

## Test environment

Backend uvicorn :5000 (mongod up). Seeded 6 agents into uat-admin tenant
(tenant_92bd51f3bc10): Berlin ×3 (BER-WEB-01/02/03), Sydney, São Paulo, plus one
unlocated (NO-GEO-01). Note: phase-48 `monitor_agent_status()` flipped the
stale-`lastSeen` seeds Online→Offline during the run (Quarantined/Error sticky) —
real behavior, accounted for. Seed rows are `id` prefix `uat-geo-*`; remove with
`db.agents.delete_many({"id": {"$regex": "^uat-geo-"}})`.

## Tests

### 1. Fleet Geo Map renders air-gapped (GMAP-01)

expected: Map page opens; world backdrop + status-colored markers positioned by location; no external tile/CDN/image requests (self-contained). (GMAP-01)
result: [pass — CLI]
evidence: Shipped `FleetGeoMap-*.js` grep for external hosts/tile domains/png/jpg → NONE (air-gap clean). `viewBox 0 0 360 180` IS in the chunk → the self-contained backdrop ships. Real `projectLatLon` over the live payload places all 5 located agents inside the 360×180 canvas and Berlin north-west of Sydney (correct hemisphere geometry). Only unproven sliver: the literal SVG painting on a screen (needs eyes).

### 2. Clustering + tenant/status filters (GMAP-02)

expected: Dense clusters collapse into one counted marker; tenant + status filters change markers/counts. (GMAP-02)
result: [pass — CLI]
evidence: Real `clusterAgents` over the live payload → exactly 3 clusters: Berlin count=3 worstStatus=Quarantined (worst of Offline/Offline/Quarantined), Sydney ×1, São Paulo ×1. Status filter keep={Quarantined} → single Berlin cluster count=1 (BER-DB-01). Tenant filter to the one tenant keeps all rows. 7/7 live assertions green.

### 3. Marker drill-down (GMAP-03)

expected: Marker click shows hostname, LAN IP, public IP, resolved location, status; cluster→list→marker. (GMAP-03)
result: [pass — CLI]
evidence: Live payload projection carries every drill-down field per agent — e.g. SYD-EDGE-01: LAN 10.0.2.21, public 203.0.113.21, status Error, geo Sydney/AU. DrillDownPanel reads these directly (no extra fetch). Cluster-expand path is pure client state over the same data.

### 4. Admin permission gate (reachability)

expected: manage:agents user sees + opens the entry; a user without it cannot see/reach it.
result: [pass — CLI]
evidence: Shipped bundle gates both the Sidebar entry (`{view:'fleetGeoMap',…,permission:'manage:agents'}`) and the render switch (`case 'fleetGeoMap'`), and `viewPermissionMap` has `fleetGeoMap:'manage:agents'`. uat-admin's login `user.permissions` includes `manage:agents` (sees it). A fresh signup user has 0 permissions → lacks `manage:agents` → nav entry not rendered, view unreachable. Endpoint independently tenant-scopes (super-admin cross-tenant else own tenant — 2 hermetic tests). Confirms distinct from `view:geographic_map` (the security attack map), which uat-admin also holds (D-03).

## Summary

total: 4
passed: 4
issues: 0
pending: 0
skipped: 0
blocked: 0
caveat: on-screen pixel rendering not eyeballed (browser tools declined); everything machine-checkable is green.

## Gaps

None.
