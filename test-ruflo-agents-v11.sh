#!/usr/bin/env bash

set -u
set -o pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$PROJECT_DIR"

TIMESTAMP="$(date '+%Y%m%d_%H%M%S')"
REPORT_DIR="$PROJECT_DIR/ruflo-agent-test-v11-$TIMESTAMP"

mkdir -p "$REPORT_DIR"

MAIN_LOG="$REPORT_DIR/ruflo-agent-test-v11.log"
CLI_LOG="$REPORT_DIR/cli.log"
AGENT_LOG="$REPORT_DIR/agents.log"
TASK_LOG="$REPORT_DIR/tasks.log"
SWARM_LOG="$REPORT_DIR/swarm.log"
PYTEST_LOG="$REPORT_DIR/pytest.log"
SUMMARY="$REPORT_DIR/summary.txt"
JSON="$REPORT_DIR/summary.json"

PASS=0
WARN=0
FAIL=0

RUFLO_CMD=""
RUFLO_VERSION="unknown"
CLI_TYPE="unknown"

log() {
    echo "$*" | tee -a "$MAIN_LOG"
}

section() {
    log
    log "============================================================"
    log "$1"
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
    local logfile="$1"
    shift

    "$@" > "$logfile" 2>&1
    return $?
}

# ------------------------------------------------------------
# HEADER
# ------------------------------------------------------------

log "RUFLO AGENT ENTERPRISE TEST v11"
log "Project : $PROJECT_DIR"
log "Date    : $(date)"
log "Host    : $(hostname)"
log "User    : $(whoami)"
log "Kernel  : $(uname -r)"
log "Report  : $REPORT_DIR"

# ------------------------------------------------------------
# 1. SYSTEM
# ------------------------------------------------------------

section "1. SYSTEM HEALTH"

CPU_CORES="$(nproc 2>/dev/null || echo unknown)"
MEM_AVAILABLE="$(free -h 2>/dev/null | awk '/Mem:/ {print $7}' || echo unknown)"
ROOT_USAGE="$(df -P "$PROJECT_DIR" | awk 'NR==2 {print $5}')"

log "CPU Cores       : $CPU_CORES"
log "Memory Available: $MEM_AVAILABLE"
log "Root Usage      : $ROOT_USAGE"

ROOT_NUM="${ROOT_USAGE%%%}"

if [[ "$ROOT_NUM" =~ ^[0-9]+$ ]]; then
    if (( ROOT_NUM < 80 )); then
        pass "Filesystem capacity healthy ($ROOT_USAGE used)"
    else
        warn "Filesystem usage elevated ($ROOT_USAGE used)"
    fi
else
    warn "Unable to determine filesystem usage"
fi

# ------------------------------------------------------------
# 2. TOOLCHAIN
# ------------------------------------------------------------

section "2. REQUIRED TOOLCHAIN"

for cmd in bash node npm npx git python3 find awk sed grep du df sort head tail jq; do
    if command -v "$cmd" >/dev/null 2>&1; then
        pass "$cmd available: $(command -v "$cmd")"
    else
        fail "$cmd is unavailable"
    fi
done

# ------------------------------------------------------------
# 3. VERSIONS
# ------------------------------------------------------------

section "3. RUNTIME VERSIONS"

NODE_VERSION="$(node --version 2>/dev/null || echo unavailable)"
NPM_VERSION="$(npm --version 2>/dev/null || echo unavailable)"
PY_VERSION="$(python3 --version 2>/dev/null || echo unavailable)"
GIT_VERSION="$(git --version 2>/dev/null || echo unavailable)"

log "Node : $NODE_VERSION"
log "npm  : $NPM_VERSION"
log "Py3  : $PY_VERSION"
log "Git  : $GIT_VERSION"

if [[ "$NODE_VERSION" =~ ^v20\. ]]; then
    pass "Node.js 20 detected"
else
    warn "Node.js version is $NODE_VERSION"
fi

# ------------------------------------------------------------
# 4. PROJECT
# ------------------------------------------------------------

