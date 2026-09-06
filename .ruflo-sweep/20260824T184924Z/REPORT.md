# Ruflo sweep — 20260824T184924Z

- **Project:** `/home/user/enterprise-omni-agent-ai-platform`
- **Stacks:** node rust docker git
- **Swarm:** hierarchical, 8 agents, security depth `full`
- **Ruflo:** `ruflo` — auto-installed (global) (ruflo v3.38.19)

| Step | Category | Result | Detail |
|---|---|---|---|
| `agent-arch-review` | agents | **PASS** | rc=0 1 |
| `agent-code-reviewer` | agents | **PASS** | rc=0 0 |
| `agent-doc-gap` | agents | **FAIL** | rc=1 0 |
| `agent-gap-hunter` | agents | **PASS** | rc=0 0 |
| `agent-list` | agents | **PASS** | rc=0 0 |
| `agent-perf-engineer` | agents | **PASS** | rc=0 0 |
| `agent-sec-architect` | agents | **PASS** | rc=0 1 |
| `agent-sec-auditor` | agents | **PASS** | rc=0 1 |
| `agent-suite-runner` | agents | **PASS** | rc=0 0 |
| `lint-npm` | tests | **PASS** | rc=0 8 |
| `memory-store` | memory | **FAIL** | rc=1 0 |
| `ruflo-doctor` | infra | **PASS** | rc=0 3 |
| `ruflo-mcp-list` | infra | **PASS** | rc=0 0 |
| `ruflo-plugins` | infra | **FAIL** | rc=1 0 |
| `ruflo-sec-cve` | security | **FAIL** | rc=1 3 |
| `ruflo-sec-report` | security | **FAIL** | rc=1 1 |
| `ruflo-sec-scan` | security | **FAIL** | rc=1 224 |
| `ruflo-sec-valid` | security | **PASS** | rc=0 0 |
| `sec-cargo-audit` | security | **PASS** | rc=0 5 |
| `sec-npm-audit` | security | **FAIL** | rc=1 13 |
| `swarm-init` | infra | **PASS** | rc=0 1 |
| `swarm-status` | agents | **PASS** | rc=0 0 |
| `test-cargo` | tests | **PASS** | rc=0 9 |
| `test-npm` | tests | **PASS** | rc=0 17 |
| `typecheck-npm` | tests | **FAIL** | rc=2 91 |

## Totals

- PASS: 17
- FAIL: 8
- TIMEOUT: 0
- SKIP/UNAVAILABLE: 0

## Gaps to review by hand

1. Any `security` row where Ruflo passed but a real scanner failed — trust the scanner.
2. Any `agents` row that PASSed in under 2s — likely a stub, not real execution.
3. Every SKIP: a tool that is missing is not a clean result.

Full logs: `/home/user/enterprise-omni-agent-ai-platform/.ruflo-sweep/20260824T184924Z/logs`
