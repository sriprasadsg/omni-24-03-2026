#!/usr/bin/env bash

# ============================================================
# Ruflo Enterprise Project Health Test v5
# ============================================================
#
# Purpose:
#   Test the project from a Ruflo / Claude Flow perspective
#   while separating genuine application failures from:
#     - optional Ruflo components
#     - external services
#     - environment-dependent tests
#     - large files/logs
#     - diagnostic-only pytest collection problems
#
# Exit codes:
#   0 = HEALTHY
#   1 = DEGRADED
#   2 = FAILED
#
# ============================================================

set -u
set -o pipefail

PROJECT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$PROJECT" || exit 2

TIMESTAMP="$(date '+%Y%m%d_%H%M%S')"
DATE_HUMAN="$(date '+%a %d %b %Y %H:%M:%S %Z')"
HOST="$(hostname)"
USER_NAME="$(id -un)"

REPORT_DIR="$PROJECT/ruflo-test-report-$TIMESTAMP"
mkdir -p "$REPORT_DIR"

MAIN_LOG="$REPORT_DIR/ruflo-enterprise-test-v5.log"
SUMMARY="$REPORT_DIR/summary.txt"
JSON_SUMMARY="$REPORT_DIR/summary.json"

PYTHON_REPORT="$REPORT_DIR/python-validation.txt"
CORE_TEST_REPORT="$REPORT_DIR/core-tests.txt"
FULL_TEST_REPORT="$REPORT_DIR/full-project-tests.txt"
RUFLO_REPORT="$REPORT_DIR/ruflo-cli.txt"
NPM_REPORT="$REPORT_DIR/npm-validation.txt"
CONFIG_REPORT="$REPORT_DIR/config-validation.txt"
STATE_REPORT="$REPORT_DIR/state-validation.txt"
SOURCE_REPORT="$REPORT_DIR/source-blockers.txt"
LARGE_FILES="$REPORT_DIR/large-files.txt"
LARGE_LOGS="$REPORT_DIR/large-logs.txt"
SERVICES_REPORT="$REPORT_DIR/external-services.txt"

PASS=0
WARN=0
FAIL=0

RESULT="HEALTHY"

log() {
    echo "$*" | tee -a "$MAIN_LOG"
}