section "4. PROJECT STRUCTURE"

[[ -f package.json ]] && pass "package.json exists" || fail "package.json missing"
[[ -f package-lock.json ]] && pass "package-lock.json exists" || warn "package-lock.json missing"
[[ -d node_modules ]] && pass "node_modules exists" || fail "node_modules missing"
[[ -d backend/venv ]] && pass "backend virtualenv exists" || warn "backend virtualenv missing"

if jq empty package.json >/dev/null 2>&1; then
    pass "package.json is valid JSON"
else
    fail "package.json is invalid JSON"
fi

# ------------------------------------------------------------
# 5. RUFLO DISCOVERY
# ------------------------------------------------------------

section "5. RUFLO CLI DISCOVERY"

{
    echo "===== command -v ====="
    command -v ruflo || true
    command -v claude-flow || true

    echo
    echo "===== node_modules/.bin ====="
    ls -la node_modules/.bin/ 2>/dev/null | grep -Ei 'ruflo|claude|flow' || true

    echo
    echo "===== package metadata ====="
    npm ls ruflo --depth=0 2>&1 || true
    npm ls claude-flow --depth=0 2>&1 || true

    echo
    echo "===== npx ruflo ====="
    npx --no-install ruflo --version 2>&1 || true

    echo
    echo "===== npx claude-flow ====="
    npx --no-install claude-flow --version 2>&1 || true
} > "$CLI_LOG"

# Prefer an installed binary.
if command -v ruflo >/dev/null 2>&1; then
    RUFLO_CMD="ruflo"
    CLI_TYPE="global-ruflo"

elif [[ -x "$PROJECT_DIR/node_modules/.bin/ruflo" ]]; then
    RUFLO_CMD="$PROJECT_DIR/node_modules/.bin/ruflo"
    CLI_TYPE="project-ruflo"

elif command -v claude-flow >/dev/null 2>&1; then
    RUFLO_CMD="claude-flow"
    CLI_TYPE="global-claude-flow"

elif [[ -x "$PROJECT_DIR/node_modules/.bin/claude-flow" ]]; then
    RUFLO_CMD="$PROJECT_DIR/node_modules/.bin/claude-flow"
    CLI_TYPE="project-claude-flow"

else
    # Ruflo has previously been available through the cached npx installation.
    if npx --no-install ruflo --version >/tmp/ruflo-v11-version.txt 2>&1; then
        RUFLO_CMD="npx --no-install ruflo"
        CLI_TYPE="npx-ruflo"
    elif npx --no-install claude-flow --version >/tmp/claude-flow-v11-version.txt 2>&1; then
        RUFLO_CMD="npx --no-install claude-flow"
        CLI_TYPE="npx-claude-flow"
    fi
fi

if [[ -n "$RUFLO_CMD" ]]; then
    pass "Ruflo/Claude Flow runtime discovered"
    log "Runtime : $RUFLO_CMD"
    log "Type    : $CLI_TYPE"

    RUFLO_VERSION="$($RUFLO_CMD --version 2>&1 | head -1)"
    log "Version : $RUFLO_VERSION"
else
    fail "No usable Ruflo/Claude Flow runtime discovered"
fi

# ------------------------------------------------------------
# 6. HELP / COMMAND CAPABILITY DISCOVERY
# ------------------------------------------------------------

section "6. RUFLO COMMAND CAPABILITY DISCOVERY"

if [[ -n "$RUFLO_CMD" ]]; then

    "$RUFLO_CMD" --help > "$REPORT_DIR/ruflo-help.txt" 2>&1 || true

    cat "$REPORT_DIR/ruflo-help.txt" >> "$CLI_LOG"

    log "Available top-level commands:"
    grep -E '^[[:space:]]+[a-zA-Z][a-zA-Z0-9_-]*' \
        "$REPORT_DIR/ruflo-help.txt" |
        head -100 |
        tee -a "$MAIN_LOG" || true

    if grep -Eiq 'agent|agents' "$REPORT_DIR/ruflo-help.txt"; then
        pass "Ruflo CLI exposes agent-related commands"
    else
        warn "Ruflo CLI help does not expose an obvious agent command"
    fi

    if grep -Eiq 'swarm' "$REPORT_DIR/ruflo-help.txt"; then
        pass "Ruflo CLI exposes swarm-related commands"
    else
        warn "Ruflo CLI help does not expose swarm command"
    fi

    if grep -Eiq 'task' "$REPORT_DIR/ruflo-help.txt"; then
        pass "Ruflo CLI exposes task-related commands"
    else
        warn "Ruflo CLI help does not expose task command"
    fi

