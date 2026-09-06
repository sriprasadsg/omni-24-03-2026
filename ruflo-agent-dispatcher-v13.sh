#!/usr/bin/env bash
# Ruflo Agent Dispatcher v13
# Enterprise multi-agent orchestration/validation harness.
#
# Default: runs in the background and writes a timestamped report.
# Foreground: ./ruflo-agent-dispatcher-v13.sh --foreground
#
# Target: Ruflo / Claude Flow v3.x (tested command design for v3.38.12).
# It prefers the working project runtime and automatically installs Ruflo if
# the runtime cannot be executed.

set -u
set -o pipefail

PROJECT="${RUFLO_PROJECT:-$(pwd)}"
RUFLO_VERSION="${RUFLO_VERSION:-3.38.12}"
RUN_ID="$(date +%Y%m%d_%H%M%S)"
REPORT_DIR="$PROJECT/ruflo-agent-dispatch-v13-$RUN_ID"
LOG="$REPORT_DIR/dispatcher.log"
SUMMARY="$REPORT_DIR/summary.txt"
JSON="$REPORT_DIR/summary.json"
AGENT_LOG="$REPORT_DIR/agents.log"
TASKS_LOG="$REPORT_DIR/tasks.log"
TASKS_RAW="$REPORT_DIR/tasks-raw.tsv"
SWARM_LOG="$REPORT_DIR/swarm.log"
RUNTIME_LOG="$REPORT_DIR/runtime.log"
PYTEST_LOG="$REPORT_DIR/pytest.log"
NPM_LOG="$REPORT_DIR/npm.log"
STATUS_FILE="$REPORT_DIR/status.txt"
PID_FILE="$REPORT_DIR/dispatcher.pid"
FOREGROUND=0
MAX_AGENTS="${RUFLO_MAX_AGENTS:-8}"
TASK_TIMEOUT="${RUFLO_TASK_TIMEOUT:-30}"

mkdir -p "$REPORT_DIR"

if [[ "${1:-}" == "--foreground" ]]; then
    FOREGROUND=1
fi

# Background wrapper. Use --foreground for debugging the dispatcher itself.
if [[ "$FOREGROUND" -eq 0 && "${RUFLO_DISPATCH_CHILD:-0}" != "1" ]]; then
    export RUFLO_DISPATCH_CHILD=1
    nohup "$0" --foreground </dev/null >"$REPORT_DIR/background-console.log" 2>&1 &
    CHILD_PID=$!
    echo "$CHILD_PID" > "$PID_FILE"
    cat > "$STATUS_FILE" <<EOT
RUNNING
PID=$CHILD_PID
REPORT=$REPORT_DIR
STARTED=$(date -Is)
EOT
    echo "RUFLO AGENT DISPATCHER v13 started in background"
    echo "PID    : $CHILD_PID"
    echo "Report : $REPORT_DIR"
    echo
    echo "Follow: tail -f '$REPORT_DIR/dispatcher.log'"
    exit 0
fi

exec > >(tee -a "$LOG") 2>&1
echo "$$" > "$PID_FILE"
cat > "$STATUS_FILE" <<EOT
RUNNING
PID=$$
REPORT=$REPORT_DIR
STARTED=$(date -Is)
EOT

finish() {
    rc=$?
    state="COMPLETED"
    [[ $rc -ne 0 ]] && state="FAILED"
    cat > "$STATUS_FILE" <<EOT
$state
PID=$$
REPORT=$REPORT_DIR
FINISHED=$(date -Is)
EXIT_CODE=$rc
EOT
}
trap finish EXIT

have() { command -v "$1" >/dev/null 2>&1; }

extract_first_id() {
    grep -oE '\b(task|agent|swarm)-[A-Za-z0-9._-]+\b' | head -1
}

if [[ ! -d "$PROJECT" || ! -f "$PROJECT/package.json" ]]; then
    echo "[FAIL] Project directory/package.json not found: $PROJECT"
    exit 2
fi
cd "$PROJECT" || exit 2

