---
phase: "81"
slug: "autonomy-gate-stop-switch-activity-ledger"
# status lifecycle: draft (seeded by plan-phase) → validated (set by validate-phase §6)
# audit-milestone §5.5 distinguishes NOT-VALIDATED (draft) from PARTIAL (validated + nyquist_compliant: false) (#2117)
status: draft
nyquist_compliant: false
wave_0_complete: false
created: "2026-10-25"
---

# Phase 81 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.
> Source: `81-RESEARCH.md` § Validation Architecture, amended by `81-CONTEXT.md` D-21..D-24. Task IDs are assigned by the planner.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | Backend: pytest 9.1.1 + pytest-asyncio 1.4.0 (`asyncio_mode = auto`). Frontend: vitest 5.0.0 + @testing-library/react (jsdom). Rust: `cargo test` (folded todo only) |
| **Config file** | `pytest.ini` (root), `backend/pyproject.toml`, `backend/tests/conftest.py` (throwaway `omni_test_<pid>` DB); `vite.config.ts` `test:` block |
| **Quick run command** | `backend/venv/bin/python -m pytest backend/tests/<file> -q -p no:cacheprovider` and `npx vitest run src/__tests__/<file>` |
| **Full suite command** | `npx vitest run src/__tests__`, `npm run build`, and `TICKET_ATTACHMENT_DIR=$(mktemp -d) FILE_SHARE_DIR=$(mktemp -d) backend/venv/bin/python -m pytest backend/tests -q -p no:cacheprovider` |
| **Estimated runtime** | quick: seconds per file; full backend ~11 min (real-app probe modules spawn child processes) |

**Verified 2026-10-25 by research:** `pytest tests/test_distributed_lock.py tests/test_scheduler_lock.py` 9 passed in 0.4 s; `npx vitest run src/__tests__/catalogueAccess.test.ts` 44 passed in 2.9 s; `cargo test --offline --test integration` 21 passed (needs `PATH=$HOME/.cargo/bin:$PATH`). Last full-backend baseline (Phase 77): 4048 passed / 47 skipped.

---

## Sampling Rate

