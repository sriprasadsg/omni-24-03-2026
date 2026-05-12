# Enterprise Omni-Agent AI Platform — Master Test Document
**Version:** 2026.04  
**Tester:** ___________________  
**Date:** ___________________  
**Backend URL:** `http://localhost:5000`  
**Frontend URL:** `http://localhost:3000`

---

## How to Use This Document

- Run each test case in sequence.
- Mark **Pass ✅ / Fail ❌ / Partial ⚠️** in the Status column.
- Score each case 0–10 in the Rating column (0 = broken, 10 = perfect).
- **Section Score** = average of all ratings in that section.
- **Overall Score** = average of all section scores.

---

## Pre-flight Checklist

| # | Check | Command / URL | Pass/Fail |
|---|-------|--------------|-----------|
| P1 | Backend starts without errors | `python run_backend.py` | |
| P2 | MongoDB connection healthy | `GET /api/health` → `status: ok` | |
| P3 | Frontend compiles without errors | `npm run dev` | |
| P4 | Super admin login works | `POST /api/auth/login` (super@omni.ai) | |
| P5 | WebSocket endpoint reachable | Browser console shows no WS errors | |
| P6 | At least one active tenant exists | `GET /api/tenants` | |

---

## Section 1 — Authentication & Authorization
**Expected baseline score: 9/10**

| ID | Test Case | Steps | Expected Result | Status | Rating (0–10) |
|----|-----------|-------|-----------------|--------|--------------|
| A1 | Super admin login | POST `/api/auth/login` `{ email:"super@omni.ai", password:"password123" }` | 200 + `access_token` JWT | | |
| A2 | JWT token contains required claims | Decode returned JWT | Must contain `sub`, `role`, `tenant_id`, `jti`, `exp` | | |
| A3 | Token expiry enforced | Wait 61 min (or manually set `exp` to past), call `/api/me` | 401 Unauthorized | | |
| A4 | Refresh token flow | POST `/api/auth/refresh` with valid refresh_token | 200 + new `access_token` | | |
| A5 | Token revocation (logout) | POST `/api/auth/logout` → retry `/api/me` with old token | 401 on retry | | |
| A6 | Wrong password rejected | POST `/api/auth/login` with wrong password | 401 with "Invalid credentials" | | |
| A7 | Tenant isolation enforced | Login as Tenant A user → call `/api/playbooks` | Only Tenant A playbooks returned | | |
| A8 | Admin bypass works | Super Admin calls same endpoint | All tenant playbooks returned | | |
| A9 | Create new tenant user | POST `/api/users` as Super Admin | 201 + user doc with tenant scoped | | |
| A10 | Cross-tenant access blocked | Tenant A user tries to read Tenant B's agent | 404 (not leaked as 403) | | |
| A11 | RBAC: viewer cannot mutate | Login as Viewer role → DELETE `/api/playbooks/:id` | 403 Forbidden | | |
| A12 | MFA enrollment (if enabled) | POST `/api/mfa/setup` | 200 + QR code data URI | | |

**Section 1 Score: ___/10**

---

## Section 2 — Agent Management (EDR Fleet)
**Expected baseline score: 8/10**

| ID | Test Case | Steps | Expected Result | Status | Rating |
|----|-----------|-------|-----------------|--------|--------|
| B1 | Register a new agent | POST `/api/agents/register` `{agent_id, hostname, tenant_id}` | 200 + `api_key` JWT | | |
| B2 | Agent JWT contains jti | Decode agent token | `jti` UUID claim present | | |
| B3 | Agent heartbeat accepted | POST `/api/agents/:id/heartbeat` with agent token | 200 + `status: ok` | | |
| B4 | Stale agent marked Offline | Stop heartbeat for 15 min (or set lastSeen past threshold) | Agent status → Offline in DB | | |
| B5 | Agent key revocation | POST `/api/agents/:id/revoke-key` → retry heartbeat | 401 Unauthorized | | |
| B6 | List agents (fleet view) | GET `/api/agents` | Paginated list with health metrics | | |
| B7 | Get single agent detail | GET `/api/agents/:id` | Full agent doc with capabilities list | | |
| B8 | Agent install instructions | GET `/api/agents/install/:tenant_id` | Returns install script / token | | |
| B9 | Agent capability management | POST `/api/agents/:id/capabilities` `{enable:["yara_scan"]}` | Capability list updated | | |
| B10 | Remote shell WebSocket | WS `ws://localhost:8000/ws/remote/:agent_id` → send "ls" | Echo or command response | | |
| B11 | Fleet summary stats | GET `/api/agents/stats` | `{online, offline, total}` counts | | |
| B12 | Agent integrity verify | POST `/api/agents/:id/verify-integrity` | 200 + hash validation result | | |

**Section 2 Score: ___/10**

