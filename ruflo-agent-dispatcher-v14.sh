#!/usr/bin/env bash

set -u
set -o pipefail

PROJECT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$PROJECT" || exit 1

VERSION="v14"
TIMESTAMP="$(date '+%Y%m%d_%H%M%S')"
REPORT_DIR="$PROJECT/ruflo-agent-dispatcher-${TIMESTAMP}"

mkdir -p "$REPORT_DIR"/{agents,logs,results,diagnostics,state}

MAIN_LOG="$REPORT_DIR/dispatcher.log"
SUMMARY="$REPORT_DIR/summary.txt"
JSON="$REPORT_DIR/report.json"

exec > >(tee -a "$MAIN_LOG") 2>&1

START_EPOCH="$(date +%s)"

echo "============================================================"
echo "RUFLO MULTI-AGENT DISPATCHER $VERSION"
echo "============================================================"
echo "Project : $PROJECT"
echo "Date    : $(date)"
echo "Host    : $(hostname)"
echo "PID     : $$"
echo "Report  : $REPORT_DIR"
echo "============================================================"
echo

###############################################################################
# Helpers
###############################################################################

PASS_COUNT=0
WARN_COUNT=0
FAIL_COUNT=0

pass() {
    PASS_COUNT=$((PASS_COUNT + 1))
    echo "[PASS] $*"
}

warn() {
    WARN_COUNT=$((WARN_COUNT + 1))
    echo "[WARN] $*"
}

fail() {
    FAIL_COUNT=$((FAIL_COUNT + 1))
    echo "[FAIL] $*"
}

run_capture() {
    local outfile="$1"
    shift
    "$@" >"$outfile" 2>&1
    return $?
}

###############################################################################
# Basic environment
###############################################################################

echo "===== ENVIRONMENT ====="

NODE_BIN="$(command -v node || true)"
NPM_BIN="$(command -v npm || true)"
NPX_BIN="$(command -v npx || true)"
CLAUDE_BIN="$(command -v claude || true)"
GIT_BIN="$(command -v git || true)"

echo "Node   : ${NODE_BIN:-NOT FOUND}"
echo "npm    : ${NPM_BIN:-NOT FOUND}"
echo "npx    : ${NPX_BIN:-NOT FOUND}"
echo "Claude : ${CLAUDE_BIN:-NOT FOUND}"
echo "Git    : ${GIT_BIN:-NOT FOUND}"

if [[ -z "$NODE_BIN" || -z "$NPX_BIN" ]]; then
    fail "Node.js/npx unavailable"
    exit 1
fi

if [[ -z "$CLAUDE_BIN" ]]; then
    warn "Claude Code executable not found"
else
    claude --version 2>&1 | tee "$REPORT_DIR/diagnostics/claude-version.txt" || true
fi

node --version 2>&1 | tee "$REPORT_DIR/diagnostics/node-version.txt" || true
npm --version 2>&1 | tee "$REPORT_DIR/diagnostics/npm-version.txt" || true

###############################################################################
# Ruflo wrapper
###############################################################################

RUFLO_CMD=(
    "$NPX_BIN"
    --no-install
    claude-flow
)

echo
echo "===== RUFLO ====="

if "${RUFLO_CMD[@]}" --version >"$REPORT_DIR/diagnostics/ruflo-version.txt" 2>&1; then
    cat "$REPORT_DIR/diagnostics/ruflo-version.txt"
    pass "Ruflo runtime available"
else
    fail "Installed Ruflo runtime unavailable"
    echo
    echo "Ruflo diagnostic:"
    cat "$REPORT_DIR/diagnostics/ruflo-version.txt" || true
    echo
    echo "This script intentionally does NOT install Ruflo automatically."
    echo "Install/fix Ruflo first, then rerun this dispatcher."
    exit 1
fi

###############################################################################
# Ruflo command capability discovery
###############################################################################

echo
echo "===== RUFLO CAPABILITIES ====="

"${RUFLO_CMD[@]}" agent --help \
    >"$REPORT_DIR/diagnostics/agent-help.txt" 2>&1 || true

"${RUFLO_CMD[@]}" task --help \
    >"$REPORT_DIR/diagnostics/task-help.txt" 2>&1 || true

"${RUFLO_CMD[@]}" swarm --help \
    >"$REPORT_DIR/diagnostics/swarm-help.txt" 2>&1 || true

