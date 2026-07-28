# Pitfalls Research — v3.3 Agent Geo & Fleet Observability

**Domain:** Adding fleet geo-map, location-based security, fleet observability, and location-history audit to an existing multi-tenant FastAPI/MongoDB/React GRC platform
**Researched:** 2026-07-29
**Confidence:** HIGH — every pitfall below is grounded in this repo's actual source (file/line cited); MEDIUM on GDPR/works-council jurisdictional specifics (flagged for legal review, not settled here)

**Method note:** Verified against `backend/geoip_service.py`, `backend/agent_heartbeat_endpoints.py`, `backend/agent_metrics_endpoints.py`, `backend/database.py` (`TenantIsolatedCollection`/`TenantIsolatedDatabase`), `backend/tenant_context.py`, `backend/tenant_middleware.py`, `backend/agent_auth.py`, `backend/itdr_service.py`, `backend/siem_endpoints.py`, `backend/insider_threat_service.py`, `backend/compliance_remediation_sla_service.py`, `backend/migrations/002_scale_indexes.py`, `frontend/package.json`, `.planning/PROJECT.md`, and the prior milestone's `.planning/research/PITFALLS.md` (v3.2, which already documents a proven background-scheduler tenant-isolation bug for `compliance_remediation_sla_service` — directly relevant here and corroborated below).

## Critical Pitfalls

### Pitfall 1: Offline-agent alerting / fleet-wide sweep jobs silently see zero agents for every tenant (repeat of an already-proven bug in this codebase)

**What goes wrong:**
Fleet observability requires detecting "this agent hasn't heartbeated in N minutes" — by definition that can't be evaluated inside a heartbeat request (an offline agent sends no request), so it must run as a periodic background sweep across the whole `agents`/`agent_metrics_history` fleet. If that sweep is written the "obvious" way — `db = get_database(); await db.agents.find({...}).to_list(...)` — it will run forever without errors and detect **zero** offline agents, for every tenant, always.

**Why it happens:**
`get_database()` returns a `TenantIsolatedDatabase` (`backend/database.py`). Every non-exempt collection (and `agents`/`agent_metrics_history` are **not** in the exemption allowlist at lines 123-134/140-150) gets wrapped in `TenantIsolatedCollection`, whose `_inject_tenant_id()` reads `get_tenant_id()` from a request-scoped `ContextVar` (`tenant_context.py`). A background `asyncio` task started outside an HTTP request has no `TenantMiddleware` dispatch around it, so `get_tenant_id()` returns `None`. Fail-closed logic then substitutes `"NON_EXISTENT_TENANT_ISOLATION_EMERGENCY"` into every `find`/`count_documents` call, and the `aggregate()` wrapper (database.py lines 92-104) prepends `{"$match": {"tenantId": effective_tenant_id}}` with that same dummy value to any pipeline — matching nothing, silently, for every tenant.

This is not hypothetical: it is the **exact, already-encountered and already-fixed bug** documented for this milestone's sibling feature in v3.2 (`compliance_remediation_sla_service.run_sla_pass`) and for the pre-existing ticketing system (`tickets_escalation_service.run_escalation_pass`). Both are fixed identically: the scheduler is registered at startup passing the raw, unwrapped `mongodb.db` — never `get_database()`. `compliance_remediation_sla_service.py`'s own comment says it plainly: "the sweep (44-02) always passes raw mongodb.db in." Fleet-observability's offline-alerting/version-drift sweep and location-based-security's fleet-wide impossible-travel/geo-fence evaluation are the same shape of job and will reproduce this bug unless built the same way from day one.

**How to avoid:**
- Wire every new background sweep (offline-agent detection, version-drift batch, fleet-wide geo-fence/impossible-travel evaluation) exactly like `compliance_remediation_sla_service.run_sla_pass` and `tickets_escalation_service.run_escalation_pass`: accept `db` as a parameter, register the scheduler at startup passing `mongodb.db` (raw), and have the sweep function do its own per-document tenant handling (read `tenantId` off each document, never assume ambient context).
- Do **not** add `agents`/`agent_metrics_history` to the `database.py` exemption allowlist as a shortcut — that would remove tenant isolation for those collections on every *request-scoped* endpoint too (much worse than the sweep problem it would "solve").
- Anything computed inside the existing heartbeat request handler (e.g., a per-heartbeat geo/impossible-travel check evaluated synchronously as the heartbeat arrives) is fine with `get_database()` as-is, because `verify_agent_key` (`agent_auth.py`) already calls `set_tenant_id()` before the handler body runs — the contextvar is genuinely populated there. The risk is specifically the *periodic, cross-tenant, no-request* sweep path.

