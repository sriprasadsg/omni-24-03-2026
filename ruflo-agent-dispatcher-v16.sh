#!/usr/bin/env bash
set -Eeuo pipefail

# Ruflo Multi-Agent Dispatcher v16
# - Runs detached in background by default
# - Detects/installs claude-flow when missing
# - Spawns 8 Ruflo agents and creates assigned tasks
# - Runs real Claude Code workers in parallel
# - Retries failed workers once
# - Keeps per-agent logs/results
# - Generates Markdown/JSON/debug reports
# - Read-only analysis by policy; workers are explicitly forbidden from modifying files

PROJECT="${PROJECT_DIR:-$(pwd)}"
MAX_AGENTS="${MAX_AGENTS:-8}"
WORKER_TIMEOUT="${WORKER_TIMEOUT:-30m}"
RETRIES="${RETRIES:-1}"
POLL_SECONDS="${POLL_SECONDS:-10}"
AUTO_INSTALL="${AUTO_INSTALL:-1}"

cd "$PROJECT"
[[ -f package.json ]] || { echo "ERROR: package.json not found in $PROJECT" >&2; exit 1; }

TS="$(date +%Y%m%d_%H%M%S)"
RUN_DIR="$PROJECT/ruflo-agent-dispatcher-v16-$TS"
WORK_DIR="$RUN_DIR/workers"
DIAG_DIR="$RUN_DIR/diagnostics"
RUFLO_DIR="$RUN_DIR/ruflo"
LAUNCH_DIR="$PROJECT/ruflo-dispatcher-runs"
mkdir -p "$WORK_DIR" "$DIAG_DIR" "$RUFLO_DIR" "$LAUNCH_DIR"

# Detached execution. Set RUFLO_V16_CHILD=1 to run in foreground.
if [[ "${RUFLO_V16_CHILD:-0}" != "1" ]]; then
  export RUFLO_V16_CHILD=1
  LAUNCH_LOG="$LAUNCH_DIR/launcher-$TS.log"
  nohup "$0" >"$LAUNCH_LOG" 2>&1 < /dev/null &
  echo "RUFLO DISPATCHER v16 STARTED IN BACKGROUND"
  echo "PID : $!"
  echo "LOG : $LAUNCH_LOG"
  echo "Monitor: tail -f \"$LAUNCH_LOG\""
  exit 0
fi

MAIN_LOG="$RUN_DIR/dispatcher.log"
exec > >(tee -a "$MAIN_LOG") 2>&1

log(){ printf '[%s] %s\n' "$(date '+%Y-%m-%d %H:%M:%S')" "$*"; }
pass(){ log "[PASS] $*"; }
warn(){ log "[WARN] $*"; }
fail(){ log "[FAIL] $*"; }

NAMES=(architect researcher code-analyzer security tester reviewer performance qa)
declare -A TYPES PROMPTS AGENT_ID TASK_ID WORKER_PID RESULT ATTEMPTS EXIT_CODE

TYPES[architect]=architect
TYPES[researcher]=researcher
TYPES[code-analyzer]=coder
TYPES[security]=security-auditor
TYPES[tester]=tester
TYPES[reviewer]=reviewer
TYPES[performance]=performance-analyzer
TYPES[qa]=tester