"${RUFLO_CMD[@]}" agent metrics \
    >"$REPORT_DIR/diagnostics/agent-metrics-before.txt" 2>&1 || true

###############################################################################
# Project snapshot
###############################################################################

echo
echo "===== PROJECT SNAPSHOT ====="

{
    echo "Project: $PROJECT"
    echo "Date: $(date)"
    echo
    echo "Git:"
    git status --short 2>&1 || true
    echo
    echo "Package:"
    if [[ -f package.json ]]; then
        node -e 'const p=require("./package.json"); console.log(JSON.stringify({name:p.name,version:p.version,dependencies:p.dependencies,devDependencies:p.devDependencies},null,2))' 2>&1 || true
    fi
    echo
    echo "Disk:"
    df -h "$PROJECT" 2>&1 || true
} >"$REPORT_DIR/diagnostics/project-snapshot.txt"

###############################################################################
# Agent definitions
###############################################################################

declare -a AGENT_TYPES=(
    "architect"
    "researcher"
    "coder"
    "security-auditor"
    "tester"
    "reviewer"
    "performance"
    "qa"
)

declare -a AGENT_NAMES=(
    "ruflo-architect"
    "ruflo-researcher"
    "ruflo-coder"
    "ruflo-security"
    "ruflo-tester"
    "ruflo-reviewer"
    "ruflo-performance"
    "ruflo-qa"
)

declare -a TASK_DESCRIPTIONS=(
    "Analyze project architecture, components, dependencies and major design risks. Read-only. Do not modify source files."
    "Analyze the repository structure, documentation, configuration and implementation patterns. Identify missing or inconsistent components. Read-only. Do not modify source files."
    "Perform a read-only code quality and implementation review. Identify bugs, dead code, risky patterns and maintainability issues. Do not modify source files."
    "Perform a security audit covering authentication, authorization, secrets, MCP configuration, APIs, dependency risks and unsafe configuration. Read-only. Do not modify source files."
    "Run and analyze the project's available tests. Identify failures, collection problems, flaky tests and missing coverage. Do not modify source files."
    "Perform a code review across backend, frontend, APIs and configuration. Identify defects and architectural concerns. Read-only."
    "Analyze performance risks including large files, expensive operations, database usage, concurrency, memory and CPU risks. Read-only."
    "Perform final QA analysis of project health, build/test readiness and integration risks. Read-only."
)

###############################################################################
# Spawn agents
###############################################################################

echo
echo "============================================================"
echo "SPAWNING MULTIPLE RUFLO AGENTS"
echo "============================================================"

declare -a AGENT_IDS=()
declare -a TASK_IDS=()
declare -a WORKER_PIDS=()

for i in "${!AGENT_TYPES[@]}"; do

    TYPE="${AGENT_TYPES[$i]}"
    NAME="${AGENT_NAMES[$i]}"

    SPAWN_LOG="$REPORT_DIR/logs/${NAME}-spawn.log"

    echo
    echo "Spawning: $NAME [$TYPE]"

    if "${RUFLO_CMD[@]}" agent spawn \
        --type "$TYPE" \
        --name "$NAME" \
        >"$SPAWN_LOG" 2>&1; then

        cat "$SPAWN_LOG"

        ID="$(
            grep -Eo 'agent-[0-9]+-[a-z0-9]+' "$SPAWN_LOG" |
            tail -1
        )"

        if [[ -n "$ID" ]]; then
            AGENT_IDS[$i]="$ID"
            pass "$NAME spawned: $ID"
        else
            warn "$NAME spawned but agent ID could not be parsed"
            AGENT_IDS[$i]=""
        fi

    else
        warn "Could not spawn $NAME"
        cat "$SPAWN_LOG" || true
        AGENT_IDS[$i]=""
    fi
done

###############################################################################
# Create tasks
###############################################################################

echo
echo "============================================================"
echo "CREATING RUFLO TASKS"
echo "============================================================"

