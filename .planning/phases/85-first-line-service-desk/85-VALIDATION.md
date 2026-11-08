---
phase: "85"
slug: "first-line-service-desk"
# status lifecycle: draft (seeded by plan-phase) → validated (set by validate-phase §6)
# audit-milestone §5.5 distinguishes NOT-VALIDATED (draft) from PARTIAL (validated + nyquist_compliant: false) (#2117)
status: draft
nyquist_compliant: false
wave_0_complete: false
created: "2026-11-08"
---

# Phase 85 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest (backend; root `pytest.ini` sets `asyncio_mode = auto`; DB fixture `backend/tests/_mongo_test_db.py`, helpers `backend/tests/autonomy_support.py`), Vitest (UI) |
| **Config file** | `pytest.ini` (repo root), `backend/tests/conftest.py`, `package.json` (`"test": "vitest run"`) |
| **Quick run command** | `backend/venv/bin/python -m pytest backend/tests/test_service_desk_sanitize.py backend/tests/test_service_desk_rules.py backend/tests/test_service_desk_retrieval.py backend/tests/test_service_desk_output_checks.py -q -p no:cacheprovider` (pure tests, no DB) |
| **Full suite command** | `MONGO_TEST_URL=mongodb://127.0.0.1:27998 MONGODB_URL=mongodb://127.0.0.1:27998 MONGO_URI=mongodb://127.0.0.1:27998 backend/venv/bin/python -m pytest backend/tests/test_service_desk_*.py backend/tests/test_autonomous_ops_*.py backend/tests/test_catalogue_*.py backend/tests/test_tickets.py -q -p no:cacheprovider`; UI `npx vitest run src/__tests__/ServiceDesk*.test.tsx src/__tests__/autonomousOpsCopy.test.ts` |
| **Estimated runtime** | ~30 seconds per quick run; ~3-5 minutes for the full backend list on the private mongod |

DB tests must use a private mongod, never the live one on 27017: `GLIBC_TUNABLES=glibc.pthread.rseq=1 /usr/bin/mongod --dbpath <scratch> --port 27998 --bind_ip 127.0.0.1 --fork --logpath <scratch>/m.log --pidfilepath <scratch>/m.pid`.

---

## Sampling Rate

- **After every task commit:** Run the task's new test file plus `test_autonomous_ops_structural.py`, `test_service_desk_structural.py` and `test_autonomous_ops_copy.py`
- **After every plan wave:** Run the full backend list above plus the touched Vitest files
- **Before `/gsd-verify-work`:** Full suite must be green. Existing `test_autonomous_ops_*`, `test_tickets.py` and the catalogue slice tests stay green
- **Max feedback latency:** 120 seconds

---

## Per-Task Verification Map

