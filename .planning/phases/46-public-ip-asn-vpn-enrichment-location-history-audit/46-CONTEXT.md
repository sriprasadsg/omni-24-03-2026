# Phase 46: Public-IP ASN/VPN Enrichment + Location-History Audit - Context

**Gathered:** 2026-07-29
**Status:** Ready for planning

<domain>
## Phase Boundary

Deliver an immutable, per-agent public-IP/geo **location-history audit trail** (GAUD-01/02) and the **heuristic ASN/VPN enrichment foundation** (GeoLite2-ASN + X4BNet) that Phase 47's security detectors depend on. Front-loads the milestone's two biggest risks: false positives (build enrichment before detectors) and privacy/legal (retention + opt-out decided before data accumulates).

**In scope:** append-only `agent_location_history` collection + change-detection on heartbeat; per-agent timeline view (GAUD-02); ASN/VPN heuristic enrichment stored on the agent doc; retention + per-tenant privacy toggle.
**Out of scope (later phases):** impossible-travel/geo-fence detectors (Phase 47), fleet map (Phase 49), observability charts (Phase 48), paid MaxMind Anonymous IP upgrade, geo-fence *blocking*.
</domain>

<decisions>
## Implementation Decisions

### Retention & Privacy Posture
- **D-01:** Location-history retention = **365 days**, routed through the **existing retention module** (do NOT hardcode a TTL; do NOT inherit the 30-day `agent_metrics_history` convention).
- **D-02:** Per-tenant **`track_agent_location` toggle** (default **ON**) — a tenant can disable agent location tracking for works-council/GDPR reasons. When OFF, no location-history rows are written and enrichment is skipped for that tenant.
- **D-03:** Add a short **disclosure note** in the relevant settings surface explaining what is tracked and why (employee-device IP/geo).
- **D-04:** Retention/privacy is a **pre-implementation gate** — this decision must be reflected before data starts accumulating (per PITFALLS.md Pitfall 5 / 2).

### Change Detection (what writes a row)
- **D-05:** Write a new `agent_location_history` row when **`publicIp` OR resolved city/country changes** vs the last recorded entry — compared against the `existing_agent` doc already fetched on heartbeat (no extra read).
- **D-06:** **De-noise NAT flip-flop** — a public IP that recurs within a short window (~10 min) collapses to one row rather than writing a row on every flip. Exact window is a planning/tuning detail.
- **D-07:** Volume tracks **IP/geo changes, not heartbeat frequency** (success criterion 3).

### Location-History Timeline (GAUD-02)
- **D-08:** New **`AgentLocationHistory` panel in the agent detail view** — same shape/placement as the existing `EscalationHistoryPanel` in `RemediationTaskModal`.
- **D-09:** Each row shows: **country flag + city/country**, **public IP**, **VPN/hosting badge** (heuristic — labelled "likely VPN/hosting", never "detected"), **timestamp**, and **dwell time** (how long the agent stayed at that location).
- **D-10:** Read-only — no edit/delete UI (matches the append-only API).

### ASN/VPN Data Packaging
- **D-11:** **GeoLite2-ASN.mmdb** loaded via a new **`GEOIP_ASN_DB_PATH`** env var, mirroring the existing City DB pattern in `geoip_service.py` (supplied out-of-band; graceful degradation when absent).
- **D-12:** **X4BNet** public-VPN IP-range lists shipped as a **bundled snapshot in the repo**, refreshed at release time (works air-gapped; no runtime fetch).
- **D-13:** Enrichment stored on the agent doc under **`geo.asn`** (AS number + org name) and **`geo.vpn_heuristic`** (boolean/label). Enrichment runs **inline** at the same spot as `geoip_service.lookup()` in the heartbeat/register handlers (new sibling module, e.g. `agent_asn_service.py`).

