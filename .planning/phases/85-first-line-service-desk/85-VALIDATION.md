---
phase: "85"
slug: "first-line-service-desk"
# status lifecycle: draft (seeded by plan-phase) → validated (set by validate-phase §6)
# audit-milestone §5.5 distinguishes NOT-VALIDATED (draft) from PARTIAL (validated + nyquist_compliant: false) (#2117)
status: validated
nyquist_compliant: true
wave_0_complete: true
created: "2026-11-08"
validated: "2026-11-09"
---

# Phase 85 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution. Filled in by plan 85-23 from the real plans and the final gate run. Everything that needs Ollama, a real CPU measurement, a real Windows tray or the live server is in the Manual-Only table and stays open until the user does it.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest (backend; root `pytest.ini` sets `asyncio_mode = auto`; DB fixture `backend/tests/_mongo_test_db.py`, helpers `backend/tests/autonomy_support.py` and `backend/tests/service_desk_support.py`), Vitest (UI) |
| **Config file** | `pytest.ini` (repo root), `backend/tests/conftest.py`, `package.json` (`"test": "vitest run"`) |
| **Quick run command** | `backend/venv/bin/python -m pytest backend/tests/test_service_desk_sanitize.py backend/tests/test_service_desk_rules.py backend/tests/test_service_desk_retrieval.py backend/tests/test_service_desk_output_checks.py -q -p no:cacheprovider` (pure tests, no DB) |
| **Full suite command** | `MONGO_TEST_URL=mongodb://127.0.0.1:27998 MONGODB_URL=mongodb://127.0.0.1:27998 MONGO_URI=mongodb://127.0.0.1:27998 TICKET_ATTACHMENT_DIR=$(mktemp -d) FILE_SHARE_DIR=$(mktemp -d) backend/venv/bin/python -m pytest backend/tests/test_service_desk_*.py backend/tests/test_autonomous_ops_*.py backend/tests/test_catalogue_slice_autonomous_ops.py backend/tests/test_catalogue_slice_billing_identity.py backend/tests/test_catalogue_slice_agents.py backend/tests/test_catalogue_slice_agents_dataplane.py backend/tests/test_catalogue_slice_settings_ops.py backend/tests/test_catalogue_route_parity.py backend/tests/test_catalogue_manifest.py backend/tests/test_route_auth_baseline.py backend/tests/test_tickets.py backend/tests/test_ticket_staff_*.py backend/tests/test_notification_*.py backend/tests/test_patch_rollout_activity.py backend/tests/test_rbac_defaults.py backend/tests/test_effective_permissions.py backend/tests/test_closure_delivery.py backend/tests/test_login_me_permissions.py backend/tests/test_roles_endpoint.py backend/tests/test_platform_roles.py backend/tests/test_bundles_and_reports.py backend/tests/test_audit_ledger.py backend/tests/test_pending_agents.py -q -p no:cacheprovider`; UI `npx vitest run src/__tests__` and `npm run build` |
| **Rust (agent 2.1.18)** | `PATH=$HOME/.cargo/bin:$PATH CARGO_BUILD_JOBS=1 CARGO_PROFILE_DEV_DEBUG=0 CARGO_TARGET_DIR=agent-install/omni-agent-rs/target/nodebug cargo test --offline --manifest-path agent-install/omni-agent-rs/Cargo.toml --lib tray_` and `cargo check --offline --manifest-path agent-install/omni-agent-rs/Cargo.toml --lib --target x86_64-pc-windows-gnu` |
| **Estimated runtime** | ~30 seconds per quick run; about 20 minutes for the full backend list on the private mongod (2,696 tests after the second gap round), about 4 minutes for vitest |

DB tests must use a private mongod, never the live one on 27017: `GLIBC_TUNABLES=glibc.pthread.rseq=1 /usr/bin/mongod --dbpath <scratch> --port 27998 --bind_ip 127.0.0.1 --fork --logpath <scratch>/m.log --pidfilepath <scratch>/m.pid`.

---

## Sampling Rate