for i in "${!AGENT_TYPES[@]}"; do

    NAME="${AGENT_NAMES[$i]}"
    TYPE="${AGENT_TYPES[$i]}"
    DESCRIPTION="${TASK_DESCRIPTIONS[$i]}"
    AGENT_ID="${AGENT_IDS[$i]:-}"

    TASK_LOG="$REPORT_DIR/logs/${NAME}-task-create.log"

    echo
    echo "Creating task for $NAME"

    if [[ -n "$AGENT_ID" ]]; then

        if "${RUFLO_CMD[@]}" task create \
            --type "$TYPE" \
            --description "$DESCRIPTION" \
            --assign "$AGENT_ID" \
            --priority normal \
            --timeout 900 \
            >"$TASK_LOG" 2>&1; then

            cat "$TASK_LOG"

            TASK_ID="$(
                grep -Eo 'task-[0-9]+-[a-zA-Z0-9]+' "$TASK_LOG" |
                tail -1
            )"

            if [[ -z "$TASK_ID" ]]; then
                TASK_ID="$(
                    grep -Eo 'task-[a-zA-Z0-9_-]+' "$TASK_LOG" |
                    tail -1
                )"
            fi

            TASK_IDS[$i]="${TASK_ID:-}"

            pass "Task created for $NAME"

        else
            warn "Ruflo task creation failed for $NAME"
            cat "$TASK_LOG" || true
            TASK_IDS[$i]=""
        fi

    else
        warn "No Ruflo agent ID for $NAME"
        TASK_IDS[$i]=""
    fi
done

###############################################################################
# Claude workers
#
# Important:
# Ruflo 3.38.12 CLI reports that actual execution happens through Claude Code
# Agent Tool / claude -p / hive-mind. Therefore we launch independent Claude
# workers here and use Ruflo for orchestration/state visibility.
###############################################################################

echo
echo "============================================================"
echo "STARTING PARALLEL CLAUDE WORKERS"
echo "============================================================"

if [[ -z "$CLAUDE_BIN" ]]; then

    fail "Claude Code executable unavailable; workers cannot execute"

else

    for i in "${!AGENT_TYPES[@]}"; do

        NAME="${AGENT_NAMES[$i]}"
        TYPE="${AGENT_TYPES[$i]}"
        DESCRIPTION="${TASK_DESCRIPTIONS[$i]}"

        WORK_LOG="$REPORT_DIR/logs/${NAME}.log"
        RESULT_FILE="$REPORT_DIR/results/${NAME}.md"

        cat >"$REPORT_DIR/agents/${NAME}.prompt" <<EOF
You are the $TYPE agent in a multi-agent enterprise project test.

Project:
$PROJECT

Mission:
$DESCRIPTION

IMPORTANT:
- Work in READ-ONLY analysis mode.
- Do not modify source code.
- Do not delete files.
- Do not install packages.
- Do not change configuration.
- Do not commit anything.
- Inspect the project carefully.
- Execute safe read-only diagnostics when useful.
- Record concrete evidence.
- Clearly distinguish PASS, WARN and FAIL.
- Identify file paths and relevant commands where useful.

At the end, produce a detailed report containing:

1. Executive Summary
2. What Was Tested
3. Evidence
4. PASS findings
5. WARN findings
6. FAIL findings
7. Recommended Remediation
8. Confidence / limitations

Write the final report to:

$RESULT_FILE
EOF

        echo "Launching $NAME ..."

        (
            START="$(date +%s)"

            "$CLAUDE_BIN" -p \
                "$(cat "$REPORT_DIR/agents/${NAME}.prompt")" \
                --output-format text \
                >"$WORK_LOG" 2>&1

            RC=$?

            END="$(date +%s)"
            ELAPSED=$((END - START))

            {
                echo
                echo "============================================================"
                echo "WORKER RESULT"
                echo "Agent     : $NAME"
                echo "Type      : $TYPE"
                echo "Exit Code : $RC"
                echo "Duration  : ${ELAPSED}s"
                echo "Finished  : $(date)"
                echo "============================================================"
            } >>"$WORK_LOG"

            exit "$RC"

        ) &

        PID=$!
        WORKER_PIDS[$i]="$PID"

        echo "$NAME PID=$PID" \
            | tee "$REPORT_DIR/state/${NAME}.pid"

        pass "$NAME worker launched"
    done
fi

###############################################################################
# Monitor workers
###############################################################################

echo
echo "============================================================"
echo "MONITORING WORKERS"
echo "============================================================"

MONITOR_LOG="$REPORT_DIR/diagnostics/worker-monitor.log"

{
    echo "Worker monitoring started: $(date)"
    echo
} >"$MONITOR_LOG"

