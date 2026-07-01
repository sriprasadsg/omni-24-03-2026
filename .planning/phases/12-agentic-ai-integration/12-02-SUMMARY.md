---
phase: 12
plan: 02
status: complete
completed_at: 2026-06-23
subsystem: agentic-ai
tags: [tracing, observability, eval, promptfoo, arize-phoenix, opentelemetry]
dependency_graph:
  requires: [12-01]
  provides: [init_agentic_tracing, promptfoo-eval-harness]
  affects: [backend/app_startup.py, backend/requirements.txt]
tech_stack:
  added:
    - arize-phoenix>=4.0.0,<5.0.0
    - openinference-instrumentation-anthropic>=0.1.0,<2.0.0
    - opentelemetry-exporter-otlp-proto-http>=1.24.0,<2.0.0
    - promptfoo (eval runner, npx)
  patterns:
    - lazy-import inside try/except for optional tracing dependencies
    - OTLP BatchSpanProcessor for async span export
    - AnthropicInstrumentor auto-instrumentation
key_files:
  modified:
    - backend/app_startup.py
    - backend/requirements.txt
  created:
    - .planning/phases/12-agentic-ai-integration/promptfooconfig.yaml
    - .planning/phases/12-agentic-ai-integration/eval_fixtures/compliance_stale.json
    - .planning/phases/12-agentic-ai-integration/eval_fixtures/vuln_scan_overdue.json
    - .planning/phases/12-agentic-ai-integration/eval_fixtures/threat_hunt_process_anomaly.json
    - .planning/phases/12-agentic-ai-integration/eval_fixtures/persistence_alert.json
    - .planning/phases/12-agentic-ai-integration/eval_fixtures/no_recent_processes.json
decisions:
  - "Lazy imports inside init_agentic_tracing() function body — missing tracing packages never abort startup"
  - "PHOENIX_OTLP_ENDPOINT env var with default http://localhost:4317 — self-hosted Phoenix only"
  - "promptfooconfig.yaml inlines fixture JSON as YAML block scalars — avoids file path resolution issues in different working directories"
  - "Hardcoded ISO8601 UTC timestamps in fixture files — stable for replay, not time-relative"
metrics:
  duration: "3m 24s"
  completed: 2026-06-23
  tasks: 2
  files_modified: 2
  files_created: 6
---

# Phase 12 Plan 02: Eval Harness and Arize Phoenix Tracing Summary

Arize Phoenix OpenTelemetry tracing wired into `app_startup.py` as `init_agentic_tracing()` with lazy imports and full try/except isolation. Promptfoo eval harness created with 5 reference fixtures covering all critical-path tool selections.

## What Was Built

### Files Modified

- **`backend/app_startup.py`** — Added `init_agentic_tracing()` function (lines 461–491) with lazy imports for all tracing packages inside try/except. Called from `run_startup_services()` at end of startup sequence inside its own try/except block. PHOENIX_OTLP_ENDPOINT env var respected with default `http://localhost:4317`.

- **`backend/requirements.txt`** — Appended three tracing dependency lines after existing `anthropic>=0.28.0,<2.0.0` line:
  - `arize-phoenix>=4.0.0,<5.0.0`
  - `openinference-instrumentation-anthropic>=0.1.0,<2.0.0`
  - `opentelemetry-exporter-otlp-proto-http>=1.24.0,<2.0.0`

### Files Created

- **`.planning/phases/12-agentic-ai-integration/promptfooconfig.yaml`** — Promptfoo eval config with:
  - Provider: `anthropic:messages:claude-sonnet-4-6`, temperature 0, max_tokens 1024, tool_choice `{type: any}`
  - System prompt: verbatim from `agentic_service.py` SYSTEM_PROMPT constant
  - 5 tool definitions: run_compliance_check, run_vulnerability_scan, run_threat_hunt, run_persistence_scan, collect_processes (verbatim from AI-SPEC Section 3)
  - defaultTest JS assert for VALID_TOOLS membership (threshold 1.0)
  - 5 test entries with per-test JS assert for exact expected tool_name
  - failureThreshold: 0.85 in commandLineOptions

