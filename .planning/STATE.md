---
gsd_state_version: 1.0
milestone: v3.3
milestone_name: — Agent Geo & Fleet Observability
current_phase: 48
current_phase_name: fleet-observability-uptime-rollups
status: verifying
stopped_at: "Phase 39 plan 39-09 (create_agent narrative generation — NarrativeOutput + word-budget validation + framework-fidelity flagging + fail-closed fallback + shim; AISPEC-39-S4/S4b/S6/S7, RESEARCH-Pat3) executed and committed 2026-07-18 (commits 995f295/a8015d7/db00e30) — backend/ai_orchestration/agents/narrative.py (generate_executive/generate_framework build a per-tenant create_agent with no tools, requesting NarrativeOutput via ToolStrategy; word budget (executive 150, framework 200) always recomputed from the actual returned text via NarrativeOutput.from_raw, never trusted from the model's self-reported word_count/limit fields; fail-closed fallback on validation failure, BLOCKED:/Error: output, guardrail block, unresolved framework-fidelity token, or any agent exception) and compliance_narrative_service.py (thin shim preserving generate_executive_summary/generate_framework_narrative's exact 4-arg signatures + str return + enrich_report_data + _render_narratives; two new optional trailing tenant_id/db kwargs let enrich_report_data pass both explicitly per RESEARCH Pitfall B). 17 hermetic unit tests green (test_narrative_agent.py, 12 -k agent / 5 -k shim). Rule-1 fix: retargeted test_compliance_narrative_service.py's 5 pre-existing tests off the now-removed compliance_narrative_service.ai_service attribute onto the new agent boundary — all 8 tests still pass. Full backend suite: 1104 passed / 23 skipped / 2 failed (both pre-existing, unrelated — test_e2e_integration.py golden path, test_rust_heartbeat_parity.py). **All four AI-surface migrations (auditor/chat/questionnaire/narrative) now complete.** Next — 39-11/39-12 (eval dimensions, code-based and LLM-judged)."
last_updated: "2026-07-29T18:31:22.500Z"
last_activity: 2026-07-29
last_activity_desc: Phase 48 execution started
progress:
  total_phases: 5
  completed_phases: 3
  total_plans: 18
  completed_plans: 18
  percent: 60
---

# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-06-20)

**Core value:** Any tenant can see exactly which compliance controls pass or fail across their endpoints — with trustworthy, current evidence and a numeric score to prove it.
**Current focus:** Phase 48 — fleet-observability-uptime-rollups

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

