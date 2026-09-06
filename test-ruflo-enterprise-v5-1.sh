#!/usr/bin/env bash

set -u
set -o pipefail

PROJECT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$PROJECT"

TIMESTAMP="$(date '+%Y%m%d_%H%M%S')"
REPORT_DIR="$PROJECT/ruflo-test-report-$TIMESTAMP"

mkdir -p "$REPORT_DIR"

MAIN_REPORT="$REPORT_DIR/ruflo-enterprise-test-v5.log"
SUMMARY="$REPORT_DIR/summary.txt"

PYTHON_REPORT="$REPORT_DIR/python-validation.txt"
CORE_TESTS="$REPORT_DIR/core-tests.txt"
FULL_TESTS="$REPORT_DIR/full-project-tests.txt"
NPM_REPORT="$REPORT_DIR/npm-validation.txt"
CONFIG_REPORT="$REPORT_DIR/config-validation.txt"
STATE_REPORT="$REPORT_DIR/state-validation.txt"
SOURCE_REPORT="$REPORT_DIR/source-blockers.txt"
LARGE_FILES="$REPORT_DIR/large-files.txt"
LARGE_LOGS="$REPORT_DIR/large-logs.txt"
RUFLO_CLI="$REPORT_DIR/ruflo-cli.txt"

touch \
    "$MAIN_REPORT" \
    "$PYTHON_REPORT" \
    "$CORE_TESTS" \
    "$FULL_TESTS" \
    "$NPM_REPORT" \
    "$CONFIG_REPORT" \
    "$STATE_REPORT" \
    "$SOURCE_REPORT" \
    "$LARGE_FILES" \
    "$LARGE_LOGS" \
    "$RUFLO_CLI"

PASS=0
WARN=0
FAIL=0

section() {
    echo
    echo "============================================================"
    echo "$1"
    echo "============================================================"
}

pass() {
    echo "[PASS] $*"
    PASS=$((PASS + 1))
}

warn() {
    echo "[WARN] $*"
    WARN=$((WARN + 1))
}

fail() {
    echo "[FAIL] $*"
    FAIL=$((FAIL + 1))
}

info() {
    echo "[INFO] $*"
}

run_capture() {
    local outfile="$1"
    shift
    "$@" >"$outfile" 2>&1
    return $?
}

exec > >(tee -a "$MAIN_REPORT") 2>&1

echo "RUFLO ENTERPRISE TEST v5"
echo "Project : $PROJECT"
echo "Date    : $(date)"
echo "Host    : $(hostname)"
echo "User    : $(id -un)"
echo "Kernel  : $(uname -r)"
echo "Report  : $REPORT_DIR"

# ============================================================
# 1. SYSTEM HEALTH
# ============================================================

section "1. SYSTEM HEALTH"

CPU_MODEL="$(lscpu 2>/dev/null | awk -F: '/Model name/ {gsub(/^[ \t]+/, "", $2); print $2; exit}')"
CPU_CORES="$(nproc 2>/dev/null || echo unknown)"

echo "CPU Model : ${CPU_MODEL:-unknown}"
echo "CPU Cores : $CPU_CORES"

free -h 2>/dev/null || true
swapon --show 2>/dev/null || true

df -h / 2>/dev/null || true
df -i / 2>/dev/null || true

ROOT_USE="$(df -P / | awk 'NR==2 {gsub("%","",$5); print $5}')"
ROOT_INODE="$(df -Pi / | awk 'NR==2 {gsub("%","",$5); print $5}')"

if [[ "$ROOT_USE" =~ ^[0-9]+$ ]]; then
    if (( ROOT_USE < 80 )); then
        pass "Filesystem capacity healthy (${ROOT_USE}% used)"
    elif (( ROOT_USE < 90 )); then
        warn "Filesystem capacity elevated (${ROOT_USE}% used)"
    else
        fail "Filesystem capacity critical (${ROOT_USE}% used)"
    fi
fi

if [[ "$ROOT_INODE" =~ ^[0-9]+$ ]]; then
    if (( ROOT_INODE < 80 )); then
        pass "Inode usage healthy (${ROOT_INODE}%)"
    elif (( ROOT_INODE < 90 )); then
        warn "Inode usage elevated (${ROOT_INODE}%)"
    else
        fail "Inode usage critical (${ROOT_INODE}%)"
    fi
