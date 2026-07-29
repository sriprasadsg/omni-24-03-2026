---
status: testing
phase: 46-public-ip-asn-vpn-enrichment-location-history-audit
source: [46-VERIFICATION.md]
started: 2026-07-29T14:15:00Z
updated: 2026-07-29T14:15:00Z
---

## Current Test

number: 1
name: Location History panel renders in a live browser
expected: |
  Open an agent's detail view (Overview tab) after a real public-IP/geo change and expand
  the Location History panel. Panel lazy-fetches on first expand and renders one row per
  recorded change: country flag + city/country, optional amber "likely VPN/hosting" badge,
  monospace public IP, UTC timestamp, and dwell time; last row suffixed "(ongoing)".
awaiting: user response

## Tests

### 1. Location History panel renders in a live browser
expected: Panel lazy-fetches on first expand and renders one row per recorded change — country flag + city/country, optional amber "likely VPN/hosting" badge, monospace public IP, UTC timestamp, dwell time; last row suffixed "(ongoing)". No edit/delete affordance.
result: [pending]

### 2. Real GeoLite2-ASN.mmdb enrichment populates geo.asn / geo.vpn_heuristic
expected: Supply a licensed GeoLite2-ASN.mmdb via GEOIP_ASN_DB_PATH; on a live agent heartbeat, agent_asn_service.lookup() returns a populated asn sub-object (number/org) for a real public IP, in addition to the vpn_heuristic flag already exercised by the hermetic tests.
result: [pending]

## Summary

total: 2
passed: 0
issues: 0
pending: 2
skipped: 0
blocked: 0

## Gaps
