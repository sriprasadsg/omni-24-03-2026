---
gsd_state_version: 1.0
milestone: v3.0
milestone_name: — Competitive Feature Closure
status: Ready to plan
stopped_at: Phase 25 Plan 03 (Cloud Checks Execution Gaps — CHK-03) complete — container scan simulated flag added to both result paths, SIMULATED badge surfaced in 3 UI sites
last_updated: "2026-07-06T14:07:23.442Z"
progress:
  total_phases: 15
  completed_phases: 1
  total_plans: 4
  completed_plans: 3
  percent: 7
---

# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-06-20)

**Core value:** Any tenant can see exactly which compliance controls pass or fail across their endpoints — with trustworthy, current evidence and a numeric score to prove it.
**Current focus:** Phase 25 complete. Phase 26 — Vendor and Risk Data Completeness — ready to plan.

## Current Phase

**v2.0 Milestone — GRC Feature Parity: COMPLETE (verified 2026-07-05)**

Goal: Implement all 9 phases (14–22) identified in the June 2026 audit against Comp AI, Probo, OpenLane Core, and Prowler.

All 9 phases (14–22) verified complete this session: every phase's test suite was re-run directly and passes, and 5 dashboards that were fully built but never reachable in the app (`SaaSIntegrationsDashboard`, `PrivacyLegalDashboard`, `CloudAccountsDashboard`, `NotificationsDashboard`, `ApiExtensionsDashboard`) were wired into `App.tsx`/`Sidebar.tsx` navigation — the same class of gap `16-VERIFICATION.md` had caught for `ProgramsDashboard` a day earlier.

**v2.1 Milestone — Windows PowerShell Evidence + IaC/Container Security: COMPLETE (verified 2026-07-05)**

Phase 23 complete. Phase 24 (IaC & Container Security) — all 16 `24-REVIEW.md` findings (5 critical) fixed, 8/8 tests pass (re-run and confirmed), dashboard restyled from inline dark theme to Tailwind per `24-UI-SPEC.md`, and wired into `App.tsx`/`Sidebar.tsx`/`types.ts` navigation under Security (SecOps). Confirmed reachable via production build chunk output.

**v3.0 Milestone — Competitive Feature Closure: IN PROGRESS (started 2026-07-06)**

14 new phases (25–38) added to the roadmap from a feature-parity audit run 2026-07-06 against Comp AI, Probo, OpenLane Core, and Prowler (69 features checked directly against source: 41 implemented, 10 partial, 15 absent, 3 unique differentiators). Ordered in 3 risk tiers — quick fixes (25–27), medium features (28–33), architectural bets (34–38).