section() {
    echo
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

command_exists() {
    command -v "$1" >/dev/null 2>&1
}

file_exists() {
    [[ -f "$1" ]]
}

dir_exists() {
    [[ -d "$1" ]]
}

# ------------------------------------------------------------
# Header
# ------------------------------------------------------------

cat > "$MAIN_LOG" <<EOF
RUFLO ENTERPRISE TEST v5
Project : $PROJECT
Date    : $DATE_HUMAN
Host    : $HOST
User    : $USER_NAME
Kernel  : $(uname -r)
Report  : $REPORT_DIR
EOF

log ""
log "RUFLO ENTERPRISE TEST v5"
log "Project : $PROJECT"
log "Date    : $DATE_HUMAN"
log "Host    : $HOST"
log "User    : $USER_NAME"
log "Kernel  : $(uname -r)"
log "Report  : $REPORT_DIR"

# ============================================================
# 1. SYSTEM HEALTH
# ============================================================

section "1. SYSTEM HEALTH"

CPU_MODEL="$(lscpu 2>/dev/null | awk -F: '/Model name/ {gsub(/^[ \t]+/,"",$2); print $2; exit}')"
CPU_CORES="$(nproc 2>/dev/null || echo unknown)"

log "CPU Model : ${CPU_MODEL:-unknown}"
log "CPU Cores : $CPU_CORES"

free -h | tee -a "$MAIN_LOG"

if command_exists swapon; then
    swapon --show | tee -a "$MAIN_LOG"
fi

df -h "$PROJECT" | tee -a "$MAIN_LOG"
df -ih "$PROJECT" | tee -a "$MAIN_LOG"

DISK_USE="$(df -P "$PROJECT" | awk 'NR==2 {gsub("%","",$5); print $5}')"
INODE_USE="$(df -Pi "$PROJECT" | awk 'NR==2 {gsub("%","",$5); print $5}')"

if [[ "$DISK_USE" =~ ^[0-9]+$ ]]; then
    if (( DISK_USE >= 90 )); then
        fail "Filesystem critically full (${DISK_USE}% used)"
    elif (( DISK_USE >= 80 )); then
        warn "Filesystem usage elevated (${DISK_USE}% used)"
    else
        pass "Filesystem capacity healthy (${DISK_USE}% used)"
    fi
else
    warn "Unable to determine filesystem usage"
fi

if [[ "$INODE_USE" =~ ^[0-9]+$ ]]; then
    if (( INODE_USE >= 90 )); then
        fail "Inode usage critically high (${INODE_USE}%)"
    elif (( INODE_USE >= 80 )); then
        warn "Inode usage elevated (${INODE_USE}%)"
    else
        pass "Inode usage healthy (${INODE_USE}%)"
    fi
fi

# ============================================================
# 2. REQUIRED TOOLCHAIN
# ============================================================

section "2. REQUIRED TOOLCHAIN"

TOOLS=(
    bash
    node
    npm
    npx
    git
    python3
    find
    awk
    sed
    grep
    du
    df
    sort
    head
    tail
    jq
)

for cmd in "${TOOLS[@]}"; do
    if command_exists "$cmd"; then
        pass "$cmd available: $(command -v "$cmd")"
    else
        fail "$cmd is missing"
    fi
done

# ============================================================
# 3. RUNTIME VERSIONS
# ============================================================

section "3. RUNTIME VERSIONS"

NODE_VERSION="$(node --version 2>/dev/null || echo unavailable)"
NPM_VERSION="$(npm --version 2>/dev/null || echo unavailable)"
NPX_VERSION="$(npx --version 2>/dev/null || echo unavailable)"
GIT_VERSION="$(git --version 2>/dev/null || echo unavailable)"
PY3_VERSION="$(python3 --version 2>/dev/null || echo unavailable)"

log "Node : $NODE_VERSION"
log "npm  : $NPM_VERSION"
log "npx  : $NPX_VERSION"
log "Git  : $GIT_VERSION"
log "Py3  : $PY3_VERSION"

NODE_MAJOR="$(echo "$NODE_VERSION" | sed -E 's/^v([0-9]+).*/\1/')"

if [[ "$NODE_MAJOR" =~ ^[0-9]+$ ]]; then
    if (( NODE_MAJOR >= 20 )); then
        pass "Node.js supported enterprise major detected: $NODE_MAJOR"
    else
        warn "Node.js major version is $NODE_MAJOR; Node 20+ is preferred"
    fi
else
    fail "Unable to determine Node.js major version"
fi

# ============================================================
# 4. NODE PROJECT
# ============================================================

section "4. NODE PROJECT"

if file_exists package.json; then
    pass "package.json exists"

    if jq empty package.json >/dev/null 2>&1; then
        pass "package.json is valid JSON"
    else
        fail "package.json contains invalid JSON"
    fi
else
    fail "package.json missing"
fi

if file_exists package-lock.json; then
    pass "package-lock.json exists"
else
    warn "package-lock.json missing"
fi

if dir_exists node_modules; then
    NODE_MODULE_SIZE="$(du -sh node_modules 2>/dev/null | awk '{print $1}')"
    pass "node_modules exists ($NODE_MODULE_SIZE)"
else
    fail "node_modules directory missing"
fi

if command_exists npm && file_exists package.json; then
    npm ls --depth=0 > "$NPM_REPORT" 2>&1
    NPM_RC=$?

    cat "$NPM_REPORT" >> "$MAIN_LOG"

    if (( NPM_RC == 0 )); then
        pass "npm top-level dependency tree is healthy"
    else
        warn "npm dependency tree has issues; see npm-validation.txt"
    fi
fi

# ============================================================
# 5. RUFLO / CLAUDE FLOW
# ============================================================

section "5. RUFLO / CLAUDE FLOW"

RUFLO_VERSION="unknown"
CLAUDE_FLOW_VERSION="unknown"

if command_exists ruflo; then
    if ruflo --version > "$RUFLO_REPORT" 2>&1; then
        RUFLO_VERSION="$(head -1 "$RUFLO_REPORT")"
        pass "Global Ruflo executable available: $RUFLO_VERSION"
    else
        warn "Global Ruflo executable exists but --version failed"
    fi
else
    warn "No global Ruflo executable"
fi

LOCAL_RUFLO=""

if [[ -x "$PROJECT/node_modules/.bin/ruflo" ]]; then
    LOCAL_RUFLO="$PROJECT/node_modules/.bin/ruflo"
elif [[ -x "$PROJECT/node_modules/.bin/claude-flow" ]]; then
    LOCAL_RUFLO="$PROJECT/node_modules/.bin/claude-flow"
fi

if [[ -n "$LOCAL_RUFLO" ]]; then
    if "$LOCAL_RUFLO" --version >> "$RUFLO_REPORT" 2>&1; then
        pass "Project-local Ruflo/Claude Flow executable works"
    else
        warn "Project-local Ruflo/Claude Flow executable exists but failed"
    fi
else
    warn "Project-local Ruflo executable not installed"
fi

if npx --no-install claude-flow --version >> "$RUFLO_REPORT" 2>&1; then
    CLAUDE_FLOW_VERSION="$(tail -1 "$RUFLO_REPORT")"
    pass "Claude Flow runtime works through npx --no-install"
else
    warn "Claude Flow is not available through npx --no-install"
fi

if grep -RqiE '"(ruflo|claude-flow)"[[:space:]]*:' package.json 2>/dev/null; then
    pass "Ruflo/Claude Flow package reference found in package.json"
else
    warn "No Ruflo/Claude Flow package declared in package.json"
fi

# ============================================================
# 6. RUFLO PROJECT STRUCTURE
# ============================================================

section "6. RUFLO PROJECT STRUCTURE"

REQUIRED_DIRS=(
    ".agents"
    ".agents/skills"
    ".agents/skills/ruflo"
    ".claude-flow"
    ".claude"
)

for d in "${REQUIRED_DIRS[@]}"; do
    if dir_exists "$d"; then
        SIZE="$(du -sh "$d" 2>/dev/null | awk '{print $1}')"
        pass "Exists: $d ($SIZE)"
    else
        warn "Expected Ruflo/Claude directory missing: $d"
    fi
done

OPTIONAL_DIRS=(
    ".hive-mind"
    ".swarm"
)

for d in "${OPTIONAL_DIRS[@]}"; do
    if dir_exists "$d"; then
        SIZE="$(du -sh "$d" 2>/dev/null | awk '{print $1}')"
        pass "Optional state directory exists: $d ($SIZE)"
    else
        warn "Optional state directory missing: $d"
    fi
done

# ============================================================
# 7. CONFIGURATION
# ============================================================

section "7. CONFIGURATION VALIDATION"

CONFIG_FILES=(
    ".mcp.json"
    ".claude.json"
    ".claude/settings.json"
    ".claude/settings.local.json"
)

: > "$CONFIG_REPORT"

for cfg in "${CONFIG_FILES[@]}"; do
    if file_exists "$cfg"; then
        if jq empty "$cfg" >/dev/null 2>&1; then
            pass "Valid JSON: $cfg"
            echo "[PASS] $cfg" >> "$CONFIG_REPORT"
        else
            fail "Invalid JSON: $cfg"
            echo "[FAIL] $cfg" >> "$CONFIG_REPORT"
        fi
    else
        warn "Configuration file missing: $cfg"
        echo "[WARN] $cfg missing" >> "$CONFIG_REPORT"
    fi
done

if file_exists CLAUDE.md; then
    pass "CLAUDE.md exists"
else
    warn "CLAUDE.md missing"
fi

# ============================================================
# 8. RUFLO STATE
# ============================================================

section "8. RUFLO STATE / PROCESSES"

: > "$STATE_REPORT"

ps aux 2>/dev/null |
    grep -Ei 'ruflo|claude-flow|claude' |
    grep -v grep > "$STATE_REPORT" || true

if [[ -s "$STATE_REPORT" ]]; then
    pass "Ruflo/Claude-related process information collected"
else
    warn "No active Ruflo/Claude process detected"
fi

if find .claude-flow .agents .swarm 2>/dev/null -type f -print -quit |
    grep -q .; then
    pass "Ruflo-related state contains files"
else
    warn "Ruflo-related state directories contain no files"
fi

# ============================================================
# 9. PYTHON ENVIRONMENT
# ============================================================

section "9. PYTHON ENVIRONMENT"

PYTHON_BIN="$PROJECT/backend/venv/bin/python"

if [[ ! -x "$PYTHON_BIN" ]]; then
    PYTHON_BIN="$(command -v python3)"
    warn "Backend virtualenv Python not found; using system Python"
else
    pass "Backend virtualenv Python detected"
fi

{
    echo "Python: $PYTHON_BIN"
    "$PYTHON_BIN" --version
    echo
    echo "=== pip check ==="
    "$PYTHON_BIN" -m pip check
    echo
    echo "=== invalid distributions ==="
    find "$PROJECT/backend/venv/lib/python3.12/site-packages" \
        -maxdepth 1 \
        -type d \
        -name '~*' \
        -printf '%f\n' 2>/dev/null | sort
} > "$PYTHON_REPORT" 2>&1

cat "$PYTHON_REPORT" >> "$MAIN_LOG"

if "$PYTHON_BIN" -m pip check >/dev/null 2>&1; then
    pass "Python pip check passed"
else
    fail "Python pip check failed; see python-validation.txt"
fi

INVALID_DIST_COUNT=0

if [[ -d "$PROJECT/backend/venv/lib/python3.12/site-packages" ]]; then
    INVALID_DIST_COUNT="$(
        find "$PROJECT/backend/venv/lib/python3.12/site-packages" \
            -maxdepth 1 \
            -type d \
            -name '~*' 2>/dev/null |
        wc -l
    )"
