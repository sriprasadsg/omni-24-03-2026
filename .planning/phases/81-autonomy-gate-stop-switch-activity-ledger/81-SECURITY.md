---
phase: "81"
slug: "autonomy-gate-stop-switch-activity-ledger"
status: verified
# threats_open = count of OPEN threats at or above workflow.security_block_on severity (the blocking gate)
threats_open: 0
asvs_level: 1
created: "2026-10-26"
---

# Phase 81 — Security

> Per-phase security contract: threat register, accepted risks, and audit trail.
> Register authored at plan time (the `<threat_model>` blocks of 81-01..81-12) and verified against the
> implementation at ASVS L1 (grep depth) on 2026-10-26, after all 12 plans executed. All 444 mapped backend
> tests and 613 vitest tests were green at audit time.

---

## Trust Boundaries

| Boundary | Description | Data Crossing |
|----------|-------------|---------------|
| API JSON (finding-derived text) -> React render | Reasons, targets and results can contain attacker-influenced strings | untrusted / safety-critical |
| Native Security console approver -> dispatch | Human approval of a remediation card | untrusted / safety-critical |
| approver click -> dispatch | A human decision turns a card into an endpoint action | untrusted / safety-critical |
| autonomy_* collections -> later UI and audit | Decision records are the evidence of what the system did | untrusted / safety-critical |
| backend queues -> agent poll | The last point where an autonomous instruction can still be stopped | untrusted / safety-critical |
| background sweeps (platform-admin context) -> tenant data | Sweeps run without a request tenant and must not leak across tenants | untrusted / safety-critical |
| browser / API key -> /api/autonomous-ops | Untrusted callers request reads and safety-critical writes | untrusted / safety-critical |
| correlation data / LLM answer -> playbook step | Telemetry-derived and model-derived input decides which containment runs | untrusted / safety-critical |
| finding / playbook input -> gate.decide | Finding fields and playbook params come from agents and operators and are untrusted | untrusted / safety-critical |
| findings (agent telemetry) -> remediate -> agent queue | The deterministic engine turns findings into endpoint actions | untrusted / safety-critical |
| gate -> agent_instructions / response_tasks | Anything written here is executed on an endpoint | untrusted / safety-critical |
| gate -> platform host and management network | An automatic action against these would take down the platform itself | untrusted / safety-critical |
| migration -> every tenant document | One-time data write at startup | untrusted / safety-critical |
| multiple backend workers -> shared lock collection | Two workers must never run the same sweep at once | untrusted / safety-critical |
| operator -> stop state | Pressing and clearing change what every agent may receive | untrusted / safety-critical |
| operator click -> stop/resume request | The brake and its release | untrusted / safety-critical |
| playbook engine -> response_tasks | The response-task queue the agent executes | untrusted / safety-critical |
| reconciler (no request tenant) -> every tenant's rows | Background work spans tenants | untrusted / safety-critical |
| role table / custom role documents -> effective permissions | Who may see, manage or act on Autonomous Ops | untrusted / safety-critical |
| sign-up / Add Tenant -> autonomy_settings | Tenant creation writes the initial autonomy level | untrusted / safety-critical |
| status payload -> banner and card | Server decides who may resume and whose name is shown | untrusted / safety-critical |
| tenant switch (Super Admin tick) -> eligibility | The tick is the opt-in that makes a tenant eligible (GATE-02) | untrusted / safety-critical |
| tenant user -> platform-scope data | Platform stop records carry platform staff identities | untrusted / safety-critical |
| viewer scope -> tenantId parameter | Which tenant's activity is requested | untrusted / safety-critical |

---

## Threat Register

