---
gsd_state_version: 1.0
milestone: v1.1
milestone_name: — Evidence Quality & Compliance Scoring
status: executing
stopped_at: Phase 08 complete — bulk evidence upload delivered (8/8 verified)
last_updated: "2026-06-22T08:22:52.642Z"
progress:
  total_phases: 4
  completed_phases: 3
  total_plans: 9
  completed_plans: 8
  percent: 75
---

# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-06-20)

**Core value:** Any tenant can see exactly which compliance controls pass or fail across their endpoints — with trustworthy, current evidence and a numeric score to prove it.
**Current focus:** Phase 09 — compliance-score-dashboard

## Current Phase

**Next phase: Phase 6 — Asset Compliance Status + UI Fix**

Goal: Wire Mark Compliant / Mark Non-Compliant buttons to a real backend endpoint so compliance status changes persist; fix source badge font-size WCAG violation from v1.0 UI audit.

Status: Executing Phase 09

## Phases

| Phase | Name | Status |
|-------|------|--------|
| 1 | Rust Agent Evidence Parity | Complete (v1.0) |
| 2 | Manual Evidence Uploads | Complete (v1.0) |
| 3 | Audit-Ready Export | Complete (v1.0) |
| 4 | Remediation Workflow | Complete (v1.0) |
| 5 | Integration and E2E Verification | Complete (v1.0) |
| 6 | Asset Compliance Status + UI Fix | Pending |
| 7 | Evidence Lifecycle (Staleness + Chain-of-Custody) | Pending |
| 8 | Bulk Evidence Upload | Complete |
| 9 | Compliance Score Dashboard | Pending |

## Decisions

