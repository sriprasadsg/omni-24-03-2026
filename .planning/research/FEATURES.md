# Feature Research

**Domain:** IT Asset Management (ITAM) lifecycle — Snipe-IT parity, added atop an existing agent-based security/observability CMDB
**Researched:** 2026-08-04
**Confidence:** MEDIUM (web-search-verified against Snipe-IT's documented behavior + cross-checked against GLPI/Freshservice for table-stakes convergence; no direct Context7/official-docs library involved since this is product-behavior research, not an API/library)

## Existing System Baseline (grounding for dependency calls below)

Read directly from the codebase (`backend/asset_endpoints.py`, `db.assets`) before scoping features:

- `assets` collection, doc id `"asset-{hostname}"`, keyed by **hostname** (agent identity), not by a human-assigned tag.
- Existing fields: `hostname`, `os`/`osName`, `type` (server/workstation/etc, agent-inferred), `serialNumber` (best-effort from agent metadata), `criticality`, `status` (agent/security-connectivity meaning — online/offline/isolated, NOT ITAM lifecycle), `tags`, `location` (free string), `owner` (free string, not a user FK), `notes`, `maintenanceWindow`, `environment`, `category`, `tenantId`.
- `bulk-update` allowlist already includes `status`, `criticality`, `tags`, `location`, `owner`, `notes`, `maintenanceWindow`, `environment`, `category` — but these are shallow scalar fields with **no history/audit trail**, no FK to a `users` collection, no enum-enforced lifecycle, and `status` is already semantically overloaded (security state, not ITAM state).
- No concept of: manually-created (non-agent) asset; check-out/check-in event; assignment target (user vs location vs another asset); manufacturer/model/category/supplier as first-class entities; custom fields; asset tag/barcode/QR; license; accessory; consumable; component; purchase/warranty/depreciation fields.
- **This confirms the milestone's own framing is correct**: the current `assets` collection is an agent-fingerprint record, not an ITAM asset record. Reusing it wholesale for hand-catalogued items (a laptop with no agent installed, a monitor, a phone) would force every manual asset to fake a `hostname` and would collide with agent auto-discovery logic that keys off `hostname` for upsert. See Feature Dependencies section for the precise fork/extend decision per field group.

## Feature Landscape

### Table Stakes (Users Expect These)

Features users assume exist in any ITAM tool once check-in/out is on the table. Missing these makes the product feel like a stripped-down demo. Confirmed as common denominator across Snipe-IT, GLPI, and Freshservice (not Snipe-IT-specific quirks).

| Feature | Why Expected | Complexity | Notes |
|---------|--------------|------------|-------|
| Check-out asset to user | Core ITAM verb; "who has this laptop" is the #1 question an ITAM tool answers | MEDIUM | Needs `assigned_to` as a typed reference (`{type: user\|location\|asset, id}`), not a free-text `owner` string. New `checkout_records` collection for the transaction log. |
| Check-in asset (return to stock) | Symmetric to checkout; without it, checkout is a one-way door | LOW | Clears `assigned_to`, appends a check-in event to `checkout_records`, sets status back to a deployable label. |
| Status lifecycle labels (deployable/deployed/archived/retired/disposed/broken) | Users expect an enum-driven lifecycle, not a raw connectivity flag | MEDIUM | Must be a **new field** (e.g. `lifecycle_status`) — cannot repurpose `assets.status`, which already means agent/security connectivity. Status labels need a `type` (deployable vs not) that gates whether checkout is allowed, per Snipe-IT's model. |
| Assignment/checkout history (audit trail) | "Who had this before?" is a routine helpdesk/audit question; also needed for compliance evidence parity with the rest of this platform | LOW–MEDIUM | Append-only collection, tenant-scoped, same pattern already used for `status_history` on compliance overrides (Phase 6) — reuse that pattern. |
| Assign asset to a location (not just a person) | Shared equipment (conference-room TV, printer) isn't assigned to one person | LOW | Locations become a first-class catalog entity (Cluster C); `assigned_to.type = location`. |
| Manual (non-agent) asset creation | ITAM must catalog things with no software agent — monitors, furniture, phones | MEDIUM | New collection (see Dependency Notes) — this is the crux integration decision for the whole milestone. |
| Asset tag (human-facing unique ID, distinct from serial number) | Physical labeling requires a short, print-friendly, org-assigned identifier; serial numbers are vendor-assigned and not always visible/scannable | LOW | Simple unique-per-tenant string field + uniqueness index. |
| Manufacturer / Model / Category / Supplier / Location as catalog entities | Without these, every asset re-types "Dell" and "Latitude 5420" as free text — no reporting, no bulk depreciation-by-model | MEDIUM | 5 small CRUD collections; models reference manufacturer + category; assets reference model. |
| Purchase cost / purchase date / PO number / supplier | Finance/procurement teams need this for every asset in an ITAM tool; it's the majority of "why doesn't this feel like ITAM yet" gap | LOW | Flat fields on the manual-asset record (or an extension sub-doc — see Dependency Notes). |
| Warranty tracking + expiry alert | Table stakes once purchase date exists; "which warranties expire this quarter" is a standard report | LOW–MEDIUM | Computed field (`purchase_date + warranty_months`) + a scheduled digest/alert, reusing existing notification infra if present. |
| Depreciation schedule (straight-line minimum) | Finance stakeholders expect current book value, not just purchase cost | MEDIUM | Model-level depreciation policy (months + floor value) applied per-asset at report time; matches Snipe-IT's model-level assignment pattern. Pure calculation, no external accounting integration (explicitly out of scope per PROJECT.md). |
| Custom fields | Every org tracks something the vendor didn't anticipate (e.g. an internal cost-center code); a rigid schema without custom fields is a common ITAM complaint | MEDIUM | Global field definitions grouped into fieldsets, fieldset attached at the model level (Snipe-IT pattern) — avoids a full EAV free-for-all while still being flexible. |
| Asset tag label generation (QR + barcode, printable) | Physical audits require scannable labels; explicitly named in this milestone's constraints (offline/air-gapped, no external services) | MEDIUM | Pure local rendering — `qrcode`-style library + barcode (Code128/Code39) + PDF/label-sheet layout. No live network calls, consistent with the platform's offline-first native-scan precedent (v3.4). |
| Software license seats (assign/reclaim/expiry) | License compliance ("do we have enough Photoshop seats") is a named cluster requirement and a top ITAM use case | MEDIUM | `licenses` collection with `seats_total`; `license_seats` sub-records or a checkout-record type extension track per-seat assignment to user or asset; expiry date + alert reuses warranty-alert plumbing. |
| Accessories / consumables (checkout with quantity, no serials) | Non-serialized bulk items (cables, toner, mice) are explicitly named in Cluster D | MEDIUM | Pool-quantity model: `quantity_total`, `quantity_available`; checkout decrements, check-in (accessories only — consumables typically aren't returned) increments. |
| Components (attached to a specific parent asset) | RAM/HDD/GPU upgrades tracked as sub-inventory of a parent asset is a named cluster item | MEDIUM | `components` collection referencing a parent asset id + quantity, distinct from accessories (which attach to people, not assets). |
| Physical audit / inventory-verification workflow | Periodic "did we actually find this asset" walkthroughs are a standard ITAM report even though not explicitly named as its own cluster — it's the natural consumer of QR/barcode labels | MEDIUM | "Mark as audited on [date]" action + last-audit-date field + overdue-audit report; can be deferred past MVP since it's a light layer on top of check-in/out + labels, but expected once labels exist. |

### Differentiators (Competitive Advantage)

Not required for Snipe-IT parity, but where this platform can go further than a bolt-on ITAM tool because it already owns the agent-based security layer.

| Feature | Value Proposition | Complexity | Notes |
|---------|-------------------|------------|-------|
| Agent-discovered ↔ manual-asset linking | "This ITAM record IS this monitored endpoint" — link a manually-catalogued asset (with PO/warranty/depreciation) to its auto-discovered security twin (with vuln/patch/criticality data) in one UI, something Snipe-IT can't do because it has no security agent at all | MEDIUM | Add an optional `linked_endpoint_asset_id` FK from the ITAM record to the existing `assets` collection; surface both panels side by side. This is the single most natural differentiator given the existing platform and should be scoped explicitly, not left implicit. |
| Compliance-evidence-aware asset lifecycle | Retiring/disposing an asset that holds compliance evidence (FIM baselines, scan history) can auto-flag/archive that evidence instead of leaving orphaned records — no ITAM competitor has a compliance evidence layer to integrate with | MEDIUM–HIGH | Hook the "retire/dispose" checkout-status transition to check for and annotate linked compliance evidence records. Good candidate for a later phase, not MVP. |
| Warranty/depreciation alerts routed through the existing notification/webhook infra (SIEM/OCSF, in-app) | Reuses the outbound webhook plumbing shipped in v3.4 (COMM-01) rather than building new alerting from scratch | LOW | Genuine reuse win — implementation cost is lower than it looks because the pipe already exists. |
| Tenant-scoped asset tag namespacing with QR deep-link into the existing multi-tenant portal | Scanning a QR code opens the exact tenant-scoped asset record directly (deep link with tenant context), which off-the-shelf Snipe-IT installs typically don't offer in a multi-tenant MSP context | LOW–MEDIUM | Mostly a URL-scheme/auth-routing concern, not new domain logic. |

### Anti-Features (Commonly Requested, Often Problematic)

| Feature | Why Requested | Why Problematic | Alternative |
|---------|---------------|------------------|-------------|
| Forking/duplicating the `assets` collection wholesale into a parallel "ITAM assets" collection with 90% overlapping fields | Feels like the fastest path — copy the schema, add fields | Two collections both called "assets" with divergent meanings is exactly the kind of drift this platform has already suffered (see `.planning/PROJECT.md` history — `compliance_remediation_tasks` vs `remediation_tasks` naming collision was deliberately avoided for this reason) | Single `itam_assets` (or similarly named) collection scoped to manually-catalogued items, with an **optional** link field to the existing `assets` collection when a hardware match exists. Do not rename or repurpose the existing collection. |
| RFID/physical scanner driver integration | "Since we're doing barcodes, why not RFID gates" | Hardware driver integration, out of scope per PROJECT.md ("QR/barcode generation only, no scanner drivers"), and scanning is solvable with any USB barcode scanner emulating keyboard input against the existing search box — no custom driver needed | Rely on standard USB HID barcode scanners hitting the existing asset-tag search field; explicitly punt hardware RFID integration |
| Full GL/accounting system integration (journal entries, multi-currency, tax) | "Depreciation should post to our accounting system" | Named out of scope in PROJECT.md; deep GL integration is its own product surface and multiplies complexity (currency conversion, fiscal-period close, chart-of-accounts mapping) | Straight-line depreciation report with book value only; export as CSV/PDF for a human to key into accounting software, same posture as the existing PDF/Excel compliance export |
| Real-time RFID/GPS asset location tracking | "Auto check-in when the asset re-enters the building" sounds compelling | Requires hardware infrastructure this platform has no reason to own, and conflicts with the "no scanner drivers" constraint | Location is a manually-selected catalog entity assigned at checkout time, consistent with Snipe-IT's model (and GLPI/Freshservice) |
| Merging ITAM "status" into the existing agent `assets.status` field | Seems like less schema sprawl | `assets.status` already carries security/connectivity meaning (online/offline/isolated) for the auto-discovered fleet; overloading it with deployable/deployed/archived/retired/disposed/broken creates an unresolvable ambiguity the moment an asset is both agent-monitored and ITAM-tracked | New, separate `lifecycle_status` field, only present on ITAM-scoped records (or on the link, not the base agent record) |
| Unlimited free-form custom fields with no fieldset grouping (pure EAV) | Maximum flexibility, "let admins add any field to any asset" | Produces unqueryable, unreportable messes in practice — this is a known pain point in less-opinionated ITAM tools | Snipe-IT's pattern: define fields once, group into fieldsets, attach fieldset to a model — every asset of that model gets a consistent shape |
| Auto-approve all checkout requests (skip approval step) for "requestable assets" self-service flow | Speeds up the common case | For a security/compliance platform, an unapproved hand-off of a laptop with sensitive data breaks the audit trail this product's core value proposition depends on | Requestable-assets flow (if built at all — not named in this milestone's clusters) should route through an approval step, mirroring the existing remediation approval-gate pattern already shipped in v3.4 |

## Feature Dependencies

```
[Manual (non-agent) asset catalog — itam_assets collection]
    └──requires──> [Manufacturer / Model / Category / Supplier / Location catalog entities]
                       └──requires──> [Custom field definitions + fieldsets]

[Check-out / Check-in flow]
    └──requires──> [Manual asset catalog] (or link to existing `assets`)
    └──requires──> [Status lifecycle labels] (checkout gated on "deployable" type)
    └──requires──> [Assignment target: user | location | asset]

[Assignment/checkout history audit trail]
    └──requires──> [Check-out / Check-in flow] (nothing to log until the verb exists)

[Warranty expiry alerts]
    └──requires──> [Purchase date + warranty_months fields on asset/model]

[Depreciation schedule]
    └──requires──> [Purchase cost + purchase date]
    └──requires──> [Asset Model] (Snipe-IT assigns depreciation policy at model level)

[Asset tag + QR/barcode label generation]
    └──requires──> [Asset tag field] (unique identifier must exist before it can be printed)
    └──enhances──> [Physical audit workflow]

[License seat assignment]
    └──requires──> [Licenses catalog entity]
    └──requires──> [Assignment target: user | asset] (seats can be assigned to either)

[Accessories / Consumables checkout]
    └──requires──> [Check-out / Check-in flow] (reuses the same transaction pattern, quantity-aware variant)

[Components]
    └──requires──> [Manual/linked asset to attach to] (components always belong to a parent asset)

[Agent-discovered ↔ manual-asset linking] (differentiator)
    └──enhances──> [Manual asset catalog] (optional FK to existing `assets` collection, not a hard dependency)

[Compliance-evidence-aware retirement] (differentiator)
    └──requires──> [Status lifecycle labels] (specifically the retire/dispose transition)
    └──requires──> [Agent-discovered ↔ manual-asset linking] (no evidence to flag without the link)
```

### Dependency Notes

- **Manual asset catalog requires catalog entities first:** you cannot meaningfully create an ITAM asset without at least a placeholder manufacturer/model/category, so Cluster C (catalog/org) is a hard prerequisite phase for Cluster A (lifecycle) and Cluster B (procurement), not a nice-to-have that can trail behind. Sequence Cluster C before A/B in the roadmap.
- **Check-out/check-in requires status lifecycle labels:** Snipe-IT enforces that checkout is only possible from a "deployable"-typed status; building checkout before the status-type concept exists means either no gating (a correctness gap) or a rework later. Build status labels first or in the same phase as checkout.
- **Depreciation requires the Model entity, not just the Asset:** Snipe-IT assigns depreciation policy at the model level so all units of the same model depreciate identically; if this platform instead puts depreciation fields directly on each asset, admins will have to re-enter the same policy per unit — a design smell worth avoiding by following the Model-level pattern from the start.
- **The existing `assets` collection is a soft dependency, not a hard one, for the manual catalog:** the manual `itam_assets` collection should be able to exist and function fully standalone (an org can run ITAM on assets with zero agents installed). The link to `assets` is additive/optional — implement it as a nullable FK, not a required join, so ITAM doesn't break for tenants with no agent-monitored fleet at all, and so the agent-fleet ingestion path is never blocked waiting on ITAM data entry.
- **`assets.status` (agent/security state) and the new `lifecycle_status` (ITAM state) must not be unified:** this is called out explicitly in Anti-Features above because it's the single highest-risk shortcut a planner could take to "save a phase."
- **Accessories/consumables/components conflict risk:** these three look similar (all "secondary assets" in Snipe-IT's own terminology) but have different checkout targets (accessories/consumables → user only; components → asset only) and different quantity semantics (components support multi-quantity checkout to an asset; Snipe-IT's core accessories/consumables are limited to 1-per-transaction, a known product gap). Recommend **not** cloning Snipe-IT's 1-per-transaction limitation — since this is a greenfield build, support quantity > 1 in accessory/consumable checkout from the start; it's a small delta in the data model (`quantity_checked_out` on the transaction record) and avoids inheriting a competitor's long-standing complaint.

## MVP Definition

### Launch With (v1 of this milestone)

Minimum to call this "ITAM, not just a checklist of fields."

- [ ] Manual (non-agent) asset creation — `itam_assets` collection, tenant-isolated — without this nothing else in the milestone has anything to operate on
- [ ] Manufacturer / Model / Category / Location catalog entities (Cluster C core) — hard prerequisite for everything else
- [ ] Asset tag (unique per tenant) — needed before check-out/in and before labels
- [ ] Status lifecycle labels with deployable/non-deployable typing (Cluster A) — gates checkout correctness from day one
- [ ] Check-out / check-in to user or location, with assignment history audit trail (Cluster A) — the defining ITAM verb; this milestone's own goal statement names it first
- [ ] Purchase cost/date/PO/supplier fields (Cluster B) — low complexity, high expected-completeness value, unlocks warranty+depreciation
- [ ] Admin-gated nav page (new `AppView` + `App.tsx` + Sidebar entry + permission gate) following the Phase 47/48 pattern named in PROJECT.md constraints

### Add After Validation (v1.x within this milestone)

- [ ] Suppliers as a distinct catalog entity (can launch with supplier as a plain string on the asset, promote to FK once the basic flow is validated)
- [ ] Warranty expiry alerts (needs purchase/warranty fields validated first; alert delivery is a small increment once dates exist)
- [ ] Depreciation schedule + book-value reporting (needs Model entity + purchase cost validated; pure calculation layer)
- [ ] Custom fields + fieldsets (valuable but not blocking; can follow once the base model/category shape is proven)
- [ ] Asset tag QR/barcode label generation (depends on asset tag existing and being stable; offline PDF/label rendering is a self-contained increment)
- [ ] Software license seats (assign/reclaim/expiry) (Cluster D — independent enough to sequence after Cluster A/B/C core is solid)
- [ ] Accessories / consumables with quantity-aware checkout (Cluster D)
- [ ] Components attached to parent assets (Cluster D)

### Future Consideration (v2+ / explicitly deferred)

- [ ] Physical audit / inventory-verification workflow — natural follow-on to labels existing, but not named as its own cluster; defer until labels + checkout are stable
- [ ] Agent-discovered ↔ manual-asset linking (differentiator) — high value but touches two data models at once; do only after both sides are individually solid
- [ ] Compliance-evidence-aware retirement (differentiator) — depends on the linking feature above; genuinely v2+
- [ ] Requestable-assets self-service flow — not named in this milestone's 4 clusters at all; do not build unless explicitly added to scope
- [ ] Multi-currency / GL integration — explicitly out of scope per PROJECT.md
- [ ] RFID/scanner hardware driver integration — explicitly out of scope per PROJECT.md

## Feature Prioritization Matrix

| Feature | User Value | Implementation Cost | Priority |
|---------|------------|---------------------|----------|
| Manual asset catalog (itam_assets) | HIGH | MEDIUM | P1 |
| Manufacturer/Model/Category/Location catalog | HIGH | MEDIUM | P1 |
| Status lifecycle labels | HIGH | MEDIUM | P1 |
| Check-out/check-in + audit history | HIGH | MEDIUM | P1 |
| Purchase cost/date/PO/supplier fields | HIGH | LOW | P1 |
| Asset tag (unique ID) | HIGH | LOW | P1 |
| Warranty expiry tracking + alerts | MEDIUM | LOW–MEDIUM | P2 |
| Depreciation schedule (straight-line) | MEDIUM | MEDIUM | P2 |
| Custom fields + fieldsets | MEDIUM | MEDIUM | P2 |
| QR/barcode label generation | MEDIUM | MEDIUM | P2 |
| Software license seats | MEDIUM | MEDIUM | P2 |
| Accessories/consumables (quantity-aware) | MEDIUM | MEDIUM | P2 |
| Components | LOW–MEDIUM | MEDIUM | P3 |
| Physical audit workflow | LOW–MEDIUM | MEDIUM | P3 |
| Agent-discovered ↔ manual-asset linking | HIGH (differentiator) | MEDIUM | P3 |
| Compliance-evidence-aware retirement | MEDIUM (differentiator) | HIGH | P3 |

**Priority key:**
- P1: Must have for launch — Clusters A core + B core + C core
- P2: Should have, add when possible — Cluster B/C completion + Cluster D
- P3: Nice to have, future consideration — differentiators and audit workflow

## Competitor Feature Analysis

| Feature | Snipe-IT (reference) | GLPI | Freshservice | Our Approach |
|---------|----------------------|------|---------------|--------------|
| Check-in/out | Core verb; status-type gated | Core verb, plus ticket-linked checkout | Core verb, workflow-approval optional | Match Snipe-IT's status-type gating; skip approval workflow for MVP (add later if requested) |
| Asset discovery | Manual entry / CSV import only (no native agent) | Native network/agent-based discovery (its main edge over Snipe-IT) | Agent + network discovery (SaaS) | We already have an agent — the differentiator is *linking* manual ITAM records to agent-discovered security records, which none of the three competitors can do because none combine ITAM + security scanning in one product |
| Depreciation | Model-level policy, straight-line, book-value report | Similar model-level depreciation | Depreciation via financial module | Match Snipe-IT's model-level pattern (straight-line minimum, per PROJECT.md scope) |
| Licenses | Seat-count field, per-seat checkout to user or asset | License management module tied to software inventory | License + contract management (SaaS) | Match Snipe-IT's seat model; our existing `SoftwareInventoryTab` (agent-observed installs) is a natural future cross-check against license seat counts (not in this milestone's scope, flag as future) |
| Accessories/consumables/components | 1-per-transaction limitation (known gap) | Similar secondary-asset categorization | Bundled into general asset/inventory items | Do NOT inherit the 1-per-transaction limitation — support quantity > 1 from the start since this is greenfield |
| Custom fields | Global fields grouped into per-model fieldsets | Similar plugin-based custom field system | Configurable fields, SaaS-managed | Match Snipe-IT's fieldset-per-model pattern |
| Labels/tags | QR (deep link) + 1D barcode, fully local rendering, configurable label sheet layout | Barcode/QR support, less emphasis on printable sheets | Primarily digital, less print-workflow focus | Match Snipe-IT's approach — fully offline rendering is a hard constraint (air-gapped deployments) already established by the v3.4 native-scan precedent |

