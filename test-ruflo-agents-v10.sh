#!/usr/bin/env bash

###############################################################################
# RUFLO AGENT ENTERPRISE TEST v10
#
# Purpose:
#   Test the project using Ruflo/Claude Flow agent orchestration.
#
# Tests:
#   1. Environment
#   2. Ruflo runtime
#   3. Project structure
#   4. Agent spawning
#   5. Agent health/listing
#   6. Swarm initialization
#   7. Task creation/assignment
#   8. Memory store/retrieve
#   9. MCP connectivity
#  10. Backend core tests
#  11. Frontend/npm validation
#  12. Git/project integrity
#  13. Runtime artifact health
#  14. Agent collaboration evidence
#  15. Final health score
#
# IMPORTANT:
#   This script does not modify application source code.
###############################################################################

set +e

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$PROJECT_DIR"

TIMESTAMP="$(date +%Y%m%d_%H%M%S)"
REPORT_DIR="$PROJECT_DIR/ruflo-agent-test-v10-$TIMESTAMP"

mkdir -p "$REPORT_DIR"

MAIN_LOG="$REPORT_DIR/ruflo-agent-test-v10.log"
SUMMARY="$REPORT_DIR/summary.txt"
JSON="$REPORT_DIR/summary.json"
AGENT_LOG="$REPORT_DIR/agents.log"
SWARM_LOG="$REPORT_DIR/swarm.log"
TASK_LOG="$REPORT_DIR/tasks.log"
MEMORY_LOG="$REPORT_DIR/memory.log"
MCP_LOG="$REPORT_DIR/mcp.log"
PYTEST_LOG="$REPORT_DIR/pytest.log"
NPM_LOG="$REPORT_DIR/npm.log"
PROJECT_LOG="$REPORT_DIR/project.log"

touch "$MAIN_LOG"

PASS=0
WARN=0
FAIL=0

###############################################################################
# Helpers
###############################################################################

log() {
    echo "$*" | tee -a "$MAIN_LOG"
}

section() {
    log ""
    log "============================================================"
    log "$*"
    log "============================================================"
}

pass() {
    PASS=$((PASS + 1))
    log "[PASS] $*"
}

warn() {
    WARN=$((WARN + 1))
    log "[WARN] $*"
}

fail() {
    FAIL=$((FAIL + 1))
    log "[FAIL] $*"
}

run_capture() {
    local outfile="$1"
    shift
    "$@" >"$outfile" 2>&1
    return $?
}

###############################################################################
# Header
###############################################################################

log "RUFLO AGENT ENTERPRISE TEST v10"
log "Project : $PROJECT_DIR"
log "Date    : $(date)"
log "Host    : $(hostname)"
log "User    : $(whoami)"
log "Kernel  : $(uname -r)"
log "Report  : $REPORT_DIR"

###############################################################################
# 1. SYSTEM
###############################################################################

section "1. SYSTEM HEALTH"

CPU_CORES="$(nproc 2>/dev/null || echo 0)"
MEM_AVAILABLE="$(free -h 2>/dev/null | awk '/Mem:/ {print $7}')"
ROOT_USAGE="$(df -P "$PROJECT_DIR" | awk 'NR==2 {print $5}' | tr -d '%')"

log "CPU Cores       : $CPU_CORES"
log "Memory Available: $MEM_AVAILABLE"
log "Root Usage      : ${ROOT_USAGE}%"

if [ "$ROOT_USAGE" -lt 80 ]; then
    pass "Filesystem capacity healthy (${ROOT_USAGE}% used)"
elif [ "$ROOT_USAGE" -lt 90 ]; then
    warn "Filesystem capacity elevated (${ROOT_USAGE}% used)"
else
    fail "Filesystem capacity critical (${ROOT_USAGE}% used)"
fi

###############################################################################
# 2. REQUIRED COMMANDS
###############################################################################

section "2. REQUIRED TOOLCHAIN"

TOOLS=(
    bash node npm npx git python3
    find awk sed grep du df sort head tail jq
)

for tool in "${TOOLS[@]}"; do
    if command -v "$tool" >/dev/null 2>&1; then
        pass "$tool available: $(command -v "$tool")"
    else
        fail "$tool is missing"
    fi