printf '%s\n' "============================================================"
printf '%s\n' "RUFLO AGENT DISPATCHER v13"
printf '%s\n' "============================================================"
echo "Project : $PROJECT"
echo "Date    : $(date)"
echo "Host    : $(hostname)"
echo "PID     : $$"
echo "Target  : Ruflo v$RUFLO_VERSION"
echo "Report  : $REPORT_DIR"
printf '%s\n' "============================================================"

echo
echo "1. TOOLCHAIN"
for c in bash node npm npx git python3 jq sed awk grep find; do
    if have "$c"; then echo "[PASS] $c: $(command -v "$c")"; else echo "[FAIL] Missing: $c"; fi
done

echo
echo "2. RUFLO RUNTIME DISCOVERY"
RUFLO_MODE=""
RUFLO_VERSION_DETECTED="unknown"

if npx --no-install claude-flow --version >"$RUNTIME_LOG" 2>&1; then
    RUFLO_MODE="project-claude-flow"
    RUFLO_CMD=(npx --no-install claude-flow)
    RUFLO_VERSION_DETECTED="$(npx --no-install claude-flow --version 2>/dev/null | tail -1)"
    echo "[PASS] Existing project runtime: $RUFLO_VERSION_DETECTED"
fi

if [[ -z "$RUFLO_MODE" ]]; then
    echo "[WARN] Working Ruflo runtime not found; installing ruflo@$RUFLO_VERSION"
    if npm install --no-save --no-package-lock "ruflo@$RUFLO_VERSION" >"$RUNTIME_LOG" 2>&1 && \
       npx --no-install ruflo --version >>"$RUNTIME_LOG" 2>&1; then
        RUFLO_MODE="local-ruflo"
        RUFLO_CMD=(npx --no-install ruflo)
        RUFLO_VERSION_DETECTED="$(npx --no-install ruflo --version 2>/dev/null | tail -1)"
        echo "[PASS] Ruflo installed: $RUFLO_VERSION_DETECTED"
    fi
fi

if [[ -z "$RUFLO_MODE" ]]; then
    echo "[WARN] Local install failed; using temporary npx Ruflo package"
    if npx --yes "ruflo@$RUFLO_VERSION" --version >"$RUNTIME_LOG" 2>&1; then
        RUFLO_MODE="temporary-ruflo"
        RUFLO_CMD=(npx --yes "ruflo@$RUFLO_VERSION")
        RUFLO_VERSION_DETECTED="$("${RUFLO_CMD[@]}" --version 2>/dev/null | tail -1)"
        echo "[PASS] Temporary Ruflo runtime: $RUFLO_VERSION_DETECTED"
    fi
fi

if [[ -z "$RUFLO_MODE" ]]; then
    echo "[FAIL] Ruflo could not be installed or executed. See $RUNTIME_LOG"
    exit 10
fi

# Show supported commands; this is useful when v3 command surfaces differ.
"${RUFLO_CMD[@]}" --help >"$REPORT_DIR/ruflo-help.txt" 2>&1 || true
"${RUFLO_CMD[@]}" task --help >"$REPORT_DIR/task-help.txt" 2>&1 || true
"${RUFLO_CMD[@]}" agent --help >"$REPORT_DIR/agent-help.txt" 2>&1 || true

# Optional repair/daemon bootstrap.
echo
echo "3. RUFLO BOOTSTRAP"
if "${RUFLO_CMD[@]}" doctor --help >/dev/null 2>&1; then
    if "${RUFLO_CMD[@]}" doctor --fix >>"$RUNTIME_LOG" 2>&1; then
        echo "[PASS] doctor --fix"
    else
        echo "[WARN] doctor --fix returned non-zero; continuing"
    fi
fi

if "${RUFLO_CMD[@]}" daemon status >>"$RUNTIME_LOG" 2>&1; then
    echo "[PASS] daemon available"
else
    if "${RUFLO_CMD[@]}" daemon start >>"$RUNTIME_LOG" 2>&1; then
        echo "[PASS] daemon started"
    else
        echo "[WARN] daemon could not be started"
    fi
fi

