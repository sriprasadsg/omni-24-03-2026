#!/usr/bin/env bash
set -Eeuo pipefail

# Ruflo Multi-Agent Dispatcher v15
# Target: Ruflo/Claude Flow v3.38.x + Claude Code 2.x
# Runs in background by default, creates per-agent logs/results/debug reports.
# Agents are read-only auditors; source files are not intentionally modified.

PROJECT="${PROJECT:-$(pwd)}"
TIMEOUT="${TIMEOUT:-900}"
POLL="${POLL:-10}"
MAX_AGENTS="${MAX_AGENTS:-8}"

for a in "$@"; do
  case "$a" in
    --foreground) FOREGROUND=1 ;;
    --timeout=*) TIMEOUT="${a#*=}" ;;
    --poll=*) POLL="${a#*=}" ;;
    --max-agents=*) MAX_AGENTS="${a#*=}" ;;
    -h|--help) echo "Usage: $0 [--foreground] [--timeout=900] [--poll=10] [--max-agents=8]"; exit 0 ;;
    *) echo "Unknown option: $a" >&2; exit 2 ;;
  esac
done

if [[ "${FOREGROUND:-0}" != 1 && "${RUFLO_V15_BG:-0}" != 1 ]]; then
  mkdir -p "$PROJECT/ruflo-dispatcher-runs"
  ts=$(date +%Y%m%d_%H%M%S)
  log="$PROJECT/ruflo-dispatcher-runs/launcher-$ts.log"
  export RUFLO_V15_BG=1
  nohup "$0" --foreground --timeout="$TIMEOUT" --poll="$POLL" --max-agents="$MAX_AGENTS" >"$log" 2>&1 &
  echo "RUFLO DISPATCHER v15 STARTED IN BACKGROUND"
  echo "PID : $!"
  echo "LOG : $log"
  echo "Monitor: tail -f \"$log\""
  exit 0
fi

cd "$PROJECT"
START_EPOCH=$(date +%s)
START_TS=$(date '+%Y-%m-%d %H:%M:%S %Z')
HOST=$(hostname)
USER_NAME=$(id -un)
TS=$(date +%Y%m%d_%H%M%S)
REPORT="$PROJECT/ruflo-agent-dispatcher-v15-$TS"
LOGDIR="$REPORT/logs"; RESULTDIR="$REPORT/results"; STATEDIR="$REPORT/state"; DIAGDIR="$REPORT/diagnostics"
mkdir -p "$LOGDIR" "$RESULTDIR" "$STATEDIR" "$DIAGDIR"
MAINLOG="$REPORT/dispatcher.log"; SUMMARY="$REPORT/summary.txt"; DEBUG="$REPORT/DEBUG-REPORT.md"; JSON="$REPORT/report.json"
exec > >(tee -a "$MAINLOG") 2>&1

log(){ printf '[%s] %s\n' "$(date '+%F %T')" "$*"; }
pass(){ log "[PASS] $*"; }
warn(){ log "[WARN] $*"; }
fail(){ log "[FAIL] $*"; }
section(){ echo; echo '============================================================'; echo "$*"; echo '============================================================'; }

# name|agent-type|task-type|description
AGENTS=(
  'ruflo-architect|architect|research|Analyze architecture, components, dependencies, design risks and major technical boundaries.'
  'ruflo-researcher|researcher|research|Inspect repository structure, documentation, configuration and implementation patterns; identify important findings.'
  'ruflo-coder|coder|implementation|Inspect backend and frontend implementation, code organization, defects and maintainability. Do not modify files.'
  'ruflo-security|security-auditor|security|Audit authentication, authorization, secrets, MCP, APIs, dependencies and security configuration.'
  'ruflo-tester|tester|testing|Analyze tests, testability, coverage gaps, failures and reproducibility; run safe bounded tests where practical.'
  'ruflo-reviewer|reviewer|review|Perform independent code-quality, correctness and maintainability review.'
  'ruflo-performance|performance-engineer|optimization|Inspect CPU, memory, disk, large artifacts, bottlenecks and scalability risks.'
  'ruflo-qa|tester|testing|Perform QA validation of configuration, startup contracts and regression risks.'
)
if (( ${#AGENTS[@]} > MAX_AGENTS )); then AGENTS=("${AGENTS[@]:0:MAX_AGENTS}"); fi

RUFLO_MODE=''
RUFLO_VERSION=''
run_ruflo(){
  case "$RUFLO_MODE" in
    local) npx --no-install claude-flow "$@" ;;
    global) claude-flow "$@" ;;
    download) npx --yes claude-flow@latest "$@" ;;
    ruflo) npx --yes ruflo@latest "$@" ;;
    *) return 127;;
  esac
}

