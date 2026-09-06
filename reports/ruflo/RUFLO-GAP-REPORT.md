# Ruflo Feature Test — Gap Report

Project: `enterprise-omni-agent-ai-platform`
Run: 2026-08-24 (UTC), binary `./node_modules/.bin/claude-flow` (local v3.38.12; latest v3.38.19)
Full sweep script: `scripts/test-ruflo-features.sh` — 37 probes, non-destructive, all CLI feature groups.
Raw table + logs: `reports/ruflo/ruflo-feature-report.md`, `reports/ruflo/logs/*.log`

## Result: 35 PASS / 2 FAIL (exit code)

Exit-code fail isn't the full story — `doctor` surfaces real config gaps even where CLI exit codes pass. See below.

## Gaps found

### 1. `ruvector status` — FAIL (exit 1)
```
[ERROR] Database name is required. Use --database or -d flag, or set PGDATABASE env.
```
RuVector PostgreSQL bridge unconfigured — no `PGDATABASE`/`--database` set for this project. Not wired to any Postgres backend. Skip unless project needs pgvector bridge.

### 2. `doctor` — FAIL (exit 1): 17 passed / 9 warnings / 1 failed
Real failure:
- **MetaHarness declared packages (ADR-150)**: declared but not installed — `@metaharness/radio`, `@metaharness/turn-credit`. MetaHarness surfaces degraded. Fix: `npm install --include=optional`

Warnings (functional but degraded/unconfigured):
| Check | Issue | Fix |
|---|---|---|
| Version Freshness | v3.38.12 installed, v3.38.19 latest | `npm update @claude-flow/cli` |
| Config File | none, using defaults | `claude-flow config init` |
| MCP Schema Overhead | 356 tools ≈ 64,858 schema tokens loaded on every session | set `CLAUDE_FLOW_MCP_TOOLS` to needed categories (e.g. `memory,swarm,agent,hooks`) + `CLAUDE_FLOW_CONTEXT_WINDOW_TOKENS` |
| AIDefence | `@claude-flow/aidefence` not loadable — `aidefence_*` MCP tools will fail | `npm install --save @claude-flow/aidefence` |
| Encryption at Rest | off — session/terminal/memory stores plaintext (mode 0600 only) | `export CLAUDE_FLOW_ENCRYPT_AT_REST=1` + `CLAUDE_FLOW_ENCRYPTION_KEY=<64-char-hex>` |
| MetaHarness version string | installed but unparseable | none required, cosmetic |
| MetaHarness integration | `plugins/ruflo-metaharness/` not found | `ruflo plugins install ruflo-metaharness` |
| Meta LLM Proxy (ADR-313) | not installed, no proxy-token | internal-only package (cognitum-one/meta-proxy) |
| Cognitum identity (ADR-306) | not logged in | `ruflo auth login` |

## Feature areas confirmed working (no config needed)

| Area | Evidence |
|---|---|
| agent | 60 agents registered, `agent list` OK |
| swarm | `swarm status` OK, 0 active consensus rounds (idle, not broken) |
| memory | search works (semantic, Transformers.js `all-MiniLM-L6-v2`, 34ms) — 0 hits because store is empty, not an error |
| task | 20/20 tasks tracked |
| hooks | 26 hooks registered |
| neural | status OK, training pipeline available |
| security | `--help` surfaced (composition-scan etc. present) |
| policy | ADR-324 engine live: mode=legacy, 21 ledger receipts, valid |
| performance | metrics OK (32 CPUs, load avg reported) |
| embeddings, guidance, hive-mind, autopilot, config, daemon, completions, migrate, workflow, analyze, route, progress, providers, plugins, deployment, claims, issues, update, process, appliance, cleanup | all responded exit 0 |

## Empty-but-not-broken states (expected on fresh project)

- `session list` → no sessions saved yet
- `workflow list` → no workflows defined yet
- `issues list` → no claims filed
- MCP server → **not running** (`status` shows "MCP Server: Not running"); start with `claude-flow mcp start` if you need MCP tool access in this project

## Recommended actions, priority order

1. `npm install --include=optional` — fixes the one real `doctor` FAIL (MetaHarness packages)
2. `npm update @claude-flow/cli` — 3.38.12 → 3.38.19 local pin is behind
3. Set `CLAUDE_FLOW_MCP_TOOLS` — 356 tools/65k tokens loaded unconditionally on every MCP session is a real cost; scope it down
4. `claude-flow config init` — no config file currently, running on defaults
5. Decide on `CLAUDE_FLOW_ENCRYPT_AT_REST` — plaintext session/memory stores, relevant if this repo handles sensitive data
6. Leave `ruvector` and `Meta LLM Proxy` alone unless a Postgres-vector or sponsored-proxy use case actually exists — false gaps for this project's current scope
