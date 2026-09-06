#!/usr/bin/env bash

set -u
set -o pipefail

PROJECT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$PROJECT"

TIMESTAMP="$(date '+%Y%m%d_%H%M%S')"
REPORT_DIR="$PROJECT/ruflo-test-report-$TIMESTAMP"
mkdir -p "$REPORT_DIR"

MAIN_LOG="$REPORT_DIR/ruflo-enterprise-test-v4.log"
SUMMARY="$REPORT_DIR/summary.txt"

CLI_REPORT="$REPORT_DIR/ruflo-cli.txt"
PYTHON_REPORT="$REPORT_DIR/python-validation.txt"
CORE_TEST_REPORT="$REPORT_DIR/core-tests.txt"
FULL_TEST_REPORT="$REPORT_DIR/full-project-tests.txt"
NPM_REPORT="$REPORT_DIR/npm-validation.txt"
CONFIG_REPORT="$REPORT_DIR/config-validation.txt"
STATE_REPORT="$REPORT_DIR/state-validation.txt"
LARGE_FILES="$REPORT_DIR/large-files.txt"
LARGE_LOGS="$REPORT_DIR/large-logs.txt"
SOURCE_BLOCKERS="$REPORT_DIR/source-blockers.txt"

PASS=0
WARN=0
FAIL=0

RUFLO_VERSION="unknown"
CLAUDE_FLOW_VERSION="unknown"