| Threat ID | Category | Component | Severity | Disposition | Mitigation | Status |
|-----------|----------|-----------|----------|-------------|------------|--------|
| T-81-01 | Elevation of Privilege | registry.effective_class / playbook YAML | high | mitigate | Classes are a read-only code mapping; only the explicit gate_class step key can raise and nothing lowers; registry test proves approve never becomes auto and that every shipped playbook keeps its registry class (block_ip stays auto per the locked split); 81-11's enumeration repeats it through decide. Evidence: `registry.py` raise-only via explicit `gate_class`; `test_autonomous_ops_registry.py`, gate enumeration | closed |
| T-81-02 | Denial of Service | protected.check against platform host and management network | high | mitigate | Built-ins computed in code (not rows, not removable), refused at every level, boundary and IPv4-mapped tests, strict ipaddress parsing (invalid_target). Evidence: `protected.py` built-ins in code, `invalid_target`, IPv4-mapped handling; `test_autonomous_ops_protected.py` | closed |
| T-81-03 | Tampering | gate.execute / execute_response_task | high | mitigate | Only stamped writers; re-read ledger row state per kind; refuse while stopped except undo/compensate (D-12); raw handle with explicit tenantId. Evidence: `gate.execute` / `execute_response_task` are the only stamped writers; structural test | closed |
| T-81-04 | Repudiation | ledger.create_intent / transition | high | mitigate | Write-ahead insert raises -> refuse ledger_unavailable; awaited audit_ledger.event per transition; CAS single winner; fault-injection and chain-verify tests. Evidence: `ledger_unavailable` refusal, awaited audit mirror, CAS; `test_autonomous_ops_ledger.py` | closed |
| T-81-05 | Information Disclosure | cross-tenant target or row | high | mitigate | Every query filters explicit tenantId; target agent must belong to the request tenant (cross_tenant_target); no ContextVar use. Evidence: `cross_tenant_target` in `gate.py`; isolation test | closed |
| T-81-06 | Elevation of Privilege | control:autonomous_ops without MFA | high | mitigate | Added to ADMIN_TIER_PERMISSIONS; _enforce_admin_mfa refuses unverified sessions; tests for built-in and custom roles (D-07). Evidence: `control:autonomous_ops` in `ADMIN_TIER_PERMISSIONS` (`rbac_defaults.py`); MFA tests | closed |
| T-81-07 | Elevation of Privilege | control:platform_autonomous_ops in a tenant custom role | high | mitigate | In PLATFORM_ONLY_PERMISSIONS; effective_permissions strips it from non-platform roles; test proves it. Evidence: `control:platform_autonomous_ops` in `PLATFORM_ONLY_PERMISSIONS`; permissions test | closed |
| T-81-08 | Elevation of Privilege | manage implies control via closure | medium | mitigate | implied_closure never derives control:; closure edge test (PROH-81-16). Evidence: closure never derives `control:`; `test_autonomous_ops_permissions.py` | closed |
| T-81-09 | Information Disclosure | Platform Billing reading activity | medium | mitigate | Platform Support reads through its role-table view: string; no platform_read guard; billing row unchanged (A8). Evidence: Platform Billing gets no access; permission matrix tests | closed |
| T-81-10 | Tampering | distributed_lock without renewal | high | mitigate | renew_lock filtered on token and unexpired; lock_with_renewal sets lost and the sweep stops; real-Mongo timing tests. Evidence: `renew_lock` / `lock_with_renewal` in `distributed_lock.py`; real-Mongo timing tests | closed |
| T-81-11 | Information Disclosure | is_duplicate_task cross-tenant query | medium | mitigate | tenantId on both queries; empty tenant fails closed; two-tenant test. Evidence: `is_duplicate_task` filters `tenantId`; `test_response_orchestrator_tenant.py` | closed |
| T-81-12 | Elevation of Privilege | scheduled legacy loop reaching the LLM path | high | mitigate | Loop and registration deleted; AST test proves nothing schedules it. Evidence: legacy loop deleted; AST test `test_legacy_remediation_loop_is_not_scheduled` | closed |
| T-81-13 | Repudiation | wrong agents in offline notifications | low | mitigate | Ids selected before update; notifications use that list; set-equality test. Evidence: ids selected before update and notified; `test_monitor_agent_status.py` | closed |
| T-81-14 | Tampering | approvals.approve double click / replay | high | mitigate | Single CAS with expiry in the filter; already_handled for the loser; gather race test with 2 and 5 callers. Evidence: single CAS with expiry filter, `already_handled`; 2- and 5-caller race tests | closed |
| T-81-15 | Elevation of Privilege | approve during a stop or after expiry | high | mitigate | Stop read first (read error = stopped); expiry check and filter; expire_due runs during a stop (D-12, D-13). Evidence: stop read first, `expire_due` runs during a stop; approvals tests | closed |
| T-81-16 | Denial of Service | approve of a now-protected or moved target | high | mitigate | Re-validate agent tenant, protected.check and effective level before dispatch. Evidence: re-validates tenant, `protected.check` and level before dispatch (`approvals.py`) | closed |
| T-81-17 | Information Disclosure | reconciler crossing tenants | high | mitigate | Explicit tenantId on every query; tenant_scope reset; ContextVar None assertion; two-tenant isolation test. Evidence: `tenant_scope` reset per tenant in `reconciler.py`; ContextVar None assertions | closed |
| T-81-18 | Tampering | two workers reconciling at once | medium | mitigate | lock_with_renewal; stop on handle.lost; concurrent-holder test. Evidence: `lock_with_renewal` in `reconciler.py`; concurrent-holder test | closed |
| T-81-19 | Tampering | queued stamped instruction delivered during a stop | high | mitigate | hold_back_autonomous in all three handlers and hold_back_response_tasks; uncached reads; press-time bulk cancel; terminal cancelled_by_stop. Evidence: hold-back hooked in all four delivery paths (agent_tasks, deployment_result, agent_instruction, response_orchestrator) | closed |
| T-81-20 | Denial of Service | stop read failure at delivery | medium | mitigate | Fail closed: withhold stamped instructions when state cannot be read; unstamped work unaffected. Evidence: `delivery.py` withholds (leaves pending) when stop or ledger is unreadable | closed |
| T-81-21 | Elevation of Privilege | clearing a Super Admin or platform stop | high | mitigate | can_clear decided from stored pressedByTier/scope; matrix test (D-11). Evidence: `stop.can_clear` from stored `pressedByTier`/scope; 7-case matrix test | closed |
| T-81-22 | Repudiation | who pressed/cleared and why | medium | mitigate | Control rows with actor and reason, audit_ledger mirror (D-14). Evidence: control rows with actor and reason, audit_ledger mirror (`stop.py`) | closed |
| T-81-23 | Information Disclosure | stamped instruction of another tenant | high | mitigate | Withhold when row tenant differs from instruction or polling tenant. Evidence: `delivery.py` refuses rows whose tenant differs from the instruction or poller | closed |
| T-81-24 | Elevation of Privilege | XDR auto-playbook steps outside the gate | high | mitigate | Automatic executors pass gate.decide; tasks only via execute_response_task on allow_auto; defaults record shadow. Evidence: `AUTOMATIC_EXECUTORS` fence in `playbook_engine_actions.py`; `test_autonomous_ops_xdr_fence.py` | closed |
| T-81-25 | Elevation of Privilege | LLM-chosen action dispatch | high | mitigate | Selectors call gate.suggest (forced Suggest), never execute_playbook (PROH-81-02). Evidence: selectors call `gate.suggest`, never `execute_playbook` (AST test) | closed |
| T-81-26 | Elevation of Privilege | 0.90 confidence auto-approve | high | mitigate | Branch and constant removed; test with 0.99 confidence still requires approval. Evidence: `AUTO_APPROVE_CONFIDENCE_THRESHOLD` removed from `backend_safety.py`; 0.99 still needs approval | closed |
| T-81-27 | Denial of Service | breaking manual SOC playbook runs | medium | mitigate | Manual path untouched below the fence; regression test of the unstamped task shape and existing playbook tests. Evidence: manual `PB-BLK-` task shape regression test | closed |
| T-81-28 | Tampering | rendering finding text (XSS) | high | mitigate | React text only; no dangerouslySetInnerHTML (grep gate); no link-ification of targets or reasons. Evidence: no `dangerouslySetInnerHTML` in any Autonomous Ops component; hostile-string test | closed |
| T-81-29 | Information Disclosure | tenantId parameter from the client | medium | mitigate | Client sends viewingTenantId only for platform staff; the server (81-09) honours it only for platform staff; tenant roles send none. Evidence: client sends `tenantId` only for platform roles; server honours it only for platform staff | closed |
| T-81-30 | Repudiation | simulation mistaken for a real action | medium | mitigate | Simulation chip, dashed rule, result sentence, excluded from state filters (PROH-81-06). Evidence: simulation chip, result prefix, excluded from state filters (client-side guard added) | closed |
| T-81-31 | Elevation of Privilege | legacy run_cycle / generate_plan / execute_plan (LLM-written scripts) | critical | mitigate | Deleted; loop removed in 81-03; AST LLM ban; structural legacy-symbol test. Evidence: `run_cycle`/`generate_plan`/`execute_plan` deleted; AST LLM-import ban; structural test | closed |
| T-81-32 | Tampering | second autonomous writer added later | high | mitigate | Grandfathered-writer and stamp tests with negative controls. Evidence: `GRANDFATHERED_WRITERS` and stamp tests with negative controls | closed |
| T-81-33 | Tampering | console double-click approval | high | mitigate | approvals.approve CAS plus remediation_requests CAS in the dispatcher; already_handled test. Evidence: approvals CAS plus `pending_approval`→`dispatching` CAS in the dispatcher | closed |
| T-81-34 | Elevation of Privilege | console approvers without the approve tier | medium | mitigate | control:autonomous_ops via verify_permission on approve/deny (D-24 (c)); JWT-only routes keep API keys out (D-10). Evidence: console approve/deny require `control:autonomous_ops` (`remediation_control_endpoints.py`) | closed |
| T-81-35 | Elevation of Privilege | tenant admin raising its own level above the cap | high | mitigate | settings.set_level refuses above maxLevel; maxLevel writable only on the platform router (Super Admin). Evidence: `settings.set_level` refuses above `maxLevel`; maxLevel only on the platform router | closed |
| T-81-36 | Elevation of Privilege | API key approving or clearing a stop | high | mitigate | _require_interactive_session on every non-press write; api_key probe cases per route (PROH-81-10). Evidence: `_require_interactive_session` on every non-press write; API-key probe cases | closed |
| T-81-37 | Information Disclosure | cross-tenant read through tenantId | high | mitigate | resolve_tenant honours tenantId only for platform owner/support; tenant roles get 403 on a foreign id; explicit tenantId on every query. Evidence: `views.resolve_tenant` honours `tenantId` only for platform owner/support | closed |
| T-81-38 | Information Disclosure | platform staff names in platform stop records | medium | mitigate | display_actor masks to "Platform administrator" for tenant viewers (D-25, PROH-81-11). Evidence: `display_actor` masks to "Platform administrator" for tenant viewers | closed |
| T-81-39 | Elevation of Privilege | Platform Support acting on a tenant | high | mitigate | Guard write requires manage/control (support holds neither); resolve_tenant refuses write for support; matrix test (PROH-81-15). Evidence: support holds neither manage nor control; write refused; matrix test | closed |
| T-81-40 | Denial of Service | unbounded list or never-touch growth | low | mitigate | limit 1..100, cursor pagination, 500-entry cap, reason and note length bounds. Evidence: limit 1..100, cursor paging, 500-entry cap, reason/note bounds | closed |
| T-81-41 | Denial of Service | stop routes silently missing after an import error | medium | mitigate | Both routers in _REQUIRED_ROUTERS so startup fails fast. Evidence: both routers in `_REQUIRED_ROUTERS` (`router_registry.py`) | closed |
| T-81-42 | Elevation of Privilege | client-side resume decision | medium | mitigate | Resume rendered from server canResume; the server re-checks (81-09); the client never derives authority. Evidence: Resume rendered from the server's `canResume` | closed |
| T-81-43 | Repudiation | hidden or dismissible stop | medium | mitigate | Banner non-dismissible, shown for every view:autonomous_ops holder on every screen (D-15, PROH-81-14). Evidence: banner has no dismiss control; test | closed |
| T-81-44 | Tampering | reason text rendered in banner/dialogs (XSS) | medium | mitigate | React text only, no dangerouslySetInnerHTML, maxLength 500 client side plus server validation. Evidence: React text only, `maxLength` 500 plus server validation | closed |
| T-81-45 | Information Disclosure | platform staff names | low | mitigate | Client renders the server's by value, which 81-09 masks for tenant viewers (D-25). Evidence: client renders the server's masked `by` | closed |
| T-81-46 | Denial of Service | rate-limit notice | low | mitigate | One notice per window through the rateLimitNotifiedAt marker; notify never raises, so a failing notice cannot block a decision. Evidence: `rateLimitNotifiedAt` once-per-window marker; `notify` never raises | closed |
| T-81-47 | Elevation of Privilege | dedupe and cooldown bypass by repeated sweeps | medium | mitigate | Unique partial index open_dedupe plus shadow and undone cooldown checks; duplicate key caught as refuse duplicate; adjacency edge tests. Evidence: `open_dedupe` unique partial index, `DuplicateKeyError` → refuse duplicate | closed |
| T-81-48 | Tampering | migration 024 overwriting a tenant's chosen level | medium | mitigate | ensure_tenant uses $setOnInsert only; idempotency and keeps-existing-level tests; platform-admin stored off/off. Evidence: `ensure_tenant` uses `$setOnInsert`; idempotency and keeps-level tests | closed |
| T-81-49 | Denial of Service | creation hook failure blocking sign-up or Add Tenant | low | mitigate | try/except with a logged warning; failure-tolerated test; startup ensure_all_tenants backstop (81-04). Evidence: creation hooks in try/except; failure-tolerated tests; startup backstop | closed |
| T-81-SC | Tampering | npm/pip/cargo installs | low | accept | No packages are installed by this plan (hypothesis deliberately not added; psutil and ipaddress already available) (see AR-81-01) | closed |