PROMPTS[architect]='Act as the ARCHITECT agent. Work strictly READ-ONLY. Analyze architecture, components, entry points, services, data flow, dependencies, configuration, deployment, technical debt and design risks. Do not create, edit, delete, rename, install or modify any project file. Do not modify git state. Return a detailed Markdown report with evidence paths, severity and recommendations.'
PROMPTS[researcher]='Act as the RESEARCHER agent. Work strictly READ-ONLY. Inspect technologies, frameworks, dependencies, integrations, MCP/Ruflo configuration, test structure and operational assumptions. Do not modify files or install anything. Return a detailed Markdown report with evidence paths, risks and open questions.'
PROMPTS[code-analyzer]='Act as the CODE ANALYSIS agent. Work strictly READ-ONLY. Review backend/frontend implementation quality, module organization, APIs, error handling, duplication, dead-code indicators, maintainability and likely defects. Do not modify files or install anything. Return concrete findings with file/path evidence and severity.'
PROMPTS[security]='Act as the SECURITY agent. Work strictly READ-ONLY. Analyze authentication, authorization, secrets, input validation, APIs, MCP configuration, dependency risks, command execution, filesystem access, unsafe defaults and security weaknesses. Do not modify files or install anything. Return an enterprise security report with severity, evidence and remediation.'
PROMPTS[tester]='Act as the TEST ENGINEER agent. Work strictly READ-ONLY. Inspect tests and run only safe diagnostics/tests that do not mutate the repository. Analyze collection errors, coverage gaps, flaky/environment-sensitive tests and CI readiness. Never modify source, fixtures, caches or lockfiles. Return a detailed test report.'
PROMPTS[reviewer]='Act as the CODE REVIEWER agent. Work strictly READ-ONLY. Independently review correctness, maintainability, architecture consistency, error handling, observability, configuration and production risks. Do not modify files. Return prioritized findings with evidence paths.'
PROMPTS[performance]='Act as the PERFORMANCE agent. Work strictly READ-ONLY. Analyze CPU, memory, disk/I/O, network, database, concurrency and startup bottlenecks. Inspect runtime/build configuration and identify expensive operations. Run only safe diagnostics. Do not modify files. Return evidence and recommended measurements/optimizations.'
PROMPTS[qa]='Act as the QA agent. Work strictly READ-ONLY. Assess release readiness across functionality, integrations, configuration, dependencies, tests, error handling, security, observability and operations. Do not modify files. Return pass/fail/risk items with evidence paths.'

# ---- Environment ----
echo
printf '%s\n' '============================================================'
printf '%s\n' 'RUFLO MULTI-AGENT DISPATCHER v16'
printf '%s\n' '============================================================'
echo "Project : $PROJECT"
echo "Date    : $(date '+%Y-%m-%d %H:%M:%S %Z')"
echo "Host    : $(hostname)"
echo "PID     : $$"
echo "Report  : $RUN_DIR"
echo "Timeout : $WORKER_TIMEOUT"
echo "Retries : $RETRIES"
printf '%s\n' '============================================================'

for c in bash node npm npx git python3 jq; do
  if command -v "$c" >/dev/null 2>&1; then pass "$c: $(command -v "$c")"; else warn "$c unavailable"; fi
done
CLAUDE_BIN="$(command -v claude || true)"
[[ -n "$CLAUDE_BIN" ]] || { fail 'Claude Code executable not found'; exit 1; }
"$CLAUDE_BIN" --version >"$DIAG_DIR/claude-version.txt" 2>&1 || true
pass "Claude: $CLAUDE_BIN"

# ---- Ruflo detection ----
RUFLO_CMD=()
detect_ruflo(){
  if command -v ruflo >/dev/null 2>&1; then RUFLO_CMD=("$(command -v ruflo)"); return 0; fi
  if [[ -x "$PROJECT/node_modules/.bin/claude-flow" ]]; then RUFLO_CMD=("$PROJECT/node_modules/.bin/claude-flow"); return 0; fi
  if npx --no-install claude-flow --version >/tmp/ruflo-v16-version.$$ 2>&1; then RUFLO_CMD=(npx --no-install claude-flow); return 0; fi
  return 1
}

if ! detect_ruflo; then
  if [[ "$AUTO_INSTALL" != 1 ]]; then fail 'Ruflo unavailable and AUTO_INSTALL=0'; exit 1; fi
  warn 'Ruflo unavailable; attempting npm installation of claude-flow'
  if npm install --save-dev claude-flow@latest >"$DIAG_DIR/ruflo-install.log" 2>&1; then
    pass 'claude-flow package installed'
  else
    fail 'Automatic Ruflo installation failed'
    tail -100 "$DIAG_DIR/ruflo-install.log" || true
    exit 1
  fi
  detect_ruflo || { fail 'Ruflo still unavailable after installation'; exit 1; }