**Warning signs:**
- New offline/version-drift/geo-fence sweep logs "0 flagged" indefinitely despite manually verified offline agents in Mongo.
- A shell query with the correct `tenantId` returns real data; the app-level job sees none.
- `logging.error("[SECURITY ALERT] DB Access without tenant context...")` (database.py line 37) firing repeatedly in logs at the sweep's cadence — this is the visible tell, but it only fires on `insert_one`/`insert_many`, not on `find`/`count_documents`/`aggregate` reads, so a silent read-only sweep won't even log the alert.

**Phase to address:** Fleet observability phase (offline alerting, version drift) and location-based security phase (any fleet-wide impossible-travel/geo-fence evaluation implemented as a sweep rather than per-heartbeat) — both must copy the `mongodb.db`-raw pattern from the very first draft, verified against a real (non-mocked) multi-tenant dataset.

---

### Pitfall 2: Treating GeoLite2 city/lat-long as a precise, presentable location

**What goes wrong:**
MaxMind GeoLite2-City resolves an IP to a *centroid* of a coarse area (commonly tens of km off, sometimes hundreds for mobile/CGNAT ranges) — it is not a device location. The fleet map plots a marker at `geo.latitude/longitude`; if the UI drops a pin at high zoom or captions it "agent location" without qualification, that's a false-precision claim. For a security/compliance product sold on evidentiary rigor, showing a wrong or over-precise location to a customer — worse, feeding it into a geo-fence *decision* that blocks or flags a real device because the centroid landed outside an allowed-region polygon — is both a credibility and a legal-exposure problem.

**Why it happens:**
`geoip_service.lookup()` (lines 89-101) extracts only `country`/`country_code`/`city`/`region`/`latitude`/`longitude` from the mmdb record. MaxMind's format also carries an `accuracy_radius` in the same `location` sub-dict this function already reads — the codebase currently discards it, so nothing downstream can know how much to trust the point.

**How to avoid:**
- Capture and persist `accuracy_radius` alongside the existing `geo` fields (same `location` dict `geoip_service.lookup()` already parses) and surface it in the UI ("±80km") and in geo-fence policy evaluation.
- Render map markers with a radius/blur, not a pinpoint icon, and label them "approximate — IP geolocation" in any tooltip or export.
- Geo-fence and impossible-travel logic should treat country/region as the primary signal; city/lat-long is supporting detail only — never gate a hard block purely on lat/long precision.
- Never present this as "device location" in any exported/audit-facing artifact; use "public IP geolocation (approximate)."

**Warning signs:**
- Map pins rendered as precise dots at high zoom with no radius/uncertainty indicator.
- Geo-fence policy stored as an exact polygon/point-radius check against raw lat/long with no accuracy buffer.
- Support tickets disputing "the map shows my agent in the wrong city."

**Phase to address:** Fleet geo map phase (data contract + rendering) and location-based security phase (geo-fence policy design) — bake the accuracy caveat in from the start.

---

### Pitfall 3: Reusing the user-login impossible-travel pipeline for agents, or wiring UI to `vpn_geo_anomaly` demo data

**What goes wrong:**
This codebase already has two *user-login* geo-anomaly mechanisms that look reusable but are the wrong shape for agent devices:
- `itdr_service.py::on_login_success()` — impossible travel keyed by `email`+`country`, writing to `itdr_login_events`, fired from `authentication_endpoints.py` on human logins (`>800km`/`30min` thresholds).
- SIEM rule `impossible_travel` (`siem_endpoints.py` ~line 551) — `conditions: {"action": "login_success", "pattern": "impossible_travel", ...}`, also authentication-event-shaped.
- `insider_threat_service.py`'s `vpn_geo_anomaly` (line 13) is **seeded/simulated demo data** — a fixed scenario list with fabricated names (e.g., "Bob Martinez," line 58) and static weight/category, not a live detector wired to real telemetry.