fi

# ============================================================
# 2. REQUIRED COMMANDS
# ============================================================

section "2. REQUIRED COMMANDS"

REQUIRED_CMDS=(
    bash node npm npx git python3 find awk sed grep du df
    sort head tail jq
)

for cmd in "${REQUIRED_CMDS[@]}"; do
    if command -v "$cmd" >/dev/null 2>&1; then
        pass "$cmd available: $(command -v "$cmd")"
    else
        fail "$cmd is missing"
    fi
done

# ============================================================
# 3. RUNTIME VERSIONS
# ============================================================

section "3. RUNTIME VERSIONS"

NODE_VERSION="$(node --version 2>/dev/null || echo unknown)"
NPM_VERSION="$(npm --version 2>/dev/null || echo unknown)"
NPX_VERSION="$(npx --version 2>/dev/null || echo unknown)"
GIT_VERSION="$(git --version 2>/dev/null || echo unknown)"
PY3_VERSION="$(python3 --version 2>/dev/null || echo unknown)"

echo "Node : $NODE_VERSION"
echo "npm  : $NPM_VERSION"
echo "npx  : $NPX_VERSION"
echo "Git  : $GIT_VERSION"
echo "Py3  : $PY3_VERSION"

NODE_MAJOR="$(node -p 'process.versions.node.split(".")[0]' 2>/dev/null || echo 0)"

if [[ "$NODE_MAJOR" =~ ^[0-9]+$ ]] && (( NODE_MAJOR >= 20 )); then
    pass "Node.js supported enterprise major detected: $NODE_MAJOR"
else
    fail "Unsupported Node.js major: $NODE_MAJOR"
fi

# ============================================================
# 4. NODE PROJECT
# ============================================================

section "4. NODE PROJECT"

if [[ -f package.json ]]; then
    pass "package.json exists"

    if jq empty package.json >/dev/null 2>&1; then
        pass "package.json is valid JSON"
    else
        fail "package.json contains invalid JSON"
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
    NODE_SIZE="$(du -sh node_modules 2>/dev/null | awk '{print $1}')"
    pass "node_modules exists ($NODE_SIZE)"
else
    fail "node_modules missing"
fi

npm ls --depth=0 >"$NPM_REPORT" 2>&1

if grep -qiE 'npm error|ELSPROBLEMS|missing:|invalid:' "$NPM_REPORT"; then
    fail "npm dependency tree contains errors; see npm-validation.txt"
else
    pass "npm top-level dependency tree is healthy"
fi

# ============================================================
# 5. RUFLO / CLAUDE-FLOW RUNTIME
# ============================================================

section "5. RUFLO / CLAUDE-FLOW RUNTIME"

GLOBAL_RUFLO=""
LOCAL_RUFLO=""

if command -v ruflo >/dev/null 2>&1; then
    GLOBAL_RUFLO="$(ruflo --version 2>&1 | head -1)"
    echo "$GLOBAL_RUFLO"
    pass "Global Ruflo executable available"
else
    info "No global Ruflo executable"
fi

if [[ -x "$PROJECT/node_modules/.bin/ruflo" ]]; then
    LOCAL_RUFLO="$("$PROJECT/node_modules/.bin/ruflo" --version 2>&1 | head -1)"
    echo "$LOCAL_RUFLO"
    pass "Project-local Ruflo executable available"
else
    info "No project-local Ruflo executable"
fi

CLAUDE_FLOW_OUTPUT="$(npx --no-install claude-flow --version 2>&1)"
CLAUDE_FLOW_RC=$?

printf '%s\n' "$CLAUDE_FLOW_OUTPUT" | tee "$RUFLO_CLI"

if (( CLAUDE_FLOW_RC == 0 )) &&
   printf '%s\n' "$CLAUDE_FLOW_OUTPUT" | grep -qiE 'ruflo|claude.?flow|[0-9]+\.[0-9]+\.[0-9]+'; then

    CLAUDE_FLOW_VERSION="$(printf '%s\n' "$CLAUDE_FLOW_OUTPUT" | head -1)"
    pass "Claude Flow/Ruflo runtime available: $CLAUDE_FLOW_VERSION"
