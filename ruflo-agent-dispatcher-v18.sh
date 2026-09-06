#!/usr/bin/env bash
# RUFLO MULTI-AGENT DISPATCHER v18
# Deterministic local Ruflo + real Claude Code workers.
set -u
set -o pipefail

VERSION=v18
PROJECT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
cd "$PROJECT_DIR" || exit 1
TS="$(date '+%Y%m%d_%H%M%S')"
RUN_DIR="$PROJECT_DIR/ruflo-agent-dispatcher-v18-$TS"
mkdir -p "$RUN_DIR"/{agents,tasks,workers,results,logs,state}
LOG="$RUN_DIR/dispatcher.log"
SUMMARY="$RUN_DIR/summary.txt"
JSON="$RUN_DIR/report.json"
DEBUG="$RUN_DIR/DEBUG-REPORT.md"
RUFLO_BIN="$PROJECT_DIR/node_modules/.bin/claude-flow"
CLAUDE_BIN="${CLAUDE_BIN:-$(command -v claude 2>/dev/null || true)}"
RETRIES="${RUFLO_V18_RETRIES:-2}"
TIMEOUT="${RUFLO_V18_TIMEOUT:-900}"
TASK_TIMEOUT="${RUFLO_V18_TASK_TIMEOUT:-300}"
PIDFILE="$RUN_DIR/state/dispatcher.pid"
echo $$ > "$PIDFILE"
trap 'rm -f "$PIDFILE"' EXIT

log(){ printf '[%s] [%s] %s\n' "$(date '+%Y-%m-%d %H:%M:%S')" "$1" "${*:2}" | tee -a "$LOG"; }
pass(){ log PASS "$@"; }; warn(){ log WARN "$@"; }; fail(){ log FAIL "$@"; }; info(){ log INFO "$@"; }

NAMES=(architect researcher code-analyzer security tester reviewer performance qa)
TYPES=(research research review security testing review optimization testing)
PROMPTS=(
'Perform a READ-ONLY software architecture audit. Inspect structure, frontend, backend, services, APIs, data flow, configuration, dependencies, deployment, observability and design risks. Do not modify files. Return complete findings directly.'
'Perform a READ-ONLY repository research audit. Identify frameworks, runtimes, libraries, APIs, MCP configuration, AI/LLM components, databases, infrastructure assumptions and dependency relationships. Do not modify files. Return complete findings directly.'
'Perform a READ-ONLY senior code review. Identify architectural smells, duplicated logic, error handling problems, maintainability issues, unsafe assumptions, API concerns and high-risk code paths. Do not modify files. Return findings with file-path evidence.'
'Perform a READ-ONLY security audit. Inspect authentication, authorization, secrets, command execution, injection risks, network exposure, dependency risks, filesystem access, logging, data protection, MCP/tool boundaries and insecure defaults. Do not exploit or modify anything. Return severity and evidence.'
'Perform a READ-ONLY QA/test audit. Identify test frameworks, existing tests, missing coverage, critical flows, integration boundaries, failure modes, CI/CD checks and recommended tests. Do not modify files. Return complete findings.'
'Perform a READ-ONLY independent technical review. Identify inconsistencies, fragile integrations, operational risks, documentation gaps and deployment concerns. Do not modify files. Return complete findings.'
'Perform a READ-ONLY performance audit. Inspect likely CPU, memory, I/O, database, network, frontend, backend, LLM, vector-search, concurrency and scalability bottlenecks. Do not run destructive workloads or modify files. Return findings.'
'Perform a READ-ONLY release readiness audit. Inspect build configuration, package manifests, environment handling, Docker/Kubernetes/deployment files, startup paths, health checks, logging, monitoring and rollback assumptions. Do not modify files. Return findings.'
)

log INFO "Ruflo Dispatcher $VERSION started"
log INFO "Project: $PROJECT_DIR"
log INFO "Run directory: $RUN_DIR"

for c in bash node npm npx git python3 jq; do
  p="$(command -v "$c" 2>/dev/null || true)"
  [[ -n "$p" ]] && pass "$c: $p" || warn "$c not found"
done

[[ -n "$CLAUDE_BIN" ]] || { fail 'Claude Code not found'; exit 1; }
pass "Claude: $CLAUDE_BIN"
"$CLAUDE_BIN" --version 2>&1 | tee "$RUN_DIR/state/claude-version.txt" | tee -a "$LOG" >/dev/null || true