Requirement-level map from `85-RESEARCH.md` § Validation Architecture. Task IDs are filled in by `/gsd-validate-phase 85` after planning.

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| TBD | TBD | TBD | DESK-01 | TBD | Post vs draft vs shadow vs refuse across switch, level, shadow, stop, desk budget and desk breaker; confirm closes; nothing auto-closes | integration (mongo) | `pytest backend/tests/test_service_desk_gate.py backend/tests/test_service_desk_lifecycle.py` | ❌ W0 | ⬜ pending |
| TBD | TBD | TBD | DESK-01 | TBD | Comment visibility defaults to staff; a staff-only comment never notifies or previews to the reporter; recipient-filtered notices | integration | `pytest backend/tests/test_service_desk_comments.py` | ❌ W0 | ⬜ pending |
| TBD | TBD | TBD | DESK-02 | TBD | Sensitive, ask-for-a-person, fulfilment, critical-priority and tenant-word rules pinned by the escalation set; password how-to answerable, unlock/MFA/access not | unit | `pytest backend/tests/test_service_desk_rules.py` | ❌ W0 | ⬜ pending |
| TBD | TBD | TBD | DESK-02 | TBD | Cut-off and minimum-terms rule pinned by the retrieval set on the starter articles; only the tenant's own Help desk articles; global seed never cited | unit + mongo | `pytest backend/tests/test_service_desk_retrieval.py` | ❌ W0 | ⬜ pending |
| TBD | TBD | TBD | DESK-03 | TBD | Sanitiser strips HTML, links and control characters before the model; compliant-stub injection set rejected by output checks; no agent-queue write | unit | `pytest backend/tests/test_service_desk_sanitize.py backend/tests/test_service_desk_injection.py backend/tests/test_service_desk_output_checks.py` | ❌ W0 | ⬜ pending |
| TBD | TBD | TBD | DESK-03 | TBD | `service_desk/` imports and queue writes are fenced by an AST test; no LLM imports inside `autonomous_ops/` | unit | `pytest backend/tests/test_service_desk_structural.py backend/tests/test_autonomous_ops_structural.py` | ❌ W0 | ⬜ pending |
| TBD | TBD | TBD | DESK-04 | TBD | Ollama down, tag missing, 503, bad JSON, mock-only or scratch wrapper → hand-off, never a post; loopback-only URL | unit (MockTransport) | `pytest backend/tests/test_service_desk_model.py` | ❌ W0 | ⬜ pending |
| TBD | TBD | TBD | DESK-05 | TBD | FIFO single worker, 10-minute arrival deadline (injected clock), no generation started that cannot finish, stale `running` recovery, timeout from measurement, per-row timing stored | integration (mongo) | `pytest backend/tests/test_service_desk_worker.py` | ❌ W0 | ⬜ pending |
| TBD | TBD | TBD | DESK-06 | TBD | Gap rows only for no-match (not fulfilment or sensitive), grouping, dismiss, access needs both ticket and KB-edit permission | integration + http | `pytest backend/tests/test_service_desk_knowledge.py` | ❌ W0 | ⬜ pending |
| TBD | TBD | TBD | DESK-07 | TBD | Starter copy idempotent under double call and concurrency; starters contain no URLs, emails, phones or vendor names | integration | `pytest backend/tests/test_service_desk_knowledge.py` | ❌ W0 | ⬜ pending |
| TBD | TBD | TBD | D-01/D-02 | TBD | Server-set `raised_via` for portal, tray, agent instruction and API-key paths; client tags alone never qualify | integration (http) | `pytest backend/tests/test_service_desk_intake.py` | ❌ W0 | ⬜ pending |
| TBD | TBD | TBD | D-06/D-14/D-34 | TBD | Tray routes refuse another agent, another Windows user and uncited articles; projection holds no staff-only or draft content | integration (http) | `pytest backend/tests/test_service_desk_tray_routes.py` | ❌ W0 | ⬜ pending |
| TBD | TBD | TBD | D-08/D-31 | TBD | Working days across a weekend and DST; return job moves `pending_customer` back to `open` | unit + mongo | `pytest backend/tests/test_service_desk_workdays.py backend/tests/test_service_desk_lifecycle.py` | ❌ W0 | ⬜ pending |
| TBD | TBD | TBD | D-23/D-25/D-30 | TBD | Tenant words validated; desk settings recorded in ledger and audit; desk breaker trips at 3 in 24 h and not at 2; Phase 81 breaker and security rate pool untouched by desk rows | integration | `pytest backend/tests/test_service_desk_settings.py backend/tests/test_service_desk_gate.py` | ❌ W0 | ⬜ pending |
| TBD | TBD | TBD | D-05 (tray, static) | TBD | `.ps1` has the My tickets window, the new routes, `client.features`, and no `Invoke-Expression` | static | `pytest backend/tests/test_service_desk_tray_static.py` | ❌ W0 | ⬜ pending |
| TBD | TBD | TBD | UI | TBD | Settings panel, draft panel, requester panel, KB toggle, gap list and starter button; copy scan passes ACTV-08 | component | `npx vitest run src/__tests__/ServiceDesk*.test.tsx src/__tests__/autonomousOpsCopy.test.ts` | ❌ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `backend/tests/fixtures/service_desk/` — `starter_articles.json` (source of truth shared with the starters module), `retrieval_set.jsonl`, `escalation_set.jsonl`, `injection_set.jsonl`, `language_set.jsonl`, `output_checks.jsonl`
- [ ] `backend/tests/service_desk_support.py` — stub model clients (compliant, benign, offline, slow) and ticket/article seeding helpers on top of `backend/tests/autonomy_support.py`
- [ ] The `test_service_desk_*.py` files in the map above (none exist yet)
- [ ] Updates to `backend/tests/test_autonomous_ops_registry.py` (new rows), `backend/tests/test_autonomous_ops_copy.py`, `shared/autonomous-ops-banned-terms.json` and `src/__tests__/autonomousOpsCopy.test.ts` (new files in the copy-scan list)
- [ ] `backend/scripts/service_desk_eval.py` — the operator measurement and calibration script

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Real CPU response time and the timeouts it sizes | DESK-05 | Ollama is not installed on this VM; installing it is the operator's step | Install Ollama bound to 127.0.0.1, `ollama pull llama3.2:3b`, run `backend/venv/bin/python backend/scripts/service_desk_eval.py --measure`, record median/p95 and tokens per second, and check API latency while it runs |
| Injection and escalation sets against the real model | DESK-02, DESK-03 | Needs the live model | Run the eval script's set mode against the real model; no output may pass the D-19 checks with a foreign link or command |
| Cut-off calibration on a real tenant knowledge base | DESK-02 | Needs real articles | Run the calibration mode on a tenant's Help desk articles; record the chosen cut-off |
| Tray "My tickets" round trip | DESK-01, D-05, D-07, D-08 | PowerShell and Windows are not available here; the tray ships in an agent release (the user's step) | Publish the agent, raise a ticket from the tray, see the pop-up, use "This fixed it" and "I still need help", and check the three-working-day return on a test tenant |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 120s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