else
    warn "Skipping Ruflo command discovery because runtime is unavailable"
fi

# ------------------------------------------------------------
# 7. RUFLO STATUS
# ------------------------------------------------------------

section "7. RUFLO STATUS"

if [[ -n "$RUFLO_CMD" ]]; then

    STATUS_OK=0

    for args in \
        "status" \
        "agent status" \
        "agents status" \
        "swarm status"
    do
        log
        log "Trying: $RUFLO_CMD $args"

        if "$RUFLO_CMD" $args >> "$AGENT_LOG" 2>&1; then
            pass "Supported status command: $args"
            STATUS_OK=1
            break
        else
            log "[INFO] Command not supported or returned non-zero: $args"
        fi
    done

    if (( STATUS_OK == 0 )); then
        warn "No known Ruflo status command succeeded"
    fi

else
    warn "Ruflo runtime unavailable"
fi

# ------------------------------------------------------------
# 8. AGENT INVENTORY
# ------------------------------------------------------------

section "8. AGENT INVENTORY"

AGENT_LIST_OK=0

if [[ -n "$RUFLO_CMD" ]]; then

    for args in \
        "agent list" \
        "agents list" \
        "agent status" \
        "agents" \
        "status --agents"
    do
        log "Trying: $RUFLO_CMD $args"

        if "$RUFLO_CMD" $args >> "$AGENT_LOG" 2>&1; then
            pass "Agent inventory command succeeded: $args"
            AGENT_LIST_OK=1
            break
        fi
    done

    if (( AGENT_LIST_OK == 0 )); then
        warn "No known agent inventory command succeeded"
    fi
else
    warn "Skipping agent inventory"
fi

# ------------------------------------------------------------
# 9. AGENT DEFINITIONS
# ------------------------------------------------------------

section "9. AGENT DEFINITIONS"

AGENT_DIRS=(
    ".agents"
    ".agents/skills"
    ".agents/skills/ruflo"
    ".claude-flow"
)

for d in "${AGENT_DIRS[@]}"; do
    if [[ -d "$d" ]]; then
        pass "Agent/Ruflo directory exists: $d"
    else
        warn "Missing agent/Ruflo directory: $d"
    fi
done

log
log "Agent-related files:"

find .agents .claude-flow .claude \
    -type f \
    \( -iname '*agent*' -o -iname '*swarm*' -o -iname '*skill*' \) \
    2>/dev/null |
    head -100 |
    tee "$REPORT_DIR/agent-files.txt" | tee -a "$MAIN_LOG"

# ------------------------------------------------------------
# 10. SAFE AGENT SPAWN DISCOVERY
# ------------------------------------------------------------

section "10. AGENT SPAWN CAPABILITY"

SPAWN_CAPABLE=0

if [[ -n "$RUFLO_CMD" ]]; then

    if grep -Eiq '(^|[^a-z])spawn([^a-z]|$)' "$REPORT_DIR/ruflo-help.txt"; then
        pass "Ruflo help exposes spawn capability"
        SPAWN_CAPABLE=1
    else
        warn "Ruflo top-level help does not expose spawn"
    fi

    if grep -Eiq 'agent.*spawn|spawn.*agent' "$REPORT_DIR/ruflo-help.txt"; then
        pass "Agent spawn capability appears available"
        SPAWN_CAPABLE=1
    fi

    # Discover subcommand help rather than guessing execution syntax.
    for args in \
        "agent --help" \
        "agents --help" \
        "spawn --help" \
        "swarm --help"
    do
        log
        log "Capability probe: $RUFLO_CMD $args"

        "$RUFLO_CMD" $args >> "$REPORT_DIR/spawn-capability.txt" 2>&1 || true
    done

    if grep -Eiq 'spawn' "$REPORT_DIR/spawn-capability.txt"; then
        pass "Agent/swarm spawn syntax discovered"
    else
        warn "Spawn syntax was not exposed by the installed CLI"
    fi