---

## Section 3 — EDR: Runtime Security & YARA
**Expected baseline score: 8/10**

| ID | Test Case | Steps | Expected Result | Status | Rating |
|----|-----------|-------|-----------------|--------|--------|
| C1 | Runtime security collect | Import + call `RuntimeSecurityCapability().collect()` | Dict with `processes`, `connections`, `suspicious_activities` | | |
| C2 | YARA scanner loads | `from agent.capabilities.yara_scanner import get_yara_scanner; s = get_yara_scanner()` | No exception; `s._yara_available` is bool | | |
| C3 | YARA rule files present | Check `agent/capabilities/yara_rules/*.yar` | 3 files present (ransomware, credential_dumpers, injectors) | | |
| C4 | String-match: Mimikatz name | `scanner.scan_string("mimikatz.exe")` | Returns match with `rule:"MimikatzSignatures"`, `severity:"critical"` | | |
| C5 | String-match: ransomware note | `scanner.scan_string("your files have been encrypted send bitcoin")` | Returns `rule:"RansomwareGeneric"` | | |
| C6 | String-match: clean process | `scanner.scan_string("chrome.exe")` | Empty list (no false positive) | | |
| C7 | File scan returns results | Create temp file with "mimikatz" text → `scanner.scan_file(path)` | Match returned | | |
| C8 | YARA match in collect() output | Run collect() when mimikatz-named process hypothetically exists | suspicious_activities includes YARA match entry | | |
| C9 | Auto-kill critical process | Set `auto_kill_critical=True`, run collect() with critical PID | `auto_killed: True` in result (PID must exist) | | |
| C10 | FIM baseline persists | `FIMCapability().collect()` twice | Second run loads baseline from disk, no "starting fresh" log | | |
| C11 | FIM violation detected | Modify a monitored file between two collect() runs | Violation entry with `previous_checksum ≠ current_checksum` | | |
| C12 | EDR telemetry endpoint | GET `/api/edr/telemetry` | 200 + process/connection data | | |

**Section 3 Score: ___/10**

---

## Section 4 — XDR: Correlation Engine & Attack Patterns
**Expected baseline score: 8/10**

| ID | Test Case | Steps | Expected Result | Status | Rating |
|----|-----------|-------|-----------------|--------|--------|
| D1 | Correlate events (API) | POST `/api/correlations/analyze` `{tenant_id, time_window_minutes:60}` | 200 + list of correlations (may be empty if no events) | | |
| D2 | Correlation stats | GET `/api/correlations/stats?tenant_id=X` | `{high:N, critical:N, ...}` | | |
| D3 | List attack patterns | GET `/api/correlations/patterns/list` | 7 patterns including new `defense_evasion`, `command_and_control` | | |
| D4 | Create custom pattern (API) | PUT `/api/correlations/patterns/custom_test` `{name:"Test",events:["test_event"],threshold:1,time_window_minutes:5}` | 200 + `status:upserted` | | |
| D5 | Custom pattern appears in list | GET `/api/correlations/patterns/list` | `custom_test` present with `source:"custom"` | | |
| D6 | Disable a pattern | PATCH `/api/correlations/patterns/custom_test/disable` | 200 + `status:disabled` | | |
| D7 | Delete custom pattern | DELETE `/api/correlations/patterns/custom_test` | 200 + `status:deleted` | | |
| D8 | Delete builtin rejected | DELETE `/api/correlations/patterns/ransomware` | 400 "is a builtin pattern" | | |
| D9 | DB patterns override builtins | Insert doc in `signature_library` with `pattern_id:"credential_access"`, `threshold:99` → restart engine → correlate | Engine uses threshold 99 | | |
| D10 | Builtins MITRE tagged | Check pattern list | All builtin patterns have non-empty `mitre` field | | |
| D11 | Ransomware event triggers correlation | Insert `{event_type:"ransomware_detected", tenant_id}` in security_events → run correlation | `ransomware` pattern fires | | |
| D12 | Correlation auto-triggers playbook | A playbook with `trigger_type:"correlation"` exists → run D11 | Playbook execution logged | | |
| D13 | Manual correlation run | POST `/api/correlations/run` | `{triggered_by:"manual", correlations_found:N}` | | |
| D14 | Mark false positive | POST `/api/correlations/false-positive/:id` | Correlation doc gains `false_positive:true` | | |

**Section 4 Score: ___/10**

---

## Section 5 — Threat Intelligence & IOC Feed Sync
**Expected baseline score: 7/10**