while true; do

    RUNNING=0

    for i in "${!AGENT_NAMES[@]}"; do

        NAME="${AGENT_NAMES[$i]}"
        PID="${WORKER_PIDS[$i]:-}"

        [[ -z "$PID" ]] && continue

        if kill -0 "$PID" 2>/dev/null; then
            RUNNING=$((RUNNING + 1))
        fi
    done

    {
        echo "$(date '+%F %T') running_workers=$RUNNING"
    } >>"$MONITOR_LOG"

    if [[ "$RUNNING" -eq 0 ]]; then
        break
    fi

    sleep 5
done

###############################################################################
# Collect worker exit statuses
###############################################################################

echo
echo "============================================================"
echo "WORKER RESULTS"
echo "============================================================"

WORKER_SUCCESS=0
WORKER_FAILURE=0

for i in "${!AGENT_NAMES[@]}"; do

    NAME="${AGENT_NAMES[$i]}"
    PID="${WORKER_PIDS[$i]:-}"

    [[ -z "$PID" ]] && continue

    if wait "$PID"; then
        pass "$NAME completed successfully"
        WORKER_SUCCESS=$((WORKER_SUCCESS + 1))
    else
        warn "$NAME exited with failure"
        WORKER_FAILURE=$((WORKER_FAILURE + 1))
    fi
done

###############################################################################
# Ruflo state collection
###############################################################################

echo
echo "============================================================"
echo "RUFLO STATE"
echo "============================================================"

"${RUFLO_CMD[@]}" agent list \
    >"$REPORT_DIR/state/agent-list.txt" 2>&1 || true

"${RUFLO_CMD[@]}" agent health \
    >"$REPORT_DIR/state/agent-health.txt" 2>&1 || true

"${RUFLO_CMD[@]}" agent metrics \
    >"$REPORT_DIR/state/agent-metrics.txt" 2>&1 || true

"${RUFLO_CMD[@]}" task list --all \
    >"$REPORT_DIR/state/task-list.txt" 2>&1 || true

"${RUFLO_CMD[@]}" swarm status \
    >"$REPORT_DIR/state/swarm-status.txt" 2>&1 || true

"${RUFLO_CMD[@]}" status \
    >"$REPORT_DIR/state/ruflo-status.txt" 2>&1 || true

echo
echo "===== AGENT LIST ====="
cat "$REPORT_DIR/state/agent-list.txt" || true

echo
echo "===== TASK LIST ====="
cat "$REPORT_DIR/state/task-list.txt" || true

echo
echo "===== SWARM ====="
cat "$REPORT_DIR/state/swarm-status.txt" || true

echo
echo "===== METRICS ====="
cat "$REPORT_DIR/state/agent-metrics.txt" || true

###############################################################################
# System diagnostics
###############################################################################

echo
echo "============================================================"
echo "SYSTEM DIAGNOSTICS"
echo "============================================================"

{
    echo "===== DATE ====="
    date

    echo
    echo "===== UPTIME ====="
    uptime

    echo
    echo "===== MEMORY ====="
    free -h

    echo
    echo "===== DISK ====="
    df -h "$PROJECT"

    echo
    echo "===== CPU ====="
    nproc
    lscpu | head -30

    echo
    echo "===== PROCESSES ====="
    ps -eo pid,ppid,stat,%cpu,%mem,etime,cmd \
        --sort=-%cpu |
        head -40

    echo
    echo "===== NODE ====="
    node --version

    echo
    echo "===== CLAUDE ====="
    claude --version 2>&1 || true

    echo
    echo "===== RUFLO ====="
    "${RUFLO_CMD[@]}" --version 2>&1 || true

} >"$REPORT_DIR/diagnostics/system.txt"

###############################################################################
# Test artifacts
###############################################################################

echo
echo "============================================================"
echo "ARTIFACT ANALYSIS"
echo "============================================================"

find "$PROJECT" \
    -type f \
    -size +500M \
    -not -path "$REPORT_DIR/*" \
    -printf '%s %p\n' \
    2>/dev/null |
    sort -nr |
    head -50 \
    >"$REPORT_DIR/diagnostics/large-files.txt"

find "$PROJECT" \
    -type f \
    \( -name "*.log" -o -name "*.txt" \) \
    -size +50M \
    -not -path "$REPORT_DIR/*" \
    -printf '%s %p\n' \
    2>/dev/null |
    sort -nr |
    head -50 \
    >"$REPORT_DIR/diagnostics/large-logs.txt"