The milestone brief asks to "integrate with the existing SIEM impossible-travel rule and insider-threat `vpn_geo_anomaly` — do not duplicate." Taken literally, a developer could (a) try to route agent heartbeat geo through the login-event pipeline (wrong entity — agents aren't users, don't have `email`, heartbeat every few minutes not per-session) or (b) assume `vpn_geo_anomaly` already does real detection and build a UI on its simulated numbers, shipping a feature that displays fabricated risk data as if it were live.

**How to avoid:**
- Do not reuse `itdr_login_events`/`on_login_success` for agents — register a *parallel* rule (same pattern/thresholds, e.g. reuse the `>800km`/window-minutes convention) keyed by `agent_id`/`tenantId` against `geo` deltas in agent telemetry, not user email.
- Add a distinct SIEM rule id (e.g. `agent_impossible_travel`) rather than mutating the existing user-login one — their false-positive profiles differ completely (see Pitfall 4: shared VPN/NAT egress is *normal* for endpoint agents, not for user logins).
- Before wiring UI/alerts to `vpn_geo_anomaly`, confirm with whoever owns insider-threat scoring whether it's still simulated-only. If so, either label it "demo data" explicitly wherever it's surfaced, or replace it with a real detector fed by the new agent geo/location-history data — never silently present seeded fixture data as production risk signal in a new customer-facing view.

**Warning signs:**
- A new endpoint imports from `itdr_service.py` or filters `itdr_login_events` by `agent_id`.
- A fleet-map "risk" badge traces back to `insider_threat_service.py`'s hardcoded scenario list.
- The SIEM rule list shows one ambiguous "impossible travel" entry serving both users and agents.

**Phase to address:** Location-based security phase — resolve explicitly in spec/discuss before implementation; flag for deeper research (confirm current real-vs-simulated status of insider-threat data with its owner).

---

### Pitfall 4: Corporate VPN/CGNAT/shared-egress makes agent impossible-travel and geo-fencing produce constant false positives (or false negatives)

**What goes wrong:**
Endpoint agents behind a corporate VPN, SASE/ZTNA gateway, or shared NAT egress all report the same (or a small rotating pool of) public IP regardless of physical device location — agents in three different cities can geolocate identically. This causes:
- **False negatives:** two genuinely different devices geolocating identically hide a real anomaly (e.g., a compromised agent that actually did travel, masked because it also rides the same VPN egress).
- **False positives:** a VPN with pooled/round-robin egress can flip country/city between heartbeats for the *same* physical device — no travel occurred — triggering "impossible travel." A residential ISP reassigning a DHCP lease overnight has the same effect.
- Geo-fence ("allowed region") policy breaks for any tenant using centralized VPN egress: every agent outside the VPN's egress country gets flagged "out of region" even though the device never left the building.
- Mobile/CGNAT IPs resolve to a carrier's regional aggregation point, not the subscriber — same coarse/wrong-region problem for any cellular-connected endpoint.

**Why it happens:** `geoip_service.py::_is_public()` (lines 61-67) only excludes private/reserved IPs — a corporate VPN egress IP, a VPS jump box, or a CGNAT carrier IP all pass this check and produce a confident-looking but misleading result. Nothing in the pipeline today classifies "this IP belongs to a known VPN/hosting/CGNAT ASN" — that data doesn't exist yet in this codebase.

**How to avoid:**
- Add ASN/IP-type classification (MaxMind GeoLite2-ASN, or a hosting/VPN/proxy reputation feed if license terms allow — see Pitfall 8) *before* building impossible-travel/geo-fence logic, tagging every heartbeat's `geo` with `asn`/`asn_org`/a coarse `ip_type`.
- Suppress or downweight impossible-travel alerts when the source IP is tagged hosting/VPN/known-corporate-egress — surface as informational ("agent reports via corporate VPN egress — geo unreliable"), not a security alert.
- Let tenants allowlist their known VPN/proxy egress ranges or ASNs for geo-fence policy so their whole fleet doesn't spuriously violate the fence on day one.
- Exclude same-ASN/same-egress-prefix transitions from impossible-travel entirely, even if MaxMind's city guess differs between lookups (a single VPN concentrator's city assignment can drift without any real device movement).
- Roll out geo-fence enforcement in alert-only mode first, per tenant, before any blocking behavior — this failure mode is close to guaranteed on first deployment given how common centralized VPN egress is among compliance/MSP customers.