| ID | Test Case | Steps | Expected Result | Status | Rating |
|----|-----------|-------|-----------------|--------|--------|
| E1 | Threat feed loop starts | Check app startup logs | "[ThreatFeed] Background loop started" message | | |
| E2 | URLhaus fetch works | `await _fetch_urlhaus(session)` directly | Non-empty list of IOC dicts with `ioc_type:"url"` | | |
| E3 | MalwareBazaar fetch works | `await _fetch_malwarebazaar(session)` directly | Non-empty list with `ioc_type:"hash"`, `sha256` values | | |
| E4 | IOCs upserted to DB | Check `edr_ioc` collection after startup | Documents present with `source_feed` field | | |
| E5 | Signature library version record | Check `signature_library` collection | Document with `version_type:"threat_feed"`, `synced_at`, `source_counts` | | |
| E6 | OTX disabled without key | Run sync without `OTX_API_KEY` set | OTX count = 0, no error thrown | | |
| E7 | OTX enabled with key | Set `OTX_API_KEY=test` (invalid) → run sync | Warning logged, gracefully returns empty list | | |
| E8 | Max IOC limit respected | `MAX_PER_SOURCE=5` env → run URLhaus fetch | Returns ≤ 5 IOCs | | |
| E9 | IOC upsert idempotent | Run sync twice → check `edr_ioc` count | Count same after second run (no duplicates) | | |
| E10 | Manual scan endpoint | POST `/api/threat-intel/scan` `{artifact:"1.2.3.4", artifact_type:"ip", tenant_id:"X"}` | 200 + verdict + detection_ratio | | |
| E11 | Threat feed endpoint | GET `/api/threat-intel/feed` | List of past scans sorted by created_at desc | | |
| E12 | Enrich security event | POST `/api/threat-intel/enrich-security-event?event_id=X` | 200 + enrichments added to event doc | | |
| E13 | UEBA IOC lookup (dual schema) | Insert IOC with `source_ip` field → run UEBA on matching IP | IOC matched via `$or` query | | |

**Section 5 Score: ___/10**

---

## Section 6 — MDR: Playbooks & Autonomous Response
**Expected baseline score: 9/10**

| ID | Test Case | Steps | Expected Result | Status | Rating |
|----|-----------|-------|-----------------|--------|--------|
| F1 | List playbooks (tenant-scoped) | GET `/api/playbooks` as Tenant A user | Only Tenant A + platform playbooks | | |
| F2 | Create playbook | POST `/api/playbooks/create` `{name, description, trigger, steps:[]}` | 201 + `id` | | |
| F3 | Get single playbook | GET `/api/playbooks/:id` | Full playbook doc | | |
| F4 | Cross-tenant access blocked | Tenant A user GET Tenant B's playbook ID | 404 | | |
| F5 | Toggle playbook on/off | PATCH `/api/playbooks/:id/toggle` | `enabled` flips; message reflects new state | | |
| F6 | Execute playbook | POST `/api/playbooks/:id/execute` `{context:{}}` | 200 + execution result with steps | | |
| F7 | Execute cross-tenant blocked | Tenant A user executes Tenant B's playbook | 403 | | |
| F8 | tenant_id from token only | Execute playbook with `{context:{tenant_id:"evil"}}` | Actual `tenant_id` comes from token, not request | | |
| F9 | Delete playbook | DELETE `/api/playbooks/:id` | 200 + `message: deleted` | | |
| F10 | Delete cross-tenant blocked | Tenant A user deletes Tenant B's playbook | 403 | | |
| F11 | Enhanced playbook: conditions | Create enhanced playbook with `if/else` step → execute | Correct branch executed based on condition | | |
| F12 | Enhanced playbook: approval gate | Create playbook with approval step → execute | Execution pauses, waiting for approval | | |
| F13 | Approval grant continues playbook | POST `/api/approvals/:id/approve` | Playbook resumes and completes remaining steps | | |
| F14 | Approval timeout | Set short timeout → wait → check | Playbook auto-advances per timeout processor (60s check) | | |
| F15 | XDR seed playbooks exist | GET `/api/playbooks` | "XDR: Ransomware Lockdown" and similar auto-seeded playbooks present | | |

**Section 6 Score: ___/10**

---

## Section 7 — SIEM: Security Events & Cases
**Expected baseline score: 8/10**