fi
"${RUFLO_CMD[@]}" --version >"$DIAG_DIR/ruflo-version.txt" 2>&1 || true
pass "Ruflo runtime: $(tr '\n' ' ' < "$DIAG_DIR/ruflo-version.txt")"

# ---- Snapshot ----
{
  echo "DATE=$(date --iso-8601=seconds)"
  echo "GIT_BRANCH=$(git branch --show-current 2>/dev/null || true)"
  echo 'GIT_STATUS:'; git status --short 2>/dev/null || true
  echo 'DISK:'; df -h "$PROJECT" 2>/dev/null || true
  echo 'TOP_LEVEL:'; find . -maxdepth 2 -type f -not -path './node_modules/*' -not -path './.git/*' | sort | head -500
} >"$DIAG_DIR/project-snapshot.txt"

"${RUFLO_CMD[@]}" status >"$DIAG_DIR/ruflo-status-before.txt" 2>&1 || true
"${RUFLO_CMD[@]}" swarm init --topology hierarchical --max-agents "$MAX_AGENTS" --auto-scale >"$RUFLO_DIR/swarm-init.txt" 2>&1 || warn 'swarm init returned non-zero; continuing'

# ---- Spawn ----
log "Spawning ${#NAMES[@]} Ruflo agents"
for name in "${NAMES[@]}"; do
  mkdir -p "$WORK_DIR/$name"
  if "${RUFLO_CMD[@]}" agent spawn --type "${TYPES[$name]}" --name "ruflo-v16-$name" >"$WORK_DIR/$name/spawn.txt" 2>&1; then
    id="$(grep -Eo 'agent-[0-9]+-[a-z0-9]+' "$WORK_DIR/$name/spawn.txt" | head -1 || true)"
    if [[ -n "$id" ]]; then AGENT_ID[$name]="$id"; pass "$name spawned: $id"; else warn "$name spawned but ID was not parsed"; fi
  else
    fail "$name spawn failed"
  fi
done

# ---- Tasks ----
log 'Creating and assigning Ruflo tasks'
for name in "${NAMES[@]}"; do
  id="${AGENT_ID[$name]:-}"
  [[ -n "$id" ]] || { warn "$name has no agent ID; task skipped"; continue; }
  desc="Read-only enterprise analysis for role $name. Do not modify project files. Return findings suitable for a debug report."
  if "${RUFLO_CMD[@]}" task create --type analysis --description "$desc" --priority high --assign "$id" --timeout 1800 >"$WORK_DIR/$name/task.txt" 2>&1; then
    tid="$(grep -Eo 'task-[0-9]+-[a-z0-9]+' "$WORK_DIR/$name/task.txt" | head -1 || true)"
    TASK_ID[$name]="$tid"
    pass "$name task created: ${tid:-unknown}"
  else
    warn "$name task creation failed"
  fi
done

# ---- Worker ----
run_worker(){
  local name="$1" attempt="$2" dir="$WORK_DIR/$1" rc
  local outfile="$dir/result-attempt-$attempt.md"
  local logfile="$dir/worker-attempt-$attempt.log"
  local status="$dir/status-attempt-$attempt.json"
  {
    echo "Agent: $name"; echo "Attempt: $attempt"; echo "Agent ID: ${AGENT_ID[$name]:-unknown}"; echo "Task ID: ${TASK_ID[$name]:-unknown}"; echo "Started: $(date --iso-8601=seconds)"
  } >"$logfile"
  set +e
  timeout --kill-after=30s "$WORKER_TIMEOUT" "$CLAUDE_BIN" -p "${PROMPTS[$name]}" --output-format text >"$outfile" 2>>"$logfile"
  rc=$?
  set -e
  jq -n --arg a "$name" --arg id "${AGENT_ID[$name]:-unknown}" --arg t "${TASK_ID[$name]:-unknown}" --argjson n "$attempt" --argjson rc "$rc" --arg finished "$(date --iso-8601=seconds)" --argjson bytes "$(wc -c < "$outfile")" '{agent:$a,agent_id:$id,task_id:$t,attempt:$n,exit_code:$rc,finished:$finished,result_bytes:$bytes}' >"$status"
  [[ $rc -eq 0 && -s "$outfile" ]]
}