if [[ ! -x "$RUFLO_BIN" ]]; then
  fail "Local Ruflo binary not found: $RUFLO_BIN"
  echo 'Install exactly with: npm install --save-dev claude-flow@3.38.12 --save-exact'
  exit 1
fi
RUFLO_VERSION="$($RUFLO_BIN --version 2>&1 || true)"
printf '%s\n' "$RUFLO_VERSION" > "$RUN_DIR/state/ruflo-version.txt"
if ! grep -Eq '3\.38\.12' <<< "$RUFLO_VERSION"; then
  fail "Expected Ruflo 3.38.12; got: $RUFLO_VERSION"
  echo 'Restore with: npm install --save-dev claude-flow@3.38.12 --save-exact'
  exit 1
fi
pass "Ruflo pinned: $RUFLO_VERSION"

{
 echo "Project: $PROJECT_DIR"
 echo "Branch: $(git branch --show-current 2>/dev/null || echo unknown)"
 echo "Commit: $(git rev-parse --short HEAD 2>/dev/null || echo unknown)"
 echo; echo 'Top-level:'
 find . -maxdepth 1 -mindepth 1 -printf '%f\n' 2>/dev/null | sort
 echo; echo 'Manifests:'
 find . -maxdepth 4 -type f \( -name package.json -o -name pyproject.toml -o -name requirements.txt -o -name Dockerfile -o -name docker-compose.yml -o -name docker-compose.yaml \) -not -path './node_modules/*' -print 2>/dev/null | sort
} > "$RUN_DIR/state/project-snapshot.txt"

# Ruflo state is orchestration metadata only; real execution below is Claude Code.
for i in "${!NAMES[@]}"; do
  n="${NAMES[$i]}"; t="${TYPES[$i]}"; d="${PROMPTS[$i]}"
  if "$RUFLO_BIN" agent spawn -t "$t" > "$RUN_DIR/agents/$n-spawn.txt" 2>&1; then
    id="$(grep -Eo 'agent-[0-9]+-[A-Za-z0-9]+' "$RUN_DIR/agents/$n-spawn.txt" | tail -1 || true)"
    echo "${id:-none}" > "$RUN_DIR/state/$n.agent"
    pass "$n agent ${id:-created}"
  else
    echo none > "$RUN_DIR/state/$n.agent"; warn "$n agent spawn failed"
  fi
  if "$RUFLO_BIN" task create -t "$t" -d "$d" -p high --timeout "$TASK_TIMEOUT" > "$RUN_DIR/tasks/$n-task.txt" 2>&1; then
    tid="$(grep -Eo 'task-[0-9]+-[A-Za-z0-9]+' "$RUN_DIR/tasks/$n-task.txt" | tail -1 || true)"
    echo "${tid:-none}" > "$RUN_DIR/state/$n.task"
    pass "$n task ${tid:-created}"
    aid="$(cat "$RUN_DIR/state/$n.agent")"
    [[ "$aid" != none && -n "$aid" && -n "$tid" ]] && "$RUFLO_BIN" task assign "$tid" --agent "$aid" >> "$RUN_DIR/tasks/$n-task.txt" 2>&1 || true
  else
    echo none > "$RUN_DIR/state/$n.task"; warn "$n task creation failed"
  fi
  printf '%s\n' "$d" > "$RUN_DIR/agents/$n.prompt"
done