else
    warn "Cannot test agent spawning without Ruflo runtime"
fi

# ------------------------------------------------------------
# 11. PROJECT CORE TESTS
# ------------------------------------------------------------

section "11. PROJECT CORE TESTS"

PYTHON=""

if [[ -x "$PROJECT_DIR/backend/venv/bin/python" ]]; then
    PYTHON="$PROJECT_DIR/backend/venv/bin/python"
elif command -v python3 >/dev/null 2>&1; then
    PYTHON="$(command -v python3)"
fi

if [[ -n "$PYTHON" ]]; then

    if "$PYTHON" -m pip check > "$REPORT_DIR/pip-check.txt" 2>&1; then
        pass "Python pip check passed"
    else
        fail "Python pip check failed"
    fi

    if find backend/venv/lib/python3.12/site-packages \
        -maxdepth 1 \
        -type d \
        -name '~*' \
        -print -quit 2>/dev/null |
        grep -q .; then

        fail "Invalid Python distributions detected"
    else
        pass "No invalid Python distributions detected"
    fi

    if "$PYTHON" - <<'PY' > "$REPORT_DIR/python-imports.txt" 2>&1
import numpy
import scipy
import pandas
import sklearn
import chromadb
import onnxruntime
import websockets

from mcp.server.fastmcp import FastMCP

print("numpy:", numpy.__version__)
print("scipy:", scipy.__version__)
print("pandas:", pandas.__version__)
print("sklearn:", sklearn.__version__)
print("chromadb:", chromadb.__version__)
print("onnxruntime:", onnxruntime.__version__)
print("websockets:", websockets.__version__)
print("FastMCP: PASS")
PY
    then
        pass "Python core imports passed"
    else
        fail "Python core imports failed"
        cat "$REPORT_DIR/python-imports.txt" >> "$MAIN_LOG"
    fi

else
    fail "Python interpreter unavailable"
fi

# ------------------------------------------------------------
# 12. PROGRAM SERVICE
# ------------------------------------------------------------

section "12. PROGRAM SERVICE CONTRACT"

if [[ -n "$PYTHON" ]]; then

"$PYTHON" - <<'PY' > "$REPORT_DIR/program-service.txt" 2>&1
import inspect
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

assert list(inspect.signature(
    program_service.create_program
).parameters) == ["db", "tenant_id", "data"]

assert list(inspect.signature(
    program_service.get_program
).parameters) == ["db", "program_id", "tenant_id"]

assert hasattr(program_service, "_compute_status_rollup")

print("PROGRAM SERVICE CONTRACT: PASS")
PY

    if [[ $? -eq 0 ]]; then
        pass "Program service contract valid"
    else
        fail "Program service contract failed"
        cat "$REPORT_DIR/program-service.txt" >> "$MAIN_LOG"
    fi

fi

# ------------------------------------------------------------
# 13. TARGETED CORE TESTS
# ------------------------------------------------------------

section "13. TARGETED CORE TESTS"

CORE_TESTS=(
    "tests/test_program_control.py"
    "backend/tests/test_mcp_server.py"
)

if [[ -n "$PYTHON" ]]; then

    if "$PYTHON" -m pytest \
        "${CORE_TESTS[@]}" \
        -q \
        --maxfail=5 \
        > "$REPORT_DIR/core-tests.txt" 2>&1; then

        pass "Ruflo/project core tests passed"

        grep -E 'passed|failed|error|collected' \
            "$REPORT_DIR/core-tests.txt" |
            tail -20 |
            tee -a "$MAIN_LOG"

    else
        fail "Core tests failed"
        cat "$REPORT_DIR/core-tests.txt" >> "$MAIN_LOG"
    fi

