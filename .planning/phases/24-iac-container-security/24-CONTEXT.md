# Phase 24: IaC & Container Security - Context

**Gathered:** 2026-07-04
**Status:** Ready for planning

<domain>
## Phase Boundary

Implement Infrastructure-as-Code scanning (Terraform, CloudFormation, Kubernetes manifests — 25+ checks) and container image vulnerability scanning (Trivy-backed, with a simulated fallback), closing the #1 gap versus Checkov, Trivy, and Snyk identified in the June 2026 audit. Delivered as two backend services + routers, a shared frontend dashboard, and — critically — that dashboard actually wired into the running application's navigation.

</domain>

<decisions>
## Implementation Decisions

### Integration & Navigation
- `IacContainerDashboard` mounts as a new top-level Sidebar nav item under "Security (SecOps)" (`view: 'iacContainer'`), lazy-imported and `case`'d in `App.tsx` — following `ProgramsDashboard`'s pattern, the one dashboard in this milestone that is actually wired correctly. **This is load-bearing**: phases 17, 18, 20, 21, and 22 all shipped their dashboard components fully built but never wired into any nav path — completely unreachable in the running app. This phase must not repeat that.
- Nav icon: `FileCodeIcon` (already imported in `Sidebar.tsx`, unused elsewhere).
- RBAC: `view:cloud_security` gates reads/scans; `manage:settings` gates scan-config writes — same tiering phase 20 established for cloud-account endpoints.
- Scan results do NOT feed the existing compliance-score aggregation in this phase — out of scope per the plan.

### Scan Engine Behavior
- Trivy-unavailable fallback returns simulated results with an explicit `"note": "Trivy not installed"` field, per the plan.
- `scan_repo` (git URL) is an MVP placeholder — same result structure, "git support pending" note. No real `git clone` in this phase.
- `severity_threshold` config filters results below the threshold out of the response (matches `cloud_checks_service`'s severity-gating convention).
- Tenant isolation for `iac_scan_results`/`container_scan_results` uses the `TenantIsolatedCollection` wrapper — the codebase's established default.

### Frontend Presentation
- IaC Scanner tab: textarea paste as the primary code-input method (matches the plan's mockup); file upload as a stretch enhancement.
- Results tables sorted severity-first (critical → low), matching sibling dashboards.
- Historical results shown as a simple list below the scan form (matches `CloudAccountsDashboard`'s pattern) — not a separate History tab.
- Loading/error states: spinner + bound `catch (e: any)` surfacing the real error message — the corrected pattern from this session's WR-01 fixes (phase 20/21), not the older silent-catch pattern still found elsewhere in the codebase.

### File Organization
- Keep `iac_scanner_service.py` and `container_scanner_service.py` as separate files, per the plan.
- `IAC_CHECKS` starts inline in `iac_scanner_service.py`; split into `iac_checks_terraform.py`/`iac_checks_k8s.py` only if the file exceeds ~400 lines (phase 17's precedent for staying under the 500-line CLAUDE.md limit).
- One `test_iac_scanner.py` covering both scanners' 8 tests, per the plan's TDD order.
- Two separate routers: `iac_scanner_endpoints.py`, `container_scanner_endpoints.py`, per the plan's file list.

### Claude's Discretion
None — all 4 grey areas were accepted as recommended with no "you decide" deferrals.

</decisions>

<code_context>
## Existing Code Insights

### Reusable Assets
- `router_registry.py`'s `_load()` registration pattern (used by every prior phase's endpoints module).
- `TenantIsolatedCollection` (`database.py`) for tenant-scoped Mongo access.
- `rbac_service.has_permission()` gating pattern established in phase 20's WR-07 fix.
- Sidebar/App.tsx nav-wiring pattern from `ProgramsDashboard` (lazy import + switch `case` + Sidebar entry) — the correct reference implementation to copy, not the broken pattern in 17/18/20/21/22.

### Established Patterns
- Python: `snake_case`, `logging.getLogger(__name__)` per module, `HTTPException` for API errors, async/await + Motor throughout.
- TypeScript: dashboards follow a list + create-form + results-table shape (see `CloudAccountsDashboard.tsx`, `ProgramsDashboard.tsx`).
- Check-definition schema: `{id, name, description, provider/service, severity, frameworks, remediation}` — same shape as `CLOUD_CHECKS` (phase 17).

### Integration Points
- `backend/router_registry.py` — register `iac_scanner_endpoints` and `container_scanner_endpoints`.
- `App.tsx` — lazy import + `case 'iacContainer'` in the view switch.
- `components/Sidebar.tsx` — new nav item under "Security (SecOps)" section (alongside `cloudSecurity`).

</code_context>

<specifics>
## Specific Ideas

No specific UI mockup deviations from the plan's ASCII layout (2 tabs: IaC Scanner, Container Scanner — each with input + results table). The plan's TDD order (8 tests) and check list (18 Terraform/CloudFormation checks + 9 Kubernetes checks = 27 total) stand as specified.

</specifics>

<deferred>
## Deferred Ideas

- Wiring the 5 other orphaned dashboards (phases 17, 18, 20, 21, 22) into navigation — a real, separately-scoped fix, not part of this phase. Flagged to the user for a dedicated follow-up.
- Wiring IaC/container scan results into the compliance score aggregation — explicitly deferred per Integration & Navigation Q4.
- Real `git clone`-based repo scanning (`scan_repo`) — explicitly deferred per Scan Engine Behavior Q2.

</deferred>