detect_tools(){
  section 'ENVIRONMENT'
  for c in bash node npm npx git python3 jq; do command -v "$c" >/dev/null 2>&1 && pass "$c: $(command -v "$c")" || warn "$c unavailable"; done
  command -v claude >/dev/null 2>&1 || { fail 'Claude Code executable not found'; exit 1; }
  pass "Claude: $(command -v claude)"; claude --version || true
  node --version; npm --version
}

detect_ruflo(){
  section 'RUFLO RUNTIME'
  if npx --no-install claude-flow --version >/dev/null 2>&1; then
    RUFLO_MODE=local; RUFLO_VERSION=$(npx --no-install claude-flow --version 2>&1 | tail -1); pass "Ruflo available: $RUFLO_VERSION"; return 0
  fi
  if command -v claude-flow >/dev/null 2>&1; then
    RUFLO_MODE=global; RUFLO_VERSION=$(claude-flow --version 2>&1 | tail -1); pass "Global Ruflo: $RUFLO_VERSION"; return 0
  fi
  warn 'Ruflo unavailable; bootstrapping with npx claude-flow@latest'
  if npx --yes claude-flow@latest --version >/dev/null 2>&1; then
    RUFLO_MODE=download; RUFLO_VERSION=$(npx --yes claude-flow@latest --version 2>&1 | tail -1); pass "Bootstrapped Ruflo: $RUFLO_VERSION"; return 0
  fi
  warn 'claude-flow bootstrap failed; trying ruflo@latest'
  if npx --yes ruflo@latest --version >/dev/null 2>&1; then
    RUFLO_MODE=ruflo; RUFLO_VERSION=$(npx --yes ruflo@latest --version 2>&1 | tail -1); pass "Bootstrapped Ruflo: $RUFLO_VERSION"; return 0
  fi
  fail 'Unable to obtain a working Ruflo CLI'; return 1
}

section 'RUFLO MULTI-AGENT DISPATCHER v15'
echo "Project : $PROJECT"; echo "Date    : $START_TS"; echo "Host    : $HOST"; echo "Report  : $REPORT"
detect_tools
detect_ruflo || exit 1

section 'PROJECT SNAPSHOT'
{
  echo "=== git status ==="; git status --short 2>&1 || true
  echo; echo "=== disk ==="; df -h "$PROJECT" 2>&1 || true
  echo; echo "=== large files >500M ==="; find "$PROJECT" -type f -size +500M -printf '%s %p\n' 2>/dev/null | sort -nr | head -50 || true
} > "$DIAGDIR/project-snapshot.txt"

section 'SPAWNING VALID RUFLO AGENTS'
: > "$STATEDIR/agents.tsv"
for spec in "${AGENTS[@]}"; do
  IFS='|' read -r name atype ttype desc <<< "$spec"
  out="$STATEDIR/spawn-$name.txt"
  if run_ruflo agent spawn --type "$atype" --name "$name" >"$out" 2>&1; then
    id=$(grep -Eo 'agent-[0-9]+-[A-Za-z0-9]+' "$out" | tail -1 || true)
    [[ -z "$id" ]] && id=$(grep -Eo 'agent-[0-9]+' "$out" | tail -1 || true)
    pass "$name spawned: ${id:-ID-not-parsed}"
    printf '%s\t%s\t%s\t%s\t%s\n' "$name" "$atype" "$ttype" "${id:-}" "$desc" >> "$STATEDIR/agents.tsv"
  else
    warn "$name spawn failed"; cat "$out" || true
    printf '%s\t%s\t%s\t\t%s\n' "$name" "$atype" "$ttype" "$desc" >> "$STATEDIR/agents.tsv"
  fi
done
run_ruflo agent list > "$STATEDIR/agent-list-after-spawn.txt" 2>&1 || true

section 'CREATING VALID RUFLO TASKS'
: > "$STATEDIR/tasks.tsv"
while IFS=$'\t' read -r name atype ttype aid desc; do
  [[ -z "$name" ]] && continue
  if [[ -z "$aid" ]]; then warn "$name has no agent ID; task skipped"; continue; fi
  taskout="$STATEDIR/task-$name.txt"
  full="${desc} Read-only audit. Do not modify, delete, rewrite, or install into project source files."
  if run_ruflo task create --type "$ttype" --description "$full" --assign "$aid" --priority high --timeout "$TIMEOUT" >"$taskout" 2>&1; then
    tid=$(grep -Eo 'task-[A-Za-z0-9_-]+' "$taskout" | tail -1 || true)
    pass "$name task created/assigned: ${tid:-ID-not-parsed}"
    printf '%s\t%s\t%s\t%s\n' "$name" "$aid" "$ttype" "${tid:-}" >> "$STATEDIR/tasks.tsv"
  else
    warn "$name task creation failed"; cat "$taskout" || true
    printf '%s\t%s\t%s\t\n' "$name" "$aid" "$ttype" >> "$STATEDIR/tasks.tsv"
  fi