fi

# ------------------------------------------------------------
# 14. FULL PYTEST DIAGNOSTIC
# ------------------------------------------------------------

section "14. FULL PROJECT PYTEST DIAGNOSTIC"

if [[ -n "$PYTHON" ]]; then

    set +e

    "$PYTHON" -m pytest \
        --collect-only \
        -q \
        > "$PYTEST_LOG" 2>&1

    PYTEST_RC=$?

    set -e

    COLLECTED="$(grep -Eo '[0-9]+ tests collected' "$PYTEST_LOG" |
        tail -1 || true)"

    ERRORS="$(grep -Eo '[0-9]+ errors?' "$PYTEST_LOG" |
        tail -1 || true)"

    log "Pytest collection: ${COLLECTED:-unknown}"
    log "Collection errors : ${ERRORS:-0}"

    if (( PYTEST_RC == 0 )); then
        pass "Full pytest collection completed"
    else
        warn "Full pytest collection has diagnostics"
    fi

fi

# ------------------------------------------------------------
# 15. MCP
# ------------------------------------------------------------

section "15. MCP / FASTMCP"

if [[ -n "$PYTHON" ]]; then

    if "$PYTHON" - <<'PY' > "$REPORT_DIR/mcp.txt" 2>&1
import mcp
from mcp.server.fastmcp import FastMCP

print("MCP:", mcp)
print("FastMCP:", FastMCP)
print("MCP IMPORT: PASS")
PY
    then
        pass "FastMCP import succeeded"
    else
        fail "FastMCP import failed"
    fi

fi

# ------------------------------------------------------------
# 16. LARGE FILES
# ------------------------------------------------------------

section "16. RUNTIME ARTIFACTS"

find "$PROJECT_DIR" \
    -type f \
    -size +500M \
    -not -path "$REPORT_DIR/*" \
    -printf '%s %p\n' \
    2>/dev/null |
    sort -nr |
    awk '{
        printf "%.0fMB %s\n", $1/1024/1024, $2
    }' > "$REPORT_DIR/large-files.txt"

if [[ -s "$REPORT_DIR/large-files.txt" ]]; then
    warn "Files larger than 500MB detected"
    cat "$REPORT_DIR/large-files.txt" | head -20 | tee -a "$MAIN_LOG"
else
    pass "No files larger than 500MB detected"
fi

find "$PROJECT_DIR" \
    -type f \
    \( -name '*.log' -o -name '*.txt' \) \
    -size +50M \
    -not -path "$REPORT_DIR/*" \
    -printf '%s %p\n' \
    2>/dev/null |
    sort -nr |
    awk '{
        printf "%.0fMB %s\n", $1/1024/1024, $2
    }' > "$REPORT_DIR/large-logs.txt"

if [[ -s "$REPORT_DIR/large-logs.txt" ]]; then
    warn "Large logs detected"
    cat "$REPORT_DIR/large-logs.txt" | head -20 | tee -a "$MAIN_LOG"
else
    pass "No large logs detected"
fi

# ------------------------------------------------------------
# 17. GIT
# ------------------------------------------------------------

section "17. GIT STATE"

if git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
    pass "Git repository detected"

    if [[ -z "$(git status --porcelain 2>/dev/null)" ]]; then
        pass "Git working tree clean"
    else
        warn "Git working tree contains changes"
        git status --short > "$REPORT_DIR/git-status.txt"
    fi
else
    warn "Git repository not detected"
fi

# ------------------------------------------------------------
# 18. AGENT COLLABORATION EVIDENCE
# ------------------------------------------------------------

section "18. AGENT COLLABORATION EVIDENCE"

EVIDENCE_COUNT=0

for d in \
    ".swarm" \
    ".hive-mind" \
    ".claude-flow" \
    ".agents"