| ID | Test Case | Steps | Expected Result | Status | Rating |
|----|-----------|-------|-----------------|--------|--------|
| G1 | Create security event | POST `/api/security-events` `{event_type, source_ip, severity, tenant_id}` | 201 + event doc | | |
| G2 | List events (tenant-scoped) | GET `/api/security-events` | Only caller's tenant events | | |
| G3 | Filter by severity | GET `/api/security-events?severity=critical` | Only critical events | | |
| G4 | Create security case | POST `/api/security-cases` `{title, severity, description}` | 201 + case with `case_id` | | |
| G5 | Update case (own tenant) | PUT `/api/security-cases/:id` with Tenant A credentials | 200 + updated doc | | |
| G6 | Update cross-tenant blocked | Tenant A tries to update Tenant B's case | 403 or 404 | | |
| G7 | List cases (tenant-scoped) | GET `/api/security-cases` | Only caller's tenant cases | | |
| G8 | Generate encryption keypair | POST `/api/security/generate-keypair` as admin | `{public_key, private_key, key_id}` — private key PEM in response | | |
| G9 | Keypair admin-only | POST `/api/security/generate-keypair` as non-admin | 403 | | |
| G10 | Audit log (tenant-scoped) | GET `/api/security/audit-log` | Only caller's tenant audit entries | | |
| G11 | Incident impact (own tenant) | GET `/api/security/incident-impact/:id` | Real DB data for matching incident | | |
| G12 | Incident impact cross-tenant | Tenant A fetches Tenant B's incident impact | 403 or 404 | | |
| G13 | Vulnerability scan list | GET `/api/vulnerability-scans` | Tenant-scoped list | | |
| G14 | Security dashboard loads | Open `/security` in browser | No console errors, cards render | | |

**Section 7 Score: ___/10**

---

## Section 8 — UEBA: User & Entity Behavior Analytics
**Expected baseline score: 7/10**

| ID | Test Case | Steps | Expected Result | Status | Rating |
|----|-----------|-------|-----------------|--------|--------|
| H1 | UEBA analyze event | POST `/api/ueba/analyze` `{user_id, event_type:"login", ip_address:"1.2.3.4"}` | 200 + `{risk_score, flags, recommendations}` | | |
| H2 | Shadow AI detection | POST with `event_type:"api_call"` to known AI provider IP | Risk flag "shadow_ai_detected" | | |
| H3 | Impossible travel detection | Two logins from distant geos within 1 hour | Flag "impossible_travel" with distance | | |
| H4 | Off-hours login flag | Login at 3AM local time | Flag "off_hours_access" | | |
| H5 | IOC match on IP | Insert IOC for test IP → analyze event with that IP | Flag "ioc_match" with threat type | | |
| H6 | IOC match via source_ip field | Insert IOC with `source_ip` field (new schema) → analyze | Match returned (dual-schema `$or` query works) | | |
| H7 | Risk score aggregation | GET `/api/ueba/risk-scores?tenant_id=X` | Sorted list of user risk scores | | |
| H8 | UEBA alerts list | GET `/api/ueba/alerts` | Tenant-scoped anomaly alerts | | |
| H9 | Shadow AI dashboard | Open `/shadow-ai` in browser | Component renders, UEBA data loads | | |

**Section 8 Score: ___/10**

---

## Section 9 — Compliance & AI Governance
**Expected baseline score: 8/10**

| ID | Test Case | Steps | Expected Result | Status | Rating |
|----|-----------|-------|-----------------|--------|--------|
| I1 | List compliance frameworks | GET `/api/compliance` | SOC2, ISO27001, NIST etc. | | |
| I2 | Create compliance evidence | POST `/api/compliance/evidence` | 201 + evidence doc | | |
| I3 | AI governance: list models | GET `/api/ai-governance/models` | Registered models list | | |
| I4 | AI governance: evaluate policy | POST `/api/ai-governance/evaluate` `{model_id, action}` | 200 + `allowed: true/false` | | |
| I5 | AI governance: ast.literal_eval safe | Policy condition `"risk_level in ['low','medium']"` with `risk_level:"high"` | Not allowed, no RCE | | |
| I6 | AI governance: reject code injection | Policy condition `"__import__('os').system('id') in []"` | ValueError / rejected safely | | |
| I7 | Compliance automation trigger | POST `/api/compliance-automation/run` `{framework_id}` | Automation steps executed | | |
| I8 | Risk management: create risk | POST `/api/risks` `{title, severity, category}` | 201 + risk doc with ID | | |
| I9 | Risk management: list risks | GET `/api/risks` | Tenant-scoped risks list | | |
| I10 | CISSP Oracle query | POST `/api/cissp/query` `{question:"What is defense in depth?"}` | Structured security recommendation | | |
| I11 | AI governance dashboard | Open `/ai-governance` in browser | Component renders, metrics visible | | |

**Section 9 Score: ___/10**

---

## Section 10 — Agentic AI Core (Reasoning & Decision Loop)
**Expected baseline score: 7/10**