**Warning signs:**
- Alert volume spikes the moment a tenant with centralized VPN egress enables the feature.
- Every agent for a tenant maps to the exact same lat/long on the fleet map (shared egress, not per-device location).
- Geo-fence "violations" cluster around known SASE/VPN provider IP ranges.

**Phase to address:** Location-based security phase — highest-value candidate for deeper phase-specific research (ASN/VPN dataset selection, false-positive suppression heuristics) before writing detection rules.

---

### Pitfall 5: Geolocating and retaining employee-device location history without a privacy/legal basis review

**What goes wrong:**
The new location-history & audit feature computes and stores an append-only, per-agent timeline tied to a public IP that, for remote/WFH endpoints, commonly resolves to an identifiable employee's home/residential location. Continuous location tracking of a company-managed-but-employee-used device is personal-data processing under GDPR (Art. 5/6/9) and, in several jurisdictions (Germany, France, and others with works-council/co-determination regimes), requires a documented legal basis, employee notice, and works-council sign-off *before* deployment. Shipping "location history" as an incremental extension of already-collected `publicIp`/`geo` fields — because the raw data already technically exists on the agent doc — understates the legal difference between *transient, overwritten-each-heartbeat* data (already the v3.2 state) and a *new, persistent, queryable, exportable, immutable audit trail* (the v3.3 requirement).

**Why it happens:** `publicIp`/`geo` are already collected and overwritten every heartbeat (v3.2), so extending that into a persisted, queryable "location history" looks like a small technical lift — mostly a new append-only collection plus UI — and is easy to underestimate as a privacy-review trigger, especially since the underlying IP-collection mechanism isn't new.

**How to avoid:**
- Get a privacy/legal review before building the history collection: identify the legal basis (legitimate interest for security monitoring is common but must be documented and balanced against employee privacy; a DPIA is likely warranted under GDPR Art. 35 given "systematic monitoring" at fleet scale).
- Give tenants (the data controller for their own employees) a retention control and a way to export/delete an individual's location history on request — the platform is the processor and needs to make tenant-side GDPR Art. 15/17 compliance possible.
- Precision minimization: store city/region/country in the persisted history by default; only store precise lat/long if a tenant explicitly opts in for a documented security reason (this also reduces the false-precision exposure from Pitfall 2).
- Confirm the agent is only ever installed on company-managed endpoints per the existing deployment model — if BYOD is in scope anywhere, that's a substantially harder consent problem to resolve before shipping this.

**Warning signs:**
- No DPIA/privacy-review ticket exists before implementation starts.
- Retention is hardcoded to "forever" (matching "immutable audit trail" language) with no per-tenant configurability or subject-access/delete path.
- Precise lat/long (not just city/region) stored in the long-lived history collection by default.

**Phase to address:** Location history & audit phase — scope and legally review *before* implementation, ideally as a pre-phase spec/discuss step. Flag for deeper phase-specific research (jurisdiction-specific: GDPR/works-council for EU tenants; relevant US state location/biometric-privacy statutes if applicable).

---

### Pitfall 6: Cloning `agent_metrics_history`'s ISO-string timestamp pattern for new time-series collections — the existing TTL index is likely already a silent no-op

**What goes wrong:**
`migrations/002_scale_indexes.py` (lines 51-58) creates a TTL index on `agent_metrics_history.timestamp` with `expireAfterSeconds=30*24*3600`, commented "auto-expire records older than 30 days to bound collection growth." But `agent_heartbeat_endpoints.py` (line 181) writes that field as `datetime.now(timezone.utc).isoformat()` — a BSON **string**, not a BSON **Date**. MongoDB TTL indexes only expire documents whose indexed field is a `Date`; on a string field, the index exists, looks healthy in `getIndexes()`, but **never expires anything**. The only thing actually bounding `agent_metrics_history` growth today is the heartbeat handler's manual "count > 100 → delete oldest" logic (lines 184-190) — the TTL index appears to be dead code, giving false confidence that growth is bounded two ways when only one mechanism actually works.