done

###############################################################################
# 3. RUNTIME
###############################################################################

section "3. RUNTIME VERSIONS"

NODE_VERSION="$(node --version 2>/dev/null)"
NPM_VERSION="$(npm --version 2>/dev/null)"
PY_VERSION="$(python3 --version 2>/dev/null)"
GIT_VERSION="$(git --version 2>/dev/null)"

log "Node : $NODE_VERSION"
log "npm  : $NPM_VERSION"
log "Py3  : $PY_VERSION"
log "Git  : $GIT_VERSION"

if [[ "$NODE_VERSION" =~ ^v20\. ]]; then
    pass "Node.js 20 detected"
else
    warn "Node.js is not version 20: $NODE_VERSION"
fi

###############################################################################
# 4. PROJECT
###############################################################################

section "4. PROJECT STRUCTURE"

if [ -f package.json ]; then
    pass "package.json exists"

    if jq empty package.json >/dev/null 2>&1; then
        pass "package.json is valid JSON"
    else
        fail "package.json is invalid JSON"
    fi
else
    fail "package.json missing"
fi

if [ -f package-lock.json ]; then
    pass "package-lock.json exists"
else
    warn "package-lock.json missing"
fi

if [ -d node_modules ]; then
    pass "node_modules exists"
else
    warn "node_modules missing"
fi

if [ -d backend/venv ]; then
    pass "backend virtualenv exists"
else
    warn "backend virtualenv missing"
fi

###############################################################################
# 5. RUFLO RUNTIME
###############################################################################

section "5. RUFLO RUNTIME"

RUFLO_VERSION="$(npx --no-install ruflo --version 2>/dev/null | head -1)"

if [ -n "$RUFLO_VERSION" ]; then
    pass "Ruflo runtime available: $RUFLO_VERSION"
else
    fail "Ruflo runtime unavailable"
fi

if command -v ruflo >/dev/null 2>&1; then
    pass "Global Ruflo executable available"
else
    warn "No global Ruflo executable"
fi

if [ -x node_modules/.bin/ruflo ]; then
    pass "Project-local Ruflo executable available"
else
    warn "No project-local Ruflo executable"
fi

if [ -d .claude-flow ]; then
    pass ".claude-flow directory exists"
else
    warn ".claude-flow directory missing"
fi

if [ -d .agents ]; then
    pass ".agents directory exists"
else
    warn ".agents directory missing"
fi

if [ -d .agents/skills/ruflo ]; then
    pass "Ruflo skills directory exists"
else
    warn "Ruflo skills directory missing"
fi

###############################################################################
# 6. RUFLO STATUS
###############################################################################

section "6. RUFLO STATUS"

run_capture "$REPORT_DIR/ruflo-status.txt" \
    npx --no-install ruflo status

if [ $? -eq 0 ]; then
    pass "Ruflo status command succeeded"
else
    warn "Ruflo status command returned non-zero"
fi

cat "$REPORT_DIR/ruflo-status.txt" >> "$MAIN_LOG"

###############################################################################
# 7. AGENT HEALTH
###############################################################################

section "7. AGENT HEALTH"

run_capture "$AGENT_LOG" \
    npx --no-install ruflo agent health

if [ $? -eq 0 ]; then
    pass "Ruflo agent health command succeeded"
else
    warn "Ruflo agent health command returned non-zero"
fi

cat "$AGENT_LOG" >> "$MAIN_LOG"

###############################################################################
# 8. AGENT LIST
###############################################################################

section "8. AGENT INVENTORY"

run_capture "$REPORT_DIR/agent-list.txt" \
    npx --no-install ruflo agent list

if [ $? -eq 0 ]; then
    pass "Agent list command succeeded"
else
    warn "Agent list command returned non-zero"
fi

cat "$REPORT_DIR/agent-list.txt" >> "$MAIN_LOG"

###############################################################################
# 9. SPAWN TEST AGENTS
###############################################################################

section "9. AGENT SPAWN TEST"

AGENTS=(
    "project-architect:architect"
    "project-researcher:researcher"
    "project-tester:tester"
    "project-reviewer:reviewer"
)

SPAWNED=0