Phase 25 (Cloud Checks Execution Gaps) complete and verified 2026-07-06: full pipeline (research → pattern-map → plan → plan-check → execute → code-review → fix → goal-verify → security-verify → UAT). Code review found and fixed 2 critical CloudFormation rule PASS/FAIL inversions plus 6 warnings. Goal verification: 15/15 must-haves confirmed. The one human-verification item (SIMULATED badge visual prominence) was confirmed by actually running the app end-to-end — backend+frontend dev servers, headless Chrome driven via raw CDP, real login, real scan trigger, screenshot — which also surfaced and fixed a real pre-existing bug (`container_scanner_endpoints.py` missing the `response: Response` param slowapi's rate limiter requires, causing every real `/api/container/scan` request to 500; unit tests never caught it since they bypass the route/middleware stack). 1/14 v3.0 phases complete.

## Phases

| Phase | Name | Status |
|-------|------|--------|
| 1 | Rust Agent Evidence Parity | Complete (v1.0) |
| 2 | Manual Evidence Uploads | Complete (v1.0) |
| 3 | Audit-Ready Export | Complete (v1.0) |
| 4 | Remediation Workflow | Complete (v1.0) |
| 5 | Integration and E2E Verification | Complete (v1.0) |
| 6 | Asset Compliance Status + UI Fix | Complete (v1.1) |
| 7 | Evidence Lifecycle (Staleness + Chain-of-Custody) | Complete (v1.1) |
| 8 | Bulk Evidence Upload | Complete (v1.1) |
| 9 | Compliance Score Dashboard | Complete (v1.1) |
| 10 | Scheduled Compliance Reports | Complete (v1.2) |
| 11 | Security Hardening | Complete (v1.3) |
| 12 | Agentic AI Integration | Complete (v1.4) |
| 13 | AI Compliance Narratives | Complete (v1.5) |
| 14 | SaaS Evidence Integration | Complete (v2.0) |
| 15 | Evidence Review Workflow | Complete (v2.0) |
| 16 | Program Control Grouping | Complete (v2.0) |
| 17 | Cloud Checks Expansion | Complete (v2.0) |
| 18 | Privacy & Legal Modules | Complete (v2.0) |
| 19 | Additional Compliance Frameworks | Complete (v2.0) |
| 20 | Multi-Account Cloud Scanning | Complete (v2.0) |
| 21 | Notification Routing & Domain Scanner | Complete (v2.0) |
| 22 | API Extensions (MCP, OCSF, CLI, DO) | Complete (v2.0) |
| 23 | Windows PowerShell Evidence Collection | Complete (v2.1) |
| 24 | IaC & Container Security | Complete (v2.1) |
| 25 | Cloud Checks Execution Gaps | Complete (v3.0) |
| 26 | Vendor and Risk Data Completeness | Planned — 5 plans, 2 waves, checker passed (v3.0) |
| 27 | Compliance Export Formats (OSCAL and SBOM) | Planned — 2 plans, 1 wave, checker passed (v3.0) |
| 28 | Governance Document Management | Pending (v3.0) |
| 29 | Public Trust Center | Pending (v3.0) |
| 30 | AI Questionnaire Auto-Answer | Pending (v3.0) |
| 31 | FAIR Risk Quantification | Pending (v3.0) |
| 32 | Cloud and SaaS Provider Expansion | Pending (v3.0) |
| 33 | Workflow Automation Connectors | Pending (v3.0) |
| 34 | Passkey and WebAuthn Authentication | Pending (v3.0) |
| 35 | GraphQL API | Pending (v3.0) |
| 36 | Fine-Grained Relationship-Based Authorization | Pending (v3.0) |
| 37 | Spec-Compliant MCP Server | Pending (v3.0) |
| 38 | Interactive AI Security Assistant | Pending (v3.0) |

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
- 09-02: ComplianceScorePanel.tsx at exactly 250 lines (plan limit); all UI states (loading/error/empty/normal) implemented
- 09-02: invalidate_cache() called synchronously on success path only — not inside exception handlers
- [Phase ?]: 10-01: email_service imported at module level for testability; schedule_history_idx in database.py (not app_startup.py); ValueError maps to 422 for SMTP validation
- 10-02: Inline approach (no ScheduleHistoryPanel.tsx split) — post-Task-1 line count was 342; adding history landed at 409 lines, under 500 threshold
- 10-02: DeliveryLog interface defined inline in ScheduledReportsDashboard.tsx (not in types.ts) — component-local
- 10-02: historyLogs cached by schedule id — avoids re-fetching on panel toggle; cleared on page reload
- 14-01: access_token_enc/refresh_token_enc field names (not access_token/refresh_token) make encryption status explicit in schema
- 14-01: _access_token_plain injection key in connection dict enables clean test mocking without Fernet round-trips in test setup
- 14-01: pull_all_evidence stores partial evidence on API error — logs warning, never raises to caller
- 14-01: OAuthProvider enum backed by str for JSON serialization compatibility with FastAPI
- 14-01: Tenant isolation check in pull-evidence returns 403 (not 404) to avoid leaking connection existence to cross-tenant callers
- 14-02: router_registry.py saas_integration_endpoints already registered in wave 1 (line 142) — no change needed in wave 2
- 14-02: OAuth popup cleanup uses setInterval poll on popup.closed to remove listener when user closes popup without completing auth
- 14-02: pulling/disconnecting tracked as Record<string,boolean> keyed by connection ID to support independent per-provider loading states
- [Phase ?]: 25-01: RUNNABLE_PROVIDERS widened to 5-tuple (aws, azure, gcp, kubernetes, digitalocean); all four provider-allowlist gates widened in a single lockstep commit so no gate accepts a provider another rejects
- [Phase ?]: 25-02: 18 CFN rules added verbatim from RESEARCH.md Pattern 2 — parity with Terraform's 17 rules, scope_lines preserved on every greedy negative_pattern (ReDoS mitigation T-25-02)
- [Phase ?]: 25-02: _CFN_TYPE_RE module-level regex fixes _detect_provider() YAML CloudFormation misclassification (pre-existing bug, T-25-02b) — checked in yaml/yml branch, json/template branch, and as extension-less fallback
- [Phase ?]: 25-02: CloudFormation early-return stub in scan_code() removed — CFN now flows through the same provider-filtered IAC_CHECKS dispatch as Terraform/Kubernetes
- [Phase 25]: 25-03: simulated field added purely additively (no fail-closed change) to preserve existing container fallback tests per Pitfall 4

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
| 09-compliance-score-dashboard | 02 | ~5m | 2 | 4 |
| Phase 10-scheduled-reports P01 | ~6m | 3 tasks | 5 files |
| Phase 10-scheduled-reports P02 | ~4m | 2 tasks | 1 file |
| 14-saas-evidence-integration | 01 | ~4m | 4 | 4 |
| Phase 14-saas-evidence-integration P02 | ~2m | 2 tasks | 1 files |
| Phase 23 P02 | 336 | 9 tasks | 8 files |
| Phase 25-cloud-checks-execution-gaps P01 | 12min | 2 tasks | 6 files |
| Phase 25-cloud-checks-execution-gaps P02 | 5min | 2 tasks | 2 files |
| Phase 25-cloud-checks-execution-gaps P03 | 6min | 2 tasks | 3 files |

## Last Session

- **Timestamp:** 2026-07-06T14:10:00.000Z
- **Stopped at:** Phase 25 (Cloud Checks Execution Gaps) complete — verified, secured, UAT passed. Ready to plan Phase 26.
- **Resume file:** None

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
*Initialized: 2026-06-17 | Last updated: 2026-06-22 (v1.1 milestone complete — Phase 09 compliance score dashboard verified)*

## Session

**Last session:** 2026-07-06T14:10:00.000Z
**Stopped at:** Phase 25 (Cloud Checks Execution Gaps) complete — verified, secured, UAT passed. Ready to plan Phase 26.
**Resume file:** None

## Accumulated Context

### Roadmap Evolution

- Phase 24 added: IaC & Container Security (Terraform/CloudFormation/Kubernetes scanning + container image vulnerability scanning). A `24-01-PLAN.md` already existed on disk (drafted ahead of execution, never wired into ROADMAP.md) — registered as Phase 24 in ROADMAP.md and REQUIREMENTS.md (IAC-01..03) reusing the existing directory/plan rather than generating a new one, so `/gsd-autonomous --only 24` can discover and execute it.
- v3.0 milestone added 2026-07-06: 14 new phases (25–38) scaffolded from a feature-parity audit run the same day against Comp AI, Probo, OpenLane Core, and Prowler (69 features checked directly against source — 41 implemented, 10 partial, 15 absent). Phases are ordered in 3 risk tiers — Tier 1 quick fixes (25–27), Tier 2 medium features (28–33), Tier 3 architectural bets (34–38: GraphQL, ReBAC, real MCP protocol, public Trust Center, passkeys). User explicitly chose "everything, in tiers" over a smaller subset. Requirements CHK/VRISK/RISK/EXP/DOC/TRUST/RAG/FAIR/PROV/WF/AUTH/GQL/REBAC/MCP/ASSIST added to REQUIREMENTS.md. Phase 25 is the first to go through full research → plan → verify.
