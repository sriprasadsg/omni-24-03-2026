# Roadmap: Enterprise OmniAgent — Security & Compliance Portal

**Created:** 2026-06-17
**Methodology:** Vertical MVP slices

## Overview

This roadmap completes the brownfield security compliance portal by verifying and wiring what is already built, then filling the gaps. Phases deliver working, verifiable capabilities in dependency order: agent evidence first, then manual evidence, then export, then remediation, then end-to-end validation. Every phase leaves the system in a demonstrably better state than it started.

## Phases

- [x] **Phase 1: Rust Agent Evidence Parity** - Rust agent heartbeat compliance data flows through `compliance_evidence_processor` identically to the Python agent (completed 2026-06-17)
- [x] **Phase 2: Manual Evidence Uploads** - Auditors can attach files to controls and view them alongside automated evidence (completed 2026-06-17)
- [ ] **Phase 3: Audit-Ready Export** - Per-tenant, per-framework PDF and Excel reports are complete and auditor-ready
- [ ] **Phase 4: Remediation Workflow** - Failed controls get assignable tasks; resolution triggers re-scan and evidence update
- [ ] **Phase 5: Integration and E2E Verification** - All four capabilities work together end-to-end across the full pipeline

## Phase Details

### Phase 1: Rust Agent Evidence Parity

**Goal**: Rust agent heartbeat compliance data is processed by the backend with identical logic to the Python agent, producing evidence records that appear in the frontend
**Depends on**: Nothing (verification of existing infrastructure)
**Requirements**: RUST-01, RUST-02, RUST-03
**Success Criteria** (what must be TRUE):

  1. A Rust agent heartbeat containing `meta.compliance_enforcement` results in evidence records appearing in the compliance control detail view in the frontend
  2. Evidence records written from Rust agent heartbeats share the same DB schema as Python agent evidence, with `agent_type: rust` preserved in metadata
  3. All 12 Rust agent compliance checks (Firewall Profiles, Windows Defender, BitLocker Encryption, UAC, RDP, SMBv1, Password Policy, Audit Logging, Windows Update, PowerShell Script Block Logging, WinRM, Secure Boot) produce evidence mapped to correct framework control IDs via `COMPLIANCE_CHECK_MAPPINGS`
  4. Sending a simulated Rust agent heartbeat payload to the heartbeat endpoint triggers `process_automated_evidence` and the resulting records are visible in the UI

**Plans**: 2 plansPlans:
**Wave 1**

- [x] 01-01-PLAN.md — Fix backend: extend process_automated_evidence with agent_type; fix heartbeat import and kwarg passthrough

**Wave 2** *(blocked on Wave 1 completion)*

- [x] 01-02-PLAN.md — Verify and simulate: write simulation test, run against live backend, assert agent_type in DB records (Task 1 committed; checkpoint:human-verify pending)

**UI hint**: yes

### Phase 2: Manual Evidence Uploads

**Goal**: Authenticated users can attach files to specific compliance controls, view those files alongside automated evidence, and delete them
**Depends on**: Phase 1
**Requirements**: EVID-01, EVID-02, EVID-03, EVID-04, EVID-05
**Success Criteria** (what must be TRUE):

  1. A user can select a control in the frontend, click an attach button, upload a PDF/PNG/JPEG/DOCX/XLSX file (up to 25 MB), and see it appear in the control detail view
  2. Uploaded evidence records include control ID, uploader identity, timestamp, and user-provided description, scoped per tenant
  3. Uploaded files appear in the same control detail view as automated (agent-collected) evidence, visually labelled by source
  4. A file owner can delete their own uploaded evidence; an admin can delete any tenant's uploaded evidence
  5. Uploading a file whose MIME type does not match its extension is rejected with a clear error message

**Plans**: 2 plans

**Wave 1**

- [x] 02-01-PLAN.md — Backend evidence endpoint fixes: 25 MB size cap, full metadata (uploaded_by/description/tenantId/source/systemGenerated), asset-scoped DELETE with owner/admin RBAC, stdlib magic-byte MIME validation

**Wave 2** *(blocked on Wave 1 completion)*

- [x] 02-02-PLAN.md — Frontend evidence UI: fix multipart Content-Type bug, add description input, Manual/Automated source badge, per-row delete button, deleteComplianceEvidence API wrapper

**UI hint**: yes