*Status: open · closed · open — below high threshold (non-blocking)*
*Severity: critical > high > medium > low — only open threats at or above workflow.security_block_on count toward threats_open*
*Disposition: mitigate (implementation required) · accept (documented risk) · transfer (third-party)*

---

## Accepted Risks Log

| Risk ID | Threat Ref | Rationale | Accepted By | Date |
|---------|------------|-----------|-------------|------|
| AR-81-01 | T-81-SC | No npm, pip or cargo package was added by any Phase 81 plan; cargo ran `--offline` against the existing lockfile. Accepted in every plan's threat model at plan time. | plan-time threat model (81-01..81-12) | 2026-10-25 |

*Accepted risks do not resurface in future audit runs.*

### Residual notes (outside the register; recorded for later phases)

- A delivered instruction that never reports a result keeps its decision row `dispatching` (81-04 covers only undelivered `pending`/`queued` instructions).
- A poll that has already fetched an instruction can still return it if a stop lands inside that single request (81-05, accepted race).
- The backend host's interface subnets (10.0.0.0/24 on this VM) are built-in never-touch entries, so an endpoint on that subnet can never be an automatic target (81-11, by design per D-19).
- `trigger_threat_hunt` and `prestage_kill_chain_defenses` (correlation_engine_threat.py) still write unstamped `agent_instructions`; they are on the structural test's grandfathered list (81-06, 81-08).

---

## Security Audit Trail

| Audit Date | Threats Total | Closed | Open | Run By |
|------------|---------------|--------|------|--------|
| 2026-10-26 | 50 | 50 | 0 | secure-phase (orchestrator, L1 grep verification) |

---

## Sign-Off

- [x] All threats have a disposition (mitigate / accept / transfer)
- [x] Accepted risks documented in Accepted Risks Log
- [x] `threats_open: 0` confirmed
- [x] `status: verified` set in frontmatter

**Approval:** verified 2026-10-26
