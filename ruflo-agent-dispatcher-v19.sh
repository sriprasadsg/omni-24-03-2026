#!/usr/bin/env bash
# RUFLO MULTI-AGENT DISPATCHER v19
# Real Claude workers; Ruflo metadata is optional and never execution proof.
set -u
set -o pipefail

VERSION="v19"
PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$PROJECT_DIR" || exit 1

STAMP="$(date '+%Y%m%d_%H%M%S')"
RUN_DIR="$PROJECT_DIR/ruflo-agent-dispatcher-${VERSION}-${STAMP}"
RESULTS_DIR="$RUN_DIR/results"
LOGS_DIR="$RUN_DIR/logs"
STATE_DIR="$RUN_DIR/state"
mkdir -p "$RESULTS_DIR" "$LOGS_DIR" "$STATE_DIR"

DISPATCHER_LOG="$RUN_DIR/dispatcher.log"
SUMMARY="$RUN_DIR/summary.txt"
DEBUG_REPORT="$RUN_DIR/DEBUG-REPORT.md"
REPORT_JSON="$RUN_DIR/report.json"

WORKER_TIMEOUT="${RUFLO_WORKER_TIMEOUT:-600}"
MAX_PARALLEL="${RUFLO_MAX_PARALLEL:-8}"

log() {
    local level="$1"; shift
    printf '[%s] [%s] %s\n' "$(date '+%Y-%m-%d %H:%M:%S')" "$level" "$*" | tee -a "$DISPATCHER_LOG"
}

have() { command -v "$1" >/dev/null 2>&1; }

log INFO "Ruflo Dispatcher $VERSION started"
log INFO "Project: $PROJECT_DIR"
log INFO "Run directory: $RUN_DIR"

for cmd in bash node npm npx git python3 jq; do
    if have "$cmd"; then
        log PASS "$cmd: $(command -v "$cmd")"
    else
        log WARN "$cmd: not found"
    fi
done

if ! have claude; then
    log FAIL "Claude Code not found"
    exit 1
fi

CLAUDE_BIN="$(command -v claude)"
log PASS "Claude: $CLAUDE_BIN"
claude --version 2>&1 | tee -a "$DISPATCHER_LOG"

# Ruflo is diagnostic/coordination only. Never download a package via npx.
if have ruflo; then
    log PASS "Ruflo: $(ruflo --version 2>/dev/null | head -1 || true)"
elif [ -x "$PROJECT_DIR/node_modules/.bin/ruflo" ]; then
    log PASS "Local Ruflo: $("$PROJECT_DIR/node_modules/.bin/ruflo" --version 2>/dev/null | head -1 || true)"
else
    log WARN "Ruflo binary unavailable; continuing with direct Claude workers"
fi

if [ -f "$PROJECT_DIR/node_modules/claude-flow/package.json" ]; then
    CF_VERSION="$(node -p "require('./node_modules/claude-flow/package.json').version" 2>/dev/null || true)"
    log INFO "Local claude-flow package: ${CF_VERSION:-unknown}"
fi

{
    echo "=== PROJECT SNAPSHOT ==="
    printf 'Files: '
    find "$PROJECT_DIR" -type f \
      -not -path "$PROJECT_DIR/.git/*" \
      -not -path "$PROJECT_DIR/node_modules/*" \
      -not -path "$PROJECT_DIR/ruflo-agent-dispatcher-*/*" 2>/dev/null | wc -l
    [ -f package.json ] && echo "package.json: present"
    [ -d frontend ] && echo "frontend/: present"
    [ -d backend ] && echo "backend/: present"
    [ -d src ] && echo "src/: present"
} > "$RUN_DIR/project-snapshot.txt"

# Keep these prompts deliberately short. Claude reads the repository itself.
WORKERS=(
"architect|Inspect repo read-only. Summarize architecture, components, data flow, and risks. Do not modify files."
"researcher|Inspect repo read-only. Identify technologies, dependencies, integrations, and purpose. Do not modify files."
"code-analyzer|Inspect repo read-only. Identify important modules, APIs, and code-quality risks. Do not modify files."
"security|Inspect repo read-only. Find security risks, secrets exposure, unsafe configs, and dependency concerns. Do not modify files."
"tester|Inspect repo read-only. Identify tests, coverage gaps, test commands, and testing risks. Do not modify files."
"reviewer|Inspect repo read-only. Give a senior engineering review with highest-priority issues. Do not modify files."
"performance|Inspect repo read-only. Identify performance bottlenecks and scalability concerns. Do not modify files."
"qa|Inspect repo read-only. Assess reliability, deployment readiness, observability, and quality risks. Do not modify files."
)