### Phase 3: Audit-Ready Export

**Goal**: Users can export a complete, auditor-ready compliance report for any framework as PDF or Excel, scoped strictly to their tenant
**Depends on**: Phase 2
**Requirements**: AUDIT-01, AUDIT-02, AUDIT-03, AUDIT-04
**Success Criteria** (what must be TRUE):

  1. A user can select a framework and click Export PDF; the downloaded file includes framework name, tenant name, export date, all controls with Pass/Fail/Partial/No-Data status, and evidence count per control
  2. A user can export the same report as XLSX with one row per control and evidence summary columns
  3. Both PDF and Excel exports include automated evidence (agent-collected) and manual evidence (uploaded files) per control, each labelled by source
  4. A tenant user's export contains only their own compliance data; no other tenant's controls or evidence appear in the output

**Plans**: 2 plans

**Wave 1**

- [ ] 03-01-PLAN.md — Data layer: source-bucket evidence ([Auto]/[Manual] + auto/manual counts), legacy download tenant-ownership check, thread tenant_id through service→data chain

**Wave 2** *(blocked on Wave 1 completion)*

- [ ] 03-02-PLAN.md — Renderers: tenant-name + export-date headers and Auto/Manual evidence columns in PDF and XLSX generators

### Phase 4: Remediation Workflow

**Goal**: A failed control can have a remediation task created, tracked, and resolved, with re-scan triggered and control status updated automatically
**Depends on**: Phase 1
**Requirements**: REM-01, REM-02, REM-03, REM-04
**Success Criteria** (what must be TRUE):

  1. A user can click on a failed control and create a remediation task with title, assignee (agent or user), due date, and description
  2. Remediation tasks appear in a dedicated list view with filterable status: Open, In Progress, Resolved
  3. Marking a task Resolved dispatches a re-scan instruction to the assigned agent for the associated control
  4. After re-scan, new evidence arriving for that control updates the control's compliance status automatically in the frontend without manual refresh

**Plans**: TBD
**UI hint**: yes

### Phase 5: Integration and E2E Verification

**Goal**: All four capabilities work together as a coherent compliance portal — agent evidence, manual uploads, export, and remediation function end-to-end in the same tenant context
**Depends on**: Phase 2, Phase 3, Phase 4
**Requirements**: (cross-cutting verification — no new requirements)
**Success Criteria** (what must be TRUE):

  1. Starting from a fresh Rust agent heartbeat, a user can trace the evidence record through to a control detail view, attach a supplemental file, export the combined evidence in a PDF report, create a remediation task for a failed control, and see the control status update after re-scan — all within a single tenant session
  2. All tenant isolation boundaries hold: uploading evidence, exporting reports, and creating remediation tasks in tenant A never expose or modify data in tenant B
  3. All file upload rejections (wrong MIME, oversized) and export edge cases (no evidence, all-pass controls) produce clear, correct UI feedback
  4. No regressions in existing Python agent evidence flow

**Plans**: TBD
**UI hint**: yes

## Progress Table

| Phase | Plans Complete | Status | Completed |
|-------|----------------|--------|-----------|
| 1. Rust Agent Evidence Parity | 2/2 | Complete   | 2026-06-17 |
| 2. Manual Evidence Uploads | 2/2 | Complete   | 2026-06-17 |
| 3. Audit-Ready Export | 0/2 | Planned | - |
| 4. Remediation Workflow | 0/? | Not started | - |
| 5. Integration and E2E Verification | 0/? | Not started | - |

## Coverage

| Requirement | Phase |
|-------------|-------|
| RUST-01 | Phase 1 |
| RUST-02 | Phase 1 |
| RUST-03 | Phase 1 |
| EVID-01 | Phase 2 |
| EVID-02 | Phase 2 |
| EVID-03 | Phase 2 |
| EVID-04 | Phase 2 |
| EVID-05 | Phase 2 |
| AUDIT-01 | Phase 3 |
| AUDIT-02 | Phase 3 |
| AUDIT-03 | Phase 3 |
| AUDIT-04 | Phase 3 |
| REM-01 | Phase 4 |
| REM-02 | Phase 4 |
| REM-03 | Phase 4 |
| REM-04 | Phase 4 |

**Coverage:** 16/16 v1 requirements mapped, 0 orphans.

---
*Roadmap created: 2026-06-17*