echo
echo "4. SWARM INITIALIZATION"
if "${RUFLO_CMD[@]}" swarm init --topology hierarchical --max-agents "$MAX_AGENTS" --strategy specialized >"$SWARM_LOG" 2>&1; then
    echo "[PASS] hierarchical swarm initialized"
else
    echo "[WARN] hierarchical swarm init failed; trying hierarchical-mesh"
    if "${RUFLO_CMD[@]}" swarm init --topology hierarchical-mesh --max-agents "$MAX_AGENTS" --strategy specialized >>"$SWARM_LOG" 2>&1; then
        echo "[PASS] hierarchical-mesh swarm initialized"
    else
        echo "[WARN] swarm initialization unavailable; continuing with agent/task mode"
    fi
fi

# Eight distinct roles. Existing named agents are reused where possible.
declare -a TYPES=(coordinator architect researcher backend frontend security-architect tester reviewer)
declare -a NAMES=(v13-coordinator v13-architect v13-researcher v13-backend v13-frontend v13-security v13-tester v13-reviewer)
declare -a TASK_TYPES=(coordination analysis research analysis analysis security testing review)
declare -a DESCS=(
"Coordinate this validation run. Inspect the project and identify the highest-risk findings. Do not modify files."
"Analyze complete project architecture, modules, data flow, configuration, and architectural risks. Do not modify files."
"Analyze dependencies, integrations, package versions, MCP/runtime assumptions, and compatibility risks. Do not modify files."
"Analyze backend Python services, APIs, database integration, imports, contracts, and runtime risks. Do not modify files."
"Analyze frontend code, build configuration, dependencies, UI structure, and API integration. Do not modify files."
"Perform a defensive security review for secrets exposure, unsafe configuration, dependency risk, auth concerns, and insecure patterns. Do not exploit or modify files."
"Run or inspect appropriate tests and separate genuine application failures from environment/network/fixture/collection diagnostics. Do not modify source files."
"Perform an independent enterprise code/configuration review and produce prioritized findings. Do not modify files."
)

echo -e "agent_name\ttype\ttask_type\ttask_id\tstate" > "$TASKS_RAW"

echo
echo "5. AGENT DISCOVERY / SPAWN"
"${RUFLO_CMD[@]}" agent list >"$REPORT_DIR/agents-before.txt" 2>&1 || true

for i in "${!NAMES[@]}"; do
    name="${NAMES[$i]}"
    type="${TYPES[$i]}"
    if grep -Fq "$name" "$REPORT_DIR/agents-before.txt"; then
        echo "[PASS] Reusing $name"
        continue
    fi
    if "${RUFLO_CMD[@]}" agent spawn --type "$type" --name "$name" >"$REPORT_DIR/spawn-$name.txt" 2>&1; then
        echo "[PASS] Spawned $name ($type)"
    else
        echo "[WARN] Spawn failed for $name"
        cat "$REPORT_DIR/spawn-$name.txt" >> "$AGENT_LOG"
    fi
done

"${RUFLO_CMD[@]}" agent list >"$REPORT_DIR/agents-after-spawn.txt" 2>&1 || true
cat "$REPORT_DIR/agents-after-spawn.txt"

echo
echo "6. AUTOMATIC TASK CREATION + ASSIGNMENT"
: > "$TASKS_LOG"