**Session 2026-07-18 (later still) — Phase 39 plan 39-05 executed (shared agent substrate: tenant-closed tools + versioned prompts + guardrail hooks + decision-log writer, AISPEC-39-S4/S4b/S6/S7, RESEARCH-Pat4/PitB/PitD).** Built `backend/ai_orchestration/tools/retrieval.py` (`make_search_evidence(tenant_id, n_results=5)` returns a `@tool search_evidence(query)` closing over `tenant_id` from the factory argument — never a tool parameter, never read from ambient context; wraps `rag_service.query` unchanged, preserving both the server-side `$or` filter and `ai_assistant_service.chat()`'s client-side belt-and-braces tenant skip; returns `[source | id]`-tagged chunks or the literal "No matching evidence found." string) and `tools/evidence.py` (`make_get_control_evidence(tenant_id, db)` scopes every `db.asset_compliance` read by BOTH `controlId` and `tenantId` explicitly). Pre-created `agents/__init__.py` to de-race wave 4. Built `prompts.py` (`PROMPT_VERSION = "39-05.v1"` + one system-prompt constant per surface, lifted from `ai_auditor_service.py`/`ai_assistant_service.py`/`questionnaire_answer_draft_service.py`/`compliance_narrative_service.py`), `guardrails.py` (async `scan_input`/`scan_output` reuse `guardrail_service.scan_and_log`; `cross_tenant_output_scan` queries the tenant-isolation-EXEMPT `db.tenants` registry and blocks + logs a SECURITY INCIDENT if any other tenant's id/name appears in output text — fails open on a lookup error since it's defense-in-depth on top of the tool-level tenant closure, not the sole control), and `decision_log.py` (`log_ai_decision` implements the plan's locked Option (a) reconciliation: writes surface-discriminated docs into the EXISTING `agent_ai_decisions` collection with `source="langchain"`, deliberately omitting the per-agent discriminator/tool-name fields the existing dashboard reader filters on so these docs can never surface there; mirrors `agentic_service.py::_log_decision`'s never-re-raise contract). 15 hermetic unit tests added (`backend/tests/test_ai_orchestration_substrate.py`, `-k tools`/`-k guardrails`/`-k decision` = 7/5/3, all green) including a dedicated reader-compat test proving a Phase 39 doc is invisible to the existing reader's `{"agent_id": ...}` filter shape. All 3 tasks committed (6721bb6, 3841e1d, 902ede7). Three Rule-1 auto-fixes caught during verification (not behavior bugs): explanatory docstrings initially tripped their own literal-string grep gates (rephrased without changing meaning), two test class names didn't match their `-k` selectors (renamed), and one test asserted an unrealistic `None` agent-id candidate (removed). This is the connective tissue 39-06 through 39-09 build `create_agent` on top of.

**Session 2026-07-18 (later still) — Phase 39 plan 39-10 executed (48-example reference dataset, AISPEC-39-S5/S1/S1b).** Built the four JSON fixtures under `backend/tests/eval_langchain/data/` the 39-02 scaffold deferred: `gold_controls.json` (20 gold-labeled control assessments — 8 clean `pass`, 4 clear `fail`, 8 traps split evenly across stale evidence/partial evidence/zero evidence/2 context-dependent auth-anomaly signals, all landing on `insufficient_evidence` or `partial`; each entry carries real-shaped evidence records, a gold status, and gold citation ids that resolve within its own evidence set), `questionnaire_qa.json` (10 pairs — 5 answerable, 3 hedged with explicit "in progress"/compensating-control language, 2 unanswerable flagged `insufficient_evidence`), `chat_questions.json` (8 questions including the required out-of-scope decline and other-customers refusal cases), and `adversarial_inputs.json` (10 entries spanning all 5 attack types from RESEARCH's Known Threat Patterns table — prompt injection, cross-tenant probe, tool-arg bypass, fabricated-control-ID bait, skip-citations — with the 3 leakage-probing types embedding the exact `conftest.CANARY_STRINGS` tenant-B canaries). Built `backend/tests/eval_langchain/dataset.py`: `load_gold_controls`/`load_questionnaire_qa`/`load_chat_questions`/`load_adversarial_inputs`, each raising (`FileNotFoundError`/`ValueError`) on a missing file, invalid JSON, empty array, missing required key, or out-of-vocabulary enum value rather than returning an empty list — T-39-10-A's mitigation lives in the loader itself, not only in tests. `backend/tests/test_eval_dataset.py` adds 23 deterministic `eval`-marked (never `llm`) tests: split counts (20/10/8/10), gold citation/control-ID internal consistency, trap-label composition, adversarial canary alignment against the real `conftest.CANARY_STRINGS` tuple, and loader-robustness against 6 distinct malformed-fixture shapes via a `tmp_path`-backed `data_dir` override parameter on every loader function. All 3 tasks committed (3bc92c5, e596801, 692a573); full `eval and not llm` run of `backend/tests/eval_langchain/` + `test_eval_dataset.py` green (23 passed, 1 deselected — the live 9router smoke test correctly skips without `AI_ROUTER_URL`). No deviations — plan executed exactly as written. This is the oracle 39-11 (code-based eval dimensions) and 39-12 (LLM-judged eval dimensions) score against; 39-11 will need to map this fixture's symbolic `cev-*` evidence ids onto real ids seeded via the conftest's `seed_tenant_evidence` fixture at consumption time, not reuse them verbatim.

**Session 2026-07-18 (later still) — Phase 39 plan 39-06 executed (create_agent compliance auditor migration, AISPEC-39-S4/S4b/S6/S7, RESEARCH-Pat3).** Built `backend/ai_orchestration/agents/auditor.py::evaluate_control(framework_name, control_desc, evidence_text, tenant_id, db, control_id=None)`: builds a per-tenant `create_agent` from the 39-04 model factory + 39-05 tenant-closed `search_evidence`/`get_control_evidence` tools + versioned `AUDITOR_SYSTEM_PROMPT`, always requesting structured output via `ToolStrategy(AuditFinding, handle_errors=...)` — never a bare `response_format=AuditFinding` — per the 39-02/39-04 `ROUTER_STRUCTURED_OUTPUT_PASSTHROUGH == "FAIL"` decision. Every returned finding is run through `validate_citations` (39-03) before return; an unresolvable citation or unknown `control_id` downgrades to `insufficient_evidence`. Guardrail `scan_input`/`scan_output`/`cross_tenant_output_scan` wrap the agent call; a fallback-provenance `pass` sets `needs_review=True` (Failure Mode 5) rather than ever equaling a primary pass. Decisions logged via `log_ai_decision`. Found and fixed a real integration gap during implementation (not in the plan's file list, so fixed via a design choice rather than touching validators.py/tools/evidence.py): `asset_compliance`/`control_evidence`/`system_settings` are NOT in `database.py`'s tenant-isolation exemption list, so `TenantIsolatedCollection` would auto-inject a top-level `tenantId` equality filter on top of `validate_citations`'s explicit tenant+`global` `$or` scope — silently excluding `global`-KB citations from ever resolving. Fixed by unwrapping to the raw db handle (`db._db`) before passing to `validate_citations`/`make_get_control_evidence`/the model-name lookup — mirrors `ai_orchestration/models.py`'s own existing unwrap for the identical reason; `log_ai_decision` still gets the original (possibly wrapped) `db`, since its `insert_one` relies on that auto-injection. Also found that `ai_auditor_endpoints.py`'s existing call site never passes a real `control_id` into `evaluate_evidence` — the model would otherwise have to invent one, defeating the whole point of the citation/control-ID validator. Since `ai_auditor_endpoints.py` is out of this plan's file scope (must_haves lock it as unchanged), added `control_id` as an optional trailing kwarg on both `evaluate_control` and the shim's `evaluate_evidence` (backward compatible with the existing 3-arg call), with a best-effort `extract_control_id_tokens(control_desc)` fallback and, when the caller does supply it, a defense-in-depth pin (`finding.model_copy(update={"control_id": control_id})`) that overrides whatever the model returned — never trust a model-fabricated control_id when the real one is known. `backend/ai_auditor_service.py` rewritten as a thin shim preserving `get_auditor()`/`evaluate_evidence()`'s exact signature and `{verified, reasoning, raw_response, evaluatedAt}` return shape; resolves tenant/db from ambient `tenant_context.get_tenant_id()`/`database.get_database()` rather than new required params. Fail-closed throughout: any agent exception maps to `verified=False`; a `needs_review` (fallback-pass) result also maps to `verified=False` with an explicit `NEEDS_REVIEW` marker in `reasoning`, since the legacy boolean contract has no third "pending review" state — this is the strongest guarantee available without changing the endpoint's write path. 14 hermetic unit tests added (`backend/tests/test_auditor_agent.py`; citation/control-ID resolution runs for real against a small mocked db rather than being mocked away, so the validator wiring is actually exercised, not just the call graph). All 3 tasks committed (e4e3482 auditor.py, bfab5e6 shim, d7f048f tests). One pre-existing, unrelated test failure confirmed reproducing in isolation and on unrelated files (`test_rust_heartbeat_parity.py::test_rust02_and_rust03_db_calls` — `agent_type` missing from a `$push.evidence` array; unrelated to this plan's 3 files, working tree already had unstaged changes to `agent-rust/`/`agent/installer/` per the sequential-executor briefing), logged as a deviation, not fixed (out of file scope). Full suite otherwise green: 1063 passed / 23 skipped / 2 failed (both pre-existing, excluded per briefing). This is the first of four agent-surface migrations (39-06..09); 39-07 (chat), 39-08 (questionnaire), 39-09 (narrative) follow the same create_agent + validate_citations + guardrails + provenance + decision-log pattern.

**Session 2026-07-20 — v3.2 roadmap defined (Phases 40-44).** Research summary (`.planning/research/SUMMARY.md`) confirmed two independent workstreams: the Rust agent 2.1.0 dependency bump is already staged and verified compiling clean (only the TLS-backend decision and the 2.1.0 rebuild remain), and four remediation-ops feature gaps close cleanly via disciplined reuse of existing patterns (Jira/ServiceNow connectors, `_compute_sla()`, the tenant-isolation wrapper, the `DO_CHECKS`-shaped check-definition pattern). 5 new phases (40-44) added, continuing numbering from Phase 39: Phase 40 (Rust Agent Modernization & Session Reliability — RUST-01, SESS-01) is a fully independent toolchain track; Phase 41 (CSPM Provider Expansion — CSPM-01/02/03) and Phase 42 (Comment Threads — CMT-01) are structurally isolated and ordered first to validate new-pattern risk cheaply; Phase 43 (Remediation-to-Ticketing Bridge — REM-01/02) is sequenced before Phase 44 (Remediation SLA & Escalation — SLA-01/02) since both mutate the same `compliance_remediation_tasks` document. All 10 v3.2 requirements mapped 1:1 to a phase, no orphans. REQUIREMENTS.md traceability table updated. Next: `/gsd-plan-phase 40`.

**Session 2026-07-29 — v3.2 shipped (Phases 40-45); v3.3 roadmap defined (Phases 46-49).** v3.2 completed all 5 planned phases plus a gap-closure Phase 45 (RUST-01 TLS-backend explicit decision), archived to `milestones/v3.2-ROADMAP.md`/`v3.2-REQUIREMENTS.md`/`v3.2-MILESTONE-AUDIT.md`. New milestone v3.3 ("Agent Geo & Fleet Observability") requirements defined same day: 11 requirements across GMAP (fleet geo map), GSEC (location-based security), FOBS (fleet observability), GAUD (location-history audit). Research (`.planning/research/SUMMARY.md`/`ARCHITECTURE.md`/`PITFALLS.md`) confirmed a strict dependency-ordered 4-phase build and flagged two dominant risks specific to this milestone: the proven tenant-isolation background-scheduler bug (every new fleet-wide sweep must use raw `mongodb.db`, exactly like `compliance_remediation_sla_service`) and a privacy/legal review gate for the new immutable, queryable employee-location-history audit trail. 4 new phases (46-49) added, continuing numbering from Phase 45: Phase 46 (GAUD-01/02 — ASN/VPN enrichment foundation + append-only location-history audit) is the foundation and front-loads the privacy gate; Phase 47 (GSEC-01/02/03 — agent-scoped impossible-travel + alert-only geo-fence + heuristic VPN/hosting flag) depends on 46; Phase 48 (FOBS-01/02/03 — metrics-history charts + uptime timeline + offline/version-drift view) is mostly independent (parallel-safe with 46/47); Phase 49 (GMAP-01/02/03 — offline SVG fleet map + clustering/filters + drill-down) is last, reading everything upstream. All 11 v3.3 requirements mapped 1:1 to a phase, no orphans. REQUIREMENTS.md traceability table updated. Next: `/gsd-plan-phase 46`.

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
| 39 | LangChain AI Integration | Complete (v3.1) — all 12 plans executed; UAT 2026-07-19 (39-UAT.md) 7 passed / 0 issues / 2 blocked-on-live-gateway (nightly judged run, 9router re-test) — 39-01 (LangChain 1.x/LangGraph runtime install), 39-02 (9router smoke test + eval harness scaffold), 39-03 (shared ai_orchestration schemas + citation/control-ID validator), 39-04 (per-tenant model factory + persistent memory + tracing infra), 39-05 (tenant-closed tools + versioned prompts + guardrail hooks + decision-log writer), 39-06 (create_agent auditor migration — AuditFinding + citation validation + shim), 39-07 (create_agent chat migration — persistent checkpointer memory + RAG/live-findings fusion), 39-08 (create_agent questionnaire migration — CitedAnswer + citation validation + shim), 39-09 (create_agent narrative migration — NarrativeOutput + word-budget validation + framework-fidelity flagging + shim), 39-10 (48-example reference dataset: gold controls + questionnaire + chat + adversarial fixtures + fail-loud loader) executed — all four AI-surface migrations complete; 39-11/12 remaining |
| 40 | Rust Agent Modernization & Session Reliability | Complete (v3.2) |
| 41 | CSPM Provider Expansion (OCI, Alibaba, Cloudflare) | Complete (v3.2) |
| 42 | Comment Threads on Compliance Controls | Complete (v3.2) |
| 43 | Remediation-to-Ticketing Bridge | Complete (v3.2) |
| 44 | Remediation SLA & Escalation | Complete (v3.2) |
| 45 | Close Gap RUST-01 — TLS Backend Explicit Decision | Complete (v3.2) |
| 46 | Public-IP ASN/VPN Enrichment + Location-History Audit | Not started (v3.3) — roadmap defined 2026-07-29 |
| 47 | Agent-Scoped Geo Security Detectors | Not started (v3.3) |
| 48 | Fleet Observability & Uptime Rollups | Not started (v3.3) |
| 49 | Fleet Geo Map | Not started (v3.3) |

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
- [Phase 39-05]: agent_ai_decisions Option (a) reconciliation implemented in decision_log.py — surface-discriminated docs (source=langchain) written into the existing collection, omitting agent_id/tool_name so the existing per-agent reader can never surface them
- [Phase 39-05]: cross_tenant_output_scan fails open on a db.tenants lookup error (defense-in-depth on top of tool-level tenant closure, not the sole control)
- [Phase 39-10]: gold_controls.json 20-entry composition locked at 8 clean pass / 4 clear fail / 8 traps (2 stale, 2 partial, 2 zero-evidence, 2 context-dependent); traps carry insufficient_evidence (6) or partial (2) status
- [Phase 39-10]: dataset.py enforces structural/enum validation in the loader itself (not deferred to tests) so a malformed fixture fails loudly for any caller, including future 39-11/39-12 code
- [Phase 39-10]: gold_controls citation/evidence ids are self-contained symbolic placeholders (cev-NNN), not pre-seeded live ChromaDB ids -- 39-11 maps fixture evidence content to real seeded ids at consumption time
- [Phase 39-06]: auditor.py unwraps db to the raw Motor handle (db._db) before calling validate_citations/make_get_control_evidence/model-name lookups -- asset_compliance/control_evidence/system_settings are NOT tenant-isolation-exempt, so TenantIsolatedCollection would otherwise inject a top-level tenantId filter on top of validate_citations' explicit tenant+global $or scope, silently excluding global-KB citations; log_ai_decision still gets the wrapped db since insert_one relies on its auto-injection
- [Phase 39-06]: control_id added as an optional trailing kwarg on evaluate_control/evaluate_evidence (not in the plan's literal signature sketch) because ai_auditor_endpoints.py's real call site never passes one and is out of this plan's file scope -- caller-supplied control_id is pinned onto the returned finding (model_copy override), never trusted from the model; absent a caller value, falls back to extract_control_id_tokens(control_desc) then UNSPECIFIED (fails framework-fidelity by design, fail-closed)
- [Phase 39-06]: shim maps a needs_review (fallback-provenance pass) result to verified=False with a NEEDS_REVIEW marker in reasoning, since the legacy 2-state {verified: bool} contract has no third "pending human review" state and ai_auditor_endpoints.py's write path could not be changed
- [Phase 39-07]: chat.py preserves ai_assistant_service.chat()'s exact RAG + live-findings fusion via direct rag_service.query()/db queries in addition to the agent's own search_evidence tool -- guarantees deterministic {type,id,title,snippet} sources regardless of whether the model calls the tool mid-turn
- [Phase 39-07]: chat.py uses the real persistent checkpointer (AsyncSqliteSaver via checkpointer_lifespan) rather than InMemorySaver, since chat is the multi-turn conversational surface 39-AI-SPEC calls out for real persistent memory across restarts (unlike 39-06 auditor's per-control InMemorySaver)
- [Phase 39-07]: test_ai_assistant.py's 5 pre-existing tests retargeted onto the new chat-agent call graph (patches on ai_orchestration.agents.chat.* instead of the now-removed ai_assistant_service.rag_service/.ai_service) -- required to satisfy the plan's own phase-level verification that this file keep passing; behavioral assertions unchanged
- [Phase ?]: [Phase 39-08]: questionnaire.py's DraftResult carries retrieved_evidence (raw RAG chunks) beyond the plan's literal field list, so the shim builds sourceEvidence without a second RAG query
- [Phase ?]: [Phase 39-08]: questionnaire citation validation uses the same validate_citations (39-03) as the auditor, which only resolves chunk_id against control_evidence/asset_compliance Mongo -- not ChromaDB ids; since this surface only has the search_evidence RAG tool (no Mongo-backed evidence tool), most real citations will conservatively downgrade to insufficient_evidence -- fail-closed by design, flagged as a known limitation not fixed (out of plan scope)
- [Phase ?]: [Phase 39-08]: test_questionnaire_auto_answer_e2e.py mocks retargeted from removed rag_service/ai_service module attributes onto the shim's own call to generate_draft (Rule 1 fix)
- [Phase ?]: [Phase 39-09]: agents/narrative.py's generate_executive/generate_framework take db as a required trailing param (not in the plan's literal signature) since build_model_for_tenant/log_ai_decision require it -- mirrors evaluate_control/generate_draft's own db param in 39-06/39-08
- [Phase ?]: [Phase 39-09]: compliance_narrative_service.py's public functions keep their exact 4-arg signatures with two new optional trailing tenant_id/db kwargs -- enrich_report_data passes both explicitly per RESEARCH Pitfall B, other callers fall back to ambient tenant_context/database resolution
- [Phase ?]: [Phase 39-09]: framework-fidelity validation failure is fail-closed (falls back to the deterministic narrative) rather than a non-blocking flag, consistent with this phase's posture on every other citation/control-ID validation surface
- [Phase 40-01]: reqwest features extended (not replaced) with native-tls, mirroring the existing tokio-tungstenite pin
- [Phase 40-01]: Rust agent version advanced straight to 2.1.3, never reusing an already-shipped number (2.1.0/2.1.1/2.1.2)
- [Phase 40-01]: Generated the optional omni-agent-2.1.3.b64 companion for parity with every prior release
- [Phase ?]: 40-02: Fixed SESS-01 by adding revoked_tokens.jti unique index (D-05 Mechanism A only); refresh_access_token logic unchanged; Mechanism B deferred
- [Phase ?]: 40-02: Live-Mongo regression test creates its own jti unique index in setup so it independently exercises the uniqueness constraint
- [Phase 41-02]: Resolved cryptography/pyOpenSSL/webauthn/alibabacloud_tea_openapi 4-way pin conflict by pinning cryptography==49.0.0/pyOpenSSL==26.3.0 — oci install downgraded both, breaking webauthn's hard >=49.0.0/>=26.3.0 requirement; alibabacloud_tea_openapi's cryptography<49.0.0 pin verified stale via functional RSA sign/verify test
- [Phase 41-02]: All 4 SUS-flagged alibabacloud_* V2 SDK packages human-verified as legitimate (official aliyun org) before install — Blocking package-legitimacy checkpoint approved by user with independently-verified PyPI metadata
- [Phase 41]: 41-01: service category for all new OCI/Alibaba/Cloudflare checks drawn strictly from shared set {iam, storage, encryption, logging} per D-03, not each provider's native taxonomy
- [Phase ?]: 41-04: Credential field keys (oci_tenancy_ocid, access_key_id, cf_api_token, etc.) taken directly from backend ingest modules' required_fields lists, not paraphrased from docs
- [Phase ?]: 41-04: AddCloudAccountModal onSave prop widened with an optional credentials field via intersection type rather than adding credentials to the shared CloudAccount type
- [Phase ?]: 41-03: separate _make_oci_client_real() helper added instead of un-mocking _make_oci_client() in place — real OCI SDK raises InvalidConfig on placeholder creds the pre-existing SIEM test uses unmocked
- [Phase ?]: 41-03: _make_cloudflare_client() un-mocked in place — verified real Cloudflare() construction never raises regardless of token content, safe for the shared SIEM path
- [Phase ?]: 41-03: Alibaba CSPM uses SAS V2 list_check_result (per-check status) rather than describe_check_warning_summary (category rollup) — closer match to required checkId/status=FAIL shape
- [Phase 41]: 41-05: Dispatch tests placed in test_cloud_findings_ingest.py (not test_cloud_accounts.py) — plan's pre-authorized alternative since poll functions were already imported there and fixtures already patch get_database for oci/alibaba/cloudflare ingest modules
- [Phase 42]: 42-01: control_comments deliberately absent from database.py's tenant-isolation exemption allowlists so TenantIsolatedCollection auto-scopes every read/write
- [Phase 42]: 42-01: GET /api/control-comments open to any authenticated tenant user (A2); only POST role-gated to admin/super_admin/compliance_reviewer (D-01)
- [Phase 42]: 42-01: no PATCH/DELETE route created for control comments — D-03 immutability enforced by omission
- [Phase 42]: 42-02: resolve_mentions tries username -> email-local-part -> case-insensitive name match against db.users, in that order
- [Phase 42]: 42-02: fixed notification_service.py send_alert to distinguish channels=None (defaults to email) from channels=[] (explicit no-dispatch) - pre-existing bug that would have violated D-02 in-app-only guarantee
- [Phase ?]: 42-03: fetchControlComments non-throwing (returns [] on error) matching fetchControlAuditLog convention; postControlComment throws on non-ok
- [Phase ?]: 42-03: ControlCommentsPanel mount NOT wrapped in canViewCoC guard — comment-thread reads available to all authenticated tenant users (A2); composer visibility gated inside panel via isReviewer
- [Phase ?]: 42-03: Rule 1 auto-fix — reworded anti-XSS code comment in ControlCommentsPanel.tsx that had spelled out the literal forbidden-prop name, tripping the plan's own grep-based acceptance gate; no behavior change
- [Phase 43]: 43-01: D-03 revised — close-loop scheduler polls every 300s (5min), matching tickets_escalation_service.py's existing interval, superseding 43-PATTERNS.md's stale 1200s example
- [Phase 43]: 43-01: D-06 — get_jira_issue_status/get_servicenow_incident_status return not_found:True on HTTP 404; run_close_loop_pass skips (never auto-resolves) a deleted/not_found ticket
- [Phase ?]: D-01 revised auto-create threshold applied (critical/high/medium, not high/critical) per plan's post-plan-checker correction
- [Phase ?]: Auto-create hook never passes provider_override; always resolves via tenant's configured ticketing provider
- [Phase 43]: 43-03: manual create-ticket endpoint always passes provider_override=body.provider explicitly, distinct from 43-02's auto-create hook which omits it to use the tenant's configured provider
- [Phase 43-04]: getTicketingConfig() uses the safe-default try/catch shape (never throws) since hasJira/hasServiceNow drive conditional rendering, not an error path
- [Phase 43-04]: Provider values are restricted to the 'jira'|'servicenow' string literal union throughout (state, radio tiles, API call) — no free-text provider input anywhere
- [Phase ?]: 44-01: sla_status defaults to ok (due_date set) / none (absent) on create_task; sweep recomputes
- [Phase ?]: 44-01: _mock_db() wires db._db = db so get_sla_at_risk_window's dual-call-site unwrap guard resolves correctly against MagicMock's auto-attribute creation
- [Phase 44]: 44-02: Escalation only fires once per tier increase (new_level > current escalation_level gate) — never re-escalates/re-notifies on repeat sweep passes within the same tier
- [Phase 44]: 44-02: send_alert skipped (not called with empty recipients) when neither assignee nor any admin resolves — remediation_escalations entry still written regardless
- [Phase ?]: 44-03: post-fetch tenantId filter added on top of the query-level AND for escalation-history reads — never trust the query filter alone (T-44-06)
- [Phase ?]: 44-03: _SETTINGS_ADMIN_ROLES kept file-local, not cross-wired with notification_manager.py's _ADMIN_ROLES (different purposes: settings-mutation gating vs. notification recipients)
- [Phase 44]: 44-04: EscalationHistoryPanel extracted to its own file — inlining pushed RemediationTaskModal.tsx to 501 lines, over the CLAUDE.md 500-line limit; pre-authorized by the plan
- [Phase 44]: 44-04: SLA badge always falls back to the neutral 'none' pill for tasks missing sla_status, never blank/undefined (T-44-11 mitigation)
- [Phase 44]: 44-04: Escalation panel renders only when task?.id is set and contains zero edit/delete/confirm/destructive controls (T-44-10 mitigation, SLA-02 locked constraint)
- [Phase 45]: reqwest pinned to native-tls-only via default-features=false; non-TLS defaults (charset/http2/system-proxy) re-listed explicitly
- [Phase ?]: 46-01: Reused geoip_service._is_public() via direct import rather than duplicating the classifier
- [Phase ?]: 46-01: lookup() omits 'asn'/'vpn_heuristic' keys entirely rather than setting None/False placeholders when their respective data sources are unavailable
- [Phase ?]: 46-02: DEBOUNCE_WINDOW locked at timedelta(minutes=10) (Claude's Discretion per CONTEXT.md D-06)
- [Phase ?]: 46-02: record_location_change() internally calls get_track_agent_location() so the toggle is enforced at a single call boundary
- [Phase ?]: 46-02: dwell time is never stored on agent_location_history rows — computed at read time in the GET endpoint (46-04/46-06)
- [Phase 46-03]: Retention-enforcement trigger locked as manual-trigger-only (POST /api/retention/run), matching existing module precedent; automatic scheduler explicitly deferred
- [Phase 46-03]: cleanup_agent_location_history compares a native datetime cutoff (never .isoformat()) since agent_location_history.timestamp is a real BSON Date, unlike the module's other 3 cleanup_* methods
- [Phase ?]: 46-04: Repaired pre-existing untracked draft agent_location_history_endpoints.py in place (agentId->agent_id query bug, timedelta->dwell_seconds serialization bug) rather than rewriting from scratch
- [Phase ?]: 46-04: dwell field named dwell_seconds per plan's own task text; flagged conflict with 46-UI-SPEC.md's client-side-dwell note for the frontend consumer plan to reconcile
- [Phase ?]: 46-05: geo.asn/geo.vpn_heuristic merged into the same 'geo' dict (not separate dotted $set keys) to avoid a MongoDB update-path conflict between 'geo' and 'geo.asn'
- [Phase ?]: 46-05: track_agent_location toggle resolved once per request in the endpoint, gating both agent_asn_service.lookup and record_location_change; geoip_service.lookup city/country enrichment stays unconditional (scope boundary, T-46-05-B)
- [Phase ?]: 46-05: extracted auto-update-push/persistence-detection/pii-scanner blocks out of agent_heartbeat_endpoints.py into two new service modules to satisfy the CLAUDE.md 500-line cap (file was already at 517 lines pre-existing this plan)
- [Phase 46]: 46-06: resolved dwell computation conflict in favor of 46-UI-SPEC.md (client-side, ignores backend dwell_seconds) — Backend computes dwell_seconds for other consumers/back-compat; UI-SPEC locks client-side computation as the panel's authoritative behavior contract.
- [Phase ?]: PrivacyDashboard reuses its own existing dark palette/toggle conventions rather than the 46-UI-SPEC.md tokens (that spec is scoped to the AgentLocationHistory timeline panel from 46-06)
- [Phase ?]: Fixed setAgentLocationTracking() to throw on non-OK PATCH responses instead of silently returning a false-success value, so 403s surface as error toasts (T-46-07-A)
- [Phase ?]: 47-01: Fixed persist_security_alert via alias (= _persist_alert), not rename — preserves 4 internal call sites untouched
- [Phase ?]: 47-01: Deferred ueba_service.py's pre-existing >500-line CLAUDE.md overage to deferred-items.md — out of scope for this minimal prerequisite fix
- [Phase ?]: 47-01: Skipped requirements.mark-complete for GSEC-02/GSEC-03 — this plan only delivers the prerequisite alert-fan-out fix; the actual detector logic spans 47-02/03/04 (GSEC-02/03) and 47-06 (GSEC-03), so the checkbox stays unchecked until those land
- [Phase ?]: 47-02: impossible-travel/geo-fence evaluate against RAW existing_agent.geo/lastSeen, never Phase 46's debounced locationConfirmed/locationPending
- [Phase ?]: 47-02: vpn_heuristic suppression checks is True only -- None/False never suppress (D-02, Pitfall 5)
- [Phase ?]: 47-02: dedup cooldown re-fires after 6h if still violating (D-07), not one-alert-per-transition-forever
- [Phase ?]: 47-05: asn typed as { number?: number | string; org?: string } to match agent_asn_service.lookup()'s stored shape
- [Phase ?]: 47-05: badge cloned verbatim from AgentLocationHistory.tsx rather than extracted into a shared component
- [Phase ?]: 47-03: geo security detector call-through gated by the same track_agent_location toggle Phase 46 used for record_location_change
- [Phase ?]: 47-03: existing_agent (PRE-update doc) passed as previous state to run_geo_security_detectors, never a debounced shadow field
- [Phase ?]: 47-04: PATCH /api/settings/geo-security re-reads via get_geo_security_settings and returns the resolved dict rather than echoing the request body, so the response always reflects actual persisted+resolved state
- [Phase ?]: 47-04: allowed_country_codes ISO 3166 alpha-2 validation lives in a Pydantic field_validator on GeoSecuritySettingsUpdate (API boundary), separate from geo_security_service's own defensive normalization
- [Phase ?]: 47-06: Kept SecuritySettingsDashboard.tsx as a new, separate component rather than folding into PrivacyDashboard.tsx per D-06 (security config distinct from privacy config)
- [Phase ?]: 47-06: geoSecurity nav item and viewPermissionMap entry both gated on manage:settings (client-side gate; backend PATCH's _require_admin is the authoritative control per T-47-06-E)
- [Phase 48]: 48-01: compute_uptime accepts optional now= kwarg for deterministic testing; endpoint never passes it, no production behavior change
- [Phase 48]: 48-01: min(received/expected,1.0) clip is a documented safety net; received_bucket_indices is bounded by construction to expected_buckets, so it never actually needs to clip
- [Phase ?]: 48-02: agent_uptime_rollups timestamp stored as native BSON Date (datetime.now(timezone.utc)), never .isoformat(), so retention's $lt comparison works correctly
- [Phase ?]: 48-02: No historical backfill on first run (D-08) — agent_uptime_rollups fills in one row per agent per day going forward only
- [Phase ?]: 48-02: retention_endpoints.py's _POLICY_DEFAULTS intentionally not extended for agent_uptime_rollups — out of this plan's declared file scope; run_cleanup's own 90-day default already applies correctly
- [Phase 48]: 48-03: Version-drift compare treats an unparseable or missing reported version as fail-closed excluded (not a crash, not flagged as drift) — T-48-08 accept disposition
- [Phase 48]: 48-03: Response includes offline_count/drift_count alongside full lists so 48-05's nav page can render summary tiles without client-side recompute
- [Phase ?]: 48-04: AgentMetricsTab and MetricsChartsTab kept as separate components (not a shared prop-toggle component) since data source, tenancy scoping, and range presets genuinely differ per D-04 CORRECTION
- [Phase ?]: 48-04: AgentUptimeTimeline receives agentId/hours as props rather than deriving its own agent-id, keeping AgentMetricsTab the single source of truth for the shared range selector
- [Phase 48]: 48-05: fetchFleetObservability throws on non-ok (rather than returning defaults) so a failed fleet load surfaces as a visible error to the admin
- [Phase 48]: 48-05: Fleet Observability nav page cloned Phase 47's SecuritySettingsDashboard 4-file registration verbatim, gated by manage:agents (D-07)

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
| Phase 39-langchain-ai-integration P05 | ~20m | 3 tasks | 8 files |
| Phase 39-langchain-ai-integration P10 | ~12m | 3 tasks | 6 files |
| Phase 39-langchain-ai-integration P06 | ~25min | 3 tasks | 3 files |
| Phase 39-langchain-ai-integration P07 | 35min | 3 tasks | 4 files |
| Phase 39-langchain-ai-integration P08 | ~35min | 3 tasks | 4 files |
| Phase 39-langchain-ai-integration P09 | ~35min | 3 tasks | 4 files |
| Phase 40 P01 | 5min | 2 tasks | 4 files |
| Phase 40 P02 | 20min | 2 tasks | 2 files |
| Phase 41 P02 | 15min | 2 tasks | 1 files |
| Phase 41 P01 | 20min | 3 tasks | 7 files |
| Phase 41 P04 | 12min | 2 tasks | 3 files |
| Phase 41 P03 | 30min | 3 tasks | 4 files |
| Phase 41 P05 | 25min | 3 tasks | 2 files |
| Phase 42 P01 | 20min | 3 tasks | 4 files |
| Phase 42 P02 | 25min | 3 tasks | 5 files |
| Phase 42 P03 | 4min | 3 tasks | 3 files |
| Phase 43 P01 | 3min | 3 tasks | 2 files |
| Phase 43 P02 | 5min | 2 tasks | 2 files |
| Phase 43 P03 | 3min | 3 tasks | 3 files |
| Phase 43 P04 | 14min | 3 tasks | 3 files |
| Phase 44 P01 | 55min | 3 tasks | 4 files |
| Phase 44 P02 | 24min | 2 tasks | 2 files |
| Phase 44 P03 | 8min | 2 tasks | 2 files |
| Phase 44 P04 | 20min | 3 tasks | 4 files |
| Phase 45 P01 | 20min | 2 tasks | 2 files |
| Phase 46 P01 | 20min | 2 tasks | 3 files |
| Phase 46 P02 | 35min | 3 tasks | 3 files |
| Phase 46 P03 | 8min | 2 tasks | 3 files |
| Phase 46 P04 | 15min | 2 tasks | 3 files |
| Phase 46 P05 | 25min | 2 tasks | 5 files |
| Phase 46 P06 | 25min | 2 tasks | 5 files |
| Phase 46 P07 | 20min | 1 tasks | 2 files |
| Phase 47 P01 | 5min | 2 tasks | 2 files |
| Phase 47 P02 | 25m | 3 tasks | 2 files |
| Phase 47 P05 | 8min | 2 tasks | 2 files |
| Phase 47 P03 | 20min | 2 tasks | 2 files |
| Phase 47 P04 | 20min | 2 tasks | 3 files |
| Phase 47 P06 | 12min | 3 tasks | 6 files |
| Phase 48 P01 | 15min | 2 tasks | 4 files |
| Phase 48 P02 | 25min | 2 tasks | 5 files |
| Phase 48 P03 | 15min | 2 tasks | 3 files |
| Phase 48 P04 | 20min | 3 tasks | 4 files |
| Phase 48 P05 | 20min | 2 tasks | 5 files |

## Last Session

- **Timestamp:** 2026-07-14T04:30:00.000Z
- **Stopped at:** Completed 48-02-PLAN.md
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

**Last session:** 2026-07-29T18:30:33.760Z
**Stopped at:** Phase 39 plan 39-09 (create_agent narrative generation — NarrativeOutput + word-budget validation + framework-fidelity flagging + fail-closed fallback + shim; AISPEC-39-S4/S4b/S6/S7, RESEARCH-Pat3) executed and committed 2026-07-18 (commits 995f295/a8015d7/db00e30) — backend/ai_orchestration/agents/narrative.py (generate_executive/generate_framework build a per-tenant create_agent with no tools, requesting NarrativeOutput via ToolStrategy; word budget (executive 150, framework 200) always recomputed from the actual returned text via NarrativeOutput.from_raw, never trusted from the model's self-reported word_count/limit fields; fail-closed fallback on validation failure, BLOCKED:/Error: output, guardrail block, unresolved framework-fidelity token, or any agent exception) and compliance_narrative_service.py (thin shim preserving generate_executive_summary/generate_framework_narrative's exact 4-arg signatures + str return + enrich_report_data + _render_narratives; two new optional trailing tenant_id/db kwargs let enrich_report_data pass both explicitly per RESEARCH Pitfall B). 17 hermetic unit tests green (test_narrative_agent.py, 12 -k agent / 5 -k shim). Rule-1 fix: retargeted test_compliance_narrative_service.py's 5 pre-existing tests off the now-removed compliance_narrative_service.ai_service attribute onto the new agent boundary — all 8 tests still pass. Full backend suite: 1104 passed / 23 skipped / 2 failed (both pre-existing, unrelated — test_e2e_integration.py golden path, test_rust_heartbeat_parity.py). **All four AI-surface migrations (auditor/chat/questionnaire/narrative) now complete.** Next — 39-11/39-12 (eval dimensions, code-based and LLM-judged).
**Resume file:** None

## Accumulated Context

### Roadmap Evolution

- Phase 45 added: Close gap: RUST-01 — TLS backend explicit decision (from v3.2 milestone audit gaps_found; reqwest default-features left on, shipping both native-tls and full rustls stack in the Windows exe)

- Phase 24 added: IaC & Container Security (Terraform/CloudFormation/Kubernetes scanning + container image vulnerability scanning). A `24-01-PLAN.md` already existed on disk (drafted ahead of execution, never wired into ROADMAP.md) — registered as Phase 24 in ROADMAP.md and REQUIREMENTS.md (IAC-01..03) reusing the existing directory/plan rather than generating a new one, so `/gsd-autonomous --only 24` can discover and execute it.
- v3.0 milestone added 2026-07-06: 14 new phases (25–38) scaffolded from a feature-parity audit run the same day against Comp AI, Probo, OpenLane Core, and Prowler (69 features checked directly against source — 41 implemented, 10 partial, 15 absent). Phases are ordered in 3 risk tiers — Tier 1 quick fixes (25–27), Tier 2 medium features (28–33), Tier 3 architectural bets (34–38: GraphQL, ReBAC, real MCP protocol, public Trust Center, passkeys). User explicitly chose "everything, in tiers" over a smaller subset. Requirements CHK/VRISK/RISK/EXP/DOC/TRUST/RAG/FAIR/PROV/WF/AUTH/GQL/REBAC/MCP/ASSIST added to REQUIREMENTS.md. Phase 25 is the first to go through full research → plan → verify.

## Current Position

Phase: 48 (fleet-observability-uptime-rollups) — EXECUTING
Plan: 5 of 5
Status: Phase complete — ready for verification
Last activity: 2026-07-29 — Phase 48 execution started

## Deferred Items

Items acknowledged and deferred at v3.2 milestone close on 2026-07-29 (16 total, project-wide scan — all predate v3.2 or are environmental). Supersedes the 2026-07-21 paused-close list: Phase 40's items are now resolved — the 401 concurrent-refresh test passes (test_auth_refresh_race.py), and the RUST-01 TLS-backend gap was closed by Phase 45 (40-VERIFICATION.md now status: passed). The only Phase 40 residue is one UAT scenario blocked on a physical Windows device.

| Category | Item | Status |
|----------|------|--------|
| uat | Phase 02 (02-UAT.md) | testing, 7 pending scenarios (pre-v3.2, v1.1) |
| uat | Phase 06 (06-UAT.md) | partial (pre-v3.2, v1.1) |
| uat | Phase 15 (15-UAT.md) | testing, 12 pending scenarios (pre-v3.2, v2.0) |
| uat | Phase 27 (27-UAT.md) | unknown (pre-v3.2, v3.0) |
| uat | Phase 28 (28-UAT.md) | unknown (pre-v3.2, v3.0) |
| uat | Phase 29 (29-UAT-SUMMARY.md) | blocked (pre-v3.2, v3.0) |
| uat | Phase 29 (29-UAT.md) | unknown (pre-v3.2, v3.0) |
| uat | Phase 30 (30-UAT.md) | unknown (pre-v3.2, v3.0) |
| uat | Phase 32 (32-UAT.md) | unknown (pre-v3.2, v3.0) |
| uat | Phase 33 (33-UAT.md) | unknown (pre-v3.2, v3.0) |
| uat | Phase 34 (34-UAT.md) | unknown (pre-v3.2, v3.0) |
| uat | Phase 35 (35-UAT.md) | unknown (pre-v3.2, v3.0) |
| uat | Phase 39 (39-UAT.md) | partial (pre-v3.2, v3.1) |
| uat | Phase 40 (40-UAT.md) | partial, 0 pending — 1 test blocked_by physical-device (agent auto-update to 2.1.3 on a real Windows box; unrunnable in sandbox) |
| verification | Phase 06 (06-VERIFICATION.md) | human_needed (pre-v3.2, v1.1) |
| verification | Phase 32 (32-02-VERIFICATION.md) | gaps_found (pre-v3.2, v3.0) |

## Operator Next Steps

- v3.3 roadmap defined (Phases 46-49, 11/11 requirements mapped). Start planning the first phase with /gsd-plan-phase 46
