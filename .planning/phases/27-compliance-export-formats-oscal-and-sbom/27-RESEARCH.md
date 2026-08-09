# Phase 27: Compliance Export Formats (OSCAL and SBOM) - Research

**Researched:** 2026-07-06
**Domain:** Compliance data export (OSCAL JSON) + Software Bill of Materials (CycloneDX JSON) for container scan results
**Confidence:** HIGH

## Summary

This phase adds two new read-only export endpoints to an already-mature export pipeline. No CONTEXT.md exists (proceeding straight from ROADMAP/REQUIREMENTS per YOLO config), so this research treats both format choices (OSCAL model variant, CycloneDX vs SPDX) as open decisions to resolve here rather than pre-locked.

The codebase already has a clean multi-format compliance report pipeline (`compliance_reports_endpoints.py` → `compliance_reporting_service.py` → format-specific renderer modules, all reusing a single shared data-fetcher `_build_report_data()` in `compliance_reporting_data.py`). The most recent format added (OCSF, Phase 22) did **not** join this pipeline — it lives in its own file (`ocsf_endpoints.py`) as simple `GET` JSON endpoints with no on-disk persistence, because OCSF findings are naturally streamed as JSON rather than downloaded as a generated report file. OSCAL export should follow the OCSF pattern (new file, `GET` endpoint, reuse `_build_report_data()` for the underlying data, return JSON directly — no disk write, no `compliance_reports` metadata row), not the CSV/Excel/PDF pattern (which writes to `static/reports/` and tracks ownership in `db.compliance_reports`).

For SBOM, the codebase already has an **unrelated but confusingly-similar** SBOM subsystem (`sbom_endpoints.py`, registered as `_load(app, "sbom_endpoints")`) that uploads/generates SBOMs for the **host's own installed packages** (via Syft/pip/npm), storing them in `db.sboms` / `db.software_components`. That is NOT what EXP-02 asks for. EXP-02 asks for SBOM export of **scanned container images** — the data already collected by `container_scanner_service.py` (Trivy-based image scanning, Phase 24/25, stored in `db.container_scan_results`). The correct implementation adds a new endpoint to the existing `container_scanner_endpoints.py` file (e.g. `GET /api/container/results/{scan_id}/sbom`) that transforms an existing scan result's `vulns` list (package name/version/CVE per entry) into a CycloneDX JSON document — it must NOT touch `sbom_endpoints.py`, `db.sboms`, or `db.software_components`, which are a separate, already-shipped feature.