# Create and assign one task per role in parallel.
dispatch_one() {
    local i="$1" name type ttype desc out task_id
    name="${NAMES[$i]}"; type="${TYPES[$i]}"; ttype="${TASK_TYPES[$i]}"; desc="${DESCS[$i]}"
    out="$REPORT_DIR/task-$name.txt"

    echo "===== $name =====" > "$out"
    echo "TYPE=$type" >> "$out"
    echo "TASK_TYPE=$ttype" >> "$out"
    echo "DESCRIPTION=$desc" >> "$out"

    if "${RUFLO_CMD[@]}" task create --type "$ttype" --description "$desc" >>"$out" 2>&1; then
        task_id="$(extract_first_id < "$out" || true)"
        if [[ -n "$task_id" ]]; then
            echo "[PASS] Created $task_id for $name" >> "$TASKS_LOG"
            if "${RUFLO_CMD[@]}" task assign "$task_id" --agent "$name" >>"$out" 2>&1; then
                echo "[PASS] Assigned $task_id -> $name" >> "$TASKS_LOG"
                printf '%s\t%s\t%s\t%s\tASSIGNED\n' "$name" "$type" "$ttype" "$task_id" >> "$TASKS_RAW"
            else
                echo "[WARN] Assignment failed: $task_id -> $name" >> "$TASKS_LOG"
                printf '%s\t%s\t%s\t%s\tASSIGN_FAILED\n' "$name" "$type" "$ttype" "$task_id" >> "$TASKS_RAW"
            fi
        else
            echo "[WARN] Task created for $name but task ID was not parsed" >> "$TASKS_LOG"
            printf '%s\t%s\t%s\t%s\tCREATE_UNPARSED\n' "$name" "$type" "$ttype" UNKNOWN >> "$TASKS_RAW"
        fi
    else
        echo "[WARN] Task creation failed for $name" >> "$TASKS_LOG"
        printf '%s\t%s\t%s\t%s\tCREATE_FAILED\n' "$name" "$type" "$ttype" UNKNOWN >> "$TASKS_RAW"
    fi
}

pids=()
for i in "${!NAMES[@]}"; do dispatch_one "$i" & pids+=("$!"); done
for p in "${pids[@]}"; do wait "$p" || true; done
cat "$TASKS_LOG"

# ---------------------------------------------------------------------------
# Monitoring. This validates orchestration state; it cannot make an LLM agent
# execute code by itself. Ruflo v3 coordinates/tracks workers; the actual work
# requires a connected worker runtime such as Claude Code/Task.
# ---------------------------------------------------------------------------
echo
echo "7. TASK / AGENT MONITOR"
"${RUFLO_CMD[@]}" agent list >"$REPORT_DIR/agents-after-dispatch.txt" 2>&1 || true
"${RUFLO_CMD[@]}" task list --all >"$REPORT_DIR/tasks-after-dispatch.txt" 2>&1 || \
"${RUFLO_CMD[@]}" task list >"$REPORT_DIR/tasks-after-dispatch.txt" 2>&1 || true
"${RUFLO_CMD[@]}" swarm status >"$REPORT_DIR/swarm-status.txt" 2>&1 || true

cat "$REPORT_DIR/agents-after-dispatch.txt"
cat "$REPORT_DIR/tasks-after-dispatch.txt"

DEADLINE=$((SECONDS + TASK_TIMEOUT * 60))
LAST=""
while (( SECONDS < DEADLINE )); do
    "${RUFLO_CMD[@]}" task list --all >"$REPORT_DIR/tasks-current.txt" 2>&1 || \
    "${RUFLO_CMD[@]}" task list >"$REPORT_DIR/tasks-current.txt" 2>&1 || true
    current="$(cat "$REPORT_DIR/tasks-current.txt" 2>/dev/null || true)"
    hash="$(printf '%s' "$current" | sha256sum | awk '{print $1}')"
    if [[ "$hash" != "$LAST" ]]; then
        echo "===== $(date -Is) =====" >> "$TASKS_LOG"
        printf '%s\n' "$current" >> "$TASKS_LOG"
        LAST="$hash"
    fi
    if [[ -n "$current" ]] && ! printf '%s\n' "$current" | grep -Eiq 'pending|running|in.progress|processing|assigned|working'; then
        break
    fi
    sleep 5
done

echo "[INFO] Monitoring window finished."

# Capture health, metrics, and logs.
echo
echo "8. AGENT EVIDENCE"
"${RUFLO_CMD[@]}" agent health >"$REPORT_DIR/agent-health.txt" 2>&1 || true
"${RUFLO_CMD[@]}" agent metrics >"$REPORT_DIR/agent-metrics.txt" 2>&1 || true
while IFS=$'\t' read -r name type ttype task_id state; do
    [[ "$name" == "agent_name" ]] && continue
    safe="$(printf '%s' "$name" | tr '/ ' '__')"
    "${RUFLO_CMD[@]}" agent logs "$name" >"$REPORT_DIR/agent-log-$safe.txt" 2>&1 || true