for ENTRY in "${AGENTS[@]}"; do

    NAME="${ENTRY%%:*}"
    TYPE="${ENTRY##*:}"

    log "Spawning $NAME [$TYPE]..."

    OUTPUT="$REPORT_DIR/spawn-$NAME.txt"

    npx --no-install ruflo agent spawn \
        --type "$TYPE" \
        --name "$NAME" \
        >"$OUTPUT" 2>&1

    RC=$?

    cat "$OUTPUT" >> "$MAIN_LOG"

    if [ $RC -eq 0 ]; then
        pass "Agent spawned: $NAME [$TYPE]"
        SPAWNED=$((SPAWNED + 1))
    else
        warn "Agent spawn returned non-zero: $NAME [$TYPE]"
    fi
done

log "Agents successfully spawned: $SPAWNED/${#AGENTS[@]}"

if [ "$SPAWNED" -ge 3 ]; then
    pass "Multi-agent orchestration is available"
elif [ "$SPAWNED" -ge 1 ]; then
    warn "Only partial multi-agent orchestration is available"
else
    fail "No Ruflo agents could be spawned"
fi

###############################################################################
# 10. AGENT LIST AFTER SPAWN
###############################################################################

section "10. AGENT STATE AFTER SPAWN"

run_capture "$REPORT_DIR/agents-after-spawn.txt" \
    npx --no-install ruflo agent list

cat "$REPORT_DIR/agents-after-spawn.txt" >> "$MAIN_LOG"

###############################################################################
# 11. SWARM INIT
###############################################################################

section "11. SWARM INITIALIZATION"

npx --no-install ruflo swarm init \
    --topology hierarchical \
    --max-agents 4 \
    >"$SWARM_LOG" 2>&1

SWARM_RC=$?

cat "$SWARM_LOG" >> "$MAIN_LOG"

if [ $SWARM_RC -eq 0 ]; then
    pass "Hierarchical swarm initialized"
else
    warn "Swarm initialization returned non-zero"
fi

###############################################################################
# 12. SWARM STATUS
###############################################################################

section "12. SWARM STATUS"

npx --no-install ruflo swarm status \
    >>"$SWARM_LOG" 2>&1

cat "$SWARM_LOG" >> "$MAIN_LOG"

###############################################################################
# 13. CREATE TEST TASKS
###############################################################################

section "13. TASK ORCHESTRATION"

TASK_DESCRIPTIONS=(
    "Analyze the architecture of this project and identify the primary application components."
    "Review the backend Python project and identify the main testing risks."
    "Review the MCP implementation and identify integration risks."
    "Review the Ruflo/Claude Flow project integration and identify configuration risks."
)

TASK_IDS=()

for DESC in "${TASK_DESCRIPTIONS[@]}"; do

    OUTPUT="$REPORT_DIR/task-create-$RANDOM.txt"

    npx --no-install ruflo task create \
        --type analysis \
        --description "$DESC" \
        >"$OUTPUT" 2>&1

    RC=$?

    cat "$OUTPUT" >> "$TASK_LOG"
    cat "$OUTPUT" >> "$MAIN_LOG"

    if [ $RC -eq 0 ]; then
        pass "Task creation succeeded"
    else
        warn "Task creation returned non-zero"
    fi
done

###############################################################################
# 14. TASK LIST
###############################################################################

section "14. TASK INVENTORY"

npx --no-install ruflo task list \
    >>"$TASK_LOG" 2>&1

cat "$TASK_LOG" >> "$MAIN_LOG"

###############################################################################
# 15. MEMORY TEST
###############################################################################

section "15. RUFLO MEMORY"

MEMORY_KEY="ruflo-v10-test-$TIMESTAMP"

npx --no-install ruflo memory store \
    --key "$MEMORY_KEY" \
    --value "Ruflo v10 project-agent integration test completed on $TIMESTAMP" \
    --namespace ruflo-test \
    >"$MEMORY_LOG" 2>&1

MEM_STORE_RC=$?

if [ $MEM_STORE_RC -eq 0 ]; then
    pass "Ruflo memory store succeeded"
else
    warn "Ruflo memory store returned non-zero"
fi

npx --no-install ruflo memory retrieve \
    --key "$MEMORY_KEY" \
    --namespace ruflo-test \
    >>"$MEMORY_LOG" 2>&1