| ID | Test Case | Steps | Expected Result | Status | Rating |
|----|-----------|-------|-----------------|--------|--------|
| J1 | Agent autonomous decision | POST `/api/agents/:id/decide` `{context:{cpu_usage:95}}` | Returns `{action, confidence, reasoning}` | | |
| J2 | Safety module blocks dangerous action | Submit context where safety would block (e.g., delete_all) | Response contains `blocked:true`, `reason` | | |
| J3 | Goal system: failing goal triggers plan | Set goal `{cpu_under_80, current:95}` → evaluate | `generate_strategic_plan` called, plan returned | | |
| J4 | Memory: store experience | `AgentMemory().store_experience(ctx, action, outcome)` | `agent_memory.json` updated with new entry | | |
| J5 | Memory: retrieve similar | Store experience → `find_similar_situations(same_ctx)` | Top-5 similar experiences returned | | |
| J6 | Memory: Jaccard fallback | Ensure Ollama not running → `find_similar_situations` | Jaccard similarity used (log says "Jaccard") | | |
| J7 | Memory: cap at 1000 entries | Add 1001 experiences | Only last 1000 kept | | |
| J8 | Predictive health: collect | `PredictiveHealthCapability().collect()` | `{current_score, predictions, warnings, anomalies}` with 12-step forecast | | |
| J9 | Predictive health: forecast values | Run collect() 10+ times (build history) | `predictions` list has 12 entries with timestamps | | |
| J10 | Predictive health: config thresholds | Set `config={mem_restart_threshold:80}` → collect() 6 times at 85% mem | `remediation.action = "restart_agent"` | | |
| J11 | Remediation: baseline avoids false alert | System normally at 85% mem → collect with 87% | No restart recommended (within 10% of baseline) | | |
| J12 | LLM engine: provider dispatch | Set `provider=backend` → `plan_remediation(ctx)` | Calls `_query_backend()`, returns JSON plan | | |
| J13 | Swarm coordinator | GET `/api/swarm/topology` | Real nodes/links from DB agents | | |

**Section 10 Score: ___/10**

---

## Section 11 — FinOps & Cost Management
**Expected baseline score: 8/10**

| ID | Test Case | Steps | Expected Result | Status | Rating |
|----|-----------|-------|-----------------|--------|--------|
| K1 | Get tenant cost summary | GET `/api/finops/costs?tenant_id=X` | `{total_spend, by_service, trend}` | | |
| K2 | Cost history 30 days | GET `/api/finops/costs/history?tenant_id=X&days=30` | Array of 30 daily cost entries (zero-filled) | | |
| K3 | Recalculate tenant costs | POST `/api/finops/recalculate?tenant_id=X` | Updated cost document with real usage | | |
| K4 | Service pricing catalog | GET `/api/finops/pricing` | 30+ services with unit prices | | |
| K5 | Budget alert threshold | Set budget 100 → spend 110 → check | Alert flag on response | | |
| K6 | FinOps dashboard renders | Open `/finops` in browser | Charts load, no console errors | | |
| K7 | Invoice generation | POST `/api/billing/invoice?tenant_id=X` | PDF or JSON invoice returned | | |

**Section 11 Score: ___/10**

---

## Section 12 — AI Chat & LLM Proxy
**Expected baseline score: 7/10**

| ID | Test Case | Steps | Expected Result | Status | Rating |
|----|-----------|-------|-----------------|--------|--------|
| L1 | AI chat: basic message | POST `/api/ai/chat` `{message:"What is XDR?"}` | Non-empty response text | | |
| L2 | AI chat: provider Gemini | Set `GEMINI_API_KEY` → send message | Response from Gemini (not mock) | | |
| L3 | AI chat: Ollama fallback | Unset Gemini key, start Ollama → send message | Response from Ollama | | |
| L4 | AI chat: safety guardrail | Send prompt containing harmful content | Blocked or sanitized response | | |
| L5 | LLM proxy: forward request | POST `/api/llm-proxy` `{provider:"gemini", prompt:"hello"}` | Proxied response | | |
| L6 | AI analysis of alert | POST `/api/ai/analyze-alert` `{alert_id}` | AI-generated severity + remediation | | |
| L7 | Streaming response | GET `/api/ai/stream?query=test` (SSE) | Server-sent events stream | | |
| L8 | Prompt library: list | GET `/api/prompts` | Saved prompt templates | | |
| L9 | AI chat renders in browser | Open `/ai` page | Chat interface renders, sends message | | |

**Section 12 Score: ___/10**

---

## Section 13 — Patch & Software Management
**Expected baseline score: 8/10**

| ID | Test Case | Steps | Expected Result | Status | Rating |
|----|-----------|-------|-----------------|--------|--------|
| M1 | List patches | GET `/api/patches` | CVE-tagged patch list | | |
| M2 | Deploy patch to agent | POST `/api/patches/:id/deploy` `{agent_ids:[...]}` | Deployment job created | | |
| M3 | Patch job status | GET `/api/patches/jobs/:job_id` | `{status, progress, target_agents}` | | |
| M4 | Rollback patch | POST `/api/patches/:id/rollback` | Rollback action dispatched to agent | | |
| M5 | SBOM generate | POST `/api/sboms/generate` `{agent_id}` | SBOM document in CycloneDX/SPDX format | | |
| M6 | SBOM list | GET `/api/sboms` | Tenant-scoped SBOM list | | |
| M7 | Software deployment | POST `/api/software/deploy` `{package, agent_ids:[...]}` | Job created with installation steps | | |
| M8 | Software deployment UI | Open `/software-deployment` | Component renders, agents selectable | | |