If fleet-observability or location-history collections clone this exact pattern (ISO string + a TTL index, "because that's how `agent_metrics_history` does it"), the new collections get the same silent no-op — and unlike `agent_metrics_history`, an **immutable, append-only** location-history trail has no equivalent per-agent manual cap catching this, so unbounded growth becomes a real production incident with no working expiry at all.

**How to avoid:**
- Store all new time-series/audit timestamps as native BSON `Date` wherever a TTL index will be relied on (keep an ISO string field alongside for API/JSON parity if needed, but index a real `datetime` field for TTL).
- Verify any new TTL index actually reaps documents in a real MongoDB instance during phase verification (insert a synthetic old-dated document and confirm it disappears) — don't just confirm the index was created.
- Treat the existing `agent_metrics_history` TTL-vs-string mismatch as a fix-forward backlog note (not blocking this milestone) since it means that collection is currently bounded only by the per-agent 100-row cap, not the documented 30-day policy.
- For location-history specifically, choose retention deliberately (audit/compliance retention is often *longer* than 30 days) rather than copying the operational-metrics TTL value verbatim.

**Warning signs:**
- `grep -n '"timestamp".*isoformat()'` shows the field written as a string in the same file that creates an `expireAfterSeconds` index on it.
- Collection row-count keeps growing past its stated TTL window in a long-running staging environment.
- Any query needing Mongo date-range operators (`$gte: datetime(...)`) against the field silently degrades to lexicographic string comparison.

**Phase to address:** Fleet observability phase (health/uptime timeline) and location history & audit phase both create new time-series data — verification gate in both should explicitly check "TTL/expiry actually fires against a real Date-typed field," not just "index was created."

## Technical Debt Patterns

| Shortcut | Immediate Benefit | Long-term Cost | When Acceptable |
|----------|--------------------|-----------------|------------------|
| Write location-history row on every heartbeat instead of on-change only | Simpler write path, no "diff against last row" logic | Row count scales 1:1 with heartbeat count × fleet size; weakens privacy posture (continuous trail vs. meaningful change log); buries signal in noise for audit review | Never for the audit-trail collection |
| Reuse `itdr_login_events`/user impossible-travel code path for agents | Fast to ship, superficially matches the "reuse" instruction | Wrong entity model (email-keyed vs agent-keyed), wrong false-positive profile (Pitfall 4), couples unrelated systems | Never — build a parallel, agent-keyed rule instead |
| Store new timestamps as `.isoformat()` strings to match existing style | Consistent with most of the codebase, simple JSON serialization | TTL indexes silently no-op (Pitfall 6) | Acceptable only if a parallel native-Date field is also stored wherever TTL/date-math is needed |
| Ship geo-fence as a hard block on day one | Satisfies "location-based security" fastest | Guaranteed false-positive storm from VPN/CGNAT-heavy tenants (Pitfall 4), erodes trust immediately | Never for GA; ship alert-only first |
| Implement offline-alert/version-drift sweep with `get_database()` for convenience | Matches the "normal" request-scoped DB access pattern everywhere else in the codebase | Silently detects nothing, forever, for every tenant (Pitfall 1) — this is a proven, already-hit bug in this exact repo | Never — always pass raw `mongodb.db` into background sweeps |

## Integration Gotchas

| Integration | Common Mistake | Correct Approach |
|-------------|------------------|--------------------|
| `TenantIsolatedDatabase`/`get_database()` | Using it inside a background scheduler/sweep for offline-agent or geo-fence evaluation | Pass raw `mongodb.db` into sweeps, exactly like `tickets_escalation_service`/`compliance_remediation_sla_service` (Pitfall 1) |
| SIEM `impossible_travel` rule / ITDR service | Extending the user-login rule/collection to also cover agent heartbeats | Register a distinct, agent-keyed rule/collection; keep user and agent impossible-travel fully independent (Pitfall 3) |
| `insider_threat_service.py` (`vpn_geo_anomaly`) | Wiring a real UI/alert surface to what is currently seeded/simulated demo data | Verify real-vs-simulated status first; replace with real detection or label clearly as demo (Pitfall 3) |
| `agent_metrics_history` TTL index | Assuming the existing 30-day TTL index works because it exists | Verify TTL against a real Date-typed field before relying on it for any new collection's growth story (Pitfall 6) |
| MaxMind GeoLite2-City (already integrated) | Adding ASN/VPN datasets assuming the same free license/mechanism | Confirm licensing and offline-bundling support per additional dataset before committing (Pitfall 8) |
| Map rendering library (net-new — no map dependency exists in `frontend/package.json` today) | Defaulting to a tile-server-based library (Leaflet+OSM/Mapbox tiles) | Use bundled TopoJSON + SVG projection (`react-simple-maps`/`d3-geo`) for air-gapped compatibility (Pitfall 7) |