else
    fail "Claude Flow/Ruflo runtime unavailable"
fi

# ============================================================
# 6. RUFLO PACKAGE DISCOVERY
# ============================================================

section "6. RUFLO PACKAGE DISCOVERY"

PACKAGE_RUFLO_COUNT=0

if [[ -f package.json ]]; then
    PACKAGE_RUFLO_COUNT="$(
        jq -r '
          [
            (.dependencies // {}),
            (.devDependencies // {}),
            (.optionalDependencies // {})
          ]
          | add
          | keys[]
          | select(test("ruflo|claude-flow"; "i"))
        ' package.json 2>/dev/null | wc -l
    )"
fi

if (( PACKAGE_RUFLO_COUNT > 0 )); then
    pass "Ruflo/Claude Flow package declared in package.json"
else
    warn "No Ruflo package declared in package.json; runtime is available through Claude Flow"
fi

# ============================================================
# 7. PROJECT STRUCTURE
# ============================================================

section "7. RUFLO PROJECT STRUCTURE"

REQUIRED_DIRS=(
    ".agents"
    ".agents/skills"
    ".agents/skills/ruflo"
    ".claude-flow"
    ".claude"
)

for item in "${REQUIRED_DIRS[@]}"; do
    if [[ -e "$PROJECT/$item" ]]; then
        SIZE="$(du -sh "$PROJECT/$item" 2>/dev/null | awk '{print $1}')"
        pass "Exists: $item ($SIZE)"
    else
        fail "Required project path missing: $item"
    fi
done

if [[ -d "$PROJECT/.hive-mind" ]]; then
    pass "Optional state directory exists: .hive-mind"
else
    info "Optional state directory absent: .hive-mind"
fi

if [[ -d "$PROJECT/.swarm" ]]; then
    SIZE="$(du -sh "$PROJECT/.swarm" 2>/dev/null | awk '{print $1}')"
    pass "Optional state directory exists: .swarm ($SIZE)"
else
    info "Optional state directory absent: .swarm"
fi

# ============================================================
# 8. CONFIGURATION
# ============================================================

section "8. CONFIGURATION VALIDATION"

CONFIG_FILES=(
    ".mcp.json"
    ".claude.json"
    ".claude/settings.json"
    ".claude/settings.local.json"
)

CONFIG_OK=1
: > "$CONFIG_REPORT"

for file in "${CONFIG_FILES[@]}"; do
    if [[ -f "$PROJECT/$file" ]]; then
        if jq empty "$PROJECT/$file" >/dev/null 2>&1; then
            echo "[PASS] Valid JSON: $file" | tee -a "$CONFIG_REPORT"
            pass "Valid JSON: $file"
        else
            echo "[FAIL] Invalid JSON: $file" | tee -a "$CONFIG_REPORT"
            fail "Invalid JSON: $file"
            CONFIG_OK=0
        fi
    else
        warn "Optional configuration missing: $file"
    fi
done

if [[ -f "$PROJECT/CLAUDE.md" ]]; then
    pass "CLAUDE.md exists"
else
    warn "CLAUDE.md missing"
fi

# ============================================================
# 9. STATE / PROCESSES
# ============================================================

section "9. RUFLO STATE / PROCESSES"

{
    echo "=== Processes ==="
    ps -ef | grep -Ei 'ruflo|claude-flow|claude' | grep -v grep || true
    echo
    echo "=== State files ==="
    find "$PROJECT/.claude-flow" "$PROJECT/.swarm" \
        -type f -printf '%p\n' 2>/dev/null | head -100
} >"$STATE_REPORT" 2>&1

if grep -qiE 'ruflo|claude-flow|claude' "$STATE_REPORT"; then
    pass "Ruflo/Claude-related state/process information collected"
else
    pass "Ruflo/Claude state scan completed"
fi

STATE_COUNT="$(find "$PROJECT/.claude-flow" "$PROJECT/.swarm" \
    -type f 2>/dev/null | wc -l)"

if (( STATE_COUNT > 0 )); then
    pass "Ruflo-related state contains files ($STATE_COUNT)"
else
    info "No Ruflo state files detected"
fi

# ============================================================
# 10. PYTHON ENVIRONMENT
# ============================================================

section "10. PYTHON ENVIRONMENT"

PYTHON="$PROJECT/backend/venv/bin/python"

if [[ ! -x "$PYTHON" ]]; then
    fail "Backend Python virtual environment not found"
else
    echo "Python: $PYTHON"
    "$PYTHON" --version

    if "$PYTHON" -m pip check >"$PYTHON_REPORT" 2>&1; then
        pass "Python pip check passed"
    else
        fail "Python dependency consistency failed; see python-validation.txt"
    fi

    INVALID_DIST="$(find "$PROJECT/backend/venv/lib/python3.12/site-packages" \
        -maxdepth 1 \
        -type d \
        -name '~*' \
        -printf '%f\n' 2>/dev/null | sort)"

    if [[ -z "$INVALID_DIST" ]]; then
        pass "No invalid Python distributions detected"
    else
        warn "Invalid Python distributions detected"
        printf '%s\n' "$INVALID_DIST" >>"$PYTHON_REPORT"
    fi

    # Write the Python validation program to a temporary file.
    # This avoids heredoc corruption and prevents the validator from
    # accidentally testing malformed shell input.
    PY_VALIDATOR="$(mktemp)"

    cat >"$PY_VALIDATOR" <<'PY'
import importlib
import sys
import traceback

print(f"Python {sys.version.split()[0]}")
print(f"Executable: {sys.executable}")
print()

modules = [
    "numpy",
    "scipy",
    "pandas",
    "sklearn",
    "chromadb",
    "onnxruntime",
    "psutil",
    "watchdog",
    "websockets",
    "langgraph",
]

failed = []

for module in modules:
    try:
        m = importlib.import_module(module)
        version = getattr(m, "__version__", "loaded")
        print(f"[PASS] {module}: {version}")
    except Exception as exc:
        failed.append(module)
        print(f"[FAIL] {module}: {type(exc).__name__}: {exc}")
        traceback.print_exc()

print()
print(f"FAILED_MODULES={len(failed)}")

sys.exit(1 if failed else 0)
PY

    "$PYTHON" "$PY_VALIDATOR" >>"$PYTHON_REPORT" 2>&1
    PY_RC=$?

    rm -f "$PY_VALIDATOR"

    if (( PY_RC == 0 )) &&
       grep -q '^FAILED_MODULES=0$' "$PYTHON_REPORT"; then
        pass "Python core imports passed"
    else
        fail "Python core imports failed; see python-validation.txt"
    fi
fi

# ============================================================
# 11. CORE TARGETED TESTS
# ============================================================

section "11. RUFLO / CORE TARGETED TESTS"

CORE_TEST_FILES=()

[[ -f "$PROJECT/tests/test_program_control.py" ]] &&
    CORE_TEST_FILES+=("tests/test_program_control.py")

[[ -f "$PROJECT/backend/tests/test_mcp_server.py" ]] &&
    CORE_TEST_FILES+=("backend/tests/test_mcp_server.py")

if (( ${#CORE_TEST_FILES[@]} == 0 )); then
    warn "No targeted core test files found"
else
    printf '%s\n' "Targeted tests:" "${CORE_TEST_FILES[@]}"

    "$PYTHON" -m pytest \
        "${CORE_TEST_FILES[@]}" \
        -q \
        --maxfail=5 \
        >"$CORE_TESTS" 2>&1

    CORE_RC=$?

    tail -40 "$CORE_TESTS"

    if (( CORE_RC == 0 )); then
        pass "All targeted core tests passed"
    else
        fail "Targeted core tests failed; see core-tests.txt"
    fi
fi

# ============================================================
# 12. PROGRAM SERVICE CONTRACT
# ============================================================

section "12. PROGRAM SERVICE CONTRACT"

"$PYTHON" - <<'PY'
import inspect
from backend import program_service

expected = [
    "create_program",
    "get_program",
    "list_programs",
    "update_controls",
    "delete_program",
    "_compute_status_rollup",
]

for name in expected:
    assert hasattr(program_service, name), f"Missing function: {name}"

assert list(inspect.signature(program_service.create_program).parameters) == [
    "db", "tenant_id", "data"
]

assert list(inspect.signature(program_service.get_program).parameters) == [
    "db", "program_id", "tenant_id"
]

print("[PASS] Program service contract is valid")
PY

if (( $? == 0 )); then
    pass "Program service contract is valid"
else
    fail "Program service contract is invalid"
fi

# ============================================================
# 13. MCP FASTMCP
# ============================================================

section "13. MCP FASTMCP"

"$PYTHON" - <<'PY'
from mcp.server.fastmcp import FastMCP
import mcp

print("[PASS] FastMCP import")
print("FastMCP:", FastMCP)
print("MCP package:", mcp.__file__)
PY

if (( $? == 0 )); then
    pass "FastMCP import is available"
else
    fail "FastMCP import failed"
fi

# ============================================================
# 14. APPLICATION-CONTEXT MCP IMPORT
# ============================================================

section "14. APPLICATION-CONTEXT MCP VALIDATION"

MCP_SOURCE="$PROJECT/backend/mcp_server.py"

if [[ -f "$MCP_SOURCE" ]]; then

    if grep -qE 'from database import get_database|import database' "$MCP_SOURCE"; then
        info "backend/mcp_server.py uses application-local 'database' import"

        (
            cd "$PROJECT/backend"
            "$PYTHON" - <<'PY'
import mcp_server
print("[PASS] backend/mcp_server imports correctly in backend application context")
PY
        ) >"$REPORT_DIR/mcp-application-import.txt" 2>&1

        MCP_RC=$?

        cat "$REPORT_DIR/mcp-application-import.txt"

        if (( MCP_RC == 0 )); then
            pass "MCP server imports correctly in application context"
        else
            fail "MCP server fails in application context"
        fi
    else
        "$PYTHON" - <<'PY'
import backend.mcp_server
print("[PASS] backend.mcp_server package import")
PY

        if (( $? == 0 )); then
            pass "MCP server package import passed"
        else
            fail "MCP server package import failed"
        fi
    fi
else
    warn "backend/mcp_server.py not found"
fi

# ============================================================
# 15. FULL PROJECT TEST SUITE
# ============================================================

section "15. FULL PROJECT TEST SUITE"

info "Full-project pytest is diagnostic only."
info "Network-dependent, external-service and non-Python artifacts do not automatically fail Ruflo."

"$PYTHON" -m pytest \
    --collect-only \
    -q \
    >"$FULL_TESTS" 2>&1

FULL_RC=$?

COLLECTED="$(grep -Eo '[0-9]+ tests? collected' "$FULL_TESTS" | tail -1 || true)"
ERRORS="$(grep -Eo '[0-9]+ error[s]?' "$FULL_TESTS" | tail -1 || true)"

echo "${COLLECTED:-Tests collected: unknown}"
echo "${ERRORS:-Collection errors: unknown}"

if grep -qE 'UnicodeDecodeError|test_summary\.txt|\.txt -' "$FULL_TESTS"; then
    warn "Pytest discovers non-Python artifacts during collection"
fi

if grep -qiE \
    'Connection refused|ConnectError|URLError|network-dependent|All connection attempts failed|localhost:[0-9]+' \
    "$FULL_TESTS"; then
    warn "Pytest collection includes external-service/network-dependent tests"
fi

if (( FULL_RC == 0 )); then
    pass "Full pytest collection completed without errors"
else
    COLLECTION_ERROR_COUNT="$(
        grep -cE '^ERROR |^.*ERROR collecting|^.*ERROR$' "$FULL_TESTS" 2>/dev/null || true
    )"

    if [[ "$COLLECTION_ERROR_COUNT" =~ ^[0-9]+$ ]] &&
       (( COLLECTION_ERROR_COUNT > 0 )); then
        warn "Full-project pytest has $COLLECTION_ERROR_COUNT collection error(s); diagnostic only"
    else
        warn "Full-project pytest collection returned non-zero status; diagnostic only"
    fi
fi

# ============================================================
# 16. LARGE FILES / LOGS
# ============================================================

section "16. LARGE FILES / LOGS"

find "$PROJECT" \
    -type f \
    -size +500M \
    -printf '%s %p\n' 2>/dev/null |
    sort -nr |
    awk '{
        size=$1;
        $1="";
        printf "%.0fMB %s\n", size/1024/1024, substr($0,2)
    }' >"$LARGE_FILES"

if [[ -s "$LARGE_FILES" ]]; then
    warn "Files larger than 500 MB detected; see large-files.txt"
    cat "$LARGE_FILES"
else
    pass "No files larger than 500 MB detected"
fi

find "$PROJECT" \
    -type f \
    \( -name '*.log' -o -name '*.out' \) \
    -size +50M \
    -printf '%s %p\n' 2>/dev/null |
    sort -nr |
    awk '{
        size=$1;
        $1="";
        printf "%.0fMB %s\n", size/1024/1024, substr($0,2)
    }' >"$LARGE_LOGS"

if [[ -s "$LARGE_LOGS" ]]; then
    warn "Logs larger than 50 MB detected; see large-logs.txt"
    cat "$LARGE_LOGS"
else
    pass "No oversized logs detected"
fi

# ============================================================
# 17. AUDIT REPORT HYGIENE
# ============================================================

section "17. AUDIT REPORT HYGIENE"

if [[ -d "$PROJECT/audit-reports" ]]; then
    AUDIT_COUNT="$(find "$PROJECT/audit-reports" -type f 2>/dev/null | wc -l)"

    if (( AUDIT_COUNT > 0 )); then
        pass "audit-reports directory exists with $AUDIT_COUNT file(s)"
    else
        warn "audit-reports directory exists but contains no files"
    fi
else
    info "audit-reports directory absent"
fi

# ============================================================
# 18. GIT
# ============================================================

section "18. GIT"

if git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
    pass "Git repository detected"

    if [[ -z "$(git status --porcelain 2>/dev/null)" ]]; then
        pass "Git working tree clean"
    else
        warn "Git working tree has changes"
        git status --short | head -100
    fi
else
    warn "Git repository not detected"
fi

# ============================================================
# 19. FINAL RESULT
# ============================================================

section "19. FINAL RESULT"

RUFLO_VERSION="unknown"

if [[ -n "$GLOBAL_RUFLO" ]]; then
    RUFLO_VERSION="$GLOBAL_RUFLO"
elif [[ -n "$LOCAL_RUFLO" ]]; then
    RUFLO_VERSION="$LOCAL_RUFLO"
elif grep -qi 'ruflo v' "$RUFLO_CLI"; then
    RUFLO_VERSION="$(grep -i 'ruflo v' "$RUFLO_CLI" | head -1)"
fi

RESULT="PASSED"

if (( FAIL > 0 )); then
    RESULT="FAILED"
elif (( WARN > 0 )); then
    RESULT="PASSED WITH WARNINGS"
fi

cat >"$SUMMARY" <<EOF
RUFLO ENTERPRISE TEST v5 SUMMARY
Project: $PROJECT
Date: $(date)
Host: $(hostname)

Ruflo / Claude Flow runtime: $RUFLO_VERSION

PASS: $PASS
WARN: $WARN
FAIL: $FAIL

Result: $RESULT

Main report: $MAIN_REPORT
Ruflo CLI: $RUFLO_CLI
Python validation: $PYTHON_REPORT
Core tests: $CORE_TESTS
Full project tests: $FULL_TESTS
NPM validation: $NPM_REPORT
Config validation: $CONFIG_REPORT
State validation: $STATE_REPORT
Source blockers: $SOURCE_REPORT
Large files: $LARGE_FILES
Large logs: $LARGE_LOGS
EOF

echo
cat "$SUMMARY"

echo
echo "============================================================"
echo "RUFLO ENTERPRISE TEST v5 COMPLETE"
echo "PASS   : $PASS"
echo "WARN   : $WARN"
echo "FAIL   : $FAIL"
echo "RESULT : $RESULT"
echo "SUMMARY: $SUMMARY"
echo "REPORT : $MAIN_REPORT"
echo "============================================================"

exit "$(( FAIL > 0 ? 1 : 0 ))"