**Section 13 Score: ___/10**

---

## Section 14 — Cloud Security & Infrastructure
**Expected baseline score: 7/10**

| ID | Test Case | Steps | Expected Result | Status | Rating |
|----|-----------|-------|-----------------|--------|--------|
| N1 | Add cloud account | POST `/api/cloud-accounts` `{provider:"aws", credentials:{}}` | 201 + account doc | | |
| N2 | Cloud posture scan | POST `/api/cloud-accounts/:id/scan` | Misconfigurations returned | | |
| N3 | Cloud remediation | POST `/api/cloud/remediation/:finding_id` | Remediation dispatched | | |
| N4 | Network device discovery | GET `/api/network-devices` | Network topology data | | |
| N5 | Network topology map | Open `/network-map` in browser | D3 or similar graph renders | | |
| N6 | Zero trust policy check | POST `/api/zero-trust/verify` `{user_id, resource, action}` | Allow/Deny decision | | |

**Section 14 Score: ___/10**

---

## Section 15 — Observability & Monitoring
**Expected baseline score: 8/10**

| ID | Test Case | Steps | Expected Result | Status | Rating |
|----|-----------|-------|-----------------|--------|--------|
| O1 | System health check | GET `/api/health` | `{status, services:{mongodb, redis, ...}}` | | |
| O2 | Agent metrics | GET `/api/agents/:id/metrics` | `{cpu, memory, disk, network}` time-series | | |
| O3 | Log query | GET `/api/logs?query=error&tenant_id=X` | Matching log entries | | |
| O4 | APM traces | GET `/api/apm/traces` | Span list with latency data | | |
| O5 | Distributed tracing | GET `/api/tracing/spans` | End-to-end trace data | | |
| O6 | ML model drift | GET `/api/ml-monitoring/drift` | Drift scores per model | | |
| O7 | Streaming dashboard | Open `/streaming-dashboard` in browser | Real-time WebSocket data flows in | | |
| O8 | Streaming WS URL resolves | Check browser network tab | WS connects to `VITE_WS_URL` or same-origin | | |
| O9 | Analytics dashboard | GET `/api/analytics/events?tenant_id=X` | Event counts by type/time | | |

**Section 15 Score: ___/10**

---

## Section 16 — RBAC (Role-Based Access Control)
**Expected baseline score: 9/10**

| ID | Test Case | Steps | Expected Result | Status | Rating |
|----|-----------|-------|-----------------|--------|--------|
| Q1 | List roles | GET `/api/roles` | Built-in roles incl. Super Admin, Tenant Admin, Viewer | | |
| Q2 | Create custom role | POST `/api/roles` `{name:"Analyst", permissions:["view:security"]}` | 201 + role doc | | |
| Q3 | Assign role to user | PUT `/api/users/:id/role` `{role:"Analyst"}` | User doc updated | | |
| Q4 | Permission check: viewer can view | Login as Viewer → GET `/api/security-events` | 200 | | |
| Q5 | Permission check: viewer cannot manage | Login as Viewer → DELETE `/api/security-events/:id` | 403 | | |
| Q6 | Super Admin has all permissions | Super Admin calls any endpoint | Always 200/201 | | |
| Q7 | Tenant Admin scoped to own tenant | Tenant Admin reads agents | Only own tenant agents | | |
| Q8 | Permission list on token | Decode JWT | `permissions` array reflects assigned role | | |

**Section 16 Score: ___/10**

---

## Section 17 — DevSecOps & SBOM
**Expected baseline score: 6/10**

| ID | Test Case | Steps | Expected Result | Status | Rating |
|----|-----------|-------|-----------------|--------|--------|
| R1 | SAST scan trigger | POST `/api/sast/scan` `{repo_url, branch}` | Job ID returned | | |
| R2 | DAST scan trigger | POST `/api/dast/scan` `{target_url}` | Job ID returned | | |
| R3 | DevSecOps pipeline view | GET `/api/devsecops/pipelines` | Pipeline run list | | |
| R4 | Supply chain scan | POST `/api/supply-chain/scan` `{artifact}` | Risk assessment returned | | |
| R5 | SBOM fetch (service) | GET `/api/sboms/:id` | CycloneDX JSON document | | |

**Section 17 Score: ___/10**

---

## Section 18 — UI/Frontend Integration
**Expected baseline score: 7/10**