- agent_type added as trailing optional param (str | None = None) to preserve backward compatibility with all existing callers
- Direct import from compliance_evidence_processor eliminates fragile transitive re-export via compliance_endpoints
- Pytest unit test with AsyncMock DB chosen over live-server script for CI compatibility; __main__ live mode retained
- 02-01: asyncio.run() used for async test cases (pytest-asyncio not installed); consistent with existing test_rust_heartbeat_parity.py pattern
- 02-01: DELETE route is asset-scoped (/api/assets/{asset_id}/compliance/evidence/{evidence_id}) per plan phase decision
- 02-01: Path-traversal guard uses str(resolved).startswith(str(_safe_dir) + os.sep) to prevent sibling-path bypass
- 02-02: Removed explicit Content-Type from multipart FormData fetch so browser sets correct boundary (T-02-07)
- 02-02: isAutomated check uses ev.systemGenerated===true OR ev.source==='auto' to handle both backend field conventions
- 02-02: FrameworkDetail.tsx updated (Rule 3 fix) to satisfy new required onDeleteEvidence prop; calls onRefresh() after delete
- 03-01: STATUS_LEGEND maps internal vocabulary to auditor standard Pass/Fail/Partial/No-Data for Wave 2 renderers
- 03-01: tenant_id added as trailing optional str=None to _build_report_data/_generate_csv/_generate_all_csv for backward compatibility
- 03-01: _SUPER_ADMIN_ROLES defined at module level in compliance_reports_endpoints.py matching authoritative route pattern
- 03-02: tenant_id added as trailing optional str=None to _generate_pdf/_generate_excel/_generate_all_excel for backward compatibility
- 03-02: tenant name resolved via db.tenants.find_one({'id': tenant_id}) with fallback chain: doc.name -> tenant_id -> "Unknown Tenant"
- 03-02: det_widths extended to 15 entries; two 0.6-inch slots for Auto Evidence and Manual Evidence columns in PDF
- 04-00: "Run Compliance Scan" added to Rust dispatch arm alongside existing alternatives — resolves REM-03 string mismatch (Python uses "Run Compliance Scan"; Rust only matched "Run Compliance Check")
- 04-00: broadcast_remediation_update placed after broadcast_compliance_alert, uses list() snapshot copy matching broadcast_mitre_heatmap pattern
- 04-00: REM-04 test patches sio.emit with AsyncMock to avoid socketio runtime dependency in CI
- 04-01: compliance_remediation_tasks collection name avoids collision with remediation_tasks (continuous_compliance_service)
- 04-01: Router prefix /api/compliance-remediation avoids collision with /api/remediation (vulnerability domain)
- 04-01: suggest_remediation fits in 5 lines (def + docstring + 2-line f-string + return) keeping ai_service.py at 499 lines
- 04-01: Two-stage broadcast: PATCH endpoint broadcasts on dispatch (optimistic UI); report_instruction_result broadcasts on evidence arrival
- 04-02: Title field disabled when editing — immutable after creation to preserve audit trail; only description/assignee/due_date mutable on edit
- 04-02: suggestRemediation requires persisted task.id; button shows tooltip when creating new task
- 04-02: filterStatus in useCallback deps drives server-side status query param, not client-side filtering
- 05-00: GAP-1 fixed with getattr(user, 'role'/'tenant_id') in _tenant_filter; TokenData has no .get()
- 05-00: GAP-2 fixed by querying db.compliance_reports.find({tenantId}) instead of os.listdir scan
- 05-00: GAP-3 fixed by trailing fallback_tenant_id=None param on process_automated_evidence; heartbeat passes _hb_tenant_id
- 05-01: golden-path test drives process_automated_evidence, _flatten_evidence, _tenant_filter, and create_task in a single tenant-a flow
- 05-01: cross-tenant isolation verified for report download (403), report list (tenant-scoped), task list filter (tenant/super-admin), and evidence upload (403)
- 05-01: regression test confirms 3-arg process_automated_evidence call still writes evidence (no Phase 4 regression)
- [Phase ?]: 06-01: compliance_status_endpoints extracted to new file — compliance_evidence_endpoints.py at 447 lines; adding inline would breach 500-line CLAUDE.md limit
- [Phase ?]: 06-01: upsert=True on asset_compliance handles both first-time status set and subsequent overrides without separate insert logic
- [Phase ?]: 06-01: asyncio.run() used for async tests consistent with existing evidence upload test pattern
- [Phase ?]: 06-02: updateAssetComplianceStatus placed after deleteComplianceEvidence for logical grouping with other compliance evidence helpers
- [Phase ?]: 06-02: onUpdateStatus uses async arrow function capturing control.id from enclosing controls.map closure — no extra state needed
- [Phase ?]: 06-02: text-xs replaces text-[10px] for WCAG AA compliance — Tailwind utility class avoids arbitrary value anti-pattern
- 07-01: Raw Motor db._db.evidence_audit_log used in _append_coc_entry to prevent TenantIsolatedCollection double-injecting tenantId from request context
- 07-01: evidence_audit_log has no TTL index — compliance audit trails must be retained long-term per research Open Question 2
- 07-01: compute_stale does not gate on systemGenerated/source — caller in 07-02 is responsible for filtering manual evidence before invoking it
- 07-02: compliance_evidence_lifecycle_endpoints.py uses APIRouter() with NO prefix — serves both /api/settings and /api/compliance URL spaces
- 07-02: _require_admin copied inline (not imported from settings_endpoints) to keep lifecycle endpoints file self-contained
- 07-02: compliance_evidence_lifecycle_endpoints added to _REQUIRED_ROUTERS to fail startup fast on load error (T-07-09)
- 08-01: compliance_bulk_evidence_endpoints.py is a new file — compliance_evidence_endpoints.py at 495 lines would breach 500-line limit if bulk handler added inline
- 08-01: Validate-all-before-commit two-pass design — pass 1 validates every zip entry; pass 2 commits atomically only if errors == []; no partial commits
- 08-01: Manifest is a Form string (JSON) field, not a separate file upload — supports both hand-built and UI-built manifest flows
- 08-01: Bulk evidence written to control_evidence collection (not asset_compliance) — BULK-03 satisfied for free via existing GET /api/compliance/controls/{id}/evidence
- 08-01: MAX_BULK_FILES=50, MAX_BULK_BYTES=200 MB (uncompressed sum); per-file cap 25 MB; zip-bomb guard via sum(i.file_size for i in zf.infolist()) before any zf.read
- 08-01: Zip-slip guard: os.path.basename(raw_name.replace("\\", "/")) + stored filename is uuid4().hex+ext (never derived from zip entry name)
- 08-01: stored filename for bulk entries is uuid4().hex+ext (same as single-file pattern) — safe_name used only as display/db label
- 08-02: BulkEvidenceUploadModal.tsx is a new component — FrameworkDetail.tsx already at 857 lines; only import + state var + button + conditional render (≤4 lines net) added to host file
- 08-02: uploadBulkEvidence() uses FormData with no explicit Content-Type header (browser sets boundary automatically, same as T-02-07 decision)
- 09-01: invalidate_cache() is synchronous — called without await (cache_service.py def invalidate_cache, not async def; consistent with agent_registry_endpoints.py usage)
- 09-01: _score_status() copied inline to compliance_score_endpoints.py — avoids circular import risk (Pitfall 5 in RESEARCH.md, precedent from 07-02 _require_admin)
- 09-01: Category-based severity mapping — Access Control/Cryptography/Incident Response=Critical, Audit/Configuration/Vulnerability=High, Operations/Risk Management=Medium, default=Low