## Performance Traps

| Trap | Symptoms | Prevention | When It Breaks |
|------|----------|------------|-----------------|
| Location-history row per heartbeat (not per change) | Row count ≈ heartbeat count × fleet size; disk/index growth outpaces fleet growth | Write only on geo/IP delta, not every beat | Noticeable within weeks at a few hundred agents heartbeating every few minutes; severe at thousands |
| Fleet map rendering every agent marker unclustered | Browser jank/DOM explosion once agent count grows | Client- or server-side clustering before render (the milestone already calls for clustering — implement it as a hard requirement, not a nice-to-have) | Visible in the hundreds-of-agents range, severe in the thousands |
| Full-resolution TopoJSON/basemap bundled into the SPA | Slower initial load, larger bundle even for tenants who never open the map | Use 110m/50m-resolution TopoJSON, code-split the map route out of the main bundle | Fixed cost from day one, compounds with every other bundle addition |
| Background sweep scanning all tenants' full `agents`/`agent_metrics_history` on every tick without an index-backed filter | Slow sweep, full collection scans as fleet/tenant count grows | Index-backed filters (`lastSeen`, `tenantId`) mirroring `idx_agents_tenant_lastseen`; batch/paginate the sweep | Noticeable once total agent count across tenants reaches the low thousands |

## Security Mistakes

| Mistake | Risk | Prevention |
|---------|------|------------|
| Background sweep using `get_database()` instead of raw `mongodb.db` | Feature appears to ship but silently detects nothing for anyone — worse than not shipping it, because it's invisible (Pitfall 1) | Copy the proven `mongodb.db`-raw pattern from `compliance_remediation_sla_service`/`tickets_escalation_service` |
| Treating geo-fence violation as ground truth for automated blocking | Legitimate agent/device blocked due to GeoIP centroid error or VPN-egress ambiguity (Pitfall 2, 4) — an availability/compliance-monitoring gap at exactly the moment the customer needs evidence | Alert-only mode first; require accuracy-radius/ASN context before any automated enforcement action |
| Presenting simulated `vpn_geo_anomaly` data as live detection | False sense of security-monitoring coverage; customer believes a real detector is running when it's fixture data | Confirm/replace before exposing in any new UI surface (Pitfall 3) |
| Storing precise (non-degraded) lat/long indefinitely in an "immutable" audit trail | Larger blast radius if the audit collection is ever exposed/breached; heavier privacy exposure than necessary | Store city/region-level by default in the long-lived history table; keep precise lat/long only where explicitly justified (Pitfall 2, 5) |

## UX Pitfalls

| Pitfall | User Impact | Better Approach |
|---------|-------------|-------------------|
| Precise-looking pin with no uncertainty indicator | Admin over-trusts a GeoIP guess, makes a wrong assumption about a device/employee's whereabouts | Render with an accuracy radius/blur and an explicit "approximate — IP geolocation" label (Pitfall 2) |
| Alert-per-flap for offline agents | Admins mute/ignore the whole alert channel after a few days of noise, missing genuinely important outages | Require a debounce window (consecutive missed heartbeats, not one miss) plus hysteresis before firing, mirroring the existing dedup discipline already used for `agent_update` instructions (`agent_heartbeat_endpoints.py` lines 156-171) |
| Map silently blank in an air-gapped install with no error message | Admin assumes the feature is broken rather than understanding it's an environment limitation | Bundle a self-contained renderer so it always works, or fail with an explicit message rather than a silent blank grid (Pitfall 7) |
| Geo-fence "violation" shown with no explanation of why (VPN egress, ASN, accuracy) | Admin can't distinguish a real anomaly from routine VPN noise, erodes trust in the feature | Show the contributing signal (ASN/VPN tag, distance, accuracy radius) alongside every flagged event, not just a red badge |