# ---- Parallel execution ----
log 'Starting real Claude Code workers in parallel'
for name in "${NAMES[@]}"; do
  ATTEMPTS[$name]=1
  run_worker "$name" 1 &
  WORKER_PID[$name]=$!
  log "[START] $name PID=${WORKER_PID[$name]}"
done

while :; do
  remaining=0
  for name in "${NAMES[@]}"; do
    pid="${WORKER_PID[$name]:-}"
    [[ -n "$pid" ]] || continue
    if kill -0 "$pid" 2>/dev/null; then
      remaining=$((remaining+1))
    else
      wait "$pid" 2>/dev/null; rc=$?
      if [[ $rc -eq 0 ]]; then RESULT[$name]=PASS; EXIT_CODE[$name]=0; log "[DONE] $name PASS"; else RESULT[$name]=FAILED; EXIT_CODE[$name]=$rc; log "[DONE] $name FAILED rc=$rc"; fi
      unset 'WORKER_PID[$name]'
    fi
  done
  [[ $remaining -eq 0 ]] && break
  sleep "$POLL_SECONDS"
done

# ---- Retry ----
for name in "${NAMES[@]}"; do
  if [[ "${RESULT[$name]:-FAILED}" == FAILED && "$RETRIES" -gt 0 ]]; then
    ATTEMPTS[$name]=2
    log "[RETRY] $name attempt 2"
    if run_worker "$name" 2; then RESULT[$name]=PASS; EXIT_CODE[$name]=0; pass "$name retry succeeded"; else rc=$?; RESULT[$name]=FAILED; EXIT_CODE[$name]=$rc; warn "$name retry failed rc=$rc"; fi
  fi
done

# ---- Diagnostics ----
log 'Collecting Ruflo diagnostics'
"${RUFLO_CMD[@]}" agent list >"$DIAG_DIR/agent-list.txt" 2>&1 || true
"${RUFLO_CMD[@]}" agent metrics >"$DIAG_DIR/agent-metrics.txt" 2>&1 || true
"${RUFLO_CMD[@]}" agent health >"$DIAG_DIR/agent-health.txt" 2>&1 || true
"${RUFLO_CMD[@]}" task list --all >"$DIAG_DIR/task-list.txt" 2>&1 || true
"${RUFLO_CMD[@]}" swarm status >"$DIAG_DIR/swarm-status.txt" 2>&1 || true
"${RUFLO_CMD[@]}" status >"$DIAG_DIR/ruflo-status-after.txt" 2>&1 || true
ps -ef >"$DIAG_DIR/processes.txt" 2>&1 || true
git status --short >"$DIAG_DIR/git-status.txt" 2>&1 || true
find "$WORK_DIR" -type f -printf '%p %s bytes\n' | sort >"$DIAG_DIR/worker-files.txt"

# ---- Reports ----
PASS_COUNT=0; FAIL_COUNT=0; EMPTY_COUNT=0
for name in "${NAMES[@]}"; do
  [[ "${RESULT[$name]:-FAILED}" == PASS ]] && PASS_COUNT=$((PASS_COUNT+1)) || FAIL_COUNT=$((FAIL_COUNT+1))
  if [[ ! -s "$WORK_DIR/$name/result-attempt-1.md" && ! -s "$WORK_DIR/$name/result-attempt-2.md" ]]; then EMPTY_COUNT=$((EMPTY_COUNT+1)); fi
done