| ID | Test Case | Steps | Expected Result | Status | Rating |
|----|-----------|-------|-----------------|--------|--------|
| S1 | Login page | Open `/login` | Form renders, login works | | |
| S2 | Sidebar navigation | Click each sidebar item | Correct component loads, no 404 | | |
| S3 | Security Dashboard | `/security-dashboard` | Threat counts, recent alerts visible | | |
| S4 | Playbook Manager | `/playbooks` | List loads, create/delete work | | |
| S5 | Agent Capabilities Dashboard | `/agent-capabilities` | Capability toggles render | | |
| S6 | EDR Dashboard | `/edr` | Process list, connection list render | | |
| S7 | Model Training Dashboard | `/model-training` | Training metrics visible | | |
| S8 | Network Topology Map | `/network-map` | Graph renders with nodes/links | | |
| S9 | Remote Terminal | `/remote-terminal` | WebSocket connects, input accepted | | |
| S10 | Remote Desktop | `/remote-desktop` | VNC/screen share component loads | | |
| S11 | Service Pricing Page | `/pricing` | 30+ services with prices listed | | |
| S12 | Tenant Branding Settings | `/branding` | Logo upload, color picker work | | |
| S13 | Unified FutureOps Dashboard | `/futureops` | KPIs, predictions, health scores | | |
| S14 | MDR Dashboard | `/mdr` | Response policies list, status | | |
| S15 | XDR Dashboard | `/xdr` | Correlation events, pattern coverage | | |
| S16 | CISSP Oracle | `/cissp-oracle` | Query input, framework output | | |
| S17 | Shadow AI | `/shadow-ai` | Detected shadow AI apps listed | | |
| S18 | Streaming Dashboard WS | `/streaming` | Live feed updating in real-time | | |

**Section 18 Score: ___/10**

---

## Section 19 — Security Hardening & Edge Cases
**Expected baseline score: 8/10**

| ID | Test Case | Steps | Expected Result | Status | Rating |
|----|-----------|-------|-----------------|--------|--------|
| T1 | SQL/NoSQL injection in search | GET `/api/security-events?severity[$gt]=` | No MongoDB operator injection; sanitized | | |
| T2 | Path traversal in file ops | Any endpoint accepting path params with `../` | Rejected or resolved safely | | |
| T3 | JWT none algorithm | Send JWT with `alg:none` | 401 rejected | | |
| T4 | Expired JWT rejected | Manually set exp=0 in token | 401 | | |
| T5 | Large payload rejected | POST with 100MB body | 413 or connection reset | | |
| T6 | CORS: allowed origin | Frontend origin → API call | 200 with correct CORS headers | | |
| T7 | CORS: unknown origin | `Origin: https://evil.com` → API call | No `Access-Control-Allow-Origin: https://evil.com` | | |
| T8 | Private key not in DB plaintext | After keypair generation, query `security_keys` collection | Only encrypted blob stored, no PEM text | | |
| T9 | Agent token jti revocation | Revoke agent → attempt API call with old token | 401 | | |
| T10 | eval() not callable in AI governance | Policy with `eval("__import__('os')")` | Exception, not execution | | |

**Section 19 Score: ___/10**

---

## Section 20 — Background Services & Schedulers
**Expected baseline score: 8/10**

| ID | Test Case | Steps | Expected Result | Status | Rating |
|----|-----------|-------|-----------------|--------|--------|
| U1 | Agent monitor heartbeat | Check logs after 60 sec | "[Monitor] Marked N stale agents as Offline" (if any stale) | | |
| U2 | XDR scanner fires every 5 min | Wait 5 min → check logs | "XDR: N correlation(s) for tenant X" or no-op | | |
| U3 | Approval timeout processor | Check logs after 60 sec | Approval timeout processor ran | | |
| U4 | Threat feed sync on startup | Check startup logs | "[ThreatFeed] Sync complete" within ~60 sec of start | | |
| U5 | Threat feed interval 6h | Check `signature_library` timestamps | Two consecutive entries ~6h apart (or env override) | | |
| U6 | FinOps scheduler | Check logs | FinOps scheduler "started" message | | |
| U7 | Deployment scheduler | Check logs | Deployment scheduler "started" message | | |
| U8 | XDR playbooks seeded | GET `/api/playbooks` after startup | Platform-level XDR playbooks present | | |
| U9 | Response policies seeded | GET `/api/response/policies` after startup | Builtin policies (auto-kill-mimikatz etc.) present | | |
| U10 | Correlation patterns reload | Insert new pattern in DB → wait for next cycle | Engine uses new pattern (log shows reload) | | |

**Section 20 Score: ___/10**

---

## Final Score Sheet