- **After every task commit:** Run the task's new test file plus `test_autonomous_ops_structural.py`, `test_service_desk_structural.py` and `test_autonomous_ops_copy.py`
- **After every plan wave:** Run the full backend list above plus the touched Vitest files
- **Before `/gsd-verify-work`:** Full suite must be green. Existing `test_autonomous_ops_*`, `test_tickets.py` and the catalogue slice tests stay green
- **Max feedback latency:** 120 seconds (per quick run)

---

## Per-Task Verification Map

Requirement-level map from `85-RESEARCH.md` § Validation Architecture, with the real plan and task ids. Rows added after the draft (tracer, ledger, pipeline, hand-off, portal routes, returns, withdraw, eval script, starters, tray contract, tray actions, tray server contract) are marked (added).

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| 85-03 T1, 85-04 T1-T2, 85-18 T2 | 85-03, 85-04, 85-18 | 1, 3, 5 | DESK-01 | T-85-02, T-85-12, T-85-13, T-85-15, T-85-68 | Post vs draft vs shadow vs refuse across switch, level, shadow, stop, desk budget and desk breaker; confirm closes; nothing auto-closes | integration (mongo) | `pytest backend/tests/test_service_desk_gate.py backend/tests/test_service_desk_lifecycle.py` | ✅ | ✅ green |
| 85-08 T1-T2 | 85-08 | 3 | DESK-01 | T-85-26, T-85-27, T-85-28 | Comment visibility defaults to staff; a staff-only comment never notifies or previews to the reporter; recipient-filtered notices | integration | `pytest backend/tests/test_service_desk_comments.py` | ✅ | ✅ green |
| 85-05 T2-T3 | 85-05 | 3 | DESK-02 | T-85-17, T-85-18 | Sensitive, ask-for-a-person, fulfilment, critical-priority and tenant-word rules pinned by the escalation set; password how-to answerable, unlock/MFA/access not | unit | `pytest backend/tests/test_service_desk_rules.py` | ✅ | ✅ green |
| 85-06 T1 | 85-06 | 3 | DESK-02 | T-85-20, T-85-21 | Cut-off and minimum-terms rule pinned by the retrieval set on the starter articles; only the tenant's own Help desk articles; global seed never cited | unit + mongo | `pytest backend/tests/test_service_desk_retrieval.py` | ✅ | ✅ green |
| 85-05 T1, 85-06 T2, 85-13 T2 | 85-05, 85-06, 85-13 | 3, 4 | DESK-03 | T-85-16, T-85-19, T-85-46, T-85-47, T-85-48 | Sanitiser strips HTML, links and control characters before the model; compliant-stub injection set rejected by output checks; no agent-queue write | unit | `pytest backend/tests/test_service_desk_sanitize.py backend/tests/test_service_desk_injection.py backend/tests/test_service_desk_output_checks.py` | ✅ | ✅ green |
| 85-07 T3 | 85-07 | 3 | DESK-03 | T-85-22, T-85-23 | `service_desk/` imports and queue writes are fenced by an AST test; no LLM imports inside `autonomous_ops/` | unit | `pytest backend/tests/test_service_desk_structural.py backend/tests/test_autonomous_ops_structural.py` | ✅ | ✅ green |
| 85-07 T1 | 85-07 | 3 | DESK-04 | T-85-03, T-85-24, T-85-25 | Ollama down, tag missing, 503, bad JSON, mock-only or scratch wrapper → hand-off, never a post; loopback-only URL | unit (MockTransport) | `pytest backend/tests/test_service_desk_model.py` | ✅ | ✅ green |
| 85-07 T2, 85-17 T1 | 85-07, 85-17 | 3, 5 | DESK-05 | T-85-64, T-85-65, T-85-66 | FIFO single worker, 10-minute arrival deadline (injected clock), no generation started that cannot finish, stale `running` recovery, timeout from measurement, per-row timing stored | integration (mongo) | `pytest backend/tests/test_service_desk_worker.py` | ✅ | ✅ green |
| 85-12 T2, 85-15 T3 | 85-12, 85-15 | 3, 4 | DESK-06 | T-85-44, T-85-56, T-85-57 | Gap rows only for no-match (not fulfilment or sensitive), grouping, dismiss, access needs both ticket and KB-edit permission | integration + http | `pytest backend/tests/test_service_desk_knowledge.py backend/tests/test_service_desk_knowledge_gaps.py` | ✅ | ✅ green |
| 85-15 T2 | 85-15 | 4 | DESK-07 | T-85-58 | Starter copy idempotent under double call and concurrency (unique `one_starter_copy` index) | integration | `pytest backend/tests/test_service_desk_knowledge.py` | ✅ | ✅ green |
| 85-02 T1 (added) | 85-02 | 1 | DESK-07 | T-85-07 | Starters contain no URLs, emails, phones or vendor names (`service_desk/starters.py`, see A-85-STARTER-SRC) | unit | `pytest backend/tests/test_service_desk_starters.py` | ✅ | ✅ green |
| 85-09 T1-T2, 85-01 T2 | 85-09, 85-01 | 2, 3 | D-01/D-02 | T-85-01, T-85-30, T-85-31, T-85-33 | Server-set `raised_via` for portal, tray, agent instruction and API-key paths; client tags alone never qualify; a stopped tenant gets no job | integration (http) | `pytest backend/tests/test_service_desk_intake.py` | ✅ | ✅ green |
| 85-19 T1-T2 | 85-19 | 5 | D-06/D-14/D-34 | T-85-71, T-85-72, T-85-74, T-85-75 | Tray routes refuse another agent, another Windows user and uncited articles; projection holds no staff-only or draft content | integration (http) | `pytest backend/tests/test_service_desk_tray_routes.py backend/tests/test_service_desk_tray_actions.py` | ✅ | ✅ green |
| 85-14 T3, 85-17 T2 | 85-14, 85-17 | 4, 5 | D-08/D-31 | T-85-67 | Working days across a weekend and DST; return job moves `pending_customer` back to `open` | unit + mongo | `pytest backend/tests/test_service_desk_workdays.py backend/tests/test_service_desk_lifecycle.py backend/tests/test_service_desk_returns.py` | ✅ | ✅ green |
| 85-11 T1-T3, 85-03 T2, 85-18 T2 | 85-11, 85-03, 85-18 | 1, 3, 5 | D-23/D-25/D-30 | T-85-09, T-85-10, T-85-38, T-85-39, T-85-40, T-85-68 | Tenant words validated; desk settings recorded in ledger and audit; desk breaker trips at 3 in 24 h and not at 2; Phase 81 breaker and security rate pool untouched by desk rows | integration | `pytest backend/tests/test_service_desk_settings.py backend/tests/test_service_desk_gate.py backend/tests/test_service_desk_withdraw.py` | ✅ | ✅ green |
| 85-10 T1-T2 | 85-10 | 3 | D-05 (tray, static) | T-85-35, T-85-36 | `.ps1` has the My tickets window, the new routes, `client.features`, and no `Invoke-Expression` | static | `pytest backend/tests/test_service_desk_tray_static.py` | ✅ | ✅ green |
| 85-23 T1 | 85-23 | 6 | D-05 (agent build) | T-85-85 | Agent 2.1.18 embeds the tray scripts; the Windows target compiles | rust | `cargo test --offline --lib tray_` and `cargo check --offline --lib --target x86_64-pc-windows-gnu` (nodebug env above) | ✅ | ✅ green |
| 85-16 T1-T3, 85-20 T1-T3, 85-21 T1-T3 | 85-16, 85-20, 85-21 | 4, 5 | UI | T-85-60, T-85-61, T-85-76, T-85-78, T-85-79 | Settings panel, draft panel, requester panel, KB toggle, gap list and starter button; copy scan passes ACTV-08 | component | `npx vitest run src/__tests__/ServiceDesk*.test.tsx src/__tests__/serviceDeskCopy.test.ts src/__tests__/autonomousOpsCopy.test.ts` | ✅ | ✅ green |
| 85-01 T1-T2, 85-17 T1 (added) | 85-01, 85-17 | 2, 5 | DESK-01, DESK-04, DESK-05 | T-85-01, T-85-03, T-85-04, T-85-05 | Tracer: a portal ticket gets one cited answer through the gate and the requester reads it back; fail-closed edges (Off, no article, model unavailable, one attempt) | integration (mongo) | `pytest backend/tests/test_service_desk_tracer.py` | ✅ | ✅ green |
| 85-03 T3 (added) | 85-03 | 1 | DESK-01 | T-85-11 | Every hand-off and draft action is a hash-chained ledger row mirrored to the audit log | integration | `pytest backend/tests/test_service_desk_ledger.py` | ✅ | ✅ green |
| 85-13 T1, T3 (added) | 85-13 | 4 | DESK-01..DESK-05 | T-85-47, T-85-49, T-85-50 | Every stage wired, every failure a hand-off; the escalation set end to end; the model's confidence never read | integration | `pytest backend/tests/test_service_desk_pipeline.py` | ✅ | ✅ green |
| 85-12 T1 (added) | 85-12 | 3 | DESK-02 | T-85-42, T-85-43, T-85-45 | The hand-off note and the requester notice; reason only in the staff note; no paging | integration | `pytest backend/tests/test_service_desk_handoff.py` | ✅ | ✅ green |
| 85-14 T1-T2 (added) | 85-14 | 4 | DESK-01 | T-85-51, T-85-52, T-85-53, T-85-54 | Send, edit, discard a draft; This fixed it and I still need help; cited articles tenant-scoped; racing actions give one winner | integration (http) | `pytest backend/tests/test_service_desk_portal_routes.py` | ✅ | ✅ green |
| 85-18 T1 (added) | 85-18 | 5 | DESK-01 | T-85-69, T-85-70 | Withdraw a posted answer through Undo; the requester sees only the withdrawal notice | integration | `pytest backend/tests/test_service_desk_withdraw.py` | ✅ | ✅ green |
| 85-22 T1-T2 (added) | 85-22 | 5 | DESK-02, DESK-03, DESK-05 | T-85-80, T-85-81 | Operator script: loopback only, only `--measure` writes, own foreign-fragment detector, calibrate writes nothing | unit + mongo | `pytest backend/tests/test_service_desk_eval_script.py` | ✅ | ✅ green |
| 85-02 T3 (added) | 85-02 | 1 | D-05, D-06 | T-85-08 | The frozen tray-to-server contract pinned by literals | unit | `pytest backend/tests/test_service_desk_tray_contract.py` | ✅ | ✅ green |
| 85-19 T3 (added) | 85-19 | 5 | D-05, D-06 | T-85-08 | Server routes agree with the frozen contract and the copy gate and catalogue ratchets | integration | `pytest backend/tests/test_service_desk_tray_server_contract.py backend/tests/test_autonomous_ops_copy.py backend/tests/test_catalogue_route_parity.py` | ✅ | ✅ green |
| 85-24 (gap) | 85-24 | 5 | DESK-03 | T-85-87, T-85-88, T-85-89 | A hidden or compatibility character never hides a foreign link or address from the output checks; the loopback model client ignores environment proxies and redirects | unit + integration | `pytest backend/tests/test_service_desk_output_fold.py backend/tests/test_service_desk_model.py` | ✅ | ✅ green |
| 85-25 (gap) | 85-25 | 5 | DESK-01 | T-85-90, T-85-91, T-85-92, T-85-93 | The reporter's ticket reads without the staff side on every route that returns a ticket; a technician or another tenant is unchanged | integration (http) | `pytest backend/tests/test_service_desk_reporter_ticket.py` | ✅ | ✅ green |
| 85-26 (gap) | 85-26 | 5 | DESK-01 | T-85-94, T-85-95 | The requester's Comments tab never renders a staff-only comment or an unsent draft, on first paint or after a failed desk read | component | `npx vitest run src/__tests__/ServiceDeskRequesterComments.test.tsx` | ✅ | ✅ green |
| 85-27 (gap) | 85-27 | 5 | DESK-01, DESK-05 | T-85-96, T-85-97 | A failed desk write after the answer is repaired and never handed off; a lost status move refuses the send | integration (injected failures) | `pytest backend/tests/test_service_desk_write_order.py` | ✅ | ✅ green |
| 85-28 (gap) | 85-28 | 5 | DESK-01 | T-85-98, T-85-99, T-85-100, T-85-101 | A staff-only notice never reaches the reporter in the feed or on the socket; mark-read, read-all and delete use the reader's own filter | integration (http) | `pytest backend/tests/test_service_desk_notification_audience.py backend/tests/test_service_desk_comments.py` | ✅ | ✅ green |
| 85-29 (gap) | 85-29 | 5 | DESK-05, DESK-06 | T-85-102, T-85-103, T-85-104 | An article from a gap must be a Help desk article (422, nothing claimed); fixtures leave out the 90-day TTL indexes; `--sets` opens no database | integration + unit | `pytest backend/tests/test_service_desk_knowledge_gaps.py backend/tests/test_service_desk_worker.py backend/tests/test_service_desk_eval_script.py` | ✅ | ✅ green |
| 85-30 (gap) | 85-30 | 7 | DESK-01 | T-85-105, T-85-106 | `manage:tickets` marks ticket staff through one `is_ticket_staff` helper; user, viewer and platform_support are requesters; custom roles start as non-staff; the role editor labels the permission | unit + component | `pytest backend/tests/test_ticket_staff_access.py backend/tests/test_rbac_defaults.py` and `npx vitest run src/__tests__/RoleEditorModal.test.tsx` | ✅ | ✅ green |
| 85-31 (gap) | 85-31 | 7 | DESK-01 | T-85-107, T-85-108, T-85-109, T-85-110, T-85-111 | The notice history and the feed routes read through the shared audience filter; a repository-wide scan finds no reader that skips it | integration (http) + structural | `pytest backend/tests/test_notification_history_audience.py backend/tests/test_notification_audience_structure.py` | ✅ | ✅ green |
| 85-32 (gap) | 85-32 | 7 | DESK-01 | T-85-112, T-85-113, T-85-114 | Anyone who is neither staff nor the reporter gets 404 on every `{ticket_id}` route, with the same answer as a missing ticket | integration (http) | `pytest backend/tests/test_ticket_staff_access.py backend/tests/test_tickets.py` | ✅ | ✅ green |
| 85-33 (gap) | 85-33 | 7 | DESK-01 | T-85-115, T-85-116, T-85-117, T-85-118 | A requester's list, stats, reports and CSV export hold only their own tickets, scoped in the query; the comment projection takes an explicit staff input | integration (http) | `pytest backend/tests/test_ticket_staff_lists.py` | ✅ | ✅ green |
| 85-34 (gap) | 85-34 | 7 | DESK-01 | T-85-119, T-85-120 | Bulk update, merge, approve, reject, escalate, work-log, watchers, links and attachment delete need `manage:tickets`; a staff reporter keeps staff actions on their own ticket | integration (http) | `pytest backend/tests/test_ticket_staff_actions.py` | ✅ | ✅ green |
| 85-35 (gap) | 85-35 | 7 | DESK-01, DESK-06 | T-85-121, T-85-122, T-85-123, T-85-124, T-85-125 | The draft routes, cited-article reader, knowledge-gap routes and Write article need ticket staff; one test classifies every ticket route | integration (http) + structural | `pytest backend/tests/test_service_desk_staff_routes.py backend/tests/test_ticket_staff_routes_structure.py` | ✅ | ✅ green |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [x] `backend/tests/fixtures/service_desk/` — `retrieval_set.jsonl`, `escalation_set.jsonl`, `injection_set.jsonl`, `language_set.jsonl`, `output_checks.jsonl`. **A-85-STARTER-SRC:** the planned `starter_articles.json` fixture does not exist; `backend/service_desk/starters.py` is the single source of the starter articles and the tests read it directly, so there is no second copy to drift.
- [x] `backend/tests/service_desk_support.py` — stub model clients (compliant, benign, offline, slow) and ticket/article seeding helpers on top of `backend/tests/autonomy_support.py` (plus `service_desk_portal_support.py`, `service_desk_knowledge_support.py`, `service_desk_tray_support.py`, `service_desk_worker_support.py`)
- [x] The `test_service_desk_*.py` files in the map above (31 files exist)
- [x] Updates to `backend/tests/test_autonomous_ops_registry.py` (new rows), `backend/tests/test_autonomous_ops_copy.py`, `shared/autonomous-ops-banned-terms.json` and `src/__tests__/autonomousOpsCopy.test.ts` (new files in the copy-scan list)
- [x] `backend/scripts/service_desk_eval.py` — the operator measurement and calibration script

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Real CPU response time and the timeouts it sizes | DESK-05 | Ollama is not installed on this VM; installing it is the operator's step | Install Ollama bound to 127.0.0.1, `ollama pull llama3.2:3b`, run `backend/venv/bin/python backend/scripts/service_desk_eval.py --measure`, record median/p95 and tokens per second, and check API latency while it runs |
| Injection and escalation sets against the real model | DESK-02, DESK-03 | Needs the live model | `backend/venv/bin/python backend/scripts/service_desk_eval.py --sets`; no output may pass the D-19 checks with a foreign link or command |
| Cut-off calibration on a real tenant knowledge base | DESK-02 | Needs real articles | `backend/venv/bin/python backend/scripts/service_desk_eval.py --calibrate --tenant <id>` on a tenant's Help desk articles; record the chosen cut-off |
| Backend restart: migration 032 and the desk worker | DESK-01, DESK-05 | Restarting is the user's step | Restart, then check the status line in Settings; with Ollama absent every person-raised ticket is handed off as service desk offline |
| Portal round trip, posting, Undo and the desk breaker | DESK-01 | Needs the live server, a test tenant and a person | Raise a portal ticket, see the staff draft, Send as is; as Super Admin lift shadow, set Undoable-auto and Post answers, see a post, Undo it from Activity, trip the breaker with three withdrawals, Restore |
| UI layout in a real browser | UI | No browser was run against the unpublished bundle | After publishing, look at Settings, the ticket panels, the KB tabs at 320px and in light and dark |
| Tray "My tickets" round trip | DESK-01, D-05, D-07, D-08, D-34 | PowerShell and Windows are not available here; the tray ships in an agent release (the user's step) | Publish agent 2.1.18, raise a ticket from the tray, see the pop-up, use "This fixed it" and "I still need help", check 150% scaling, and check the three-working-day return on a test tenant |

---

## Validation Sign-Off

- [x] All tasks have `<automated>` verify or Wave 0 dependencies
- [x] Sampling continuity: no 3 consecutive tasks without automated verify
- [x] Wave 0 covers all MISSING references
- [x] No watch-mode flags
- [x] Feedback latency < 120s (per quick run)
- [x] `nyquist_compliant: true` set in frontmatter

**Approval:** validated 2026-11-09 for the automated gates (plan 85-23). The Manual-Only rows are open and belong to the user.

## Validation Audit 2026-11-09

| Metric | Count |
|---|---|
| Gaps found | 0 |
| Resolved | 0 |
| Escalated | 0 |

Gap round (plans 85-24 to 85-29), 2026-11-09: the full backend list on the private mongod passed 2179 tests with 0 failed and 0 skipped, `npx vitest run src/__tests__` passed 1873 tests in 117 files with 0 failed, and `npm run build` exited 0. Gaps found 0, resolved 0, escalated 0.

Second gap round (plans 85-30 to 85-35, plan 85-36), 2026-11-09: the full backend list on the private mongod collected 2696 tests and passed 2694 with 0 skipped on the working tree; the 2 failures are `test_catalogue_route_parity.py::test_unguarded_routers_are_ledgered` and `::test_ledger_ratchets`, which name only reporting_endpoints and come from the user's uncommitted `shared/catalogue-gaps.json` paired with their set-aside edits; `test_catalogue_route_parity.py` and `test_catalogue_manifest.py` pass 65 of 65 on a clean checkout of HEAD, so the committed code is 2696 of 2696. `npx vitest run src/__tests__` passed 1876 tests in 117 files with 0 failed, and `npm run build` exited 0. Gaps found 0, resolved 0, escalated 0.