MEM_RETRIEVE_RC=$?

cat "$MEMORY_LOG" >> "$MAIN_LOG"

if [ $MEM_RETRIEVE_RC -eq 0 ]; then
    pass "Ruflo memory retrieve succeeded"
else
    warn "Ruflo memory retrieve returned non-zero"
fi

###############################################################################
# 16. MCP
###############################################################################

section "16. MCP / FASTMCP"

if [ -x backend/venv/bin/python ]; then

    backend/venv/bin/python - <<'PY' >"$MCP_LOG" 2>&1
from mcp.server.fastmcp import FastMCP
import mcp

print("FastMCP:", FastMCP)
print("MCP module:", mcp)
print("MCP_IMPORT_PASS")
PY

    if grep -q "MCP_IMPORT_PASS" "$MCP_LOG"; then
        pass "FastMCP import succeeded"
    else
        fail "FastMCP import failed"
    fi

else
    warn "Backend virtualenv unavailable; MCP test skipped"
fi

cat "$MCP_LOG" >> "$MAIN_LOG"

###############################################################################
# 17. PYTHON DEPENDENCIES
###############################################################################

section "17. PYTHON DEPENDENCY HEALTH"

if [ -x backend/venv/bin/python ]; then

    backend/venv/bin/python -m pip check \
        >"$REPORT_DIR/pip-check.txt" 2>&1

    if [ $? -eq 0 ]; then
        pass "Python pip check passed"
    else
        fail "Python dependency conflicts detected"
    fi

    INVALID_COUNT="$(
        find backend/venv/lib/python3.12/site-packages \
            -maxdepth 1 \
            -type d \
            -name '~*' \
            2>/dev/null | wc -l
    )"

    if [ "$INVALID_COUNT" -eq 0 ]; then
        pass "No invalid Python distributions detected"
    else
        warn "$INVALID_COUNT invalid Python distributions detected"
    fi
fi

###############################################################################
# 18. CORE TESTS
###############################################################################

section "18. PROJECT CORE TESTS"

CORE_TESTS=()

[ -f tests/test_program_control.py ] && \
    CORE_TESTS+=("tests/test_program_control.py")

[ -f backend/tests/test_mcp_server.py ] && \
    CORE_TESTS+=("backend/tests/test_mcp_server.py")

if [ "${#CORE_TESTS[@]}" -gt 0 ]; then

    backend/venv/bin/python -m pytest \
        "${CORE_TESTS[@]}" \
        -q \
        --maxfail=5 \
        >"$PYTEST_LOG" 2>&1

    PYTEST_RC=$?

    cat "$PYTEST_LOG" >> "$MAIN_LOG"

    if [ $PYTEST_RC -eq 0 ]; then
        pass "Ruflo core project tests passed"
    else
        fail "Ruflo core project tests failed"
    fi

else
    warn "No targeted core tests found"
fi

###############################################################################
# 19. PROGRAM SERVICE
###############################################################################

section "19. PROGRAM SERVICE CONTRACT"

if [ -f backend/program_service.py ]; then

    backend/venv/bin/python - <<'PY' \
        >"$REPORT_DIR/program-service.txt" 2>&1

from backend import program_service

expected = [
    "create_program",
    "get_program",
    "list_programs",
    "update_controls",
    "delete_program",
]

for name in expected:
    assert hasattr(program_service, name), f"Missing function: {name}"

assert hasattr(
    program_service,
    "_compute_status_rollup"
)

print("PROGRAM_SERVICE_PASS")
PY

    if grep -q "PROGRAM_SERVICE_PASS" "$REPORT_DIR/program-service.txt"; then
        pass "Program service contract valid"
    else
        fail "Program service contract invalid"
    fi

else
    warn "Program service not present"
fi

###############################################################################
# 20. NPM
###############################################################################

section "20. NPM VALIDATION"

npm install --package-lock-only --ignore-scripts \
    >"$NPM_LOG" 2>&1

if [ $? -eq 0 ]; then
    pass "npm dependency metadata is healthy"
else
    warn "npm package-lock validation returned non-zero"
fi

npm ls --depth=0 \
    >>"$NPM_LOG" 2>&1

