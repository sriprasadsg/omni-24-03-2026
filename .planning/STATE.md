---
gsd_state_version: 1.0
milestone: v3.0
milestone_name: — Competitive Feature Closure
status: In progress — all phases executed, verification backlog remains
stopped_at: Phase 39 plan 39-04 (per-tenant LangChain model factory + persistent memory + tracing infra, AISPEC-39-S4/S5/S7, RESEARCH-Pat1/PitC) executed and committed 2026-07-18 (commits b5266e5/55beed9/ed261a5) — backend/ai_orchestration/models.py (async build_model_for_tenant with init_chat_model + .with_fallbacks, single shared ai_service provider cache, model_provenance helper), memory.py (persistent AsyncSqliteSaver under data/, mandatory tenant-prefixed make_thread_id), and tracing.py (LangChainInstrumentor wired into app_startup's init_agentic_tracing with graceful degrade) built with 25 passing hermetic unit tests. This is the shared runtime substrate 39-06 through 39-09 will build create_agent on top of. Next — 39-05 onward (agent-surface migrations); Phase 29 also fully complete (all 4 plans, TRUST-01/02/03 done, 940 passed/22 skipped/0 failed); still open — 32 human verification, 35 integration tests, UAT files for 33/34.
last_updated: "2026-07-17T21:25:31.383Z"
progress:
  total_phases: 15
  completed_phases: 14
  total_plans: 42
  completed_plans: 48
  percent: 93
---

# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-06-20)

**Core value:** Any tenant can see exactly which compliance controls pass or fail across their endpoints — with trustworthy, current evidence and a numeric score to prove it.
**Current focus:** Phase 39 — langchain-ai-integration

## Current Phase

**v2.0 Milestone — GRC Feature Parity: COMPLETE (verified 2026-07-05)**

Goal: Implement all 9 phases (14–22) identified in the June 2026 audit against Comp AI, Probo, OpenLane Core, and Prowler.

All 9 phases (14–22) verified complete this session: every phase's test suite was re-run directly and passes, and 5 dashboards that were fully built but never reachable in the app (`SaaSIntegrationsDashboard`, `PrivacyLegalDashboard`, `CloudAccountsDashboard`, `NotificationsDashboard`, `ApiExtensionsDashboard`) were wired into `App.tsx`/`Sidebar.tsx` navigation — the same class of gap `16-VERIFICATION.md` had caught for `ProgramsDashboard` a day earlier.

**v2.1 Milestone — Windows PowerShell Evidence + IaC/Container Security: COMPLETE (verified 2026-07-05)**

Phase 23 complete. Phase 24 (IaC & Container Security) — all 16 `24-REVIEW.md` findings (5 critical) fixed, 8/8 tests pass (re-run and confirmed), dashboard restyled from inline dark theme to Tailwind per `24-UI-SPEC.md`, and wired into `App.tsx`/`Sidebar.tsx`/`types.ts` navigation under Security (SecOps). Confirmed reachable via production build chunk output.

**v3.0 Milestone — Competitive Feature Closure: IN PROGRESS (started 2026-07-06)**

14 new phases (25–38) added to the roadmap from a feature-parity audit run 2026-07-06 against Comp AI, Probo, OpenLane Core, and Prowler (69 features checked directly against source: 41 implemented, 10 partial, 15 absent, 3 unique differentiators). Ordered in 3 risk tiers — quick fixes (25–27), medium features (28–33), architectural bets (34–38).

Phase 25 (Cloud Checks Execution Gaps) complete and verified 2026-07-06: full pipeline (research → pattern-map → plan → plan-check → execute → code-review → fix → goal-verify → security-verify → UAT). Code review found and fixed 2 critical CloudFormation rule PASS/FAIL inversions plus 6 warnings. Goal verification: 15/15 must-haves confirmed. The one human-verification item (SIMULATED badge visual prominence) was confirmed by actually running the app end-to-end — backend+frontend dev servers, headless Chrome driven via raw CDP, real login, real scan trigger, screenshot — which also surfaced and fixed a real pre-existing bug (`container_scanner_endpoints.py` missing the `response: Response` param slowapi's rate limiter requires, causing every real `/api/container/scan` request to 500; unit tests never caught it since they bypass the route/middleware stack). 1/14 v3.0 phases complete.

Phases 26 (Vendor and Risk Data Completeness) **complete and verified 2026-07-12** (Phase 27 completed before this was updated).
Phases 27 (Compliance Export Formats — OSCAL and SBOM) **complete and verified 2026-07-12**.

Phase 29 (Public Trust Center) planned and plan-checker-passed 2026-07-07 — retrofits the internal-only `trust_service.py`/`trust_endpoints.py`/`TrustCenter.tsx` module into a real customer-facing surface. Research corrected the phase brief's own framing: this is not the first public route in the codebase (`agent_registry_endpoints.register_agent` already does it) — the plan clones that existing tenant-resolution pattern rather than inventing one. This was the first v3.0 phase to trip the UI safety gate (block:true — `frontend: true`, no UI-SPEC), so `/gsd-ui-phase 29` ran first (gsd-ui-researcher → gsd-ui-checker, approved with 2 non-blocking FLAGs, one aria-label gap closed inline). Two genuine scope decisions from research's Open Questions were confirmed with the user via AskUserQuestion: custom domain (TRUST-03) scoped to Host-header resolution only (no automated TLS/DNS), and NDA-gated document delivery scoped to out-of-band sharing via the existing `file_share_endpoints.access_share` mechanism (no new external-viewer auth system). 4 plans across 3 waves, all 3 requirements (TRUST-01/02/03) covered, plan-checker passed clean on first pass. Planner agent hit a session-limit failure on first dispatch (no partial PLAN.md written); retried identically after the reset and succeeded. 5/14 v3.0 phases planned (25 also executed); 26/27/28/29 planned only.

User then requested planning all remaining phases (30-38) in one batch (typo'd as "30-40" — 39/40 don't exist, corrected to 30-38). Phase 30 (AI Questionnaire Auto-Answer) planned and plan-checker-passed 2026-07-08 — first v3.0 phase to trip the `workflow.ai_integration_phase` keyword gate (goal text contains "RAG"), so `/gsd-ai-integration-phase 30` ran first: framework-selector found this codebase already has every RAG/AI primitive needed (`rag_service.py` ChromaDB, `ai_service.py` multi-provider generation, `compliance_narrative_service.py`'s Pydantic-validated-output pattern, Phase 15's evidence-review human-approval-gate shape) — no new framework introduced. That research surfaced a real pre-existing bug: `rag_service.py`'s ChromaDB collection has zero tenant scoping (cross-tenant leak risk), now a Wave-1 blocking prerequisite fix with a dedicated isolation test. User confirmed via AskUserQuestion that questionnaire intake should be file upload + parsing (Excel/CSV via existing pandas/openpyxl, cloning `compliance_framework_mgmt_endpoints.py`) rather than the lighter-weight manual-entry-only recommendation — a real scope expansion. Planner hit a session-limit failure mid-run (5 of 6 plans written, no frontend plan yet); resumed with a targeted continuation planner for the missing 30-06 frontend plan after the reset. Plan-checker's first pass found 1 blocker (30-02/03/04 deferred router registration to "consolidated in 30-05" but 30-05 never did it — routes would 404 in the real app) — fixed with a targeted revision to 30-05, re-check passed clean. 6 plans across 3 waves, both requirements (RAG-01/02) covered. 6/14 v3.0 phases planned (25 also executed); 26/27/28/29/30 planned only. Continuing sequentially through 31-38.

**Session 2026-07-13 — Phases 37/38 closed out, backend import chain repaired.** A full project verification found `backend/app.py` had an unconditional `from graphql_endpoints import` after the socketio wrap (added during Phase 35), which — with `strawberry` uninstallable — broke every backend import and all test runs, and would have thrown `AttributeError` even with strawberry present (`socketio.ASGIApp` has no `include_router`; the router is already registered as optional in `router_registry.py`). Removed (commit c06d5369). Two more Phase 38 defects fixed in the same commit: `ai_assistant_endpoints.py` defined `ChatRequestBody(BaseModel)` before importing `BaseModel` (NameError at import), and called `.chat()` on a module-level `ai_assistant_service = None` that nothing ever initialized (AttributeError on every real request) — endpoints now call `chat()` directly. Both Phase 37 and 38 test files were rewritten and pass: the old `test_mcp_server.py` imported a nonexistent `main` module and tested pre-Phase-37 REST routes that no longer exist; it now tests the real FastMCP server (12/12). `test_ai_assistant.py` used `backend.`-prefixed imports that made every patch a no-op and mocked Motor's sync `find()` as async; rewritten per project conventions (5/5, includes tenant-isolation and empty-query coverage). Full suite: **846 passed, 22 skipped, 27 failures + 14 errors — all pre-existing** (verified identical on the parent commit): Phase 30 questionnaire (19), Phase 32 posture/ingest (8), singles in 28/34/35, plus `test_rebac.py` breaking collection because `openfga_sdk` isn't installed (run with `--ignore=backend/tests/test_rebac.py`). Tests must run via `backend/venv/bin/python -m pytest` — the system Python has no pytest and the env is externally managed.

**Session 2026-07-13 (later) — Phase 30/32 test debt cleared; missing 30-01 RAG tenant isolation actually implemented (commit 7c4727a9).** Investigating the 27 failures revealed that Phase 30-01's Wave-1 blocking security fix — tenant-scoped RAG — **was never actually implemented**: `rag_service.py` was untouched since Phase 16, the claimed `test_rag_service_tenant_isolation.py` did not exist, and 30-UAT's "Tenant Isolation (RAG): Passed" line referred to work that wasn't in the tree. Implemented now per the 30-01 design (tenantId metadata + `global` sentinel on ingest, `$or` where-filter on query) with a real-ChromaDB isolation test (5 tests, hermetic deterministic embeddings). Five more latent product bugs fixed that tests had never actually exercised: missing `import uuid` in `questionnaire_answer_draft_service.py` (NameError on every draft), `_insufficient_evidence_draft` referencing an out-of-scope `db` with an unawaited insert, missing `datetime` import in `questionnaire_inbound_endpoints.py` (NameError on every upload), CSV header case-mismatch in `questionnaire_inbound_service.py` (documented "Question Text" header → KeyError → 500), and `_tenant(user: User)` missing its `Depends(get_current_user)` default in all three questionnaire endpoint files (FastAPI demanded a request body on GETs). The failing tests themselves were unrunnable as written (no-op `patch()` without `with`, `backend.`-prefixed duplicate-module imports, Depends-captured `get_db` patched at module level) and were rewritten per project conventions — 42 tests now pass across the 7 files. Suite: **884 passed / 22 skipped; remaining 7 failures + 5 errors are phases 28/34/35 + singles (e2e-integration, powershell, rust-parity, smoke)**.

**Session 2026-07-14 — Full project verification; uncommitted green-suite work committed; docs reconciled.** Full suite verified **932 passed / 22 skipped / 0 failed** (35s) and frontend build clean — all prior debt gone (test_rebac collects and passes, passkey/graphql/governance/e2e/powershell/smoke all green; strawberry-graphql + openfga_sdk installed since cd66ce1e). Discovered ~25 files of uncommitted content changes the green suite depended on — committed as 5f78f43e: GraphQL resolver auth rework (user resolved once in router context, per-resolver tenant+RBAC), Phase 30 reviewer-role gate + Mongo `_id` projection fixes + review-router registration order (GET /pending-review was shadowed), Phase 28 governance test rewritten to dependency-override `get_database`, Phase 30 frontend wiring (InboundQuestionnaireDashboard, apiService functions, types), Phase 32 attack-path edge field names, Phase 29 trust_service deny-path fix + new test_trust_center.py (9 tests). Remaining ~115 modified files were chmod mode-only noise, committed with tooling churn as cd4d6a4b. ROADMAP.md/STATE.md were stale (33/34 marked "Pending", 35 "Blocked", 36 caveated on a dep that's now installed) — reconciled against git: 33 executed (4 plans, commits 54715098/8e6ffbac/64acf247/0cb6a8dd), 34 executed (a1e23c8d), 35/36 verified with deps installed. Junk left untracked deliberately: c.txt, d.txt, backend/check_user.py, backend/.continue-here.md.

**Session 2026-07-14 (later) — Phase 29 plan 29-01 re-executed for real (TRUST-01/03).** Confirmed via `git log --all` that the prior claimed completion of 29-01 had zero commits — the 2026-07-14 runtime UAT finding was correct, not the earlier SUMMARY. Re-executed all 3 tasks from the actual plan against the actual tree: `trust_service.py` rewritten from the in-memory `TrustService` singleton to async Mongo-backed module-level helpers (`get_profile`/`update_profile`/`get_requests`/`create_request`/`update_request_status`/`_ensure_trust_slug`) reading/writing `db.trust_profiles`/`db.trust_access_requests` through the tenant-isolated `db` handle; `trust_endpoints.py`'s 5 admin routes converted to `async def` with auth model unchanged (`Depends(get_current_user)` + `_TRUST_ADMIN_ROLES`); `trust_slug`/`trust_domain` surfaced on `db.tenants` (exempt collection). `test_trust_center.py` fully rewritten (old file tested a `MockTrustService` shape with no analog in the new async API) — 6 tests, all green (`persistence`/`tenant`/`admin_auth`/`admin_settings` suites per 29-VALIDATION.md's `-k` marker contract). `trust_profiles`/`trust_access_requests` confirmed absent from `database.py`'s exemption allowlist. Full backend suite: 925/22 (one run) — a pre-existing, order-dependent `test_auth_mfa.py` flake (10 tests) reproduces identically with `test_trust_center.py` excluded entirely, confirmed unrelated, logged to `29-public-trust-center/deferred-items.md`. Commits: 21ed35b3 (test scaffold), 435213be (trust_service.py), 86575edb (trust_endpoints.py), a97280d0 (SUMMARY). Remaining for phase 29: plans 29-02 (public route + NDA flow), 29-03 (custom domain), 29-04 (frontend admin view).

**Session 2026-07-14 (later still) — Phase 29 plan 29-02 executed (public route + NDA flow, TRUST-02/03).** Built directly on 29-01's fresh async `trust_service.py`. Added a second, no-prefix `public_router` in `trust_endpoints.py` (registered as its own `router_registry.py` entry alongside the existing admin `router`) carrying `GET`/`POST /api/public/trust/{slug}(/requests)` — neither requires `get_current_user`, both clone `agent_registry_endpoints.register_agent`'s pattern: resolve tenant via the exempt `db.tenants` collection (Host-header `trust_domain` first, then `trust_slug` fallback, identical 404 for both no-match cases), then explicit `set_tenant_id(...)` before any tenant-scoped `trust_service` call. `_public_view` strips `private_documents` to name-only stubs server-side. `AccessRequestCreate` enforces explicit NDA consent (400 if missing/false) and captures `ip_address`/`user_agent`/`requested_at` exclusively from the request/server — forged body values for those fields are silently dropped by Pydantic before the handler runs. Both routes carry the `response: Response` param slowapi's `@limiter.limit(...)` requires (verified via real `TestClient` HTTP calls per the documented Phase-25 pitfall, not import checks). While building rate-limit tests, discovered `@limiter.limit(...)` binds a route's static limit string to the specific `Limiter` instance that decorated it at import time (the process-wide `rate_limiter.limiter` singleton) rather than to whatever's later assigned to `app.state.limiter` — a naive fresh-`Limiter()` test app would silently not enforce anything and, worse, the real singleton's shared in-memory storage bled hit-counts across unrelated tests in the same file. Fixed by wiring the rate-limit test app's `app.state.limiter` to the real shared singleton (matching production) and adding an autouse pytest fixture that resets its storage before/after every test in `test_trust_center.py`. `test_trust_center.py` grew from 6 to 17 tests (all green): `TestPublicTrustGet`, `TestPublicDocFilter`, `TestCustomDomainResolution`, `TestPublicAccessRequestPost`, `TestPublicRateLimit` (GET 429s at request 31/30-per-minute; POST 429s at request 6/5-per-minute, strictly sooner). Full backend suite: **936 passed / 22 skipped / 0 failed** — the previously-flagged `test_auth_mfa.py` order-dependent flake did not reproduce this run. `database.py`'s tenant-isolation exemption allowlist confirmed unweakened (`trust_profiles`/`trust_access_requests` absent). Commits: 1ee31791 (Task 1: public GET), 1bcc8361 (Task 2: public POST), fac0c4e9 (Task 3: rate-limit tests), b61d062d/c6e2de48 (SUMMARY + self-check). Requirements TRUST-02/TRUST-03 marked complete in REQUIREMENTS.md. Remaining for phase 29: plan 29-03 (custom domain — Host-header resolution is already fully delivered by 29-02's `_resolve_tenant_from_request`; check 29-03-PLAN.md's actual remaining scope before executing) and 29-04 (frontend admin view).

**Session 2026-07-14 (later still) — Phase 29 plan 29-03 executed (trust center admin UI, TRUST-01/03).** 29-03's actual scope (confirmed against the real PLAN.md rather than the prior session note's guess) was the two real frontend gaps: `services/apiService.ts` had no client function for the already-existing `PUT /api/trust-center/profile` route, and `components/TrustCenter.tsx` rendered the profile read-only with no edit form, no custom-domain/public-link admin surface, and silent (non-toasted) approve/deny actions. Added `updateTrustProfile(updates)` to `apiService.ts` (mirrors `updateTrustRequest`'s shape). Extended `TrustCenter.tsx` with an "Edit Profile" toggle, a read-only "Sharing" section on the profile preview (Public Trust Page URL `{origin}/trust/{trust_slug}` + working Copy Link via `navigator.clipboard.writeText` + toast, and the current Custom Domain value), and toast+aria-label additions on the existing Approve/Deny buttons (`showToast('Request approved.'/'Request denied.', 'success')` on success, error toast on failure; `aria-label="Approve request"`/`"Deny request"` added; no confirmation modal, interaction model unchanged per UI-SPEC). The full edit form (company name, description, contact email, logo URL, compliance-framework and public/private-document add-remove-row editors, editable Custom Domain input with the exact UI-SPEC helper text) was extracted into a new `components/TrustProfileEditForm.tsx` (243 lines) per the plan's own pre-authorized fallback, since inlining it would have pushed `TrustCenter.tsx` past the CLAUDE.md 500-line limit — `TrustCenter.tsx` ended at 349 lines. `npm run build` (Vite) and `npx tsc --noEmit` both passed clean after every task. No deviations from plan; no new npm packages. Commits: cda3692c (Task 1: updateTrustProfile), d43c89cd (Task 2: edit form + custom domain + sharing), e3a045bc (Task 3: toasts + aria-labels), plus SUMMARY/self-check commit. Manual UAT (log in as admin, edit+save profile, copy link, set custom domain, approve/deny and see toast) remains outstanding per 29-VALIDATION.md's Manual-Only gate — not exercised in a live browser this session. Remaining for phase 29: confirm whether 29-04 has any scope left beyond what 29-01/29-02/29-03 already delivered (TRUST-01/02/03 are all now functionally complete across backend+frontend).

**Session 2026-07-14 (later still) — Phase 29 plan 29-04 executed (public trust page + serving route, TRUST-02 final wave).** Confirmed 29-04's remaining scope (the one genuinely new artifact in this phase with no in-codebase precedent): a standalone public trust page and its serving route. Added `GET /trust/{slug}` (`include_in_schema=False`) to `app.py`, cloned from the `/.well-known/security.txt` FileResponse precedent — no auth dependency, no `/api` prefix, `slug` unused server-side (consumed client-side by the page's own JS). Built `backend/static/trust-page.html` (468 lines) as a fully self-contained document: inline hand-written CSS using the UI-SPEC Surface A tokens (14/16/20/32px type scale, `#f8fafc`/`#ffffff`/`#00a8cc`/`#dc2626`/`#15803d` colors, Outfit font via Google Fonts `<link>`) and inline vanilla JS (zero dependencies). Fetches `/api/public/trust/{slug}` and renders header/framework-badges/public-docs (working download links)/restricted-docs (name-only stubs + "Request Access", never a url/href) and the NDA access-request form (email + consent validated client-side, posts to `/api/public/trust/{slug}/requests`); implements the exact 404/rate-limit/network-error/empty/success copy from the UI-SPEC Copywriting Contract. Discovered the plan's own `<verify>` command (`app.app.routes`) is stale — a pre-existing, unrelated socketio-wrap in `app.py` reassigns the module-level `app` name to a `socketio.ASGIApp` wrapper with no `.routes` attribute (the real FastAPI instance is `_fastapi_app`); verified route registration against `_fastapi_app.routes` and a live `TestClient` GET request instead — no code deviation, just a corrected verification method. All plan structural/copy grep checks pass; `test_trust_center.py` still 17/17; full backend suite **940 passed / 22 skipped / 0 failed**. Commits: 795aa444 (Task 1: GET /trust/{slug} route), b6b82a15 (Task 2: trust-page.html), plus SUMMARY/self-check commits. **Phase 29 (Public Trust Center) is now fully complete — all 4 plans executed, TRUST-01/02/03 all done.** Manual/UAT browser verification remains outstanding per 29-VALIDATION.md's Manual-Only gate (not exercised in a live browser this session — TestClient covers the automated portion only). Also hand-corrected a `roadmap.update-plan-progress` tool bug this session: the SDK's summary-file glob counted `29-UAT-SUMMARY.md` alongside the 4 real plan summaries, producing a garbled "5/4" row in ROADMAP.md's phase table — fixed manually to the correct phase name/tier/status text.

**Session 2026-07-18 — Phase 39 plan 39-03 executed (shared ai_orchestration schemas + citation/control-ID validator, AISPEC-39-S4b/S5/S6, RESEARCH-Pat3).** Built `backend/ai_orchestration/schemas.py` (Citation, AuditFinding with `citations: min_length=1`, CitedAnswer, NarrativeOutput — all reject empty/`BLOCKED:`/`Error:` strings, generalizing `questionnaire_answer_draft_service.AnswerDraft` and `compliance_narrative_service.NarrativeOutput`'s existing validator shapes verbatim in intent) and `backend/ai_orchestration/validators.py` (async `validate_citations(obj, tenant_id, db)` resolving every citation `chunk_id` against tenant-scoped + `global` `control_evidence`/`asset_compliance`, and `control_id` against `db.compliance_frameworks` — never a hardcoded map, per RESEARCH Pattern 3; unresolved ids fail with `reason="citation_validation_failed"` and return a downgraded `insufficient_evidence` copy; plus `validate_framework_fidelity`/`extract_control_id_tokens` sweeping free text for control-ID-shaped tokens). Caught and fixed one bug during implementation before commit: the first regex draft false-positived on bare framework-name mentions (`"SOC 2"`) as fabricated control IDs — tightened to require the digit run directly after the letter code. 27 hermetic unit tests added (`backend/tests/test_ai_orchestration_schemas.py`, mocked `db`, no live model/gateway). All 3 tasks committed (3d29b1f, 4eaf04b, 784c994); `pytest backend/tests/test_ai_orchestration_schemas.py -q` → 27 passed. This is the structural anti-fabrication foundation 39-06 through 39-09 (auditor/questionnaire/chat/narrative agent migrations) will import directly rather than re-implementing per surface.

**Session 2026-07-18 (later) — Phase 39 plan 39-04 executed (per-tenant LangChain model factory + persistent memory + tracing infra, AISPEC-39-S4/S5/S7, RESEARCH-Pat1/PitC).** Built `backend/ai_orchestration/models.py` (async `build_model_for_tenant(tenant_id, db, surface)` reading the same `system_settings` "llm" document `ai_service.get_provider_for_tenant` reads, mapping provider strings — router/9router/ollama/anthropic/gemini — onto `init_chat_model`, returning `primary.with_fallbacks([local_ollama])` with per-surface temp/max_tokens from AI-SPEC Section 4; reuses `ai_service.invalidate_tenant_provider` exclusively, zero `_tenant_providers` occurrences confirmed by grep; `model_provenance()` tags responses `"primary"`/`"fallback:<model>"`; records the 39-02 router structured-output passthrough FAIL decision as a module constant + docstring for 39-06..09), `backend/ai_orchestration/memory.py` (`checkpointer_lifespan()` defaulting to a persistent `AsyncSqliteSaver` under `backend/data/`, `InMemorySaver` dev-mode switch; `make_thread_id(tenant_id, conversation_id)` enforces the mandatory tenant-prefix, raises on empty ids), and `backend/ai_orchestration/tracing.py` (`instrument_langchain()` wraps `LangChainInstrumentor().instrument(tracer_provider=...)` in the identical ImportError/Exception graceful-degrade shape as the existing `AnthropicInstrumentor` wiring; `attach_span_attributes()` for the four mandatory span attributes) wired into `app_startup.py::init_agentic_tracing` right after the Anthropic instrumentor call — one startup hook, reusing the same `TracerProvider`. 25 hermetic unit tests added (`backend/tests/test_ai_orchestration_infra.py`, `-k models`/`-k memory`/`-k tracing` all green, no live model/gateway/network). All 3 tasks committed (b5266e5, 55beed9, ed261a5); `cd backend && venv/bin/python -c "import app_startup"` exits 0. While confirming no regression, a full-suite run surfaced one new environmental observation (logged to `deferred-items.md` item 6, not a regression): `test_router_passthrough.py` now attempts a live call instead of skipping when collected as part of the full suite, because `AI_ROUTER_URL` resolves from `.env` in this sandbox session — unrelated to this plan's files, confirmed via import-graph check. This is the shared runtime substrate 39-06 through 39-09 will build `create_agent` on top of.

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
| 26 | Vendor and Risk Data Completeness | Complete (v3.0) |
| 27 | Compliance Export Formats (OSCAL and SBOM) | Complete (v3.0) |
| 28 | Governance Document Management | Complete (v3.0) — runtime UAT passed 2026-07-14; 4 defects fixed (368f01d9) incl. unregistered router that 404'd every route |
| 29 | Public Trust Center | **Complete (v3.0) — all 4 plans re-executed and verified against real git history 2026-07-14** (29-01: 21ed35b3/435213be/86575edb/a97280d0; 29-02: 1ee31791/1bcc8361/fac0c4e9; 29-03: cda3692c/d43c89cd/e3a045bc; 29-04: 795aa444/b6b82a15). TRUST-01/02/03 all done: DB-backed trust_service.py, public GET/POST routes with NDA consent + rate limiting + custom-domain Host resolution, admin profile-edit/sharing UI, and the standalone public trust-page.html + serving route. Full backend suite 940 passed / 22 skipped / 0 failed. Manual/UAT browser verification still outstanding per 29-VALIDATION.md's Manual-Only gate. |
| 30 | AI Questionnaire Auto-Answer | Complete (v3.0) — runtime UAT passed 2026-07-14 (8/8 items); 3 defects fixed (368f01d9) incl. reviewer-role lockout and unreachable submit |
| 31 | FAIR Risk Quantification | Complete (v3.0) — 3/3 plans executed 2026-07-10 |
| 32 | Cloud and SaaS Provider Expansion | Executed (v3.0) — 5/5 plans done; test debt cleared 2026-07-13 (16 tests pass); verification `human_needed` (3/4 must-haves) remains |
| 33 | Workflow Automation Connectors | Executed (v3.0) — all 4 plans committed 2026-07-13 (54715098, 8e6ffbac, 64acf247, 0cb6a8dd); no UAT file yet |
| 34 | Passkey and WebAuthn Authentication | Executed (v3.0) — commit a1e23c8d 2026-07-13, backend + frontend UI, test_passkey_auth.py passes; no UAT file yet |
| 35 | GraphQL API | Executed (v3.0) — strawberry installed (cd66ce1e), resolver auth rework committed 2026-07-14 (5f78f43e), test_graphql.py passes; 7 UAT integration items pending |
| 36 | Fine-Grained Relationship-Based Authorization | Complete (v3.0) — openfga_sdk installed (cd66ce1e), test_rebac.py 4/4 pass |
| 37 | Spec-Compliant MCP Server | Complete (v3.0) — tests rewritten against FastMCP and passing (12/12, 2026-07-13) |
| 38 | Interactive AI Security Assistant | Complete (v3.0) — plan 38-03 verified 2026-07-13 (5/5 tests pass) |
| 39 | LangChain AI Integration | In progress (v3.0) — 39-01 (LangChain 1.x/LangGraph runtime install), 39-02 (9router smoke test + eval harness scaffold), 39-03 (shared ai_orchestration schemas + citation/control-ID validator), 39-04 (per-tenant model factory + persistent memory + tracing infra) executed; 39-05+ remaining |

## Decisions

- ReBAC Engine Selection: Chose OpenFGA over SpiceDB for its superior Python client maturity (`openfga-client-py`), active development ecosystem, and flexible deployment models.
- ReBAC Architecture: Adopted a sidecar pattern to isolate policy decisions from business logic, ensuring scalability and consistency across the platform.
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
- [Phase 29]: 29-02: Public trust routes built on a second no-prefix APIRouter (public_router) in trust_endpoints.py, registered as a separate router_registry.py entry, keeping the admin router's prefix/auth model untouched
- [Phase 29]: 29-02: slowapi @limiter.limit binds route limits to the specific Limiter instance at decoration time (rate_limiter.limiter singleton), not app.state.limiter -- rate-limit tests wire the real shared limiter and reset its storage via an autouse fixture
- [Phase 29]: 29-04: GET /trust/{slug} cloned verbatim from the /.well-known/security.txt FileResponse precedent -- no auth dependency, no /api prefix, slug unused server-side (page JS reads it from window.location)
- [Phase 29]: 29-04: trust-page.html is fully self-contained (inline CSS + vanilla JS, zero deps except the Google Fonts CDN link) -- restricted-document rendering never reads/constructs a url/href from private_documents entries, relying entirely on the 29-02 server-side _public_view filter
- [Phase 39-01]: langchain-chroma intentionally excluded from LangChain install; langgraph-checkpoint-sqlite==3.1.0 added despite absence from AI-SPEC pinned list per RESEARCH.md Wave 0 Gaps
- [Phase 39-02]: 9router passthrough decision UNRESOLVED-IN-THIS-SANDBOX (no live AI_ROUTER_URL access) — treated conservatively as FAIL; downstream agent plans 39-06/39-07/39-08/39-09 should build against the documented fallback path (ChatAnthropic direct, or ToolStrategy) until re-run with live gateway access confirms PASS
- [Phase 39-02]: force-added backend/tests/eval_langchain/data/README.md with git add -f past .gitignore's blanket data/ rule (intended for runtime dirs, not test fixtures)
- [Phase 39-03]: CitedAnswer.citations kept additive (no min_length) alongside source_evidence_ids; only AuditFinding.citations requires min_length=1, per plan's must_haves scope
- [Phase 39-03]: control-ID token regex requires digit run directly after letter code to avoid false-positiving on bare framework-name mentions like SOC 2
- [Phase 39-04]: 9router structured-output/tool-calling passthrough remains scoped FAIL (39-02); build_model_for_tenant still routes plain generation through the router, but response_format/tools must not assume router passthrough — ai_orchestration/models.py records ROUTER_STRUCTURED_OUTPUT_PASSTHROUGH='FAIL' for 39-06..09 to read
- [Phase 39-04]: LangChainInstrumentor wiring lives in app_startup.py's own nested try/except calling ai_orchestration.tracing.instrument_langchain(provider) — single startup hook, single source of truth for degrade logic — satisfies both the literal grep gate on app_startup.py and the plan's one-hook requirement

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
| Phase 36-fine-grained-relationship-based-authorization 36-01 | ~5min | 1 task | 1 file |
| Phase 29-public-trust-center P02 | 18min | 3 tasks | 3 files |
| Phase 29-public-trust-center P04 | 12min | 2 tasks | 2 files |
| Phase 39-langchain-ai-integration P01 | ~12m | 2 tasks | 1 files |
| Phase 39-langchain-ai-integration P02 | ~15m | 2 tasks | 5 files |
| Phase 39-langchain-ai-integration P03 | ~20m | 3 tasks | 4 files |
| Phase 39-langchain-ai-integration P04 | ~25min | 3 tasks | 6 files |

## Last Session

- **Timestamp:** 2026-07-14T04:30:00.000Z
- **Stopped at:** Completed 39-04-PLAN.md (LangChain model factory + persistent memory + tracing infra)
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

**Last session:** 2026-07-17T21:25:31.367Z
**Stopped at:** Runtime verification vs live services (2026-07-14): Phase 32 4/4 must-haves closed (attack-path stale-doc simulated-flag defect fixed, posture-results ObjectId 500 fixed, PROV-03 RBAC 200/404/401 confirmed, PyPI publisher evidence recorded); Phase 33 live signed-delivery round trip verified (HMAC byte-match at local receiver; 3 webhook defects fixed: create-response 500, duplicate $set losing lastResult, deliveries never recorded). Full suite 946/22/0. NOTE: backend restart required to pick up the endpoint fixes. Remaining human-only: 34 real-browser passkey ceremony; optional hosted n8n/Zapier test.
**Resume file:** None

## Accumulated Context

### Roadmap Evolution

- Phase 24 added: IaC & Container Security (Terraform/CloudFormation/Kubernetes scanning + container image vulnerability scanning). A `24-01-PLAN.md` already existed on disk (drafted ahead of execution, never wired into ROADMAP.md) — registered as Phase 24 in ROADMAP.md and REQUIREMENTS.md (IAC-01..03) reusing the existing directory/plan rather than generating a new one, so `/gsd-autonomous --only 24` can discover and execute it.
- v3.0 milestone added 2026-07-06: 14 new phases (25–38) scaffolded from a feature-parity audit run the same day against Comp AI, Probo, OpenLane Core, and Prowler (69 features checked directly against source — 41 implemented, 10 partial, 15 absent). Phases are ordered in 3 risk tiers — Tier 1 quick fixes (25–27), Tier 2 medium features (28–33), Tier 3 architectural bets (34–38: GraphQL, ReBAC, real MCP protocol, public Trust Center, passkeys). User explicitly chose "everything, in tiers" over a smaller subset. Requirements CHK/VRISK/RISK/EXP/DOC/TRUST/RAG/FAIR/PROV/WF/AUTH/GQL/REBAC/MCP/ASSIST added to REQUIREMENTS.md. Phase 25 is the first to go through full research → plan → verify.
