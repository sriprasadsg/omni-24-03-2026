# Ruflo Feature Test Report

- Project: enterprise-omni-agent-ai-platform
- Run at (UTC): 2026-08-24T18:06:00Z
- Binary: `./node_modules/.bin/claude-flow`
- Pass: 35  Fail/Timeout: 2  Total: 37

| Feature | Command | Status | Exit | Time | Last output |
|---|---|---|---|---|---|
| init (dry check) | `init --help` | PASS | 0 | 0s |   $ claude-flow init --all-agents     Install all agent categories (~89 agents; ADR-128 opt-in)   |
| start (help) | `start --help` | PASS | 0 | 1s |   $ claude-flow start stop     Stop the running system   |
| status | `status` | PASS | 0 | 1s | MCP Server [INFO]   Not running   |
| agent list | `agent list` | PASS | 0 | 1s | +----------------------+-----------------+--------+------------+--------------+  [INFO] Total: 60 agents  |
| swarm status | `swarm status` | PASS | 0 | 0s |   - Consensus Rounds: 0   - Messages Sent: 0   - Conflicts Resolved: 0  |
| memory search | `memory search -q test` | PASS | 0 | 1s |  [WARN] No results found Try: claude-flow memory store -k "key" --value "data"  |
| task list | `task list` | PASS | 0 | 1s | +----+----------------+--------------------------------+----------+---------+----------+  [INFO] Showing 20 of 20 tasks  |
| session list | `session list` | PASS | 0 | 0s |  [INFO] No sessions found [INFO] Run "claude-flow session save" to create a session  |
| mcp status | `mcp status` | PASS | 0 | 1s | \| PID       \|   10812 \| \| Transport \|   stdio \| +-----------+---------+  |
| hooks list | `hooks list` | PASS | 0 | 0s | +----------------------+--------------+---------+----------+------------+---------------+  [INFO] Total: 26 hooks  |
| neural status | `neural status` | PASS | 0 | 1s | \| Training Pipeline   \| Available  \| native @ruvector/ruvllm pipel... \| \| Graph Database      \| Active     \| 0 nodes, 0 edges                 \| +------- |
| security scan (help) | `security --help` | PASS | 0 | 1s |   $ claude-flow security composition-scan     Scan MCP tool descriptions for cross-tool injection (dream-cycle #2783)   |
| policy status | `policy status` | PASS | 0 | 0s |     "length": 29   } }  |
| performance metrics | `performance metrics` | PASS | 0 | 0s |  Load Average: 0.50, 0.58, 0.36 CPUs: 32 \| Platform: linux 7.0.0-30-generic  |
| embeddings status | `embeddings --help` | PASS | 0 | 0s |   $ claude-flow embed neural -f drift     Neural substrate   |
| hive-mind status | `hive-mind status` | PASS | 0 | 0s |  Worker Agents [INFO] No workers in hive. Use "claude-flow hive-mind spawn" to add workers.  |
| ruvector status | `ruvector status` | FAIL | 1 | 1s | ============================================================  [ERROR] Database name is required. Use --database or -d flag, or set PGDATABASE env.  |
| guidance status | `guidance --help` | PASS | 0 | 0s |   $ claude-flow guidance ab-test     Run A/B behavioral comparison   |
| autopilot status | `autopilot status` | PASS | 0 | 1s | Elapsed: 0 min Tasks: 18/39 (46%) Sources: team-tasks, swarm-tasks, file-checklist  |
| config list | `config list` | PASS | 0 | 0s |   - reset      - Reset to defaults   - export     - Export configuration   - import     - Import configuration  |
| doctor | `doctor` | FAIL | 1 | 2s | Run with --fix to see 9 suggested commands (does not auto-apply)  Some checks failed. Please address the issues above.  |
| daemon status | `daemon status` | PASS | 0 | 1s | \| predict     \| ○  \| disabled \| 0    \| 0%      \| never    \| -        \| \| document    \| ○  \| disabled \| 0    \| 0%      \| never    \| -        \ |
| completions (help) | `completions --help` | PASS | 0 | 0s |   $ claude-flow completions powershell >> $PROFILE     Install PowerShell completions   |
| migrate (help) | `migrate --help` | PASS | 0 | 1s |   $ claude-flow migrate fix --agents     Restore ADR-128-removed agents   |
| workflow list | `workflow list` | PASS | 0 | 0s | Workflows  [INFO] No workflows found  |
| analyze (help) | `analyze --help` | PASS | 0 | 0s |   $ claude-flow analyze deps --security     Check dependency vulnerabilities   |
| route (help) | `route --help` | PASS | 0 | 1s |   $ claude-flow route stats     Show routing statistics   |
| progress | `progress` | PASS | 0 | 0s |   hooks: 100%   packages: 18%   ddd: 70%  |
| providers list | `providers list` | PASS | 0 | 1s | +-----------------+-----------+---------------------------+-------------------+  Tip: Use "providers configure -p <name> -k <key>" to set API keys.  |
| plugins list | `plugins list` | PASS | 0 | 3s |  Source: claude-flow-official (demo) Registry CID: bafybeiplugina8ab2aa18f63f1369...  |
| deployment list | `deployment list` | PASS | 0 | 0s |   - Deployment previews for PRs  Created with love by ruv.io  |
| claims list | `claims list` | PASS | 0 | 1s |   - task:create  Config: /home/user/enterprise-omni-agent-ai-platform/.claude-flow/claims.json  |
| issues list | `issues list` | PASS | 0 | 0s | [INFO] No claims found  |
| update check | `update check` | PASS | 0 | 1s | [INFO] Update check skipped: Last check was 0h ago (next check in ~24h) Use --force to check anyway  |
| process list | `process list` | PASS | 0 | 0s |   claude-flow process monitor --watch   claude-flow process workers --action spawn --type task --count 3   claude-flow process logs --follow --level error  |
| appliance list | `appliance list` | PASS | 0 | 1s |   - offline  - Fully air-gapped with bundled models (~4 GB)  Use "ruflo appliance <subcommand> --help" for details.  |
| cleanup (dry-run) | `cleanup --dry-run` | PASS | 0 | 0s |    This was a dry run. Use --force to actually remove artifacts.   |

## Gaps

- | ruvector status | `ruvector status` | FAIL | 1 | 1s | ============================================================  [ERROR] Database name is required. Use --database or -d flag, or set PGDATABASE env.  |
- | doctor | `doctor` | FAIL | 1 | 2s | Run with --fix to see 9 suggested commands (does not auto-apply)  Some checks failed. Please address the issues above.  |

Full logs: `reports/ruflo/logs/*.log`