###############################################################################
# 21. FULL PYTEST DIAGNOSTIC
###############################################################################

section "21. FULL PROJECT PYTEST DIAGNOSTIC"

if [ -x backend/venv/bin/python ]; then

    backend/venv/bin/python -m pytest \
        --collect-only \
        -q \
        >"$REPORT_DIR/full-pytest-collection.txt" 2>&1

    FULL_RC=$?

    COLLECTED="$(
        grep -Eo '[0-9]+ tests? collected' \
        "$REPORT_DIR/full-pytest-collection.txt" \
        | tail -1
    )"

    ERRORS="$(
        grep -Eo '[0-9]+ errors?' \
        "$REPORT_DIR/full-pytest-collection.txt" \
        | tail -1
    )"

    log "Pytest collection: ${COLLECTED:-unknown}"
    log "Collection errors : ${ERRORS:-0}"

    if [ $FULL_RC -eq 0 ]; then
        pass "Full project pytest collection clean"
    else
        warn "Full project pytest collection has diagnostics"
    fi
fi

###############################################################################
# 22. SOURCE SCAN
###############################################################################

section "22. SOURCE BLOCKER SCAN"

BLOCKER_COUNT=0

if grep -RniE \
    "from mcp\.server\.fastmcp|import mcp" \
    backend \
    --include='*.py' \
    >/dev/null 2>&1; then

    if backend/venv/bin/python - <<'PY' >/dev/null 2>&1
from mcp.server.fastmcp import FastMCP
PY
    then
        pass "MCP source imports are resolvable"
    else
        fail "MCP source import failure"
        BLOCKER_COUNT=$((BLOCKER_COUNT + 1))
    fi
fi

###############################################################################
# 23. LARGE ARTIFACTS
###############################################################################

section "23. RUNTIME ARTIFACTS"

find "$PROJECT_DIR" \
    -type f \
    -size +500M \
    -printf '%s %p\n' \
    2>/dev/null \
    | sort -nr \
    >"$REPORT_DIR/large-files.txt"

if [ -s "$REPORT_DIR/large-files.txt" ]; then
    warn "Large files over 500MB detected"
    cat "$REPORT_DIR/large-files.txt" >> "$MAIN_LOG"
else
    pass "No files over 500MB detected"
fi

find "$PROJECT_DIR" \
    -type f \
    \( -name '*.log' -o -name '*.out' \) \
    -size +50M \
    -printf '%s %p\n' \
    2>/dev/null \
    | sort -nr \
    >"$REPORT_DIR/large-logs.txt"

if [ -s "$REPORT_DIR/large-logs.txt" ]; then
    warn "Large logs over 50MB detected"
    cat "$REPORT_DIR/large-logs.txt" >> "$MAIN_LOG"
else
    pass "No logs over 50MB detected"
fi

###############################################################################
# 24. GIT
###############################################################################

section "24. GIT STATE"

if git rev-parse --is-inside-work-tree >/dev/null 2>&1; then

    pass "Git repository detected"

    git status --short >"$REPORT_DIR/git-status.txt"

    if [ -s "$REPORT_DIR/git-status.txt" ]; then
        warn "Git working tree contains changes"
        cat "$REPORT_DIR/git-status.txt" >> "$MAIN_LOG"
    else
        pass "Git working tree clean"
    fi

else
    warn "Git repository not detected"
fi

###############################################################################
# 25. AGENT COLLABORATION EVIDENCE
###############################################################################

section "25. AGENT COLLABORATION EVIDENCE"

run_capture "$REPORT_DIR/final-agent-list.txt" \
    npx --no-install ruflo agent list

cat "$REPORT_DIR/final-agent-list.txt" >> "$MAIN_LOG"

run_capture "$REPORT_DIR/final-agent-health.txt" \
    npx --no-install ruflo agent health

cat "$REPORT_DIR/final-agent-health.txt" >> "$MAIN_LOG"

if grep -Eiq \
    "project-architect|project-researcher|project-tester|project-reviewer" \
    "$REPORT_DIR/final-agent-list.txt"; then

    pass "Named test agents are visible in Ruflo state"

else
    warn "Named test agents are not visible in final agent inventory"