fi

if (( INVALID_DIST_COUNT == 0 )); then
    pass "No invalid Python distributions detected"
else
    fail "$INVALID_DIST_COUNT invalid Python distributions detected"
fi

# Core Python imports
CORE_IMPORT_OUTPUT="$(
"$PYTHON_BIN" - <<'PY'
modules=(
    numpy
    scipy
    pandas
    sklearn
    chromadb
    onnxruntime
    psutil
    watchdog
    websockets
    langgraph
)

failed=0

for module in "${modules[@]}"; do
    if python -c "import $module" >/dev/null 2>&1; then
        echo "[PASS] $module"
    else
        echo "[FAIL] $module"
        failed=1
    fi
done

exit "$failed"
PY
)" || true

echo "$CORE_IMPORT_OUTPUT" >> "$PYTHON_REPORT"
echo "$CORE_IMPORT_OUTPUT" >> "$MAIN_LOG"

if echo "$CORE_IMPORT_OUTPUT" | grep -q '\[FAIL\]'; then
    fail "Python core imports failed; see python-validation.txt"
else
    pass "Python core imports passed"
fi

# ============================================================
# 10. PROGRAM SERVICE CONTRACT
# ============================================================

section "10. PROGRAM SERVICE CONTRACT"

PROGRAM_OUTPUT="$(
"$PYTHON_BIN" - <<'PY'
import inspect
from backend import program_service