## Sources

- [Product Features — Snipe-IT](https://snipeitapp.com/product) — MEDIUM confidence (websearch, verified/cross-checked)
- [Snipe-IT Docs: Barcodes](https://snipe-it.readme.io/docs/barcodes) — MEDIUM confidence
- [Snipe-IT Docs: Managing Assets](https://snipe-it.readme.io/docs/managing-assets) — MEDIUM confidence
- [Snipe-IT Docs: Custom Fields](https://snipe-it.readme.io/docs/custom-fields) — MEDIUM confidence
- [Snipe-IT Docs: Asset Labels](https://snipe-it.readme.io/docs/asset-labels) — MEDIUM confidence
- [Snipe-IT Docs: Importing Licenses](https://snipe-it.readme.io/docs/importing-licenses-1) — MEDIUM confidence
- [GitHub grokability/snipe-it Issue #15679 — status label type behavior](https://github.com/grokability/snipe-it/issues/15679) — MEDIUM confidence
- [GitHub grokability/snipe-it Issue #18890 — Deployable asset view](https://github.com/grokability/snipe-it/issues/18890) — MEDIUM confidence
- [GitHub grokability/snipe-it Discussion #11342 — Depreciation calculation](https://github.com/grokability/snipe-it/discussions/11342) — MEDIUM confidence
- [GitHub grokability/snipe-it Issue #5140 — checkout quantities for accessories/consumables](https://github.com/grokability/snipe-it/issues/5140) — MEDIUM confidence
- [GitHub grokability/snipe-it Issue #7348 — accessories/consumables quantity on checkout](https://github.com/snipe/snipe-it/issues/7348) — MEDIUM confidence
- [DeepWiki grokability/snipe-it — Accessories & Components](https://deepwiki.com/grokability/snipe-it/3.2-accessories-and-components) — MEDIUM confidence (secondary/community source)
- [Compare GLPI vs Snipe-IT — SoftwareSuggest](https://www.softwaresuggest.com/compare/snipe-it-vs-glpi) — LOW-MEDIUM confidence (vendor-comparison marketing content, used only for the discovery-vs-manual-catalog convergence point)
- [Compare Snipe-IT vs Freshservice — SoftwareSuggest](https://www.softwaresuggest.com/compare/snipe-it-vs-freshservice) — LOW-MEDIUM confidence
- Existing codebase: `/home/user/enterprise-omni-agent-ai-platform/backend/asset_endpoints.py` — HIGH confidence (direct source read)
- `/home/user/enterprise-omni-agent-ai-platform/.planning/PROJECT.md` — HIGH confidence (direct source read, milestone scope/constraints)

---
*Feature research for: IT Asset Management (ITAM) lifecycle, Snipe-IT parity, v4.0 milestone*
*Researched: 2026-08-04*