**Primary recommendation:** Hand-roll both JSON formats as plain Python dict builders (no new pip dependency). Target OSCAL `assessment-results` model v1.1.2 (metadata + uuid + results[] with reviewed-controls + findings), fed by the existing `_build_report_data()` control/evidence rows. Target CycloneDX 1.6 JSON (`bomFormat`/`specVersion`/`components[]`/`vulnerabilities[]`), fed by a new dedup/component-building step over `container_scan_results.vulns`. This avoids adding a [SUS]-flagged dependency (see Package Legitimacy Audit) and matches this codebase's existing precedent of hand-parsing CycloneDX JSON manually in `sbom_endpoints.py`.

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|-------------------|
| EXP-01 | Compliance control/evidence data is exportable as an OSCAL-conformant JSON document | Pattern 1 (OCSF-style thin endpoint) + Pattern 2 (minimal valid `assessment-results` document) + Pitfall 1/Open Question 1 (status-vocabulary mapping) — new `oscal_endpoints.py` reusing `_build_report_data()` |
| EXP-02 | Software Bill of Materials (CycloneDX or SPDX) export for scanned container images/assets | Standard Stack (CycloneDX chosen over SPDX) + Pattern 3 (CycloneDX from Trivy `vulns`) + Pitfall 2/3 (dedup, simulated-data handling) — new route on existing `container_scanner_endpoints.py` |
</phase_requirements>

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| OSCAL document assembly | API / Backend | Database (read-only) | Pure transform of existing `compliance_frameworks` / `asset_compliance` / `compliance_artifacts` docs already fetched by `_build_report_data()`; no new persistence needed |
| CycloneDX SBOM assembly | API / Backend | Database (read-only) | Pure transform of an existing `container_scan_results` document; no new persistence needed |
| Export trigger UI | Browser / Client | — | Two new buttons following the exact `exportOcsf()` blob-download pattern already in `ApiExtensionsDashboard.tsx` |
| Router registration | API / Backend | — | New `oscal_endpoints.py` registered in `router_registry.py`; container SBOM route added to the already-registered `container_scanner_endpoints.py` (no new registry line needed) |
| Auth / tenant scoping | API / Backend | — | Must match the pattern of the file being extended: `compliance_reports_endpoints.py`-style manual tenant check for OSCAL (join the compliance export family), `rbac_service.has_permission(...)` for container SBOM (join the container-scanner family) |

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| *(none — hand-rolled)* | — | OSCAL JSON assembly | A minimal valid OSCAL `assessment-results` document is a shallow, well-documented dict structure; no library needed for a one-way export (see Don't Hand-Roll caveat below on why this is the exception, not the rule) |
| *(none — hand-rolled)* | — | CycloneDX JSON assembly | Existing codebase precedent (`sbom_endpoints.py`) already hand-parses/builds CycloneDX-shaped dicts without a library |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| `uuid` (stdlib) | builtin | OSCAL/CycloneDX require RFC 4122 UUIDs (`metadata.uuid`, `bom-ref`, `serialNumber`) | Every document — both formats mandate UUID identifiers |
| `datetime` (stdlib) | builtin | `metadata.last-modified` (OSCAL, ISO-8601 with timezone), report timestamps | Every document |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| Hand-rolled OSCAL dict | `compliance-trestle` (PyPI, IBM/oscal-compass, `pip index versions` confirms 4.2.0 current [VERIFIED: pypi registry]) | Trestle is a full "compliance-as-code" authoring platform (workspace init, catalog/profile/SSP authoring, CLI tasks) — massive over-fit for "export existing Mongo rows as one OSCAL JSON file." Violates CLAUDE.md "no unnecessary abstractions." Only reconsider if the platform later needs to *author* full OSCAL catalogs/profiles, not just assessment-results exports. |
| Hand-rolled CycloneDX dict | `cyclonedx-python-lib` ([SUS] — see Package Legitimacy Audit) | Gives schema validation and serialization guarantees, but (a) flagged SUS by the legitimacy gate, (b) is a pure data-model library, not a generator — you'd still write all the mapping code yourself, so the LOC savings vs. hand-rolling a ~40-line dict builder is minimal. Revisit only if OSCAL/CycloneDX validation failures become a recurring bug source. |
| CycloneDX | SPDX 2.3 / 3.0 | SPDX has no native vulnerability model (2.3) or is a much heavier RDF-graph model (3.0); CycloneDX's built-in `vulnerabilities[]` array with `affects[].ref` → `bom-ref` maps directly onto the Trivy `vulns` list already returned by `container_scanner_service.py`. CycloneDX is also the format the codebase already partially supports (`sbom_endpoints.py` upload/parse). |

**Installation:**
```bash
# No new packages required — both formats hand-rolled with stdlib only.
```

**Version verification:**
```bash
pip index versions cyclonedx-python-lib   # 11.11.0 confirmed current [VERIFIED: pypi registry] — NOT recommended, see above
pip index versions compliance-trestle     # 4.2.0 confirmed current [VERIFIED: pypi registry] — NOT recommended, see above
```

## Package Legitimacy Audit

> Included for completeness even though the primary recommendation adds zero new dependencies. If the planner or a future phase later decides to adopt a library instead of hand-rolling, this audit applies.

| Package | Registry | Age | Downloads | Source Repo | Verdict | Disposition |
|---------|----------|-----|-----------|-------------|---------|-------------|
| `cyclonedx-python-lib` | pypi | Latest release 2026-06-17 per registry metadata (project itself has 90+ historical releases back to 2021 per `pip index versions`) | unknown (registry API returned null) | github.com/CycloneDX/cyclonedx-python-lib | **SUS** (`too-new`, `unknown-downloads`) | Not adopted — hand-roll instead. If a future phase wants to adopt it anyway, gate behind `checkpoint:human-verify` per protocol; the SUS signal is very likely a false positive driven by the *latest point-release* date rather than package age (this is the official OWASP CycloneDX org's reference Python library), but the gate must still be honored mechanically. |
| `compliance-trestle` | pypi | Confirmed present, 100+ historical releases (IBM/oscal-compass org) | not checked (not recommended regardless) | github.com/oscal-compass/compliance-trestle | Not run through legitimacy gate — rejected on architectural fit grounds (over-abstraction) before reaching the gate | Not adopted |

**Packages removed due to [SLOP] verdict:** none
**Packages flagged as suspicious [SUS]:** `cyclonedx-python-lib` — not used in the recommended approach; if planner chooses to add it anyway, insert `checkpoint:human-verify` before the `pip install` step.

## Architecture Patterns

### System Architecture Diagram

```
┌─────────────────────────────┐
│  ApiExtensionsDashboard.tsx │  "Export OSCAL" button (new)
│  (existing OCSF export UI)  │──────────────┐
└─────────────────────────────┘              │ GET (blob download,
                                              │  same exportOcsf() pattern)
┌─────────────────────────────┐              ▼
│ IacContainerDashboard.tsx   │──────┐  ┌─────────────────────────┐
│ (existing container results)│      │  │  oscal_endpoints.py NEW │
│ "Export SBOM" button (new)  │      │  │  GET /api/oscal/        │
└─────────────────────────────┘      │  │      assessment-results │
              │ GET (blob download)  │  │      ?framework_id=     │
              ▼                      │  └────────────┬────────────┘
┌──────────────────────────────┐     │               │ reuses
│ container_scanner_endpoints.py│     │               ▼
│ NEW route:                    │◄────┘  ┌─────────────────────────┐
│ GET /api/container/results/   │        │ compliance_reporting_   │
│     {scan_id}/sbom            │        │ data.py                 │
└───────────────┬────────────────┘        │ _build_report_data()   │
                │ reads                   │ (existing, unchanged)  │
                ▼                          └────────────┬────────────┘
┌──────────────────────────────┐                        │ reads
│ db.container_scan_results     │                        ▼
│ (existing collection, written │        ┌─────────────────────────┐
│ by container_scanner_service) │        │ db.compliance_frameworks│
└────────────────────────────────┘        │ db.asset_compliance     │
                                           │ db.compliance_artifacts│
                                           │ db.assets               │
                                           └─────────────────────────┘
```

### Recommended Project Structure
```
backend/
├── oscal_endpoints.py            # NEW — GET /api/oscal/assessment-results, reuses compliance_reporting_data
├── container_scanner_endpoints.py  # MODIFIED — add GET /{scan_id}/sbom (CycloneDX)
├── container_scanner_service.py    # UNCHANGED — data source (do not duplicate its query logic)
├── compliance_reporting_data.py    # UNCHANGED — reused via _build_report_data()
├── router_registry.py              # MODIFIED — one new line: _load(app, "oscal_endpoints", "router")
components/
├── ApiExtensionsDashboard.tsx      # MODIFIED — add "Export OSCAL" button next to existing OCSF buttons
├── IacContainerDashboard.tsx       # MODIFIED — add "Export SBOM" button per container scan history row
```

### Pattern 1: OCSF-style thin export endpoint (use for OSCAL)
**What:** A dedicated `GET` endpoint that assembles a JSON document in memory and returns it directly — no file write, no `compliance_reports` metadata row, no `Content-Disposition` header dance. The browser-side blob-download trick (`res.blob()` → `URL.createObjectURL`) is what turns a plain JSON response into a "download" from the user's perspective; the backend just returns JSON.
**When to use:** Any export where the document is cheap to regenerate and doesn't need to be listed/re-downloaded later (matches EXP-01/EXP-02 — no requirement mentions a report history for these two formats).
**Example:**
```python
# Source: existing backend/ocsf_endpoints.py (Phase 22), adapted pattern
from fastapi import APIRouter, Depends, Query, HTTPException
from authentication_service import get_current_user
from compliance_reporting_data import _build_report_data

router = APIRouter(prefix="/api/oscal", tags=["OSCAL Export"])

@router.get("/assessment-results")
async def oscal_assessment_results(
    framework_id: str = Query(...),
    current_user=Depends(get_current_user),
):
    tenant_id = getattr(current_user, "tenant_id", None) or None
    if not tenant_id:
        raise HTTPException(status_code=403, detail="Tenant context required")
    try:
        framework, asset_summary, control_rows = await _build_report_data(framework_id, tenant_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    return _to_oscal_assessment_results(framework, control_rows)  # pure dict builder, see below
```

### Pattern 2: OSCAL `assessment-results` minimal valid document
**What:** The smallest structurally-valid OSCAL v1.1.2 assessment-results document. `metadata` requires `title`, `last-modified`, `version`, `oscal-version`; the root requires `uuid` + `metadata`; each entry in `results[]` requires `uuid`, `title`, `description`, `start`, and `reviewed-controls.control-selections` (at least one, may be an empty-selector "all controls" selection). `findings[]` entries require `uuid`, `title`, and a `target` object whose `implementation-status` is one of: `implemented`, `partial`, `planned`, `alternative`, `not-applicable`.
**When to use:** EXP-01 — map each `control_row` from `_build_report_data()` to one OSCAL `finding`.
**Example:**
```python
# Source: https://pages.nist.gov/OSCAL-Reference/models/v1.1.2/assessment-results/json-reference/
# [CITED: pages.nist.gov/OSCAL-Reference — assessment-results v1.1.2 required-field reference]
import uuid
from datetime import datetime, timezone

_IMPL_STATUS = {
    "Compliant": "implemented", "Implemented": "implemented", "Pass": "implemented", "Passed": "implemented",
    "Non-Compliant": "not-applicable" ,  # placeholder — planner should confirm mapping; see Open Questions
    "Warning": "partial", "In Progress": "partial",
}

def _to_oscal_assessment_results(framework: dict, control_rows: list) -> dict:
    now = datetime.now(timezone.utc).isoformat()
    return {
        "assessment-results": {
            "uuid": str(uuid.uuid4()),
            "metadata": {
                "title": f"{framework.get('name', framework.get('id'))} Assessment Results",
                "last-modified": now,
                "version": "1.0.0",
                "oscal-version": "1.1.2",
            },
            "import-ap": {"href": "#"},  # no formal assessment-plan model in this platform — stub required field
            "results": [{
                "uuid": str(uuid.uuid4()),
                "title": f"{framework.get('name', framework.get('id'))} Assessment Result",
                "description": f"Automated control/evidence assessment export for framework {framework.get('id')}",
                "start": now,
                "reviewed-controls": {
                    "control-selections": [{"description": "All controls in framework", "include-all": {}}]
                },
                "findings": [
                    {
                        "uuid": str(uuid.uuid4()),
                        "title": row["Control Name"] or row["Control ID"],
                        "description": row.get("Evidence Desc", "") or "No description",
                        "target": {
                            "type": "objective-id",
                            "target-id": row["Control ID"],
                            "status": {"state": _IMPL_STATUS.get(row["Control Status"], "partial")},
                        },
                    }
                    for row in control_rows
                ],
            }],
        }
    }
```

### Pattern 3: CycloneDX 1.6 SBOM from Trivy scan results
**What:** CycloneDX requires `bomFormat: "CycloneDX"`, `specVersion`, `version` (integer), and a `components[]` array where each component has `type`, `name`, `version`, `bom-ref`. Vulnerabilities live in a separate top-level `vulnerabilities[]` array, each referencing components via `affects[].ref` → the component's `bom-ref`. Deduplicate by `(pkg_name, installed_version)` since Trivy's `vulns` list has one row per CVE, not per package.
**When to use:** EXP-02 — transform one `container_scan_results` document (already has `image`, `vulns[]` with `pkg_name`/`installed_version`/`id`/`severity`) into CycloneDX.
**Example:**
```python
# Source: https://cyclonedx.org/docs/1.6/json/  [CITED: cyclonedx.org/docs/1.6/json]
import uuid

_CDX_SEV_MAP = {"CRITICAL": "critical", "HIGH": "high", "MEDIUM": "medium", "LOW": "low", "UNKNOWN": "unknown"}

def _to_cyclonedx(scan_result: dict) -> dict:
    components, comp_ref = [], {}
    for v in scan_result.get("vulns", []):
        key = (v["pkg_name"], v["installed_version"])
        if key not in comp_ref:
            ref = f"pkg:{v['pkg_name']}@{v['installed_version']}"
            comp_ref[key] = ref
            components.append({
                "type": "library",
                "bom-ref": ref,
                "name": v["pkg_name"],
                "version": v["installed_version"],
                "purl": f"pkg:generic/{v['pkg_name']}@{v['installed_version']}",
            })
    vulnerabilities = [{
        "id": v["id"],
        "source": {"name": "NVD"},
        "ratings": [{"severity": _CDX_SEV_MAP.get(v["severity"], "unknown")}],
        "description": v.get("description", ""),
        "affects": [{"ref": comp_ref[(v["pkg_name"], v["installed_version"])]}],
    } for v in scan_result.get("vulns", [])]
    return {
        "bomFormat": "CycloneDX",
        "specVersion": "1.6",
        "serialNumber": f"urn:uuid:{uuid.uuid4()}",
        "version": 1,
        "metadata": {"component": {"type": "container", "name": scan_result.get("image", "")}},
        "components": components,
        "vulnerabilities": vulnerabilities,
    }
```

### Anti-Patterns to Avoid
- **Wiring OSCAL/SBOM into `compliance_reporting_service.py`:** That module's file-write-then-download-by-filename pattern (`static/reports/` + `db.compliance_reports` ownership tracking) exists because CSV/Excel/PDF are large binary/formatted documents users re-download later. OSCAL and SBOM JSON documents are small and cheap — following the file-based pattern adds needless disk I/O, tenant-ownership bookkeeping, and a `download/{filename}` round-trip for no benefit. Follow the OCSF `GET`-returns-JSON pattern instead.
- **Reusing/renaming `sbom_endpoints.py`:** That file is a fully separate, already-shipped feature (host package inventory via Syft/pip/npm, `db.sboms`/`db.software_components`). Adding container-image SBOM export there would silently couple two unrelated data models and risk breaking the existing upload/generate/correlate-vulnerabilities flows. Add the new route to `container_scanner_endpoints.py` instead.
- **Treating "assets" in EXP-02's wording as the `assets` collection:** `container_scan_results` documents have no `assetId` field — they're keyed purely by `scan_id`/`image`. Do not attempt to join against `db.assets`; there is no such linkage in the current schema.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| UUID generation | Custom ID scheme | stdlib `uuid.uuid4()` | Both OSCAL and CycloneDX mandate RFC 4122 UUIDs for `metadata.uuid` / `bom-ref` / `serialNumber` — a homegrown ID format will fail schema validation in downstream OSCAL/CycloneDX tooling (e.g. NIST's oscal-cli validator, cyclonedx-cli) |
| ISO-8601 timestamps with timezone | Manual string formatting | `datetime.now(timezone.utc).isoformat()` | OSCAL's `last-modified`/`start` fields require timezone-qualified timestamps; a naive `datetime.now().isoformat()` (no tz) is a common validation failure mode |

**Key insight:** The *document assembly* (OSCAL/CycloneDX dict structure) is intentionally hand-rolled per the primary recommendation above — the "don't hand-roll" items here are narrow (UUIDs, timestamps), not the overall format generation.

## Common Pitfalls

### Pitfall 1: OSCAL `implementation-status` enum mismatch
**What goes wrong:** This platform's internal control-status vocabulary (`Compliant` / `Non-Compliant` / `Warning` / `Partially Compliant` / `Not Implemented`, per `_score_status()`/`_overall_verdict()` in `compliance_reporting_data.py`) does not map 1:1 onto OSCAL's five-value `implementation-status` enum (`implemented`, `partial`, `planned`, `alternative`, `not-applicable`). A naive mapping (e.g. `Non-Compliant` → `not-applicable`) is semantically wrong — `not-applicable` means the control doesn't apply, not that it failed.
**Why it happens:** The platform's status vocabulary was designed for human-readable dashboards (matching auditor Pass/Fail/Partial/No-Data conventions per the 03-01 STATUS_LEGEND decision already recorded in STATE.md), not for OSCAL's implementation-status semantics.
**How to avoid:** Confirm the mapping table explicitly during planning (flagged as Open Question 1 below) rather than guessing; document the chosen mapping inline in code with a comment citing this pitfall.
**Warning signs:** Any OSCAL consumer/validator reports "Non-Compliant control incorrectly excluded from scope" — a symptom of `not-applicable` being used for failing controls.

### Pitfall 2: CycloneDX component de-duplication using the wrong key
**What goes wrong:** `container_scan_results.vulns` has one entry **per CVE**, not per package — a single package (e.g. `libssl3` at one version) can have several CVEs. Building `components[]` by iterating `vulns` without deduplicating on `(pkg_name, installed_version)` produces duplicate component entries with the same `bom-ref`, which most CycloneDX consumers reject as invalid (BOM-ref must be unique within the document).
**Why it happens:** The existing `_parse_trivy_output()` in `container_scanner_service.py` is vulnerability-centric by design (built for the container-scan dashboard's CVE list view), not component-centric.
**How to avoid:** Build a `(pkg_name, installed_version) -> bom-ref` map first (see Pattern 3 above), and only append to `components[]` on first sight of a key.
**Warning signs:** `bom-ref` collisions surfaced by any CycloneDX JSON schema validator (e.g. `cyclonedx-cli validate`).

### Pitfall 3: Simulated (non-Trivy) scan results silently producing a "valid-looking" SBOM
**What goes wrong:** `container_scanner_service.py`'s `_simulated_results()` fallback (used when Trivy isn't installed, per the `simulated` field added in Phase 25 T-25-03) returns a fixed, fake CVE list. An SBOM generated from a `simulated: true` scan result is not a real bill of materials — exporting it without a warning could mislead an auditor into thinking it reflects the actual scanned image.
**Why it happens:** `scan_image()` transparently falls back to simulated data on any Trivy failure (not found, timeout, parse error) and callers historically haven't needed to distinguish real from simulated results for the CVE-dashboard use case.
**How to avoid:** The SBOM export endpoint must check `scan_result.get("simulated")` and either (a) refuse export with a 4xx explaining Trivy is unavailable, or (b) include a clear `metadata.properties` flag (e.g. `{"name": "omniagent:simulated", "value": "true"}`) in the CycloneDX output so downstream consumers know the data is synthetic. Planner must pick one.
**Warning signs:** Exported SBOM component list is always identical (the same 6 hardcoded CVEs from `_simulated_results()`) regardless of the image name.

### Pitfall 4: Auth pattern drift between the two new endpoints
**What goes wrong:** `compliance_reports_endpoints.py` (the OSCAL export's sibling file) uses `Depends(get_current_user)` + a manual `tenant_id` check with no RBAC permission gate. `container_scanner_endpoints.py` (the SBOM export's sibling file) uses `Depends(rbac_service.has_permission("view:dashboard"))`. Copying the wrong pattern into the wrong file breaks consistency within that file's existing auth model and could either over- or under-restrict access.
**Why it happens:** This codebase has two independently-evolved auth conventions for "compliance"-adjacent vs. "devsecops/container"-adjacent endpoints; there is no single unified pattern to copy blindly.
**How to avoid:** OSCAL endpoint (new file, joins the compliance-report family) → follow `compliance_reports_endpoints.py`'s exact pattern (`get_current_user` + manual tenant check, `_SUPER_ADMIN_ROLES` frozenset for cross-tenant access). SBOM endpoint (added to `container_scanner_endpoints.py`) → follow that file's exact pattern (`rbac_service.has_permission("view:dashboard")`, consistent with its `/scan` and `/results` routes). Consider `rbac_service.has_permission("view:sbom")` instead of `"view:dashboard"` for the SBOM route specifically, since `"view:sbom"`/`"manage:sbom"` permissions already exist in `rbac_service.py`'s role definitions for the (unrelated) host-SBOM feature and are the more semantically correct fit — but this is a judgment call for the planner, not a hard requirement, since it's a different resource than the existing `sbom_endpoints.py` SBOMs.
**Warning signs:** Code review flags an export endpoint with no auth dependency at all, or with a dependency copied from the wrong sibling file.

## Code Examples

Verified patterns from official sources:

### Frontend export button (extend existing pattern, do not invent a new one)
```typescript
// Source: existing components/ApiExtensionsDashboard.tsx exportOcsf() — generalize by renaming
// the existing function (it's already fetch+blob+download, format-agnostic) rather than adding
// a near-duplicate helper.
const exportFile = async (endpoint: string, filename: string) => {
  try {
    const res = await authFetch(endpoint);
    if (!res.ok) throw new Error(`Export failed (${res.status})`);
    const blob = await res.blob();
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a'); a.href = url; a.download = filename;
    a.click(); URL.revokeObjectURL(url);
    showToast(`Exported ${filename}`, 'success');
  } catch { showToast('Export failed', 'error'); }
};
// New button:
// <button onClick={() => exportFile(`/api/oscal/assessment-results?framework_id=${fw}`, 'assessment-results-oscal.json')}>
//   Export OSCAL
// </button>
```

### Router registration (one new line)
```python
# Source: existing backend/router_registry.py, line 241 region
_load(app, "ocsf_endpoints",              "router")
_load(app, "oscal_endpoints",             "router")   # NEW — add immediately after ocsf_endpoints
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|---------------|--------|
| CycloneDX 1.5 as the common baseline | CycloneDX 1.6 is the current ECMA-ratified stable spec; 1.7 released ~Oct 2025 with patent/provenance/crypto extensions [CITED: fossa.com/blog/whats-new-cyclone-dx-1-7, cyclonedx.org/specification/overview] | 1.6 ratified 2024; 1.7 Oct 2025 | Target 1.6 for this phase — broadest tool compatibility; none of 1.7's new fields (patents, crypto/CBOM) are relevant to a Trivy-package-list export |
| OSCAL v1.0.x | OSCAL v1.1.2 is the current stable release referenced by NIST's own reference docs [CITED: pages.nist.gov/OSCAL-Reference/models/v1.1.2] | ongoing NIST maintenance releases | Target `oscal-version: "1.1.2"` in the metadata field |

**Deprecated/outdated:** none directly relevant — both target specs are current stable releases, not deprecated versions.

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | Mapping of platform's `Non-Compliant`/`Warning`/`Compliant` status vocabulary onto OSCAL's `implementation-status` enum, as sketched in Pattern 2's `_IMPL_STATUS` dict | Pitfall 1 / Pattern 2 | An auditor-facing OSCAL export could misrepresent failing controls as "not applicable" — a compliance-credibility risk, not just a bug. Planner/user must confirm the mapping before implementation. |
| A2 | `component.type: "library"` and `purl: pkg:generic/...` are acceptable defaults for OS/library packages surfaced by Trivy (vs. distinguishing `type: "operating-system"` for OS packages) | Pattern 3 | Cosmetic — CycloneDX validators will still accept `"library"` for OS packages, but a stricter downstream consumer (e.g. a vulnerability-management platform ingesting the SBOM) might expect `"operating-system"` for OS-level packages. Low risk. |
| A3 | Simulated (non-Trivy) scan results should either block SBOM export or be flagge, per Pitfall 3 — exact behavior (block vs. flag) not yet decided | Pitfall 3 | If unaddressed, could ship an export feature that silently produces fake compliance evidence when Trivy isn't installed in the deployment environment. |

**If this table is empty:** N/A — see rows above; all three should be confirmed with the user or explicitly decided by the planner before/during implementation.

## Open Questions (RESOLVED)

1. **Exact OSCAL implementation-status mapping (see A1)**
   - What we know: OSCAL defines 5 valid values (`implemented`, `partial`, `planned`, `alternative`, `not-applicable`); this platform has its own ~5-value status vocabulary that doesn't semantically align 1:1.
   - What's unclear: Whether `Non-Compliant` should map to `not-applicable` (wrong per OSCAL semantics — reserved for out-of-scope controls) or whether a different modeling choice is needed (e.g. using OSCAL's `observations[]`/`risks[]` arrays instead of overloading `implementation-status` for failure states).
   - Recommendation: Planner should treat `Non-Compliant` findings as `implementation-status: "planned"` (control is in-scope, assessed, not yet fully implemented) rather than `not-applicable`, and additionally emit a `target.status.reason` or an `observations[]` entry describing the specific gap — this is the closer OSCAL-idiomatic pattern for "assessed and failing." Confirm with user if compliance-domain precision matters for this export's downstream consumers (e.g. FedRAMP submission vs. internal dashboard mirror).
   - **RESOLVED: `Non-Compliant` maps to `implementation-status: "planned"` + an `observations[]` gap note, as recommended — implemented in 27-01-PLAN.md.**

2. **Should SBOM export be gated on `simulated: false` (see A3)?**
   - What we know: `container_scanner_service.py` transparently falls back to hardcoded fake CVE data when Trivy is unavailable; the `simulated` boolean field already exists on every scan result (added Phase 25).
   - What's unclear: Whether the platform should refuse to export an SBOM for simulated scans (safer, but reduces feature availability in environments without Trivy installed) or export with a visible `simulated` flag embedded in the CycloneDX metadata (more permissive, matches existing dashboard behavior which already surfaces `containerResult.simulated` to the user).
   - Recommendation: Embed the flag (option b) — consistent with how `ContainerScanDashboard.tsx`/`IacContainerDashboard.tsx` already surface `simulated` in the UI rather than hiding simulated data. Blocking export entirely would be a UX regression relative to existing CVE-view behavior.
   - **RESOLVED: flag embedded via `metadata.properties`, export not blocked, as recommended — implemented in 27-02-PLAN.md.**

3. **Does OSCAL export need a `component-definition` variant in addition to `assessment-results`?**
   - What we know: EXP-01 says "OSCAL-conformant JSON for control/evidence data" — `assessment-results` (control status + evidence-backed findings) is the closer semantic fit than `component-definition` (which models reusable control implementations for a software component, not assessment outcomes).
   - What's unclear: Whether a future phase (e.g. Phase 28 Governance Document Management) expects a `component-definition` or `system-security-plan` (SSP) export instead/also.
   - Recommendation: Scope this phase strictly to `assessment-results` per the closer requirement match; do not build `component-definition` speculatively.
   - **RESOLVED: scoped strictly to `assessment-results`, as recommended — implemented in 27-01-PLAN.md.**

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| Trivy CLI | Real (non-simulated) container SBOM data | Not verified in this research pass — `container_scanner_service.py` already handles absence gracefully via `_simulated_results()` | — | Existing simulated-data fallback (see Pitfall 3 / Open Question 2) — no new fallback needed for this phase |
| Python stdlib (`uuid`, `datetime`) | OSCAL/CycloneDX document assembly | Yes | builtin | — |
| `pip` / PyPI registry access | Only needed if planner overrides the hand-roll recommendation | Yes (`pip index versions` succeeded in this research session) | pip 24.x+ | — |

**Missing dependencies with no fallback:** none.
**Missing dependencies with fallback:** Trivy (existing simulated fallback already in place, unrelated to this phase's new code).

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest (`pytest.ini` at repo root, `asyncio_mode = auto`) |
| Config file | `/home/user/enterprise-omni-agent-ai-platform/pytest.ini` |
| Quick run command | `pytest backend/tests/test_oscal_export.py backend/tests/test_container_sbom_export.py -x` (new files, see Wave 0 Gaps) |
| Full suite command | `pytest backend/tests -x` |

### Phase Requirements → Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| EXP-01 | `GET /api/oscal/assessment-results?framework_id=X` returns a structurally-valid OSCAL assessment-results document (uuid, metadata required fields, results[] with reviewed-controls + findings mapped from control_rows) | unit | `pytest backend/tests/test_oscal_export.py -x` | ❌ Wave 0 |
| EXP-01 | Tenant isolation: caller from tenant A cannot pull framework data scoped to tenant B via this endpoint (mirrors existing `_build_report_data(tenant_id=...)` scoping already exercised by `test_bundles_and_reports.py`) | unit | `pytest backend/tests/test_oscal_export.py -x -k tenant` | ❌ Wave 0 |
| EXP-02 | `GET /api/container/results/{scan_id}/sbom` returns valid CycloneDX 1.6 JSON (bomFormat/specVersion/components/vulnerabilities, no duplicate bom-refs) | unit | `pytest backend/tests/test_container_sbom_export.py -x` | ❌ Wave 0 |
| EXP-02 | Simulated scan results correctly flagged/handled per the Open Question 2 decision | unit | `pytest backend/tests/test_container_sbom_export.py -x -k simulated` | ❌ Wave 0 |

### Sampling Rate
- **Per task commit:** `pytest backend/tests/test_oscal_export.py backend/tests/test_container_sbom_export.py -x`
- **Per wave merge:** `pytest backend/tests -x`
- **Phase gate:** Full suite green before `/gsd-verify-work`

### Wave 0 Gaps
- [ ] `backend/tests/test_oscal_export.py` — covers EXP-01, follow the `TestClient` + `AsyncMock` DB mocking pattern already established in `backend/tests/test_bundles_and_reports.py` (mock `db.compliance_frameworks.find_one`, `db.asset_compliance.find`, etc., matching `_build_report_data()`'s query shape)
- [ ] `backend/tests/test_container_sbom_export.py` — covers EXP-02, mock `db._db.container_scan_results.find_one` (note: `container_scanner_service.py` uses the raw `db._db` accessor, not the tenant-isolated wrapper — see `save_result`/`list_results` in that file)
- No new framework/fixture install needed — pytest + AsyncMock already fully set up project-wide

## Security Domain

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-------------------|
| V2 Authentication | yes | Existing `get_current_user` (OSCAL) / `rbac_service.has_permission(...)` (SBOM) dependency injection — no new auth mechanism needed |
| V3 Session Management | no | Unchanged — reuses existing JWT session handling |
| V4 Access Control | yes | Tenant isolation: OSCAL export must filter by `tenant_id` exactly like `compliance_reports_endpoints.py`'s existing routes; SBOM export must verify the `scan_id` belongs to the caller's tenant (mirrors `container_scanner_service.list_results(db, tenant_id)` scoping) before serving |
| V5 Input Validation | yes | `framework_id` / `scan_id` path/query params must be validated to exist and belong to caller's tenant before use (404 vs 403 ordering — follow the existing `compliance_reports_endpoints.py` "check tenant BEFORE existence" pattern documented inline in that file, to avoid the same enumeration leak it was written to prevent) |
| V6 Cryptography | no | No new cryptographic material — UUIDs are identifiers, not secrets |

### Known Threat Patterns for this stack

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|-----------------------|
| Cross-tenant data disclosure via `framework_id`/`scan_id` enumeration | Information Disclosure | Verify tenant ownership before returning data (403 for wrong-tenant, not silently empty/404 — match existing precedent in `compliance_reports_endpoints.py`'s `download_compliance_report`) |
| Simulated scan data presented as authoritative compliance evidence | Spoofing (of assessment authenticity) | Explicit `simulated` flag surfaced in export output per Pitfall 3 / Open Question 2 — do not let synthetic Trivy fallback data pass as real evidence in an audit-facing export |
| Formula/script injection in exported JSON string fields (evidence descriptions, control names) | Tampering | Lower risk than CSV/XLSX (no formula auto-execution in JSON viewers), but still ensure `json.dumps`/FastAPI's default JSON encoder is used (never raw string concatenation) so embedded quotes/control characters can't break the document structure |

## Sources

### Primary (HIGH confidence)
- `pip index versions cyclonedx-python-lib` / `compliance-trestle` — direct PyPI registry queries run in this session [VERIFIED: pypi registry]
- Codebase read: `backend/compliance_reports_endpoints.py`, `compliance_reporting_data.py`, `compliance_reporting_service.py`, `compliance_reporting_pdf.py`, `ocsf_endpoints.py`, `container_scanner_service.py`, `container_scanner_endpoints.py`, `container_scan_endpoints.py`, `sbom_endpoints.py`, `router_registry.py`, `rbac_service.py`, `auth_roles.py` — direct file reads, exact current state of this repo

### Secondary (MEDIUM confidence)
- [OSCAL Assessment Results Model v1.1.2 JSON Format Reference](https://pages.nist.gov/OSCAL-Reference/models/v1.1.2/assessment-results/json-reference/) — required-field structure for metadata/root [CITED]
- [OSCAL Assessment Results Model v1.1.2 JSON Format Outline](https://pages.nist.gov/OSCAL-Reference/models/v1.1.2/assessment-results/json-outline/) — result-level required fields [CITED]
- [OSCAL Assessment Layer: Assessment Results Model](https://pages.nist.gov/OSCAL/learn/concepts/layer/assessment/assessment-results/) — finding object required fields (uuid, title, target, implementation-status enum) [CITED]
- [CycloneDX 1.6 JSON specification](https://cyclonedx.org/docs/1.6/json/) — bomFormat/specVersion/component/vulnerability structure [CITED]
- [What's New in CycloneDX 1.7](https://fossa.com/blog/whats-new-cyclone-dx-1-7/) — confirms 1.6 vs 1.7 delta, 1.6 remains broadly supported [CITED]
- [cyclonedx-python-lib on PyPI](https://pypi.org/project/cyclonedx-python-lib/) — confirms library is data-model-only, not a standalone generator [CITED]
- [compliance-trestle on GitHub (oscal-compass)](https://github.com/oscal-compass/compliance-trestle) — confirms full authoring-platform scope, not a lightweight export helper [CITED]

### Tertiary (LOW confidence)
- None used as authoritative — all WebSearch findings were cross-referenced against an official docs URL before being cited above.

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — hand-roll recommendation grounded in direct codebase precedent (`sbom_endpoints.py` already hand-parses CycloneDX) plus a legitimacy-gate result (SUS) against the main library alternative
- Architecture: HIGH — directly read every file in the existing export pipeline; the OCSF-vs-CSV/Excel/PDF pattern distinction is empirically verified, not assumed
- Pitfalls: MEDIUM — OSCAL status-mapping and simulated-data-handling pitfalls are real but their exact resolution (Open Questions 1 & 2) requires a product/compliance judgment call, not just engineering research

**Research date:** 2026-07-06
**Valid until:** 2026-08-05 (30 days — stable specs, low churn risk; re-verify CycloneDX/OSCAL point-release versions if this phase is replanned after that date)