expected = [
    "create_program",
    "get_program",
    "list_programs",
    "update_controls",
    "delete_program",
]

failed = False

for name in expected:
    if hasattr(program_service, name):
        print(f"[PASS] {name}")
    else:
        print(f"[FAIL] Missing function: {name}")
        failed = True

if hasattr(program_service, "create_program"):
    params = list(inspect.signature(program_service.create_program).parameters)
    expected_params = ["db", "tenant_id", "data"]

    if params == expected_params:
        print("[PASS] create_program signature")
    else:
        print(
            f"[FAIL] create_program signature: "
            f"{params} != {expected_params}"
        )
        failed = True

if hasattr(program_service, "get_program"):
    params = list(inspect.signature(program_service.get_program).parameters)
    expected_params = ["db", "program_id", "tenant_id"]

    if params == expected_params:
        print("[PASS] get_program signature")
    else:
        print(
            f"[FAIL] get_program signature: "
            f"{params} != {expected_params}"
        )
        failed = True

if hasattr(program_service, "_compute_status_rollup"):
    print("[PASS] status rollup implementation")
else:
    print("[FAIL] status rollup implementation missing")
    failed = True

raise SystemExit(1 if failed else 0)
PY
)" || true

echo "$PROGRAM_OUTPUT" >> "$SOURCE_REPORT"
echo "$PROGRAM_OUTPUT" >> "$MAIN_LOG"