done < "$TASKS_RAW"

# Project diagnostics.
echo
echo "9. PROJECT DIAGNOSTICS"
if npm ls --depth=0 >"$NPM_LOG" 2>&1; then echo "[PASS] npm dependency tree"; else echo "[WARN] npm dependency diagnostics"; fi
if [[ -x "$PROJECT/backend/venv/bin/python" ]]; then PY="$PROJECT/backend/venv/bin/python"; else PY="$(command -v python3)"; fi
if "$PY" -m pip check >"$REPORT_DIR/pip-check.txt" 2>&1; then echo "[PASS] pip check"; else echo "[WARN] pip check"; fi
if [[ -f pytest.ini || -f pyproject.toml || -f setup.cfg ]]; then "$PY" -m pytest -q --collect-only >"$PYTEST_LOG" 2>&1 || true; fi

# Final state.
echo
echo "10. FINAL STATE"
"${RUFLO_CMD[@]}" agent list >"$REPORT_DIR/agents-final.txt" 2>&1 || true
"${RUFLO_CMD[@]}" task list --all >"$REPORT_DIR/tasks-final.txt" 2>&1 || \
"${RUFLO_CMD[@]}" task list >"$REPORT_DIR/tasks-final.txt" 2>&1 || true
"${RUFLO_CMD[@]}" swarm status >"$REPORT_DIR/swarm-final.txt" 2>&1 || true

spawned="$(grep -c '\[PASS\] Spawned ' "$LOG" 2>/dev/null || true)"
created="$(grep -c '\[PASS\] Created ' "$TASKS_LOG" 2>/dev/null || true)"
assigned="$(grep -c '\[PASS\] Assigned ' "$TASKS_LOG" 2>/dev/null || true)"
failed="$(grep -Eic 'failed|error|not found|unavailable' "$TASKS_LOG" 2>/dev/null || true)"

cat > "$SUMMARY" <<EOT
RUFLO AGENT DISPATCHER v13
Project: $PROJECT
Runtime: $RUFLO_MODE
Ruflo version: $RUFLO_VERSION_DETECTED

Configured roles: ${#NAMES[@]}
Agents spawned this run: $spawned
Tasks created: $created
Tasks assigned: $assigned
Task-log error/warning lines: $failed

NOTE:
Ruflo/Claude Flow v3 is an orchestration/state layer. An "idle" agent is not
necessarily broken; after a task finishes, idle is expected. This script proves
spawn/create/assign/state evidence. Actual LLM/code execution requires a
connected worker runtime (for example Claude Code/Task) capable of executing
those assigned tasks.

REPORT: $REPORT_DIR
Runtime log: $RUNTIME_LOG
Agent log: $AGENT_LOG
Task log: $TASKS_LOG
Agent final state: $REPORT_DIR/agents-final.txt
Task final state: $REPORT_DIR/tasks-final.txt
Swarm final state: $REPORT_DIR/swarm-final.txt
EOT

python3 - "$JSON" <<PY
import json
p = {
  "test": "ruflo-agent-dispatcher-v13",
  "project": r"$PROJECT",
  "runtime": r"$RUFLO_MODE",
  "ruflo_version": r"$RUFLO_VERSION_DETECTED",
  "configured_roles": ${#NAMES[@]},
  "agents_spawned_this_run": int("$spawned" or 0),
  "tasks_created": int("$created" or 0),
  "tasks_assigned": int("$assigned" or 0),
  "task_log_error_lines": int("$failed" or 0),
  "report_directory": r"$REPORT_DIR",
  "idle_after_completion_is_normal": True,
  "actual_worker_execution_requires_connected_worker_runtime": True
}
with open(r"$JSON", "w") as f: json.dump(p, f, indent=2)
PY

echo
echo "============================================================"
echo "RUFLO AGENT DISPATCHER v13 COMPLETE"
echo "============================================================"
cat "$SUMMARY"
echo "============================================================"