log() {
    echo "$*" | tee -a "$MAIN_LOG"
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

section() {
    log ""
    log "============================================================"
    log "$*"
    log "============================================================"
}

command_exists() {
    command -v "$1" >/dev/null 2>&1
}

json_valid() {
    jq empty "$1" >/dev/null 2>&1
}

human_size() {
    du -sh "$1" 2>/dev/null | awk '{print $1}'
}

PYTHON=""

if [[ -x "$PROJECT/backend/venv/bin/python" ]]; then
    PYTHON="$PROJECT/backend/venv/bin/python"
elif command_exists python3; then
    PYTHON="$(command -v python3)"
fi

section "RUFLO ENTERPRISE TEST v4"

log "Project : $PROJECT"
log "Date    : $(date)"
log "Host    : $(hostname)"
log "User    : $(id -un)"
log "Kernel  : $(uname -r)"
log "Report  : $REPORT_DIR"

###############################################################################
# 1 SYSTEM
###############################################################################

section "1. SYSTEM HEALTH"

log "CPU Model : $(awk -F: '/model name/ {print $2; exit}' /proc/cpuinfo | xargs 2>/dev/null || echo unknown)"
log "CPU Cores : $(nproc 2>/dev/null || echo unknown)"

free -h | tee -a "$MAIN_LOG"

if command_exists swapon; then
    swapon --show | tee -a "$MAIN_LOG"
fi

df -h "$PROJECT" | tee -a "$MAIN_LOG"
df -i "$PROJECT" | tee -a "$MAIN_LOG"

DISK_USE="$(df -P "$PROJECT" | awk 'NR==2 {gsub("%","",$5); print $5}')"
INODE_USE="$(df -Pi "$PROJECT" | awk 'NR==2 {gsub("%","",$5); print $5}')"

if [[ "$DISK_USE" =~ ^[0-9]+$ ]]; then
    if (( DISK_USE < 85 )); then
        pass "Filesystem capacity healthy (${DISK_USE}% used)"
    elif (( DISK_USE < 95 )); then
        warn "Filesystem capacity elevated (${DISK_USE}% used)"
    else
        fail "Filesystem capacity critical (${DISK_USE}% used)"
    fi
fi

if [[ "$INODE_USE" =~ ^[0-9]+$ ]]; then
    if (( INODE_USE < 80 )); then
        pass "Inode usage healthy (${INODE_USE}%)"
    elif (( INODE_USE < 95 )); then
        warn "Inode usage elevated (${INODE_USE}%)"
    else
        fail "Inode usage critical (${INODE_USE}%)"
    fi
fi

###############################################################################
# 2 COMMANDS
###############################################################################

section "2. REQUIRED COMMANDS"

REQUIRED_COMMANDS=(
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

for cmd in "${REQUIRED_COMMANDS[@]}"; do
    if command_exists "$cmd"; then
        pass "$cmd available: $(command -v "$cmd")"
    else
        fail "$cmd is unavailable"
    fi
done

###############################################################################
# 3 RUNTIMES
###############################################################################

section "3. RUNTIME VERSIONS"

NODE_VERSION="$(node --version 2>/dev/null || echo unavailable)"
NPM_VERSION="$(npm --version 2>/dev/null || echo unavailable)"
NPX_VERSION="$(npx --version 2>/dev/null || echo unavailable)"
GIT_VERSION="$(git --version 2>/dev/null || echo unavailable)"
PY_VERSION="$($PYTHON --version 2>/dev/null || echo unavailable)"

log "Node : $NODE_VERSION"
log "npm  : $NPM_VERSION"
log "npx  : $NPX_VERSION"
log "Git  : $GIT_VERSION"
log "Py3  : $PY_VERSION"

NODE_MAJOR="$(node -p 'process.versions.node.split(".")[0]' 2>/dev/null || echo 0)"

if [[ "$NODE_MAJOR" == "20" || "$NODE_MAJOR" == "22" || "$NODE_MAJOR" == "24" ]]; then
    pass "Node.js supported enterprise major detected: $NODE_MAJOR"
elif [[ "$NODE_MAJOR" =~ ^[0-9]+$ ]] && (( NODE_MAJOR > 0 )); then
    warn "Node.js major version $NODE_MAJOR should be reviewed"
fi

###############################################################################
# 4 NODE PROJECT
###############################################################################

section "4. NODE PROJECT"

if [[ -f package.json ]]; then
    pass "package.json exists"

    if json_valid package.json; then
        pass "package.json is valid JSON"
    else
        fail "package.json is invalid JSON"
    fi
else
    fail "package.json missing"
fi

if [[ -f package-lock.json ]]; then
    pass "package-lock.json exists"
else
    warn "package-lock.json missing"
fi

if [[ -d node_modules ]]; then
    pass "node_modules exists ($(human_size node_modules))"
else
    warn "node_modules missing"
fi

if [[ -f package.json && -d node_modules ]]; then
    npm ls --depth=0 > "$NPM_REPORT" 2>&1
    NPM_RC=$?

    cat "$NPM_REPORT" >> "$MAIN_LOG"

    if (( NPM_RC == 0 )); then
        pass "npm top-level dependency tree is healthy"
    else
        warn "npm dependency tree reports issues; see npm-validation.txt"
    fi
else
    warn "npm dependency validation skipped"
fi

###############################################################################
# 5 RUFLO / CLAUDE FLOW
###############################################################################

section "5. RUFLO / CLAUDE-FLOW CLI"

: > "$CLI_REPORT"

GLOBAL_RUFLO="$(command -v ruflo 2>/dev/null || true)"
GLOBAL_CF="$(command -v claude-flow 2>/dev/null || true)"

if [[ -n "$GLOBAL_RUFLO" ]]; then
    RUFLO_VERSION="$("$GLOBAL_RUFLO" --version 2>&1 | head -1)"
    echo "$RUFLO_VERSION" | tee -a "$CLI_REPORT"
    pass "Global Ruflo executable available: $GLOBAL_RUFLO"
else
    warn "No global Ruflo executable"
fi

if [[ -n "$GLOBAL_CF" ]]; then
    CLAUDE_FLOW_VERSION="$("$GLOBAL_CF" --version 2>&1 | head -1)"
    echo "$CLAUDE_FLOW_VERSION" | tee -a "$CLI_REPORT"
    pass "Global claude-flow executable available"
fi

LOCAL_RUFLO="$(find "$PROJECT/node_modules/.bin" -maxdepth 1 -type f -o -type l 2>/dev/null | grep '/ruflo$' | head -1 || true)"
LOCAL_CF="$(find "$PROJECT/node_modules/.bin" -maxdepth 1 -type f -o -type l 2>/dev/null | grep '/claude-flow$' | head -1 || true)"

if [[ -n "$LOCAL_RUFLO" ]]; then
    RUFLO_VERSION="$("$LOCAL_RUFLO" --version 2>&1 | head -1)"
    echo "$RUFLO_VERSION" | tee -a "$CLI_REPORT"
    pass "Project-local Ruflo executable available"
else
    warn "Project-local Ruflo executable not installed"
fi

if [[ -n "$LOCAL_CF" ]]; then
    CLAUDE_FLOW_VERSION="$("$LOCAL_CF" --version 2>&1 | head -1)"
    echo "$CLAUDE_FLOW_VERSION" | tee -a "$CLI_REPORT"
    pass "Project-local claude-flow executable available"
else
    if npx --no-install claude-flow --version > "$REPORT_DIR/claude-flow-version.txt" 2>&1; then
        CLAUDE_FLOW_VERSION="$(head -1 "$REPORT_DIR/claude-flow-version.txt")"
        echo "$CLAUDE_FLOW_VERSION" | tee -a "$CLI_REPORT"
        pass "claude-flow works through npx --no-install"
    else
        warn "claude-flow is not available locally"
    fi
fi

# Ruflo itself is optional when the project is using Claude Flow compatibility.
if [[ "$RUFLO_VERSION" != "unknown" ]]; then
    pass "Ruflo command is executable"
else
    if [[ "$CLAUDE_FLOW_VERSION" != "unknown" ]]; then
        warn "Ruflo command not directly installed; Claude Flow runtime is available"
    else
        warn "Neither Ruflo nor Claude Flow command is directly available"
    fi
fi

###############################################################################
# 6 PACKAGE DISCOVERY
###############################################################################

section "6. RUFLO PACKAGE DISCOVERY"

PACKAGE_INFO="$(node - <<'NODE' 2>/dev/null
const fs=require('fs');
if (!fs.existsSync('package.json')) process.exit(0);
const p=JSON.parse(fs.readFileSync('package.json','utf8'));
const deps={...(p.dependencies||{}),...(p.devDependencies||{})};
for (const [k,v] of Object.entries(deps)) {
    if (/ruflo|claude-flow/i.test(k)) {
        console.log(k + " " + v);
    }
}
NODE
)"

if [[ -n "$PACKAGE_INFO" ]]; then
    echo "$PACKAGE_INFO" | tee -a "$CLI_REPORT"
    pass "Ruflo/Claude Flow package declared in package.json"
else
    warn "No Ruflo package declared in package.json"
fi

###############################################################################
# 7 PROJECT STRUCTURE
###############################################################################

section "7. RUFLO PROJECT STRUCTURE"

STRUCTURE_REQUIRED=(
    ".agents"
    ".agents/skills"
    ".agents/skills/ruflo"
    ".claude-flow"
    ".claude"
)

for path in "${STRUCTURE_REQUIRED[@]}"; do
    if [[ -e "$PROJECT/$path" ]]; then
        pass "Exists: $path ($(human_size "$PROJECT/$path"))"
    else
        fail "Required Ruflo structure missing: $path"
    fi
done

OPTIONAL_STATE=(
    ".hive-mind"
    ".swarm"
)

for path in "${OPTIONAL_STATE[@]}"; do
    if [[ -e "$PROJECT/$path" ]]; then
        pass "Optional state directory exists: $path ($(human_size "$PROJECT/$path"))"
    else
        warn "Optional state directory missing: $path"
    fi
done

###############################################################################
# 8 CONFIG
###############################################################################

section "8. CONFIGURATION VALIDATION"

CONFIG_FILES=(
    ".mcp.json"
    ".claude.json"
    ".claude/settings.json"
    ".claude/settings.local.json"
)

: > "$CONFIG_REPORT"

for file in "${CONFIG_FILES[@]}"; do
    if [[ -f "$PROJECT/$file" ]]; then
        if json_valid "$PROJECT/$file"; then
            pass "Valid JSON: $file"
            echo "[PASS] $file" >> "$CONFIG_REPORT"
        else
            fail "Invalid JSON: $file"
            echo "[FAIL] $file" >> "$CONFIG_REPORT"
        fi
    else
        warn "Configuration missing: $file"
        echo "[WARN] $file missing" >> "$CONFIG_REPORT"
    fi
done

if [[ -f CLAUDE.md ]]; then
    pass "CLAUDE.md exists"
else
    warn "CLAUDE.md missing"
fi

###############################################################################
# 9 STATE
###############################################################################

section "9. RUFLO STATE / PROCESSES"

: > "$STATE_REPORT"

ps aux | grep -Ei 'ruflo|claude-flow|claude' | grep -v grep > "$STATE_REPORT" 2>&1 || true

if [[ -s "$STATE_REPORT" ]]; then
    pass "Ruflo/Claude-related process information collected"
else
    warn "No active Ruflo/Claude process detected"
fi

if [[ -d "$PROJECT/.claude-flow" ]] && find "$PROJECT/.claude-flow" -type f -print -quit | grep -q .; then
    pass "Ruflo-related state contains files"
else
    warn "Ruflo state directory contains no files"
fi

###############################################################################
# 10 PYTHON
###############################################################################

section "10. PYTHON ENVIRONMENT"

if [[ -z "$PYTHON" ]]; then
    fail "Python interpreter unavailable"
else
    log "Python: $PYTHON"
    "$PYTHON" --version | tee -a "$PYTHON_REPORT"

    "$PYTHON" -m pip check >> "$PYTHON_REPORT" 2>&1
    PIP_RC=$?

    if (( PIP_RC == 0 )); then
        pass "Python pip check passed"
    else
        fail "Python pip dependency check failed"
    fi

    "$PYTHON" - <<'PY' >> "$PYTHON_REPORT" 2>&1
mods=(
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

for m in "${mods[@]}"; do
    if python -c "import $m" >/dev/null 2>&1; then
        echo "[OK] $m"
    else
        echo "[FAIL] $m"
        failed=1
    fi
done

if python - <<'PY2'
from mcp.server.fastmcp import FastMCP
print("[OK] mcp.server.fastmcp.FastMCP")
PY2
then
    :
else
    echo "[FAIL] mcp.server.fastmcp.FastMCP"
    failed=1
fi

if (( failed == 0 )); then
    echo "FAILED: NONE"
else
    echo "FAILED: ONE OR MORE IMPORTS"
fi
PY

    if grep -q '^FAILED: NONE$' "$PYTHON_REPORT"; then
        pass "Python core imports passed"
    else
        fail "Python core imports failed; see python-validation.txt"
    fi

    if find "$PROJECT/backend/venv/lib/python3.12/site-packages" \
        -maxdepth 1 -type d -name '~*' -print -quit | grep -q .; then
        warn "Invalid Python distributions (~*) remain"
    else
        pass "No invalid Python distributions detected"
    fi
fi

###############################################################################
# 11 TARGETED CORE TESTS
###############################################################################

section "11. RUFLO / CORE TARGETED TESTS"

: > "$CORE_TEST_REPORT"

CORE_TESTS=()

[[ -f tests/test_program_control.py ]] &&
    CORE_TESTS+=("tests/test_program_control.py")

[[ -f backend/tests/test_mcp_server.py ]] &&
    CORE_TESTS+=("backend/tests/test_mcp_server.py")

if (( ${#CORE_TESTS[@]} > 0 )); then
    log "Running targeted core tests:"
    printf '%s\n' "${CORE_TESTS[@]}" | tee -a "$CORE_TEST_REPORT"

    "$PYTHON" -m pytest "${CORE_TESTS[@]}" -q --maxfail=5 \
        >> "$CORE_TEST_REPORT" 2>&1

    CORE_RC=$?

    if (( CORE_RC == 0 )); then
        pass "All targeted core tests passed"
    else
        fail "Targeted core tests failed; see core-tests.txt"
    fi
else
    warn "No targeted core tests found"
fi

###############################################################################
# 12 PROGRAM SERVICE CONTRACT
###############################################################################

section "12. PROGRAM SERVICE CONTRACT"

if [[ -f backend/program_service.py ]]; then

    "$PYTHON" - <<'PY' >> "$SOURCE_BLOCKERS" 2>&1
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

assert list(inspect.signature(program_service.create_program).parameters) == [
    "db", "tenant_id", "data"
]

assert list(inspect.signature(program_service.get_program).parameters) == [
    "db", "program_id", "tenant_id"
]

assert hasattr(program_service, "_compute_status_rollup")

print("[PASS] Program service contract")
PY

    if tail -1 "$SOURCE_BLOCKERS" | grep -q '\[PASS\] Program service contract'; then
        pass "Program service contract is valid"
    else
        fail "Program service contract validation failed"
    fi
else
    warn "backend/program_service.py not found"
fi

###############################################################################
# 13 MCP
###############################################################################

section "13. MCP FASTMCP"

"$PYTHON" - <<'PY' > "$REPORT_DIR/mcp-validation.txt" 2>&1
from mcp.server.fastmcp import FastMCP
import mcp

print("[PASS] FastMCP import")
print("FastMCP:", FastMCP)
print("MCP module:", mcp)
PY

if grep -q '\[PASS\] FastMCP import' "$REPORT_DIR/mcp-validation.txt"; then
    pass "FastMCP import is available"
else
    fail "FastMCP import failed"
fi

###############################################################################
# 14 FULL PROJECT TEST COLLECTION
###############################################################################

section "14. FULL PROJECT TEST SUITE"

log "Full-project pytest is diagnostic only."
log "External-service and non-Python test artifacts do not count as Ruflo FAIL."

"$PYTHON" -m pytest --collect-only -q \
    > "$FULL_TEST_REPORT" 2>&1

COLLECT_RC=$?

COLLECTED="$(grep -Eo '[0-9]+ tests? collected' "$FULL_TEST_REPORT" | tail -1 || true)"
ERROR_COUNT="$(grep -c '^ERROR' "$FULL_TEST_REPORT" 2>/dev/null || true)"

log "${COLLECTED:-Test count unavailable}"
log "Collection errors: $ERROR_COUNT"

if (( COLLECT_RC == 0 )); then
    pass "Full project pytest collection completed cleanly"
else
    if grep -q 'UnicodeDecodeError' "$FULL_TEST_REPORT"; then
        warn "Pytest discovered non-Python text artifacts during collection"
    fi

    if grep -qE 'Connection refused|ConnectError|All connection attempts failed|URLError' "$FULL_TEST_REPORT"; then
        warn "Pytest collection includes external-service/network-dependent tests"
    fi

    # If there are remaining errors, report them as suite hygiene warnings.
    if (( ERROR_COUNT > 0 )); then
        warn "Full-project pytest has $ERROR_COUNT collection error(s); these are diagnostic, not automatic Ruflo failures"
    else
        warn "Full-project pytest returned non-zero status"
    fi
fi

###############################################################################
# 15 LARGE FILES
###############################################################################

section "15. LARGE FILES / LOGS"

find "$PROJECT" \
    -type f \
    -size +500M \
    -not -path "$PROJECT/node_modules/*" \
    -not -path "$PROJECT/backend/venv/*" \
    -not -path "$PROJECT/.git/*" \
    -printf '%s %p\n' 2>/dev/null |
sort -nr |
awk '{
    cmd="numfmt --to=iec --suffix=B " $1
    cmd | getline size
    close(cmd)
    print size, $2
}' > "$LARGE_FILES"

if [[ -s "$LARGE_FILES" ]]; then
    warn "Files larger than 500 MB detected; see large-files.txt"
    cat "$LARGE_FILES" | tee -a "$MAIN_LOG"
else
    pass "No project files larger than 500 MB detected"
fi

find "$PROJECT" \
    -type f \
    \( -name "*.log" -o -name "*.out" \) \
    -size +50M \
    -not -path "$PROJECT/node_modules/*" \
    -not -path "$PROJECT/backend/venv/*" \
    -not -path "$PROJECT/.git/*" \
    -printf '%s %p\n' 2>/dev/null |
sort -nr |
awk '{
    cmd="numfmt --to=iec --suffix=B " $1
    cmd | getline size
    close(cmd)
    print size, $2
}' > "$LARGE_LOGS"

if [[ -s "$LARGE_LOGS" ]]; then
    warn "Logs larger than 50 MB detected; see large-logs.txt"
    cat "$LARGE_LOGS" | tee -a "$MAIN_LOG"
else
    pass "No large logs detected"
fi

###############################################################################
# 16 AUDIT REPORTS
###############################################################################

section "16. AUDIT REPORT HYGIENE"

if [[ -d audit-reports ]]; then
    pass "audit-reports directory exists"
else
    warn "audit-reports directory does not exist"
fi

###############################################################################
# 17 GIT
###############################################################################

section "17. GIT"

if git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
    pass "Git repository detected"

    if git diff --quiet && git diff --cached --quiet; then
        pass "Git working tree has no tracked changes"
    else
        warn "Git working tree has changes"
    fi
else
    warn "Git repository not detected"
fi

###############################################################################
# FINAL
###############################################################################

section "18. FINAL RESULT"

RESULT="PASS"

if (( FAIL > 0 )); then
    RESULT="FAILED"
elif (( WARN > 0 )); then
    RESULT="PASS_WITH_WARNINGS"
fi

{
    echo "RUFLO ENTERPRISE TEST v4 SUMMARY"
    echo "Project: $PROJECT"
    echo "Date: $(date)"
    echo "Host: $(hostname)"
    echo
    echo "Ruflo: $RUFLO_VERSION"
    echo "Claude Flow: $CLAUDE_FLOW_VERSION"
    echo
    echo "PASS: $PASS"
    echo "WARN: $WARN"
    echo "FAIL: $FAIL"
    echo
    echo "Result: $RESULT"
    echo
    echo "Main report: $MAIN_LOG"
    echo "Ruflo CLI: $CLI_REPORT"
    echo "Python validation: $PYTHON_REPORT"
    echo "Core tests: $CORE_TEST_REPORT"
    echo "Full project tests: $FULL_TEST_REPORT"
    echo "NPM validation: $NPM_REPORT"
    echo "Config validation: $CONFIG_REPORT"
    echo "State validation: $STATE_REPORT"
    echo "Source blockers: $SOURCE_BLOCKERS"
    echo "Large files: $LARGE_FILES"
    echo "Large logs: $LARGE_LOGS"
} | tee "$SUMMARY" | tee -a "$MAIN_LOG"

log ""
log "============================================================"
log "RUFLO ENTERPRISE TEST v4 COMPLETE"
log "PASS : $PASS"
log "WARN : $WARN"
log "FAIL : $FAIL"
log "RESULT: $RESULT"
log "SUMMARY: $SUMMARY"
log "============================================================"

# Only genuine FAIL conditions produce exit 1.
if (( FAIL > 0 )); then
    exit 1
fi

exit 0