do
    if [[ -d "$d" ]]; then
        COUNT="$(find "$d" -type f 2>/dev/null | wc -l)"
        log "$d : $COUNT file(s)"

        if (( COUNT > 0 )); then
            EVIDENCE_COUNT=$((EVIDENCE_COUNT + 1))
        fi
    fi
done

if (( EVIDENCE_COUNT >= 2 )); then
    pass "Ruflo agent/swarm state evidence exists"
else
    warn "Insufficient agent collaboration state evidence"
fi

# ------------------------------------------------------------
# 19. HEALTH SCORE
# ------------------------------------------------------------

section "19. RUFLO AGENT HEALTH SCORE"

# Scoring deliberately prioritizes actual runtime and agent capabilities.
SCORE=100

# Runtime is critical.
if [[ -z "$RUFLO_CMD" ]]; then
    SCORE=$((SCORE - 35))
fi

if (( AGENT_LIST_OK == 0 )); then
    SCORE=$((SCORE - 10))
fi

if (( SPAWN_CAPABLE == 0 )); then
    SCORE=$((SCORE - 10))
fi

if (( FAIL > 0 )); then
    SCORE=$((SCORE - FAIL * 5))
fi

if (( WARN > 0 )); then
    SCORE=$((SCORE - WARN * 2))
fi

if (( SCORE < 0 )); then
    SCORE=0
fi

if (( FAIL > 0 )); then
    RESULT="FAILED"
elif (( SCORE >= 85 )); then
    RESULT="HEALTHY"
elif (( SCORE >= 70 )); then
    RESULT="DEGRADED"
else
    RESULT="AT_RISK"
fi

log "Health Score : $SCORE / 100"
log "PASS         : $PASS"
log "WARN         : $WARN"
log "FAIL         : $FAIL"
log "RESULT       : $RESULT"

# ------------------------------------------------------------
# 20. FINAL REPORT
# ------------------------------------------------------------

section "20. FINAL RESULT"

cat > "$SUMMARY" <<EOF
RUFLO AGENT ENTERPRISE TEST v11 SUMMARY

Project: $PROJECT_DIR
Date: $(date)
Host: $(hostname)

Ruflo Runtime: ${RUFLO_CMD:-UNAVAILABLE}
Runtime Type: $CLI_TYPE
Ruflo Version: $RUFLO_VERSION

Health Score: $SCORE / 100

PASS: $PASS
WARN: $WARN
FAIL: $FAIL

Result: $RESULT

Important:
This test distinguishes:
1. Ruflo runtime availability
2. Supported CLI capabilities
3. Agent inventory capability
4. Agent spawn capability
5. Project core health
6. Full pytest environmental diagnostics

The script does NOT treat unsupported Ruflo commands
as application failures.

Report directory:
$REPORT_DIR
EOF

cat "$SUMMARY"

cat > "$JSON" <<EOF
{
  "project": "$PROJECT_DIR",
  "timestamp": "$(date --iso-8601=seconds)",
  "ruflo_command": "$RUFLO_CMD",
  "cli_type": "$CLI_TYPE",
  "ruflo_version": "$RUFLO_VERSION",
  "health_score": $SCORE,
  "pass": $PASS,
  "warn": $WARN,
  "fail": $FAIL,
  "result": "$RESULT",
  "agent_inventory": $AGENT_LIST_OK,
  "spawn_capability": $SPAWN_CAPABLE
}
EOF

log
log "============================================================"
log "RUFLO AGENT ENTERPRISE TEST v11 COMPLETE"
log "============================================================"
log "PASS   : $PASS"
log "WARN   : $WARN"
log "FAIL   : $FAIL"
log "SCORE  : $SCORE / 100"
log "RESULT : $RESULT"
log
log "Summary : $SUMMARY"
log "JSON    : $JSON"
log "Report  : $MAIN_LOG"
log "CLI     : $CLI_LOG"
log "Agents  : $AGENT_LOG"
log "Tasks   : $TASK_LOG"
log "Swarm   : $SWARM_LOG"
log "============================================================"

exit 0