| # | Section | Max | Your Score | % |
|---|---------|-----|-----------|---|
| 1 | Authentication & Authorization | 10 | | |
| 2 | Agent Management (EDR Fleet) | 10 | | |
| 3 | EDR: Runtime Security & YARA | 10 | | |
| 4 | XDR: Correlation Engine & Patterns | 10 | | |
| 5 | Threat Intelligence & IOC Feed Sync | 10 | | |
| 6 | MDR: Playbooks & Autonomous Response | 10 | | |
| 7 | SIEM: Security Events & Cases | 10 | | |
| 8 | UEBA: Behavior Analytics | 10 | | |
| 9 | Compliance & AI Governance | 10 | | |
| 10 | Agentic AI Core | 10 | | |
| 11 | FinOps & Cost Management | 10 | | |
| 12 | AI Chat & LLM Proxy | 10 | | |
| 13 | Patch & Software Management | 10 | | |
| 14 | Cloud Security & Infrastructure | 10 | | |
| 15 | Observability & Monitoring | 10 | | |
| 16 | RBAC | 10 | | |
| 17 | DevSecOps & SBOM | 10 | | |
| 18 | UI/Frontend Integration | 10 | | |
| 19 | Security Hardening & Edge Cases | 10 | | |
| 20 | Background Services & Schedulers | 10 | | |
| | **OVERALL TOTAL** | **200** | | |

**Overall Percentage: ____%**

---

## Rating Interpretation

| Score | Grade | Meaning |
|-------|-------|---------|
| 9.0–10.0 | A+ | Production-ready, no issues |
| 8.0–8.9 | A | Production-ready, minor gaps |
| 7.0–7.9 | B | Mostly working, some stubs |
| 6.0–6.9 | C | Core works, significant gaps |
| 5.0–5.9 | D | Partially working |
| < 5.0 | F | Broken / not implemented |

---

## Known Gaps (Pre-Test)

The following items are known partial implementations and will score lower by design:

| Area | Gap | Expected Impact |
|------|-----|-----------------|
| Remote Desktop | VNC relay is a UI shell only | S10 likely ❌ |
| Remote Shell | WebSocket echoes only (mock) | B10 likely ⚠️ |
| SAST/DAST | Return job IDs but no actual scanner | R1–R2 likely ⚠️ |
| Chaos Engineering | Stub endpoints only | Not tested |
| Digital Twin | Scaffold only | Not tested |
| Voice Bot | Stub only | Not tested |
| MFA (TOTP) | Enrollment works; enforce on login may be stub | A12 may ⚠️ |
| SSO (OIDC/SAML) | Scaffolding only | Not tested |
| yara-python binary | Commented out in requirements.txt; string fallback active | C2 should pass as fallback |

---

## Quick Smoke Test (5-minute sanity check)

Run these 10 commands in order. All must pass for the platform to be considered functional:

```bash
# 1. Health check
curl -s http://localhost:8000/api/health | python -m json.tool

# 2. Login + save token
TOKEN=$(curl -s -X POST http://localhost:8000/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"super@omni.ai","password":"password123"}' \
  | python -c "import sys,json; print(json.load(sys.stdin)['access_token'])")

# 3. List attack patterns
curl -s http://localhost:8000/api/correlations/patterns/list \
  -H "Authorization: Bearer $TOKEN" | python -m json.tool

# 4. List playbooks
curl -s http://localhost:8000/api/playbooks \
  -H "Authorization: Bearer $TOKEN" | python -m json.tool

# 5. Check threat feed collection in DB
curl -s "http://localhost:8000/api/threat-intel/feed" \
  -H "Authorization: Bearer $TOKEN" | python -m json.tool

# 6. Create a security event
curl -s -X POST http://localhost:8000/api/security-events \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"event_type":"ransomware_detected","source_ip":"10.0.0.1","severity":"critical","description":"Test"}' \
  | python -m json.tool

# 7. Run manual correlation
curl -s -X POST http://localhost:8000/api/correlations/run \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"tenant_id":"platform-admin","time_window_minutes":60}' \
  | python -m json.tool

# 8. YARA string scan (Python one-liner)
python -c "
import sys; sys.path.insert(0,'agent')
from capabilities.yara_scanner import get_yara_scanner
s = get_yara_scanner()
print(s.scan_string('mimikatz.exe'))
print(s.scan_string('chrome.exe'))
"

# 9. Verify token has jti
python -c "
import jwt, os
token = '$TOKEN'
data = jwt.decode(token, options={'verify_signature':False})
print('jti present:', 'jti' in data)
print('role:', data.get('role'))
"

# 10. List roles
curl -s http://localhost:8000/api/roles \
  -H "Authorization: Bearer $TOKEN" | python -m json.tool
```

All 10 should return `200` responses with valid JSON. Any failure here indicates a critical issue.

---

*Document generated: 2026-04-20 | Platform version: 2030.0*