###############################################################################
# Git
###############################################################################

git status --short >"$REPORT_DIR/diagnostics/git-status.txt" 2>&1 || true

###############################################################################
# Consolidated report
###############################################################################

END_EPOCH="$(date +%s)"
DURATION=$((END_EPOCH - START_EPOCH))

TOTAL_AGENTS="${#AGENT_NAMES[@]}"

cat >"$SUMMARY" <<EOF
RUFLO MULTI-AGENT ENTERPRISE TEST $VERSION

Project:
$PROJECT

Started:
$(date -d "@$START_EPOCH" '+%F %T %Z')

Finished:
$(date '+%F %T %Z')

Duration:
${DURATION}s

Ruflo:
$("${RUFLO_CMD[@]}" --version 2>&1 | head -1)

Claude:
$(claude --version 2>&1 | head -1)

============================================================
AGENTS
============================================================

Configured agents : $TOTAL_AGENTS
Workers launched  : ${#WORKER_PIDS[@]}
Workers success   : $WORKER_SUCCESS
Workers failed    : $WORKER_FAILURE

============================================================
DISPATCHER RESULT
============================================================

PASS : $PASS_COUNT
WARN : $WARN_COUNT
FAIL : $FAIL_COUNT

============================================================
REPORT DIRECTORY
============================================================

$REPORT_DIR

Main log:
$MAIN_LOG

Summary:
$SUMMARY

Worker logs:
$REPORT_DIR/logs/

Worker reports:
$REPORT_DIR/results/

Ruflo state:
$REPORT_DIR/state/

Diagnostics:
$REPORT_DIR/diagnostics/
EOF

###############################################################################
# JSON report
###############################################################################

python3 - "$JSON" "$PROJECT" "$REPORT_DIR" "$TOTAL_AGENTS" "$WORKER_SUCCESS" "$WORKER_FAILURE" "$PASS_COUNT" "$WARN_COUNT" "$FAIL_COUNT" "$DURATION" <<'PY'
import json
import os
import sys
from datetime import datetime, timezone

(
    output,
    project,
    report_dir,
    total_agents,
    worker_success,
    worker_failure,
    passed,
    warned,
    failed,
    duration,
) = sys.argv[1:]

data = {
    "report_version": "ruflo-agent-dispatcher-v14",
    "timestamp": datetime.now(timezone.utc).isoformat(),
    "project": project,
    "report_directory": report_dir,
    "ruflo": "ruflo v3.38.12",
    "configured_agents": int(total_agents),
    "workers_success": int(worker_success),
    "workers_failed": int(worker_failure),
    "pass": int(passed),
    "warn": int(warned),
    "fail": int(failed),
    "duration_seconds": int(duration),
    "artifacts": {
        "summary": os.path.join(report_dir, "summary.txt"),
        "main_log": os.path.join(report_dir, "dispatcher.log"),
        "agents": os.path.join(report_dir, "agents"),
        "worker_logs": os.path.join(report_dir, "logs"),
        "results": os.path.join(report_dir, "results"),
        "diagnostics": os.path.join(report_dir, "diagnostics"),
        "state": os.path.join(report_dir, "state"),
    },
}

with open(output, "w", encoding="utf-8") as f:
    json.dump(data, f, indent=2)
PY

###############################################################################
# Final
###############################################################################

echo
echo "============================================================"
echo "RUFLO MULTI-AGENT DISPATCH COMPLETE"
echo "============================================================"

cat "$SUMMARY"

echo
echo "============================================================"
echo "Useful commands"
echo "============================================================"

echo
echo "View live dispatcher log:"
echo "tail -f \"$MAIN_LOG\""

echo
echo "View worker logs:"
echo "ls -lh \"$REPORT_DIR/logs/\""

echo
echo "View agent reports:"
echo "ls -lh \"$REPORT_DIR/results/\""

echo
echo "View Ruflo agents:"
echo "npx --no-install claude-flow agent list"

echo
echo "View Ruflo tasks:"
echo "npx --no-install claude-flow task list --all"

echo
echo "View Ruflo metrics:"
echo "npx --no-install claude-flow agent metrics"

echo
echo "Final report:"
echo "$SUMMARY"

echo
echo "JSON:"
echo "$JSON"

echo
echo "============================================================"
echo "DONE"
echo "============================================================"