done < "$STATEDIR/agents.tsv"
run_ruflo task list --all > "$STATEDIR/task-list-after-create.txt" 2>&1 || true

section 'STARTING REAL CLAUDE WORKERS IN PARALLEL'
: > "$STATEDIR/workers.tsv"
while IFS=$'\t' read -r name atype ttype aid desc; do
  [[ -z "$name" ]] && continue
  prompt="$STATEDIR/prompt-$name.txt"
  result="$RESULTDIR/$name.md"; err="$LOGDIR/$name.stderr.log"; combined="$LOGDIR/$name-combined.log"; state="$STATEDIR/$name.exit"
  cat > "$prompt" <<EOF2
You are $name in an enterprise read-only project audit.
Project: $PROJECT
Ruflo agent type: $atype
Ruflo task type: $ttype

Mission: $desc

Rules:
- READ ONLY. Do not modify source/configuration/project files.
- Do not delete files or install dependencies.
- Run safe bounded inspection/tests when useful.
- Redact secrets/tokens/passwords.
- Save findings to $result.
- Include executive summary, inspected areas, commands/tests, evidence, findings, errors, risks, remediation recommendations and final PASS/WARN/FAIL.
EOF2
  : > "$err"; echo RUNNING > "$state"
  (
    set +e
    claude -p "$(cat "$prompt")" --output-format text >"$result" 2>"$err"
    rc=$?
    echo "$rc" > "$state"
    { echo "Agent: $name"; echo "Ruflo ID: ${aid:-unknown}"; echo "Type: $atype"; echo "Task: $ttype"; echo "Exit: $rc"; echo; echo '=== STDERR ==='; cat "$err"; echo; echo '=== RESULT ==='; cat "$result"; } > "$combined"
    exit "$rc"
  ) &
  wp=$!
  printf '%s\t%s\t%s\t%s\t%s\n' "$name" "$wp" "$aid" "$ttype" "$state" >> "$STATEDIR/workers.tsv"
  pass "$name worker started PID=$wp"
done < "$STATEDIR/agents.tsv"

section 'MONITORING WORKERS'
deadline=$(( $(date +%s) + TIMEOUT ))
while :; do
  running=0
  ps -eo pid,ppid,stat,etime,%cpu,%mem,cmd | grep -E '(^ *PID|claude -p|claude)' | head -50 > "$DIAGDIR/processes-latest.txt" || true
  run_ruflo agent list > "$STATEDIR/agent-list-live.txt" 2>&1 || true
  run_ruflo task list --all > "$STATEDIR/task-list-live.txt" 2>&1 || true
  run_ruflo agent metrics > "$STATEDIR/metrics-live.txt" 2>&1 || true
  run_ruflo swarm status > "$STATEDIR/swarm-live.txt" 2>&1 || true
  while IFS=$'\t' read -r name wp aid ttype state; do
    [[ -z "$name" ]] && continue
    if kill -0 "$wp" 2>/dev/null; then running=$((running+1)); fi
  done < "$STATEDIR/workers.tsv"
  (( running == 0 )) && break
  if (( $(date +%s) >= deadline )); then
    warn "Timeout reached; terminating remaining workers"
    while IFS=$'\t' read -r name wp aid ttype state; do
      kill -0 "$wp" 2>/dev/null && { kill "$wp" 2>/dev/null || true; sleep 1; kill -9 "$wp" 2>/dev/null || true; echo TIMEOUT > "$state"; }
    done < "$STATEDIR/workers.tsv"
    break
  fi
  sleep "$POLL"
done

# Reap children and normalize status.
completed=0; failed=0; timeout=0; total=0
while IFS=$'\t' read -r name wp aid ttype state; do
  [[ -z "$name" ]] && continue
  total=$((total+1)); set +e; wait "$wp"; rc=$?; set -e
  if [[ -f "$state" ]] && [[ "$(cat "$state")" == TIMEOUT ]]; then timeout=$((timeout+1)); st=TIMEOUT
  elif [[ "$rc" == 0 ]]; then completed=$((completed+1)); st=COMPLETED; echo 0 > "$state"
  else failed=$((failed+1)); st="FAILED($rc)"; echo "$rc" > "$state"; fi
  log "$name => $st"
done < "$STATEDIR/workers.tsv"