## Performance Metrics

| Phase | Plan | Duration | Tasks | Files |
|-------|------|----------|-------|-------|
| 01-rust-agent-evidence-parity | 01 | ~5m | 2 | 2 |
| 01-rust-agent-evidence-parity | 02 | ~3m | 1 | 1 |
| 02-manual-evidence-uploads | 01 | ~20m | 3 | 3 |
| 02-manual-evidence-uploads | 02 | ~15m | 2 | 3 |
| 03-audit-ready-export | 01 | ~4m | 3 | 4 |
| 03-audit-ready-export | 02 | ~3m | 2 | 4 |
| 04-remediation-workflow | 00 | ~3m | 3 | 3 |
| 04-remediation-workflow | 01 | ~4m | 3 | 7 |
| 04-remediation-workflow | 02 | ~3m | 3 | 4 |
| 05-integration-and-e2e-verification | 00 | ~3m | 4 | 5 |
| 05-integration-and-e2e-verification | 01 | ~7m | 3 | 1 |
| Phase 06-asset-compliance-status-ui-fix P01 | ~1m | 3 tasks | 3 files |
| Phase 06-asset-compliance-status-ui-fix P02 | ~2m | 3 tasks | 3 files |
| 07-evidence-lifecycle-staleness-chain-of-custody | 01 | ~3m | 3 | 4 |
| 07-evidence-lifecycle-staleness-chain-of-custody | 02 | ~5m | 3 | 4 |
| 09-compliance-score-dashboard | 01 | ~7m | 3 | 5 |

## Last Session

- **Timestamp:** 2026-06-22T00:00:00Z
- **Stopped at:** Phase 08 complete — 2 plans, 12 tests passing, 8/8 verified; 3 code review findings open (CR-01 role check, CR-02 zip-bomb bypass, CR-03 no rollback)
- **Resume file:** .planning/phases/09-compliance-score-dashboard/ (Phase 09)

## Configuration

- **Mode**: YOLO (auto-approve)
- **Granularity**: Standard
- **Parallelization**: Enabled
- **Models**: Balanced (Sonnet)
- **Research**: Enabled
- **Plan verification**: Enabled
- **Work verification**: Enabled
- **Git tracking**: Enabled

## Planning Docs

- [PROJECT.md](.planning/PROJECT.md)
- [REQUIREMENTS.md](.planning/REQUIREMENTS.md)
- [ROADMAP.md](.planning/ROADMAP.md)
- [Codebase map](.planning/codebase/)

---
*Initialized: 2026-06-17 | Last updated: 2026-06-20 (v1.1 milestone started — Evidence Quality & Compliance Scoring; phases 6–9 defined)*

## Session

**Last session:** 2026-06-22T08:22:52.631Z
**Stopped at:** Completed 07-02-PLAN.md
**Resume file:** None