fi

###############################################################################
# 26. SWARM STOP
###############################################################################

section "26. SWARM CLEANUP"

npx --no-install ruflo swarm stop \
    >>"$REPORT_DIR/swarm-stop.txt" 2>&1

if [ $? -eq 0 ]; then
    pass "Ruflo swarm cleanup completed"
else
    warn "Ruflo swarm cleanup returned non-zero"
fi

###############################################################################
# 27. HEALTH SCORE
###############################################################################

section "27. RUFLO AGENT HEALTH SCORE"

# Weighting:
#   PASS = +1
#   WARN = -0.5
#   FAIL = -2
#
# Normalized to 100.

TOTAL=$((PASS + WARN + FAIL))

if [ "$TOTAL" -gt 0 ]; then

    SCORE_RAW=$((100 * (PASS * 1 - WARN / 2 - FAIL * 2) / TOTAL))

    if [ "$SCORE_RAW" -lt 0 ]; then
        SCORE_RAW=0
    fi

    if [ "$SCORE_RAW" -gt 100 ]; then
        SCORE_RAW=100
    fi

else
    SCORE_RAW=0
fi

if [ "$FAIL" -gt 0 ]; then
    RESULT="FAILED"
elif [ "$SCORE_RAW" -ge 85 ]; then
    RESULT="HEALTHY"
elif [ "$SCORE_RAW" -ge 70 ]; then
    RESULT="DEGRADED"
else
    RESULT="AT_RISK"
fi

log "Health Score : $SCORE_RAW / 100"
log "PASS         : $PASS"
log "WARN         : $WARN"
log "FAIL         : $FAIL"
log "RESULT       : $RESULT"

###############################################################################
# 28. SUMMARY
###############################################################################

section "28. FINAL RESULT"

cat > "$SUMMARY" <<EOF
RUFLO AGENT ENTERPRISE TEST v10 SUMMARY

Project: $PROJECT_DIR
Date: $(date)
Host: $(hostname)

Ruflo: ${RUFLO_VERSION:-unknown}

Health Score: $SCORE_RAW / 100

PASS: $PASS
WARN: $WARN
FAIL: $FAIL

Result: $RESULT

Spawned Agents: $SPAWNED / ${#AGENTS[@]}

Reports:
  Main Log       : $MAIN_LOG
  Agent Log      : $AGENT_LOG
  Swarm Log      : $SWARM_LOG
  Task Log       : $TASK_LOG
  Memory Log     : $MEMORY_LOG
  MCP Log        : $MCP_LOG
  Pytest Log     : $PYTEST_LOG
  NPM Log        : $NPM_LOG
EOF

cat "$SUMMARY"

###############################################################################
# JSON
###############################################################################

cat > "$JSON" <<EOF
{
  "test": "Ruflo Agent Enterprise Test v10",
  "project": "$PROJECT_DIR",
  "timestamp": "$(date -Iseconds)",
  "host": "$(hostname)",
  "ruflo": "${RUFLO_VERSION:-unknown}",
  "health_score": $SCORE_RAW,
  "pass": $PASS,
  "warn": $WARN,
  "fail": $FAIL,
  "result": "$RESULT",
  "agents_spawned": $SPAWNED,
  "agents_requested": ${#AGENTS[@]},
  "reports": {
    "summary": "$SUMMARY",
    "main_log": "$MAIN_LOG",
    "agent_log": "$AGENT_LOG",
    "swarm_log": "$SWARM_LOG",
    "task_log": "$TASK_LOG",
    "memory_log": "$MEMORY_LOG",
    "mcp_log": "$MCP_LOG",
    "pytest_log": "$PYTEST_LOG",
    "npm_log": "$NPM_LOG"
  }
}
EOF

log ""
log "============================================================"
log "RUFLO AGENT ENTERPRISE TEST v10 COMPLETE"
log "============================================================"
log "PASS   : $PASS"
log "WARN   : $WARN"
log "FAIL   : $FAIL"
log "SCORE  : $SCORE_RAW / 100"
log "RESULT : $RESULT"
log ""
log "Summary : $SUMMARY"
log "JSON    : $JSON"
log "Report  : $MAIN_LOG"
log "============================================================"

exit 0
