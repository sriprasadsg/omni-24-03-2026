# Phase 46 Discussion Log

**Date:** 2026-07-29
**Mode:** discuss (default)
**For:** human reference only — not consumed by downstream agents (see 46-CONTEXT.md for the canonical decisions).

## Areas selected for discussion
Retention & privacy posture · What counts as a "change" · Timeline view (GAUD-02) · ASN/VPN data packaging (all four).

## Decisions

### Retention & privacy posture
- **Options presented:** 365d + per-tenant opt-out (rec) · 180d + opt-out · Indefinite + opt-out · 90d always-on.
- **Chosen:** 365d via existing retention module + per-tenant `track_agent_location` toggle (default ON) + disclosure note.
- **Note:** treated as a pre-implementation privacy/legal gate (PITFALLS §2/§5).

### What counts as a "change"
- **Options presented:** IP or geo change (rec) · IP only · IP/geo/VPN-flag.
- **Chosen:** write a row on publicIp OR city/country change; de-noise NAT flip-flop within ~10 min. Volume tracks changes, not heartbeats.

### Timeline view (GAUD-02)
- **Options presented:** Panel in agent detail (rec) · Separate tab · Panel + mini on card.
- **Chosen:** new `AgentLocationHistory` panel in agent detail (clone `EscalationHistoryPanel`); rows = flag + city/country, public IP, VPN/hosting badge (heuristic), timestamp, dwell time. Read-only.

### ASN/VPN data packaging
- **Options presented:** Droppable path + bundled X4BNet (rec) · All bundled in image · ASN only, defer X4BNet.
- **Chosen:** GeoLite2-ASN.mmdb via `GEOIP_ASN_DB_PATH` (mirrors City DB, out-of-band); X4BNet lists bundled snapshot in repo; flags stored under `geo.asn` / `geo.vpn_heuristic`; enrichment inline via new `agent_asn_service.py`.

## Claude's discretion
- NAT-flip de-dup window value, index shapes, exact `agent_location_history` schema, one-vs-two enrichment modules.

## Deferred (out of phase scope)
- Paid MaxMind Anonymous IP upgrade · geo-fence blocking + impossible-travel (Phase 47) · native time-series migration.

No scope creep occurred.