## "Looks Done But Isn't" Checklist

- [ ] **Offline-agent alerting / version-drift sweep:** Often built with `get_database()` out of habit — verify it's passed raw `mongodb.db` and actually flags a manually-staged offline agent in a real multi-tenant test (Pitfall 1)
- [ ] **Fleet geo map:** Often missing an accuracy-radius/"approximate location" disclosure — verify markers don't imply street-level precision (Pitfall 2)
- [ ] **Fleet geo map (air-gapped):** Often missing a no-network test pass — verify the map actually renders with outbound network blocked (Pitfall 7)
- [ ] **Impossible-travel / geo-fence for agents:** Often missing ASN/VPN-egress suppression — verify a tenant's shared corporate VPN egress doesn't flood alerts on day one (Pitfall 4)
- [ ] **Location history & audit:** Often missing a change-only write filter — verify row count doesn't scale 1:1 with heartbeat count (write-amplification)
- [ ] **Location history & audit:** Often missing a documented retention/legal-basis decision — verify a privacy review happened before persisting employee-linked location timelines (Pitfall 5)
- [ ] **New TTL indexes (any new time-series collection):** Often missing verification that the indexed field is a native Date, not an ISO string — verify by inserting a synthetic old-dated document and confirming Mongo actually reaps it (Pitfall 6)
- [ ] **SIEM/insider-threat integration:** Often assumes `vpn_geo_anomaly` is a live detector — verify its real-vs-simulated status before building UI on top of it (Pitfall 3)

## Recovery Strategies

| Pitfall | Recovery Cost | Recovery Steps |
|---------|-----------------|------------------|
| Background sweep silently detecting nothing (Pitfall 1) | LOW-MEDIUM | Swap `get_database()` for raw `mongodb.db` passed at registration time; add a regression test asserting the sweep detects a manually-staged offline/stale agent across more than one tenant |
| TTL index discovered non-functional after the fact (Pitfall 6) | MEDIUM | Add a native-Date field via migration/backfill, rebuild the TTL index on that field, run a one-time manual purge of over-retention documents, then let TTL take over |
| Alert-fatigue from flapping-agent offline notifications | LOW-MEDIUM | Ship a debounce/hysteresis patch; optionally bulk-suppress/clear the noisy alert backlog and note it in a changelog so admins re-enable notifications they may have muted |
| Legal/privacy gap discovered after location-history ships (Pitfall 5) | HIGH | Pause new-history writes pending review; retroactive DPIA; offer affected tenants an export/delete path for already-collected history; may require a retention-window change or feature opt-out |
| Geo-fence false-positive storm on a VPN-heavy tenant (Pitfall 4) | LOW-MEDIUM | Flip that tenant (or globally) to alert-only mode immediately; add ASN/egress allowlisting; backfill suppression rules before re-enabling enforcement |

## Pitfall-to-Phase Mapping

| Pitfall | Prevention Phase | Verification |
|---------|--------------------|----------------|
| Background sweep tenant-isolation fail-closed (1) | Fleet observability phase + location-based security phase (any fleet-wide sweep) | Sweep registered with raw `mongodb.db`; regression test against ≥2 tenants confirms real detections, not silent zero-results |
| False-precision GeoIP display/geo-fence (2) | Fleet geo map phase + location-based security phase | UI shows accuracy radius/label; geo-fence policy never gates on raw lat/long alone |
| Wrong-entity reuse of user-login impossible-travel / simulated `vpn_geo_anomaly` (3) | Location-based security phase | New rule is agent-keyed, separately registered in the SIEM rule set; simulated-data status of `vpn_geo_anomaly` explicitly resolved before UI wiring |
| VPN/CGNAT/corporate-egress false positives (4) | Location-based security phase | Alert-only rollout first; ASN/egress-based suppression tested against a simulated shared-VPN-egress fleet before enabling enforcement |
| Privacy/legal basis for location history (5) | Location history & audit phase (pre-implementation spec/discuss step) | DPIA/legal sign-off artifact exists; retention configurable; subject export/delete path present |
| TTL-on-string-field silent no-op (6) | Fleet observability phase + location history & audit phase | Synthetic old-dated doc inserted and confirmed reaped by Mongo in a real (non-mocked) DB during verification |
| Air-gapped map breakage / bundle bloat (7) | Fleet geo map phase | Map tested with outbound network blocked; bundle-size delta checked against a size budget |
| ASN/VPN dataset licensing + staleness (8) | Location-based security phase (dataset selection, pre-implementation) | License terms confirmed for air-gapped bundling; `.mmdb` build-date surfaced somewhere observable; refresh process documented |