if echo "$PROGRAM_OUTPUT" | grep -q '\[FAIL\]'; then
    fail "Program service contract failed"
else
    pass "Program service contract is valid"
fi

# ============================================================
# 11. MCP FASTMCP
# ============================================================

section "11. MCP FASTMCP"

MCP_OUTPUT="$(
"$PYTHON_BIN" - <<'PY'
try:
    from mcp.server.fastmcp import FastMCP
    import mcp

    print("[PASS] FastMCP import")
    print("FastMCP:", FastMCP)
    print("MCP module:", mcp.__file__)

except Exception as e:
    print("[FAIL]", type(e).__name__, str(e))
    raise SystemExit(1)
PY
)" || true

echo "$MCP_OUTPUT" >> "$MAIN_LOG"
echo "$MCP_OUTPUT" >> "$SOURCE_REPORT"

if echo "$MCP_OUTPUT" | grep -q '\[FAIL\]'; then
    fail "FastMCP import failed"
else
    pass "FastMCP import is available"
fi

# ============================================================
# 12. TARGETED RUFLO CORE TESTS
# ============================================================

section "12. TARGETED RUFLO CORE TESTS"

CORE_TESTS=()

[[ -f tests/test_program_control.py ]] &&
    CORE_TESTS+=("tests/test_program_control.py")

[[ -f backend/tests/test_mcp_server.py ]] &&
    CORE_TESTS+=("backend/tests/test_mcp_server.py")