### Claude's Discretion
- Exact NAT-flip de-dup window value, index shapes, and the precise `agent_location_history` document schema (planner/executor decide, following the `remediation_escalations` shape).
- Whether ASN + VPN enrichment lands in one `agent_asn_service.py` module or two — implementation detail.
</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Milestone research (this phase's basis)
- `.planning/research/SUMMARY.md` — phase 46 rationale, build order, risks.
- `.planning/research/ARCHITECTURE.md` — inline-enrichment integration point, cheap change-detection, append-only clone, scheduler notes.
- `.planning/research/PITFALLS.md` — §Pitfall 2 (privacy/legal), §Pitfall 5 (ISO-string TTL no-op — use BSON Date), §Pitfall 1 (raw `mongodb.db` for any sweep), §false-positives.
- `.planning/research/STACK.md` — GeoLite2-ASN vs paid Anonymous IP; X4BNet; maxminddb reader reuse.

### Requirements
- `.planning/REQUIREMENTS.md` — GAUD-01, GAUD-02 (+ Future/Out-of-Scope framing).
- `.planning/ROADMAP.md` §"Phase 46" — goal + 4 success criteria.

### Code patterns to clone/extend (see code_context)
- `backend/geoip_service.py` — mirror for the ASN reader (`GEOIP_ASN_DB_PATH`, graceful degrade, private-IP skip).
- `backend/compliance_remediation_sla_service.py` / `remediation_escalations` — append-only audit pattern to clone.
- `backend/agent_heartbeat_endpoints.py` (+ `agent_registry_endpoints.py`) — the inline geo enrichment + `existing_agent` fetch where change-detection hooks in.
- Retention module: `backend/retention_endpoints.py` / `retention_tiers_endpoints.py` — route the 365-day policy here.
</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `geoip_service.py`: exact template for `agent_asn_service.py` (lazy `.mmdb` open via env path, `_is_public()` skip, graceful None on missing DB).
- `EscalationHistoryPanel.tsx` (in `RemediationTaskModal.tsx`): the read-only append-only timeline panel shape to clone for `AgentLocationHistory`.
- `remediation_escalations` collection + its GET-only endpoint: the append-only audit + no-mutation-route pattern.
- `flagEmoji`/`formatGeo` helpers already in `components/AgentList.tsx` — reuse for timeline rows.

### Established Patterns
- Inline enrichment in `report_heartbeat()` / registration already calls `geoip_service.lookup()`; `existing_agent` is fetched just above — change-detection compares against it with zero extra reads.
- Retention routed through the dedicated retention module (not per-collection hardcoded TTL).
- Tenant isolation via the `TenantIsolatedDatabase` wrapper; any background work must use raw `mongodb.db` (PITFALLS §1).

### Integration Points
- New `agent_location_history` collection (append-only) — written from the heartbeat/register enrichment path.
- New `agent_asn_service.py` — called alongside `geoip_service.lookup()`.
- New read-only GET endpoint for a given agent's location history → new frontend panel.
- Per-tenant `track_agent_location` setting gates writes + enrichment.
</code_context>

<specifics>
## Specific Ideas

- VPN badge copy must read as heuristic ("likely VPN/hosting"), never authoritative "detected" — the free GeoLite2-ASN + X4BNet path is not a licensed anonymizer feed.
- Timeline entry includes **dwell time** at each location (not just the change timestamp) — that was the chosen entry content.
</specifics>

<deferred>
## Deferred Ideas

- **Paid MaxMind GeoIP2 Anonymous IP** upgrade (authoritative VPN/proxy/Tor) — Future Requirement; upgrades GSEC-01 if a license is procured.
- **Geo-fence blocking** and **impossible-travel** — Phase 47.
- **Native MongoDB time-series** migration for history if 365d/volume outgrows the approach — Future Requirement.

None of the discussion strayed outside the phase scope.
</deferred>

---

*Phase: 46-public-ip-asn-vpn-enrichment-location-history-audit*
*Context gathered: 2026-07-29*