run_worker() {
    local name="$1"
    local prompt="$2"
    local out="$RESULTS_DIR/${name}.md"
    local err="$LOGS_DIR/${name}.stderr.log"
    local rcfile="$STATE_DIR/${name}.exit"
    local promptfile="$STATE_DIR/${name}.prompt"

    printf '%s\n' "$prompt" > "$promptfile"
    log INFO "$name worker starting"

    # Only a compact prompt is passed. No repository contents are embedded.
    (
      cd "$PROJECT_DIR" || exit 1
      timeout --signal=TERM --kill-after=15s "$WORKER_TIMEOUT" \
        "$CLAUDE_BIN" -p "$prompt" --output-format text
    ) >"$out" 2>"$err"

    local rc=$?
    printf '%s\n' "$rc" > "$rcfile"

    if [ "$rc" -eq 0 ] && [ -s "$out" ]; then
        log PASS "$name completed ($(wc -c < "$out") bytes)"
    elif [ "$rc" -eq 124 ]; then
        log WARN "$name timed out"
        printf '\n[WORKER TIMEOUT]\n' >> "$out"
    else
        log FAIL "$name failed rc=$rc"
        {
          echo "[WORKER FAILED: exit $rc]"
          echo
          echo "STDERR:"
          cat "$err" 2>/dev/null || true
        } >> "$out"
    fi
}

PIDS=()
NAMES=()

for entry in "${WORKERS[@]}"; do
    name="${entry%%|*}"
    prompt="${entry#*|}"
    run_worker "$name" "$prompt" &
    pid=$!
    PIDS+=("$pid")
    NAMES+=("$name")
    echo "$pid" > "$STATE_DIR/${name}.pid"
    log INFO "$name real Claude worker PID=$pid"

    if [ "${#PIDS[@]}" -ge "$MAX_PARALLEL" ]; then
        break
    fi
done

for pid in "${PIDS[@]}"; do
    wait "$pid" 2>/dev/null || true
done

completed=0
failed=0
timeout_count=0

for name in "${NAMES[@]}"; do
    rc="$(cat "$STATE_DIR/${name}.exit" 2>/dev/null || echo 999)"
    if [ "$rc" -eq 0 ] && [ -s "$RESULTS_DIR/${name}.md" ]; then
        completed=$((completed + 1))
    elif [ "$rc" -eq 124 ]; then
        timeout_count=$((timeout_count + 1))
    else
        failed=$((failed + 1))
    fi
done

{
    echo "RUFLO MULTI-AGENT DISPATCHER $VERSION"
    echo "Project: $PROJECT_DIR"
    echo "Run: $RUN_DIR"
    echo "Workers: ${#NAMES[@]}"
    echo "Completed: $completed"
    echo "Failed: $failed"
    echo "Timeout: $timeout_count"
    echo
    for name in "${NAMES[@]}"; do
        echo "===== $name ====="
        cat "$RESULTS_DIR/${name}.md" 2>/dev/null || echo "No result"
        echo
    done
} > "$DEBUG_REPORT"

cat > "$SUMMARY" <<EOF
RUFLO DISPATCHER $VERSION
Project   : $PROJECT_DIR
Run       : $RUN_DIR
Completed : $completed
Failed    : $failed
Timeout   : $timeout_count
Workers   : ${#NAMES[@]}
EOF

cat > "$REPORT_JSON" <<EOF
{
  "version": "$VERSION",
  "project": "$PROJECT_DIR",
  "run_directory": "$RUN_DIR",
  "workers": ${#NAMES[@]},
  "completed": $completed,
  "failed": $failed,
  "timeout": $timeout_count,
  "execution_model": "direct-claude-code",
  "ruflo_execution_required": false
}
EOF

log INFO "Dispatcher complete: completed=$completed failed=$failed timeout=$timeout_count"

echo
echo "============================================================"
echo "RUFLO MULTI-AGENT DISPATCHER $VERSION COMPLETE"
echo "============================================================"
echo "Run directory : $RUN_DIR"
echo "Summary       : $SUMMARY"
echo "Debug         : $DEBUG_REPORT"
echo "JSON          : $REPORT_JSON"
echo "Results       : $RESULTS_DIR"
echo "Live log      : $DISPATCHER_LOG"
echo "Completed     : $completed"
echo "Failed        : $failed"
echo "Timeout       : $timeout_count"
echo "============================================================"