section 'PROJECT DIAGNOSTICS'
{
  echo '=== package ==='; [[ -f package.json ]] && jq '{name,version,scripts}' package.json 2>/dev/null || true
  echo; echo '=== npm ls ==='; npm ls --depth=0 2>&1 || true
} > "$DIAGDIR/npm.txt"
{
  echo '=== python ==='; python3 --version 2>&1 || true; python3 -m pip check 2>&1 || true
  [[ -x backend/.venv/bin/python ]] && backend/.venv/bin/python -m pip check 2>&1 || true
} > "$DIAGDIR/python.txt"
{
  echo '=== pytest collection ===';
  if [[ -x backend/.venv/bin/pytest ]]; then backend/.venv/bin/pytest --collect-only -q 2>&1 || true; elif command -v pytest >/dev/null 2>&1; then pytest --collect-only -q 2>&1 || true; else echo pytest-unavailable; fi
} > "$DIAGDIR/pytest-collection.txt"
git status --short > "$DIAGDIR/git.txt" 2>&1 || true
{
  echo '=== >500M ==='; find . -type f -size +500M -printf '%s %p\n' 2>/dev/null | sort -nr | head -100 || true
  echo; echo '=== logs >50M ==='; find . -type f \( -name '*.log' -o -name '*.out' \) -size +50M -printf '%s %p\n' 2>/dev/null | sort -nr | head -100 || true
} > "$DIAGDIR/artifacts.txt"
{ run_ruflo doctor 2>&1 || true; echo; run_ruflo status 2>&1 || true; } > "$DIAGDIR/ruflo-doctor-status.txt"

END_EPOCH=$(date +%s); DURATION=$((END_EPOCH-START_EPOCH))
cat > "$SUMMARY" <<EOF2
RUFLO MULTI-AGENT ENTERPRISE DEBUG REPORT v15

Project: $PROJECT
Ruflo: $RUFLO_VERSION
Started: $START_TS
Finished: $(date '+%Y-%m-%d %H:%M:%S %Z')
Duration: ${DURATION}s

Configured agents: $total
Workers completed: $completed
Workers failed: $failed
Workers timed out: $timeout

IMPORTANT: Ruflo agent registration/task state and actual Claude Code execution are tracked separately. A Ruflo agent being idle does not by itself mean Claude is not available; actual work is proven by worker PID, exit code and report/log artifacts.

Agent/task mappings:
$(cat "$STATEDIR/agents.tsv")

Artifacts:
Dispatcher log: $MAINLOG
Worker logs: $LOGDIR/
Agent reports: $RESULTDIR/
Ruflo state: $STATEDIR/
Diagnostics: $DIAGDIR/
EOF2

cat > "$DEBUG" <<EOF2
# Ruflo Multi-Agent Enterprise Debug Report v15

## Execution
- Ruflo: \">$RUFLO_VERSION\"
- Project: \">$PROJECT\"
- Configured: $total
- Completed: $completed
- Failed: $failed
- Timed out: $timeout
- Duration: ${DURATION}s

## Important distinction
Ruflo's `agent spawn` registers an agent identity/state. Actual LLM execution is performed by Claude Code workers in this dispatcher. Therefore the report records both layers independently instead of treating `idle` as a failure.

## Worker results

| Agent | Type | Task type | Result |
|---|---|---|---|
EOF2
while IFS=$'\t' read -r name atype ttype aid desc; do
  [[ -z "$name" ]] && continue
  state='UNKNOWN'; [[ -f "$STATEDIR/$name.exit" ]] && state=$(cat "$STATEDIR/$name.exit")
  echo "| $name | $atype | $ttype | $state |" >> "$DEBUG"
done < "$STATEDIR/agents.tsv"
cat >> "$DEBUG" <<EOF2

## Debug artifacts
- Dispatcher: \">$MAINLOG\"
- Results: \">$RESULTDIR\"
- Logs: \">$LOGDIR\"
- Ruflo state: \">$STATEDIR\"
- Diagnostics: \">$DIAGDIR\"
EOF2

python3 - "$JSON" <<PY
import json,datetime
p='$JSON'
data={'report_version':'15','project':'''$PROJECT''','ruflo':'''$RUFLO_VERSION''','generated_at':datetime.datetime.now().astimezone().isoformat(),'configured_agents':$total,'workers_completed':$completed,'workers_failed':$failed,'workers_timed_out':$timeout,'duration_seconds':$DURATION}
open(p,'w').write(json.dumps(data,indent=2))
PY

section 'RUFLO MULTI-AGENT DISPATCH COMPLETE'
pass "Configured: $total | Completed: $completed | Failed: $failed | Timeout: $timeout"
echo "Report : $REPORT"
echo "Summary: $SUMMARY"
echo "Debug  : $DEBUG"
echo "JSON   : $JSON"
echo "Live log: tail -f \"$MAINLOG\""
echo "Agents : ls -lh \"$RESULTDIR\""