## Additional Pitfalls (folded into the mapping above but detailed here for completeness)

### Pitfall 7: Air-gapped/offline map rendering breaks on external tile fetches

No map library exists in `frontend/package.json` today — this is a net-new integration. Tile-based libraries (Leaflet+OSM/Mapbox, Google Maps JS) default to fetching tile images per pan/zoom from an internet endpoint. The platform explicitly targets air-gapped deployments (`geoip_service.py`'s own docstring calls this out for GeoIP, and the milestone brief flags it for the map too). Picking a tile-based library the default way renders a blank/broken-image grid in any air-gapped or heavily firewalled environment — exactly the deployment tier this product's regulated customers fall into.

**Prevention:** Use a bundled, static low-resolution world/country TopoJSON (e.g., world-atlas `countries-110m.json`) rendered with `react-simple-maps`/`d3-geo` as SVG paths — no tile fetches, no basemap imagery. There's no accuracy benefit to a high-res basemap given GeoIP's own city-level accuracy ceiling (Pitfall 2). Test with network access blocked as part of phase verification, not just in a connected dev environment.

### Pitfall 8: ASN/VPN/proxy datasets carry separate licensing constraints from the GeoLite2-City DB already in use

`geoip_service.py` already notes the GeoLite2-City `.mmdb` is "licensed and supplied out-of-band" with no built-in staleness check (loads whatever file is present once at startup, never checks its age). Location-based security additionally needs ASN classification (free, GeoLite2-ASN, same MaxMind mechanism) and ideally VPN/hosting/proxy reputation (typically a **paid**, separately-licensed product — MaxMind GeoIP2 Anonymous IP, IPQualityScore, IP2Proxy — with its own redistribution/on-prem-bundling terms).

**Prevention:** Treat "add ASN" and "add VPN/proxy detection" as two separate procurement/legal decisions. For air-gapped customers, confirm whichever VPN/proxy dataset is chosen supports offline `.mmdb`-style bundling rather than requiring live API calls (a live-lookup-only API reintroduces the outbound dependency `geoip_service.py` was designed to avoid). Add a startup log line or admin-visible indicator showing the loaded `.mmdb`'s build date so staleness is at least observable — there is currently zero staleness signal anywhere in the geo pipeline.

## Sources

- This repository (all code-line references above current as of 2026-07-29, branch `feat/rust-agent-2.1.0-and-fixes`): `backend/geoip_service.py`, `backend/agent_heartbeat_endpoints.py`, `backend/agent_metrics_endpoints.py`, `backend/database.py`, `backend/tenant_context.py`, `backend/tenant_middleware.py`, `backend/agent_auth.py`, `backend/itdr_service.py`, `backend/siem_endpoints.py`, `backend/insider_threat_service.py`, `backend/compliance_remediation_sla_service.py`, `backend/migrations/002_scale_indexes.py`, `frontend/package.json`, `.planning/PROJECT.md`.
- Prior milestone's `.planning/research/PITFALLS.md` (v3.2) — independently documents the same background-scheduler/`TenantIsolatedDatabase` fail-closed bug for `compliance_remediation_sla_service` and `tickets_escalation_service`, corroborating Pitfall 1 as a proven, recurring failure mode in this codebase rather than a hypothetical.
- MaxMind GeoLite2 accuracy/licensing characteristics and MongoDB TTL-index Date-type requirement are well-established platform behaviors (MEDIUM-HIGH confidence, general product/platform knowledge — recommend a quick doc-check against current MaxMind/MongoDB docs during phase-specific research if exact figures are needed for customer-facing copy).
- GDPR/works-council employee-location-monitoring risk is a well-known compliance pattern for endpoint/device-monitoring products generally (MEDIUM confidence — jurisdiction-specific; explicitly flagged for legal review rather than treated as settled here).

---
*Pitfalls research for: Agent geo & fleet observability milestone (v3.3)*
*Researched: 2026-07-29*