if (( ${#CORE_TESTS[@]} == 0 )); then
    warn "No targeted Ruflo/core tests found"
else
    log "Running targeted core tests:"
    printf '%s\n' "${CORE_TESTS[@]}" | tee "$CORE_TEST_REPORT" >> "$MAIN_LOG"

    "$PYTHON_BIN" -m pytest \
        "${CORE_TESTS[@]}" \
        -q \
        --maxfail=10 >> "$CORE_TEST_REPORT" 2>&1

    CORE_RC=$?

    cat "$CORE_TEST_REPORT" >> "$MAIN_LOG"

    if (( CORE_RC == 0 )); then
        pass "All targeted core tests passed"
    else
        fail "Targeted core tests failed; see core-tests.txt"
    fi
fi

# ============================================================
# 13. FULL PROJECT PYTEST - DIAGNOSTIC
# ============================================================

section "13. FULL PROJECT TEST SUITE"

log "Full-project pytest is diagnostic."
log "External-service, network-dependent and non-Python artifacts"
log "are classified separately from core application failures."

"$PYTHON_BIN" -m pytest \
    --collect-only \
    -q \
    > "$FULL_TEST_REPORT" 2>&1

PYTEST_RC=$?

COLLECTED="$(
    grep -Eo '[0-9]+ tests? collected' "$FULL_TEST_REPORT" |
    tail -1 |
    awk '{print $1}'
)"

ERROR_COUNT="$(
    grep -E '^[[:space:]]*ERROR|ERROR collecting|ERROR ' \
    "$FULL_TEST_REPORT" |
    wc -l
)"

log "Collected tests: ${COLLECTED:-unknown}"
log "Collection diagnostics: $ERROR_COUNT"

if (( PYTEST_RC == 0 )); then
    pass "Full pytest collection completed without errors"
else
    if grep -Eqi \
        'Connection refused|ConnectError|URLError|httpx|network|UnicodeDecodeError|test_summary.txt|external' \
        "$FULL_TEST_REPORT"; then

        warn "Full pytest collection contains environment/external-service issues"
    else
        warn "Full pytest collection has diagnostic errors; see full-project-tests.txt"
    fi
fi

if grep -Eqi 'test_summary\.txt' "$FULL_TEST_REPORT"; then
    warn "Pytest discovered non-Python text artifacts"
fi

if grep -Eqi \
    'Connection refused|ConnectError|URLError|All connection attempts failed' \
    "$FULL_TEST_REPORT"; then
    warn "Pytest collection includes external-service/network-dependent tests"
fi

# ============================================================
# 14. SOURCE BLOCKER SCAN
# ============================================================

section "14. SOURCE-LEVEL BLOCKER SCAN"

: > "$SOURCE_REPORT"

SOURCE_BLOCKERS=0

# Broken imports commonly seen in the project
if grep -Rni \
    'from backend.program_service import.*get_program_status' \
    tests backend \
    --include='*.py' 2>/dev/null |
    grep -q .; then

    if ! grep -q 'def get_program_status' backend/program_service.py 2>/dev/null; then
        echo "[FAIL] Tests still reference missing get_program_status" >> "$SOURCE_REPORT"
        fail "Tests still reference missing get_program_status"
        SOURCE_BLOCKERS=$((SOURCE_BLOCKERS + 1))
    fi
fi

# MCP source import
if grep -Rni \
    'from mcp.server.fastmcp import FastMCP' \
    backend \
    --include='*.py' 2>/dev/null |
    grep -q .; then

    if "$PYTHON_BIN" -c 'from mcp.server.fastmcp import FastMCP' >/dev/null 2>&1; then
        pass "MCP source imports are currently resolvable"
    else
        echo "[FAIL] MCP FastMCP source import unavailable" >> "$SOURCE_REPORT"
        fail "MCP FastMCP source import unavailable"
        SOURCE_BLOCKERS=$((SOURCE_BLOCKERS + 1))
    fi
fi

if (( SOURCE_BLOCKERS == 0 )); then
    pass "No known source-level blockers detected"
fi

# ============================================================
# 15. LARGE FILES
# ============================================================

section "15. LARGE FILES / LOGS"

find "$PROJECT" \
    -type f \
    -size +500M \
    -not -path "$REPORT_DIR/*" \
    -not -path "$PROJECT/backend/venv/*" \
    -printf '%s %p\n' 2>/dev/null |
    sort -nr |
    awk '{
        size=$1
        file=$0
        sub(/^[0-9]+ /,"",file)
        printf "%.0fMB %s\n", size/1024/1024, file
    }' > "$LARGE_FILES"

if [[ -s "$LARGE_FILES" ]]; then
    warn "Files larger than 500MB detected; see large-files.txt"
    cat "$LARGE_FILES" | tee -a "$MAIN_LOG"
else
    pass "No files larger than 500MB detected"
fi

find "$PROJECT" \
    -type f \
    \( -name '*.log' -o -name '*.out' \) \
    -size +50M \
    -not -path "$REPORT_DIR/*" \
    -not -path "$PROJECT/backend/venv/*" \
    -printf '%s %p\n' 2>/dev/null |
    sort -nr |
    awk '{
        size=$1
        file=$0
        sub(/^[0-9]+ /,"",file)
        printf "%.0fMB %s\n", size/1024/1024, file
    }' > "$LARGE_LOGS"

if [[ -s "$LARGE_LOGS" ]]; then
    warn "Logs larger than 50MB detected; see large-logs.txt"
    cat "$LARGE_LOGS" | tee -a "$MAIN_LOG"
else
    pass "No oversized logs detected"
fi

# ============================================================
# 16. AUDIT REPORT HYGIENE
# ============================================================

section "16. AUDIT REPORT HYGIENE"

if dir_exists audit-reports; then
    AUDIT_COUNT="$(find audit-reports -type f 2>/dev/null | wc -l)"

    if (( AUDIT_COUNT > 0 )); then
        pass "audit-reports directory exists with $AUDIT_COUNT files"
    else
        warn "audit-reports directory exists but is empty"
    fi
