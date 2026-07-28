# Requirements: v3.3 — Agent Geo & Fleet Observability

**Milestone goal:** Turn the agent `publicIp` + `geo` data landed in v3.2 into a full geo + observability surface — a fleet geo map, location-based security detectors, fleet observability, and an immutable location-history audit trail. Offline-first (air-gapped safe) throughout.

**Numbering:** continues from the v3.2 milestone. Phases start at **46**.

---

## v3.3 Requirements

### Geo Map (GMAP)

- [ ] **GMAP-01**: An admin can view a fleet map of agent locations, with markers placed by city/country from each agent's `geo` data. The map renders fully self-contained (bundled TopoJSON/SVG — no external tile servers) so it works in air-gapped deployments.
- [ ] **GMAP-02**: The fleet map clusters dense/overlapping markers and can be filtered by tenant and by agent status (online/offline/error/quarantined).
- [ ] **GMAP-03**: Clicking a map marker drills into the agent — showing identity (hostname), LAN + public IP, resolved location, and current status.

### Location Security (GSEC)

- [ ] **GSEC-01**: An agent's public IP is enriched with a heuristic VPN/proxy/hosting flag (AS-org from GeoLite2-ASN + X4BNet public VPN IP-range lists, bundled offline) and the flag is surfaced on the agent. UI labels it as a heuristic ("likely VPN/hosting"), never an authoritative "detected".
- [ ] **GSEC-02**: Agent-scoped impossible-travel detection raises an alert when an agent's consecutive check-ins come from two locations too far apart for the elapsed time (haversine + time window, keyed by `agent_id`), reusing the existing alert/notification fan-out.
- [ ] **GSEC-03**: A tenant admin can define allowed regions (geo-fence); an agent check-in from outside the allowed regions raises an alert. v3.3 is **alert-only** — no connection blocking.

### Fleet Observability (FOBS)

- [ ] **FOBS-01**: An admin can view an agent's CPU / memory / disk history as charts (consuming the existing `GET /agents/{id}/metrics/history` endpoint via the already-installed `recharts`).
- [ ] **FOBS-02**: An admin can see a per-agent heartbeat/uptime timeline and an uptime % over a selectable range.
- [ ] **FOBS-03**: An admin can see a fleet-level view of offline agents and agent version-drift (which agents lag the latest version).

### Location Audit (GAUD)

- [ ] **GAUD-01**: Every change to an agent's public IP / geo is recorded in an immutable, append-only location-history collection (change detected cheaply against the already-fetched agent doc on heartbeat; append-only pattern cloned from `remediation_escalations`).
- [ ] **GAUD-02**: An admin can view a per-agent location-history timeline (chronological IP/geo changes with timestamps).

---

## Future Requirements (deferred)

- **Paid MaxMind GeoIP2 Anonymous IP** upgrade — authoritative VPN/proxy/hosting/Tor classification (`is_anonymous_vpn`, `is_hosting_provider`, `is_public_proxy`, `is_residential_proxy`, `is_tor_exit_node`) via the same `maxminddb` reader. Upgrades GSEC-01 from heuristic to authoritative if a MaxMind license is procured.
- **Geo-fence block enforcement** — reject/quarantine out-of-region agents (v3.3 is alert-only).
- **Street-level map** — MapLibre GL + self-hosted PMTiles for precise pan/zoom (v3.3 uses country/city SVG only).
- **Native time-series rollups** — migrate uptime/metrics history to MongoDB native time-series collections if retention ranges outgrow the current cap.

## Out of Scope

- **Real-time GPS / precise device location** — agents report IP only; GeoIP lat/long is a coarse city centroid. Implying precision is a legal/UX risk (see PITFALLS.md).
- **External tile servers / live IP-intel APIs at runtime** — breaks air-gapped deployments; all geo data is bundled or supplied as an offline `.mmdb`.
- **Rebuilding offline-agent detection or version tracking** — `monitor_agent_status()` and `AgentList` upgrade flows already exist; v3.3 only adds the aggregate UI.

---

## Traceability

| Requirement | Phase | Status |
|-------------|-------|--------|
| GMAP-01 | — | Planned |
| GMAP-02 | — | Planned |
| GMAP-03 | — | Planned |
| GSEC-01 | — | Planned |
| GSEC-02 | — | Planned |
| GSEC-03 | — | Planned |
| FOBS-01 | — | Planned |
| FOBS-02 | — | Planned |
| FOBS-03 | — | Planned |
| GAUD-01 | — | Planned |
| GAUD-02 | — | Planned |

**Coverage:**

- v3.3 requirements: 11 total (GMAP-01/02/03, GSEC-01/02/03, FOBS-01/02/03, GAUD-01/02), 0 complete — roadmap defined 2026-07-29. Phase mapping filled by the roadmapper.

*Last updated: 2026-07-29 — v3.3 requirements defined (VPN detection scoped to free heuristic GeoLite2-ASN + X4BNet; geo-fence alert-only).*
