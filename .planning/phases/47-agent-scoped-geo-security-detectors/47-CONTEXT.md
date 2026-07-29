# Phase 47: Agent-Scoped Geo Security Detectors - Context

**Gathered:** 2026-07-29
**Status:** Ready for planning

<domain>
## Phase Boundary

Turn Phase 46's geo/ASN enrichment and location-history into **alert-only** location security signal for tenant admins:

- **GSEC-01** — surface the heuristic VPN/proxy/hosting flag on the agent, always labeled "likely VPN/hosting", never authoritative "detected".
- **GSEC-02** — agent-scoped impossible-travel detection (haversine + time window, keyed by `agent_id`), reusing the existing alert fan-out.
- **GSEC-03** — per-tenant allowed-region geo-fence; out-of-region check-in raises an alert.

**Alert-only for v3.3** — no connection blocking, no quarantine. Detectors run on the check-in path, reusing existing infrastructure — never a parallel alert channel.

</domain>

<decisions>
## Implementation Decisions

### Impossible-Travel (GSEC-02)
- **D-01:** Threshold is a **fixed max speed of ~1000 km/h** (commercial-flight ceiling). Two consecutive check-ins for one `agent_id` whose haversine distance ÷ elapsed time exceeds this raises the alert. Not per-tenant configurable in v3.3 (keep config surface minimal; revisit if tenants ask).
- **D-02:** **Suppress the impossible-travel alert entirely when either endpoint carries the VPN/hosting heuristic flag.** This is the load-bearing GSEC-01→GSEC-02 link — corporate-VPN egress is the dominant false-positive source, and the goal explicitly front-loads killing it. (No downgraded/low-severity alert — full suppression.)

### Geo-Fence (GSEC-03)
- **D-03:** Allowed regions are a **country-code allowlist (ISO 3166 alpha-2)**. The check-in country is already resolved by `geoip_service` — compare against the tenant's allowlist; not-in-list → alert. No region/state or radius/coordinate fencing in v3.3.
- **D-04:** Alert-only — a violation raises an alert and does nothing to the connection (no reject, no quarantine). Deferred: block enforcement.

### Alert Noise Control (GSEC-02 + GSEC-03)
- **D-05:** **Dedup per (agent_id, violation_type) on state transition + cooldown window.** Fire one alert when the violation state changes (clean→violating), then suppress repeats within a cooldown window (default **6h**) even if every heartbeat keeps violating. Model the transition/de-noise after Phase 46's `record_location_change` state-machine idea — alert volume tracks violations, not heartbeat frequency.

### Config Surface (UI — GSEC-03)
- **D-06:** Geo-fence allowed-regions + detector on/off live in a **new admin-gated Security settings panel** (separate from Phase 46's PrivacyDashboard — keep security config distinct from privacy). Per-tenant config stored via the existing `system_settings` type-keyed doc pattern (clone of `track_agent_location`), admin-gated GET/PATCH like the 46 toggle endpoints.

### Claude's Discretion
- Alert `alert_type` strings and `severity` values fed to `persist_security_alert` (suggest `impossible_travel` / `geo_fence_violation`; severity `high` / `medium`) — planner/executor choose, consistent with existing UEBA alert taxonomy.
- Exact detector placement in the heartbeat handler (inline alongside 46's `record_location_change`, toggle-gated) — architecture detail for planning.
- Cooldown-window storage mechanism (agent shadow field vs dedicated collection) — planner decides.

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Requirements & Roadmap
- `.planning/REQUIREMENTS.md` §Location Security (GSEC) — GSEC-01/02/03 definitions + the paid MaxMind GeoIP2 Anonymous-IP upgrade and geo-fence-block deferrals.
- `.planning/ROADMAP.md` §Phase 47 — goal, success criteria, dependency on Phase 46.

### Phase 46 foundation (dependency)
- `.planning/phases/46-public-ip-asn-vpn-enrichment-location-history-audit/46-CONTEXT.md` — locked decisions for ASN/VPN enrichment + location-history (D-02 default-ON toggle, retention).
- `backend/agent_asn_service.py` — `lookup(ip)` returns the `vpn_heuristic` flag GSEC-01/02 consume.
- `backend/agent_location_history_service.py` — `record_location_change` + `get_track_agent_location`; "previous known geo" source for impossible-travel; de-noise state-machine to model D-05 on.
- `backend/geoip_service.py` — resolves check-in country for GSEC-03.

### Alert fan-out (reuse — do not rebuild)
- `backend/ueba_service.py` — `persist_security_alert(db, alert_type=…, severity=…)`, the existing fan-out invoked inline from the heartbeat handler.
- `backend/agent_heartbeat_endpoints.py` — existing `persist_security_alert` call sites (shadow_ai, ueba_anomaly, fim_violation) show the inline pattern to follow.

### Config pattern (reuse)
- `backend/agent_location_history_endpoints.py` — admin-gated GET/PATCH toggle endpoints (clone for the new Security settings panel).
- `system_settings` collection, type-keyed docs (e.g. `track_agent_location`) — per-tenant config storage pattern.

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `ueba_service.persist_security_alert(db, alert_type, severity)` — the alert fan-out both detectors MUST reuse (success criteria are explicit about not building a parallel channel).
- `agent_asn_service.lookup()` `vpn_heuristic` flag — the D-02 suppression input.
- `agent_location_history_service` — previous-geo source + de-noise pattern for D-05 dedup.
- `agent_location_history_endpoints.py` admin-gated toggle — template for the Security settings config endpoints.

### Established Patterns
- Detectors invoked inline in `agent_heartbeat_endpoints.py`, toggle-gated (same spot 46 wired `record_location_change`).
- Per-tenant config via `system_settings` type-keyed docs, admin-gated GET/PATCH.
- UI: "likely VPN/hosting" heuristic labeling convention already set in Phase 46 (`AgentLocationHistory.tsx` amber badge) — GSEC-01 reuses it.

### Integration Points
- Heartbeat handler: after `record_location_change`, run impossible-travel + geo-fence checks (toggle-gated), call `persist_security_alert` on violation (post-dedup).
- New Security settings panel (frontend) + admin-gated config endpoints (backend) for the allowed-region allowlist and detector toggles.

</code_context>

<specifics>
## Specific Ideas

- ~1000 km/h is the deliberate impossible-travel ceiling (commercial-flight speed) — not a tunable in v3.3.
- 6h default cooldown for dedup — a starting value, planner may refine.
- VPN suppression is full suppression, not a severity downgrade — the goal treats corporate-VPN false positives as the #1 risk to eliminate.

</specifics>

<deferred>
## Deferred Ideas

- **Paid MaxMind GeoIP2 Anonymous-IP** upgrade — authoritative VPN/proxy/hosting/Tor classification; upgrades GSEC-01 from heuristic to authoritative if a license is procured. (Already noted in REQUIREMENTS.md.)
- **Geo-fence block enforcement** — reject/quarantine out-of-region agents. v3.3 is alert-only. (Already noted in REQUIREMENTS.md.)
- **Per-tenant configurable impossible-travel threshold** — revisit if tenants request it; fixed 1000 km/h for now.
- **Region/state or radius geo-fencing** — finer granularity beyond country-code allowlist.

None else — discussion stayed within phase scope.

</deferred>

---

*Phase: 47-agent-scoped-geo-security-detectors*
*Context gathered: 2026-07-29*