else
    warn "audit-reports directory does not exist"
fi

# ============================================================
# 17. GIT
# ============================================================

section "17. GIT"

if git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
    pass "Git repository detected"

    if git diff --quiet && git diff --cached --quiet; then
        pass "Git working tree clean"
    else
        warn "Git working tree has changes"
    fi

    git status --short > "$REPORT_DIR/git-status.txt"
else
    warn "Project is not a Git repository"
fi

# ============================================================
# 18. EXTERNAL SERVICES
# ============================================================

section "18. EXTERNAL SERVICE / ENVIRONMENT DIAGNOSTICS"

cat > "$SERVICES_REPORT" <<EOF
External-service diagnostics are informational.
These checks do not automatically cause Ruflo FAIL.
EOF

# Common ports that may be used by this project
for port in 3000 8000 8080 11434 27017 5432 6379; do
    if command_exists ss &&
       ss -ltn 2>/dev/null | awk '{print $4}' | grep -qE ":${port}$"; then
        echo "[INFO] TCP port $port is listening" >> "$SERVICES_REPORT"
    fi
done

cat "$SERVICES_REPORT" >> "$MAIN_LOG"

# ============================================================
# 19. FINAL STATUS
# ============================================================

section "19. FINAL RESULT"

if (( FAIL > 0 )); then
    RESULT="FAILED"
elif (( WARN > 0 )); then
    RESULT="DEGRADED"
else
    RESULT="HEALTHY"
fi

log "RUFLO ENTERPRISE TEST v5 SUMMARY"
log "Project: $PROJECT"
log "Date: $DATE_HUMAN"
log "Host: $HOST"
log ""
log "Ruflo: $RUFLO_VERSION"
log "Claude Flow: $CLAUDE_FLOW_VERSION"
log ""
log "PASS: $PASS"
log "WARN: $WARN"
log "FAIL: $FAIL"
log ""
log "RESULT: $RESULT"

cat > "$SUMMARY" <<EOF
RUFLO ENTERPRISE TEST v5 SUMMARY

Project: $PROJECT
Date: $DATE_HUMAN
Host: $HOST

Ruflo: $RUFLO_VERSION
Claude Flow: $CLAUDE_FLOW_VERSION

PASS: $PASS
WARN: $WARN
FAIL: $FAIL

RESULT: $RESULT

Main report:
$MAIN_LOG

Ruflo CLI:
$RUFLO_REPORT

Python validation:
$PYTHON_REPORT

Core tests:
$CORE_TEST_REPORT

Full project tests:
$FULL_TEST_REPORT

NPM validation:
$NPM_REPORT

Config validation:
$CONFIG_REPORT

State validation:
$STATE_REPORT

Source blockers:
$SOURCE_REPORT

Large files:
$LARGE_FILES

Large logs:
$LARGE_LOGS

External services:
$SERVICES_REPORT
EOF

cat > "$JSON_SUMMARY" <<EOF
{
  "test": "ruflo-enterprise-v5",
  "project": "$PROJECT",
  "host": "$HOST",
  "date": "$DATE_HUMAN",
  "ruflo": "$RUFLO_VERSION",
  "claude_flow": "$CLAUDE_FLOW_VERSION",
  "pass": $PASS,
  "warn": $WARN,
  "fail": $FAIL,
  "result": "$RESULT",
  "report_directory": "$REPORT_DIR",
  "main_report": "$MAIN_LOG",
  "summary": "$SUMMARY"
}
EOF

log ""
log "============================================================"
log "RUFLO ENTERPRISE TEST v5 COMPLETE"
log "============================================================"
log "PASS   : $PASS"
log "WARN   : $WARN"
log "FAIL   : $FAIL"
log "RESULT : $RESULT"
log ""
log "Summary : $SUMMARY"
log "JSON    : $JSON_SUMMARY"
log "Report  : $MAIN_LOG"
log "============================================================"

# Exit status intentionally reflects actual project health.
case "$RESULT" in
    HEALTHY)
        exit 0
        ;;
    DEGRADED)
        exit 1
        ;;
    FAILED)
        exit 2
        ;;
esac
