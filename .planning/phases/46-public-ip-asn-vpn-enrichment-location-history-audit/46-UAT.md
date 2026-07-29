---
status: complete
phase: 46-public-ip-asn-vpn-enrichment-location-history-audit
source: [46-VERIFICATION.md]
started: 2026-07-29T14:15:00Z
updated: 2026-07-29T14:30:00Z
---

## Current Test

[testing complete]

## Tests

### 1. Location History panel renders in a live browser
expected: Panel lazy-fetches on first expand and renders one row per recorded change — country flag + city/country, optional amber "likely VPN/hosting" badge, monospace public IP, UTC timestamp, dwell time; last row suffixed "(ongoing)". No edit/delete affordance.
result: pass
note: Accepted on code + build evidence (component mounted in AgentOverviewTab.tsx:215, wired to GET endpoint, no mutation affordance, amber badge, tsc --noEmit + npm run build clean). Live pixel render is deploy-time; user chose to proceed.

### 2. Real GeoLite2-ASN.mmdb enrichment populates geo.asn / geo.vpn_heuristic
expected: Supply a licensed GeoLite2-ASN.mmdb via GEOIP_ASN_DB_PATH; on a live agent heartbeat, agent_asn_service.lookup() returns a populated asn sub-object (number/org) for a real public IP, in addition to the vpn_heuristic flag already exercised by the hermetic tests.
result: skipped
reason: Requires a licensed MaxMind GeoLite2-ASN database supplied out-of-band at deploy time. Graceful-degrade path (no DB present) is unit-tested; real-DB enrichment is a deploy-time verification.

## Summary

total: 2
passed: 1
issues: 0
pending: 0
skipped: 1
blocked: 0

## Gaps

[none]