{
  echo '# Ruflo Multi-Agent Dispatcher v16'; echo
  echo "- Project: \\`$PROJECT\\`"; echo "- Run: \\`$TS\\`"; echo "- Worker timeout: \\`$WORKER_TIMEOUT\\`"; echo "- Retries: \\`$RETRIES\\`"; echo
  echo '## Agent Results'; echo; echo '| Agent | Ruflo Agent ID | Task ID | Result | Attempts |'; echo '|---|---|---|---|---:|'
  for name in "${NAMES[@]}"; do echo "| $name | ${AGENT_ID[$name]:-unknown} | ${TASK_ID[$name]:-unknown} | ${RESULT[$name]:-FAILED} | ${ATTEMPTS[$name]:-1} |"; done
  echo
  for name in "${NAMES[@]}"; do
    echo "## $name"
    if [[ -s "$WORK_DIR/$name/result-attempt-2.md" ]]; then cat "$WORK_DIR/$name/result-attempt-2.md"; elif [[ -s "$WORK_DIR/$name/result-attempt-1.md" ]]; then cat "$WORK_DIR/$name/result-attempt-1.md"; else echo '_No worker result produced._'; tail -50 "$WORK_DIR/$name"/worker-attempt-*.log 2>/dev/null || true; fi
    echo
  done
} >"$RUN_DIR/DEBUG-REPORT.md"

jq -n \
  --arg version v16 --arg project "$PROJECT" --arg run "$TS" --arg timeout "$WORKER_TIMEOUT" \
  --argjson configured "${#NAMES[@]}" --argjson completed "$PASS_COUNT" --argjson failed "$FAIL_COUNT" --argjson empty "$EMPTY_COUNT" \
  --argjson agents "$(printf '%s\n' "${NAMES[@]}" | while read -r n; do jq -n --arg n "$n" --arg id "${AGENT_ID[$n]:-unknown}" --arg t "${TASK_ID[$n]:-unknown}" --arg r "${RESULT[$n]:-FAILED}" --argjson a "${ATTEMPTS[$n]:-1}" '{name:$n,agent_id:$id,task_id:$t,result:$r,attempts:$a}'; done | jq -s .)" \
  '{version:$version,project:$project,run:$run,worker_timeout:$timeout,configured_agents:$configured,completed:$completed,failed:$failed,empty_results:$empty,agents:$agents}' \
  >"$RUN_DIR/report.json"

SCORE=$((PASS_COUNT*100/${#NAMES[@]}))
if [[ $FAIL_COUNT -eq 0 ]]; then FINAL=PASSED; elif [[ $PASS_COUNT -gt 0 ]]; then FINAL=PARTIAL; else FINAL=FAILED; fi

{
  echo 'RUFLO MULTI-AGENT DISPATCHER v16'
  echo "Project: $PROJECT"
  echo "Run: $TS"
  echo "Configured agents: ${#NAMES[@]}"
  echo "Completed successfully: $PASS_COUNT"
  echo "Failed: $FAIL_COUNT"
  echo "Empty results: $EMPTY_COUNT"
  echo "Score: $SCORE / 100"
  echo "Result: $FINAL"
  echo
  for name in "${NAMES[@]}"; do echo "  $name => ${RESULT[$name]:-FAILED} attempts=${ATTEMPTS[$name]:-1} agent=${AGENT_ID[$name]:-unknown} task=${TASK_ID[$name]:-unknown}"; done
  echo
  echo "DEBUG-REPORT.md: $RUN_DIR/DEBUG-REPORT.md"
  echo "JSON: $RUN_DIR/report.json"
  echo "Dispatcher log: $MAIN_LOG"
} >"$RUN_DIR/summary.txt"

printf '\n============================================================\n'
printf 'RUFLO MULTI-AGENT DISPATCH COMPLETE\n'
printf '============================================================\n'
echo "Configured : ${#NAMES[@]}"
echo "Completed  : $PASS_COUNT"
echo "Failed     : $FAIL_COUNT"
echo "Empty      : $EMPTY_COUNT"
echo "Score      : $SCORE / 100"
echo "Result     : $FINAL"
echo "Report     : $RUN_DIR"
echo "Summary    : $RUN_DIR/summary.txt"
echo "Debug      : $RUN_DIR/DEBUG-REPORT.md"
echo "JSON       : $RUN_DIR/report.json"
echo "Live log   : tail -f \"$MAIN_LOG\""
printf '%s\n' '============================================================'