run_worker(){
  local i="$1" n="${NAMES[$1]}" prompt="${PROMPTS[$1]}" out="$RUN_DIR/results/${NAMES[$1]}.md"
  local so="$RUN_DIR/workers/${NAMES[$1]}.stdout" se="$RUN_DIR/workers/${NAMES[$1]}.stderr" rc=1 attempt=1
  local full="You are worker '$n' in a controlled repository audit. READ-ONLY CONTRACT: do not create, edit, delete, rename or move files; do not install packages; do not run npm audit fix, git commit/reset/checkout, sudo, or destructive commands. Inspect safely and return COMPLETE findings directly in your response. Repository: $PROJECT_DIR. Assignment: $prompt"
  while (( attempt <= RETRIES + 1 )); do
    info "$n Claude attempt $attempt/$((RETRIES+1))"
    : > "$so"; : > "$se"
    if command -v timeout >/dev/null 2>&1; then
      timeout --signal=TERM --kill-after=15 "$TIMEOUT" "$CLAUDE_BIN" -p "$full" --output-format text > "$so" 2> "$se"; rc=$?
    else
      "$CLAUDE_BIN" -p "$full" --output-format text > "$so" 2> "$se"; rc=$?
    fi
    cp "$so" "$out" 2>/dev/null || true
    if [[ $rc -eq 0 && -s "$so" ]] && ! grep -Eqi 'empty or malformed response|proxy or gateway intercepting' "$so"; then
      printf '%s\n' 0 > "$RUN_DIR/state/$n.exit"; pass "$n completed"; return 0
    fi
    { echo "attempt=$attempt exit=$rc"; echo '--- stdout ---'; tail -40 "$so"; echo '--- stderr ---'; tail -40 "$se"; } > "$RUN_DIR/workers/$n.attempt-$attempt.txt"
    warn "$n failed (exit $rc); retrying when attempts remain"
    (( attempt <= RETRIES )) && sleep $((attempt*5))
    attempt=$((attempt+1))
  done
  printf '%s\n' "$rc" > "$RUN_DIR/state/$n.exit"
  { echo "# $n"; echo; echo '**STATUS: FAILED**'; echo; echo "Exit code: $rc"; echo; echo '## stdout'; cat "$so"; echo; echo '## stderr'; cat "$se"; } > "$out"
  fail "$n failed after retries"; return 1
}

pids=(); count=0
for i in "${!NAMES[@]}"; do
  run_worker "$i" > "$RUN_DIR/logs/${NAMES[$i]}.log" 2>&1 &
  pids[$i]=$!; count=$((count+1)); info "${NAMES[$i]} real Claude worker PID=${pids[$i]}"
done

completed=0; failed=0
for i in "${!NAMES[@]}"; do
  if wait "${pids[$i]}"; then completed=$((completed+1)); else failed=$((failed+1)); fi
done

{
 echo "# Ruflo Multi-Agent Dispatcher v18"
 echo; echo "Project: $PROJECT_DIR"; echo "Run: $TS"; echo "Ruflo: $RUFLO_VERSION"
 echo "Configured: $count"; echo "Completed: $completed"; echo "Failed: $failed"
 echo; echo '## Workers'
 for n in "${NAMES[@]}"; do
   echo "- $n: exit=$(cat "$RUN_DIR/state/$n.exit" 2>/dev/null || echo unknown), agent=$(cat "$RUN_DIR/state/$n.agent" 2>/dev/null || echo none), task=$(cat "$RUN_DIR/state/$n.task" 2>/dev/null || echo none)"
 done
} > "$SUMMARY"

python3 - "$JSON" "$PROJECT_DIR" "$RUN_DIR" "$RUFLO_VERSION" "$count" "$completed" "$failed" <<'PY'
import json,sys,os
p,project,run,ruflo,count,completed,failed=sys.argv[1:]
names=['architect','researcher','code-analyzer','security','tester','reviewer','performance','qa']
workers=[]
for n in names:
    ep=os.path.join(run,'state',n+'.exit')
    rc=None
    if os.path.exists(ep):
        try: rc=int(open(ep).read().strip())
        except: pass
    workers.append({'name':n,'exit_code':rc,'success':rc==0,'result':f'results/{n}.md','log':f'logs/{n}.log'})
json.dump({'version':'v18','project':project,'run_directory':run,'ruflo':ruflo,'configured':int(count),'completed':int(completed),'failed':int(failed),'workers':workers},open(p,'w'),indent=2)
PY

{
 echo '# DEBUG REPORT'; echo; cat "$RUN_DIR/state/ruflo-version.txt"; cat "$RUN_DIR/state/claude-version.txt"; echo
 echo '## Snapshot'; cat "$RUN_DIR/state/project-snapshot.txt"; echo
 echo '## Worker logs'; for f in "$RUN_DIR/logs"/*.log; do [[ -f "$f" ]] && { echo; echo "### $f"; cat "$f"; }; done
} > "$DEBUG"

cat <<EOF
============================================================
RUFLO MULTI-AGENT DISPATCHER v18 COMPLETE
============================================================
Run directory : $RUN_DIR
Summary       : $SUMMARY
Debug         : $DEBUG
JSON          : $JSON
Results       : $RUN_DIR/results
Live log      : $LOG
Completed     : $completed
Failed        : $failed
============================================================
EOF
(( failed == 0 ))