- **After every task commit:** the new or changed test file plus any exact-list test it touches.
- **After every plan wave:** `npx vitest run src/__tests__` and `backend/venv/bin/python -m pytest backend/tests/test_autonomous_ops_*.py backend/tests/test_rbac_defaults.py backend/tests/test_custom_role_mfa.py backend/tests/test_admin_mfa_required.py backend/tests/test_catalogue_manifest.py backend/tests/test_tenant_feature_switches.py backend/tests/test_remediation_guards.py backend/tests/test_autonomous_remediation_loop.py backend/tests/test_ueba_remediation_trigger.py -q -p no:cacheprovider`
- **Before `/gsd-verify-work`:** full suite green, including `npm run build` and the slow parity modules (`test_catalogue_route_parity.py`, `test_audit_parity.py`, `test_route_auth_baseline.py`).
- **Max feedback latency:** ~60 seconds per task (function-level files).

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| TBD | TBD | TBD | GATE-01 | — | Migration 024 writes an explicit level for every tenant (idempotent); Platform tenant stored Off (D-24b); new tenants default Undoable-auto | real-Mongo | `pytest backend/tests/test_autonomous_ops_migration.py` | ❌ W0 | ⬜ pending |
| TBD | TBD | TBD | GATE-02 | — | Unticked tenant = Off, refused and nothing recorded (D-23); unreadable settings = Suggest; literal tick membership; Platform tenant always refused | unit | `pytest backend/tests/test_autonomous_ops_gate.py` | ❌ W0 | ⬜ pending |
| TBD | TBD | TBD | GATE-03 | — | Exhaustive decision-table order; only the gate writes stamped autonomous instructions (AST structural test) | unit + structural | `pytest backend/tests/test_autonomous_ops_gate.py backend/tests/test_autonomous_ops_structural.py` | ❌ W0 | ⬜ pending |
| TBD | TBD | TBD | GATE-04 | — | Registry classes pinned; YAML only raises; every ACTION_MAP key registered; undo targets exist; every command capability-mapped | unit | `pytest backend/tests/test_autonomous_ops_registry.py backend/tests/test_agent_capabilities.py` | ❌ W0 / exists | ⬜ pending |
| TBD | TBD | TBD | GATE-05 | — | Legacy `run_cycle`/`generate_plan`/`execute_plan` symbols absent; no LLM imports in the package; only registry-listed stamped instructions with no `script`; confidence bypass removed; XDR selector/fallback cannot auto-run (D-21) | unit + structural | `pytest backend/tests/test_autonomous_ops_structural.py backend/tests/test_autonomous_remediation_loop.py backend/tests/test_autonomous_ops_xdr_fence.py` | ❌ W0 / modify | ⬜ pending |
| TBD | TBD | TBD | GATE-06 | — | Platform and tenant stop: decisions refused; queued stamped instructions withheld at both agent poll handlers and the response-task poll (D-21); undo delivered; approve refused; clear authority per D-11; no restart | unit + real-Mongo | `pytest backend/tests/test_autonomous_ops_stop.py backend/tests/test_agent_instruction_poll_tenant_scoping.py` | ❌ W0 / exists | ⬜ pending |
| TBD | TBD | TBD | GATE-07 | — | Intent written before dispatch (fault injection refuses dispatch); audit mirror per transition; `audit_ledger.verify` valid; retention never touches decision records | real-Mongo | `pytest backend/tests/test_autonomous_ops_ledger.py` | ❌ W0 | ⬜ pending |
| TBD | TBD | TBD | GATE-08 | — | Built-in never-touch entries cannot be removed; block of platform IP / management subnet refused; host cap = 1 | unit | `pytest backend/tests/test_autonomous_ops_protected.py` | ❌ W0 | ⬜ pending |
| TBD | TBD | TBD | GATE-09 | — | Env master and tenant flag each force shadow; shadow dispatches nothing; lifting shadow is Super Admin only | unit | `pytest backend/tests/test_autonomous_ops_gate.py` | ❌ W0 | ⬜ pending |
| TBD | TBD | TBD | GATE-10 | — | Two concurrent approves dispatch once; expired approval refused; expiry keeps running during a stop | real-Mongo | `pytest backend/tests/test_autonomous_ops_ledger.py backend/tests/test_autonomous_ops_stop.py` | ❌ W0 | ⬜ pending |
| TBD | TBD | TBD | GATE-11 | — | Two-tenant isolation of settings, ledger, queue and list; tenant ContextVar reset after each sweep iteration; lock renewal; `is_duplicate_task` tenant filter | real-Mongo | `pytest backend/tests/test_autonomous_ops_isolation.py backend/tests/test_distributed_lock.py backend/tests/test_response_orchestrator_tenant.py` | ❌ W0 / modify | ⬜ pending |
| TBD | TBD | TBD | GATE-12 | — | 5-minute offline cadence pinned by a frozen clock; the offline notification names the agents that went offline (D-24d) | unit | `pytest backend/tests/test_monitor_agent_status.py` | ❌ W0 | ⬜ pending |
| TBD | TBD | TBD | GATE-13 | — | Permission matrix over the real app (viewer, analyst, security_analyst, incident_responder, tenant_admin, platform_support, platform_billing, super_admin; API key vs session; level above cap 403; platform routes owner-only) | real-app probe | `pytest backend/tests/test_autonomous_ops_endpoints.py backend/tests/test_catalogue_slice_autonomous_ops.py` | ❌ W0 | ⬜ pending |
| TBD | TBD | TBD | GATE-14 | — | 3 consecutive undone/failed within 24 h trips to Suggest, previous level recorded, no auto re-arm; rate limit trips at 20/h; shadow rows excluded | unit | `pytest backend/tests/test_autonomous_ops_breaker.py` | ❌ W0 | ⬜ pending |
| TBD | TBD | TBD | ACTV-01 | — | Six state buckets, display fields (what/why/target/result), pagination, tenant selector gate; Stop/Resume + status readout (D-22) | backend + component | `pytest backend/tests/test_autonomous_ops_endpoints.py` ; `npx vitest run src/__tests__/AutonomousOpsActivity.test.tsx` | ❌ W0 | ⬜ pending |
| TBD | TBD | TBD | ACTV-03 | — | Shadow rows labelled as a simulation | component | `npx vitest run src/__tests__/AutonomousOpsActivity.test.tsx` | ❌ W0 | ⬜ pending |
| TBD | TBD | TBD | ACTV-08 | — | Banned terms fail both gates; negative controls; Windows Autopilot screen and `.planning/**` out of scope | pytest + vitest | `pytest backend/tests/test_autonomous_ops_copy.py` ; `npx vitest run src/__tests__/autonomousOpsCopy.test.ts` | ❌ W0 | ⬜ pending |
| TBD | TBD | TBD | D-15 | — | Stop banner shown only to users who can view the screen, with who/when/why | component | `npx vitest run src/__tests__/AutonomousOpsStopBanner.test.tsx` | ❌ W0 | ⬜ pending |
| TBD | TBD | TBD | Folded todo | — | Rust integration suite green; todo moved to completed | cargo | `cd agent-install/omni-agent-rs && PATH=$HOME/.cargo/bin:$PATH cargo test --offline --test integration` | ✅ | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `backend/tests/autonomy_support.py` — fake ledger and permissive-settings fixtures reused by the three legacy remediation test files
- [ ] `backend/tests/test_autonomous_ops_{registry,gate,ledger,stop,protected,breaker,isolation,structural,endpoints,migration,copy,xdr_fence}.py`, `backend/tests/test_catalogue_slice_autonomous_ops.py`, `backend/tests/test_monitor_agent_status.py`, `backend/tests/test_response_orchestrator_tenant.py`
- [ ] `src/__tests__/AutonomousOpsActivity.test.tsx`, `src/__tests__/AutonomousOpsStopBanner.test.tsx`, `src/__tests__/autonomousOpsCopy.test.ts`
- [ ] `shared/autonomous-ops-banned-terms.json`
- [ ] Updated existing tests: `test_rbac_defaults.py`, `test_custom_role_mfa.py`, `test_admin_mfa_required.py`, `test_catalogue_manifest.py`, `test_closure_delivery.py`, `test_role_visibility.py`, `src/__tests__/catalogueAccess.test.ts` (view counts 203/189 → 204/190), `test_remediation_guards.py`, `test_autonomous_remediation_loop.py`, `test_ueba_remediation_trigger.py`
- Framework install: none.

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Migration 024 applied on the live server | GATE-01 | Runs at backend restart, which is the user's step | Restart the backend; confirm every tenant has a stored level and `platform-admin` is Off |
| Platform stop holds back a queued instruction on a real agent poll without a restart | GATE-06 | Needs a live agent | Queue a stamped test instruction in shadow-off test tenant, press stop, confirm the next real poll does not deliver it |
| Agent status cadence on the live fleet | GATE-12 | Live timing | Stop an agent; confirm it shows Offline within ~5 minutes and the notification names it |
| Security Analyst / Incident Responder MFA enrolment prompt | GATE-13 / D-07 | Live sign-in flow | Sign in as each role; confirm the MFA enrolment prompt |
| UI publish: screen, Stop/Resume, banner | ACTV-01 / D-15 / D-22 | UI publish is the user's step | Open Autonomous Ops as an approver; press Stop; confirm the app-wide banner; Resume with a reason |
| Shadow stays on at first deploy; env master value | GATE-09 | Env value is a secret-file setting the user owns | Confirm `AUTONOMOUS_REMEDIATION_DRY_RUN` is not set to false, and every tenant's shadow flag is on |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 60s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