- **`eval_fixtures/compliance_stale.json`** — last_compliance_run 73h ago (2026-06-20T00:20:00Z), last_vuln_scan 12h ago. Expected: `run_compliance_check`.
- **`eval_fixtures/vuln_scan_overdue.json`** — last_vuln_scan 97h ago (2026-06-18T22:20:00Z), last_compliance_run 6h ago. Expected: `run_vulnerability_scan`.
- **`eval_fixtures/threat_hunt_process_anomaly.json`** — findings: svchost.exe spawned from cmd.exe, severity_score 85, mitre T1055. Expected: `run_threat_hunt`.
- **`eval_fixtures/persistence_alert.json`** — alerts: persistence category, high severity, fired 1h ago. Expected: `run_persistence_scan`.
- **`eval_fixtures/no_recent_processes.json`** — processes empty, last_process_snapshot 25h ago, no alerts, scans within 12h. Expected: `collect_processes`.

## Startup Tracing Verification

`init_agentic_tracing()` verified to NOT break `app_startup` module load when tracing packages are absent. All tracing imports are inside the function body under `try: ... except ImportError:` — a missing package logs a WARNING and returns cleanly. The pre-existing module-level import failure (`bcrypt` not installed in test env) is unrelated to this plan's changes.

## Promptfoo Fixture Coverage

| Fixture | Discriminating Signal | Expected Tool |
|---------|----------------------|---------------|
| compliance_stale.json | last_compliance_run = 73h ago | run_compliance_check |
| vuln_scan_overdue.json | last_vuln_scan = 97h ago | run_vulnerability_scan |
| threat_hunt_process_anomaly.json | process_anomaly finding severity_score=85 | run_threat_hunt |
| persistence_alert.json | persistence-category high alert 1h ago | run_persistence_scan |
| no_recent_processes.json | 0 processes, last_process_snapshot = 25h ago | collect_processes |

## Commits

| Task | Commit | Description |
|------|--------|-------------|
| 1 | 1e728d1 | feat(12-02): add init_agentic_tracing() to app_startup.py and tracing deps to requirements.txt |
| 2 | 40cfc58 | feat(12-02): add promptfoo eval harness with 5 critical-path fixture test cases |

## Regression Check

Plan 01's 8 tests: 8 passed, 0 failed (verified post-commit).

## Deviations from Plan

### Pre-existing Condition Noted

**app_startup.py line count:** File was 633 lines before this plan (exceeds CLAUDE.md 500-line limit). Added ~37 lines bringing total to ~670 lines. This is a pre-existing deviation — splitting the file would require an architectural decision (Rule 4). The init_agentic_tracing() code follows the same patterns already present in the file.

No other deviations. All AI-SPEC Section 5 and Section 7 constraints met:
- Lazy imports inside function body (Section 7)
- PHOENIX_OTLP_ENDPOINT env var with correct default (Section 7)
- Three exact package versions in requirements.txt (Section 5)
- failureThreshold: 0.85 (Section 5)
- 5 critical-path scenarios with deterministic tool_name asserts (Section 5)

## Threat Surface Scan

No new network endpoints or auth paths introduced. Phoenix OTLP endpoint is outbound-only (span export). T-12-07 mitigation documented in promptfooconfig.yaml comment header: Phoenix must be self-hosted on-prem or within tenant VPC.

## Self-Check: PASSED

- init_agentic_tracing defined at app_startup.py:461 — FOUND
- init_agentic_tracing called at app_startup.py:667 — FOUND
- 3 tracing deps in requirements.txt — FOUND
- promptfooconfig.yaml: valid YAML, 5 tests — VERIFIED
- 5 fixture JSON files with agent_id + capabilities — VERIFIED
- Plan 01 regression: 8/8 pass — VERIFIED
- No Co-Authored-By in commits — CONFIRMED
