#!/usr/bin/env bash

# ============================================================
# RUFLO ENTERPRISE TEST v2
# Accurate Ruflo / Claude-Flow / Project Environment Audit
# ============================================================

set -u
set -o pipefail

PROJECT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$PROJECT" || exit 1

TIMESTAMP="$(date '+%Y%m%d_%H%M%S')"
REPORT_DIR="$PROJECT/ruflo-test-report-$TIMESTAMP"
mkdir -p "$REPORT_DIR"

REPORT="$REPORT_DIR/ruflo-enterprise-test-v2.log"
SUMMARY="$REPORT_DIR/summary.txt"
PYTHON_REPORT="$REPORT_DIR/python-validation.txt"
PYTEST_REPORT="$REPORT_DIR/pytest-collection.txt"
RUFLO_REPORT="$REPORT_DIR/ruflo-cli.txt"
LARGE_FILES="$REPORT_DIR/large-files.txt"
LARGE_LOGS="$REPORT_DIR/large-logs.txt"
CONFIG_REPORT="$REPORT_DIR/config-validation.txt"
PROCESS_REPORT="$REPORT_DIR/processes.txt"
STATE_REPORT="$REPORT_DIR/state.txt"

touch "$REPORT"

PASS_COUNT=0
WARN_COUNT=0
FAIL_COUNT=0

# ------------------------------------------------------------
# Logging
# ------------------------------------------------------------

log() {
    printf '%s\n' "$*" | tee -a "$REPORT"
}

section() {
    log ""
    log "============================================================"
    log "$1"
    log "============================================================"
}

pass() {
    PASS_COUNT=$((PASS_COUNT + 1))
    log "[PASS] $*"
}

warn() {
    WARN_COUNT=$((WARN_COUNT + 1))
    log "[WARN] $*"
}

fail() {
    FAIL_COUNT=$((FAIL_COUNT + 1))
    log "[FAIL] $*"
}

info() {
    log "[INFO] $*"
}

command_exists() {
    command -v "$1" >/dev/null 2>&1
}

run_capture() {
    "$@" 2>&1
}

# ------------------------------------------------------------
# Header
# ------------------------------------------------------------

section "RUFLO ENTERPRISE TEST v2"

log "Project : $PROJECT"
log "Date    : $(date)"
log "Host    : $(hostname)"
log "User    : $(id -un)"
log "Kernel  : $(uname -r)"
log "Report  : $REPORT"

# ============================================================
# 1. BASIC SYSTEM
# ============================================================

section "1. BASIC SYSTEM"

log "CPU:"
lscpu 2>/dev/null | egrep \
    'Architecture|CPU\(s\)|Model name|Virtualization|NUMA node' \
    | tee -a "$REPORT" || true

log ""
log "Memory:"
free -h 2>/dev/null | tee -a "$REPORT" || true

log ""
log "Disk:"
df -h "$PROJECT" | tee -a "$REPORT"

# ============================================================
# 2. REQUIRED COMMANDS
# ============================================================

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
        fail "$cmd is not available"
    fi
done

# ============================================================
# 3. VERSION INFORMATION
# ============================================================

section "3. VERSION INFORMATION"

if command_exists node; then
    log "Node : $(node --version 2>&1)"
fi

if command_exists npm; then
    log "npm  : $(npm --version 2>&1)"
fi

if command_exists npx; then
    log "npx  : $(npx --version 2>&1)"
fi

if command_exists git; then
    log "Git  : $(git --version 2>&1)"
fi

if command_exists python3; then
    log "Py3  : $(python3 --version 2>&1)"
fi

# Node 20+ recommended for this environment.
if command_exists node; then
    NODE_MAJOR="$(node -p 'process.versions.node.split(".")[0]' 2>/dev/null || echo 0)"

    if [[ "$NODE_MAJOR" =~ ^[0-9]+$ ]] && (( NODE_MAJOR >= 20 )); then
        pass "Node.js major version is $NODE_MAJOR"
    else
        warn "Node.js major version is $NODE_MAJOR; Node.js 20+ is recommended"
    fi
fi

# ============================================================
# 4. PROJECT PACKAGE VALIDATION
# ============================================================

section "4. PROJECT PACKAGE VALIDATION"

if [[ -f package.json ]]; then
    if jq empty package.json >/dev/null 2>&1; then
        pass "package.json is valid JSON"
    else
        fail "package.json is invalid JSON"
    fi
else
    warn "package.json not found"
fi

if [[ -f package-lock.json ]]; then
    pass "package-lock.json exists"
else
    warn "package-lock.json missing"
fi

if [[ -d node_modules ]]; then
    NODE_SIZE="$(du -sh node_modules 2>/dev/null | awk '{print $1}')"
    info "node_modules size: ${NODE_SIZE:-unknown}"

    if [[ -f package-lock.json ]]; then
        NPM_CHECK="$(npm ls --depth=0 --omit=optional 2>&1)"
        NPM_RC=$?

        printf '%s\n' "$NPM_CHECK" > "$REPORT_DIR/npm-health.txt"

        if [[ "$NPM_RC" -eq 0 ]]; then
            pass "npm top-level dependency tree is healthy"
        else
            warn "npm dependency tree has reported issues; see npm-health.txt"
        fi
    fi
else
    warn "node_modules does not exist"
fi

# ============================================================
# 5. RUFLO CLI DISCOVERY
# ============================================================

section "5. RUFLO CLI DISCOVERY"

RUFLO_CMD=""

if command_exists ruflo; then
    RUFLO_CMD="$(command -v ruflo)"
    pass "Global Ruflo executable found: $RUFLO_CMD"
else
    info "Global Ruflo executable not found"
fi

if command_exists claude-flow; then
    pass "Global claude-flow executable found: $(command -v claude-flow)"
else
    info "Global claude-flow executable not found"
fi

# ============================================================
# 6. LOCAL / NPX RUFLO
# ============================================================

section "6. LOCAL / NPX RUFLO"

NPX_RUFLO_AVAILABLE=0
RUFLO_VERSION="unknown"

if command_exists npx; then

    if npx --no-install ruflo --version > "$RUFLO_REPORT" 2>&1; then
        NPX_RUFLO_AVAILABLE=1
        RUFLO_VERSION="$(head -1 "$RUFLO_REPORT" | tr -d '\r')"
        pass "Local Ruflo available through npx --no-install: $RUFLO_VERSION"

    elif npx ruflo@latest --version > "$RUFLO_REPORT" 2>&1; then
        NPX_RUFLO_AVAILABLE=1
        RUFLO_VERSION="$(head -1 "$RUFLO_REPORT" | tr -d '\r')"
        pass "Ruflo available through npx ruflo@latest: $RUFLO_VERSION"

    else
        warn "Ruflo executable/package unavailable through npx"
        info "See $RUFLO_REPORT"
    fi

else
    fail "npx is unavailable; Ruflo cannot be tested"
fi

# ============================================================
# 7. RUFLO CLI HELP
# ============================================================

section "7. RUFLO CLI HELP"

if [[ "$NPX_RUFLO_AVAILABLE" -eq 1 ]]; then

    if npx --no-install ruflo --help > "$REPORT_DIR/ruflo-help.txt" 2>&1; then
        pass "Ruflo CLI help works"
    elif npx ruflo@latest --help > "$REPORT_DIR/ruflo-help.txt" 2>&1; then
        pass "Ruflo CLI help works through npx"
    else
        warn "Ruflo CLI help returned an error"
    fi

else
    warn "Ruflo CLI help skipped because Ruflo is unavailable"
fi

# ============================================================
# 8. RUFLO DOCTOR
# ============================================================

section "8. RUFLO DOCTOR"

if [[ "$NPX_RUFLO_AVAILABLE" -eq 1 ]]; then

    if npx --no-install ruflo doctor > "$REPORT_DIR/ruflo-doctor.txt" 2>&1; then
        pass "Ruflo doctor completed successfully"
    elif npx ruflo@latest doctor > "$REPORT_DIR/ruflo-doctor.txt" 2>&1; then
        pass "Ruflo doctor completed successfully"
    else
        warn "Ruflo doctor reported issues; see ruflo-doctor.txt"
    fi

else
    warn "Ruflo doctor skipped"
fi

# ============================================================
# 9. RUFLO STATUS
# ============================================================

section "9. RUFLO STATUS"

if [[ "$NPX_RUFLO_AVAILABLE" -eq 1 ]]; then

    if npx --no-install ruflo status > "$REPORT_DIR/ruflo-status.txt" 2>&1; then
        pass "Ruflo status command works"
    elif npx ruflo@latest status > "$REPORT_DIR/ruflo-status.txt" 2>&1; then
        pass "Ruflo status command works"
    else
        warn "Ruflo status returned an error; see ruflo-status.txt"
    fi

else
    warn "Ruflo status skipped"
fi

# ============================================================
# 10. RUFLO PROJECT STRUCTURE
# ============================================================

section "10. RUFLO PROJECT STRUCTURE"

DIRS=(
    ".agents"
    ".agents/skills"
    ".agents/skills/ruflo"
    ".claude-flow"
    ".claude"
)

for d in "${DIRS[@]}"; do
    if [[ -d "$PROJECT/$d" ]]; then
        SIZE="$(du -sh "$PROJECT/$d" 2>/dev/null | awk '{print $1}')"
        pass "Directory exists: $d ($SIZE)"
    else
        warn "Directory missing: $d"
    fi
done

# ============================================================
# 11. RUFLO CONFIGURATION
# ============================================================

section "11. RUFLO CONFIGURATION"

CONFIGS=(
    "CLAUDE.md"
    ".mcp.json"
    ".claude.json"
    ".claude/settings.json"
    ".claude/settings.local.json"
)

: > "$CONFIG_REPORT"

for cfg in "${CONFIGS[@]}"; do

    if [[ ! -f "$PROJECT/$cfg" ]]; then
        info "Optional configuration missing: $cfg"
        continue
    fi

    pass "Configuration exists: $cfg"

    case "$cfg" in
        *.json)
            if jq empty "$PROJECT/$cfg" >> "$CONFIG_REPORT" 2>&1; then
                pass "Valid JSON: $cfg"
            else
                fail "Invalid JSON: $cfg"
            fi
            ;;
    esac
done

# ============================================================
# 12. RUFLO SKILLS
# ============================================================

section "12. RUFLO SKILLS"

SKILL_DIR="$PROJECT/.agents/skills/ruflo"

if [[ -d "$SKILL_DIR" ]]; then

    SKILL_COUNT="$(find "$SKILL_DIR" -type f \
        \( -name 'SKILL.md' -o -name '*.md' \) \
        2>/dev/null | wc -l)"

    info "Ruflo skill files: $SKILL_COUNT"

    if (( SKILL_COUNT > 0 )); then
        pass "Ruflo skills discovered: $SKILL_COUNT"
    else
        warn "Ruflo skill directory exists but no skill files were found"
    fi

else
    warn "Ruflo skill directory does not exist"
fi

# ============================================================
# 13. RUFLO STATE
# ============================================================

section "13. RUFLO STATE"

: > "$STATE_REPORT"

if [[ -d "$PROJECT/.claude-flow" ]]; then

    find "$PROJECT/.claude-flow" -maxdepth 3 -type f \
        -printf '%p\n' 2>/dev/null \
        | sort | tee -a "$STATE_REPORT"

    STATE_COUNT="$(find "$PROJECT/.claude-flow" -type f 2>/dev/null | wc -l)"
    STATE_SIZE="$(du -sh "$PROJECT/.claude-flow" 2>/dev/null | awk '{print $1}')"

    log ""
    log "State files: $STATE_COUNT"
    log "State size : $STATE_SIZE"

    if (( STATE_COUNT > 0 )); then
        pass "Ruflo state files discovered"
    else
        warn "Ruflo state directory exists but contains no files"
    fi

else
    warn ".claude-flow state directory does not exist"
fi

# ============================================================
# 14. RUFLO FUNCTIONAL TESTS
# ============================================================

section "14. RUFLO FUNCTIONAL TESTS"

if [[ "$NPX_RUFLO_AVAILABLE" -eq 1 ]]; then

    info "Testing safe read-only Ruflo commands."

    if npx --no-install ruflo agent list \
        > "$REPORT_DIR/ruflo-agent-list.txt" 2>&1; then
        pass "Ruflo agent list"
    elif npx ruflo@latest agent list \
        > "$REPORT_DIR/ruflo-agent-list.txt" 2>&1; then
        pass "Ruflo agent list"
    else
        warn "Ruflo agent list returned an error"
    fi

    if npx --no-install ruflo memory list \
        > "$REPORT_DIR/ruflo-memory-list.txt" 2>&1; then
        pass "Ruflo memory list"
    elif npx ruflo@latest memory list \
        > "$REPORT_DIR/ruflo-memory-list.txt" 2>&1; then
        pass "Ruflo memory list"
    else
        warn "Ruflo memory list unavailable"
    fi

else
    warn "Functional Ruflo tests skipped"
fi

# ============================================================
# 15. PROCESS CHECK
# ============================================================

section "15. RUFLO / CLAUDE PROCESS CHECK"

ps -ef 2>/dev/null \
    | grep -Ei 'ruflo|claude-flow|claude.*mcp|mcp.*ruflo' \
    | grep -v grep \
    | tee "$PROCESS_REPORT" || true

if [[ -s "$PROCESS_REPORT" ]]; then
    pass "Ruflo/Claude-related processes detected"
else
    info "No active Ruflo/Claude process detected"
fi

# ============================================================
# 16. PYTHON ENVIRONMENT
# ============================================================

section "16. PYTHON ENVIRONMENT"

PYTHON_BIN=""

if [[ -x "$PROJECT/backend/venv/bin/python" ]]; then
    PYTHON_BIN="$PROJECT/backend/venv/bin/python"
    pass "Backend Python environment found"
elif [[ -x "$PROJECT/venv/bin/python" ]]; then
    PYTHON_BIN="$PROJECT/venv/bin/python"
    pass "Project Python environment found"
else
    warn "Project Python virtual environment not found"
fi

if [[ -n "$PYTHON_BIN" ]]; then

    "$PYTHON_BIN" --version | tee -a "$PYTHON_REPORT"

    if "$PYTHON_BIN" -m pip check > "$REPORT_DIR/pip-check.txt" 2>&1; then
        pass "Python pip check passed"
    else
        warn "Python pip check reported dependency issues"
    fi

    IMPORT_RESULT="$REPORT_DIR/python-imports.txt"

    "$PYTHON_BIN" - <<'PY' > "$IMPORT_RESULT" 2>&1
import importlib

modules = [
    ("numpy", "NumPy"),
    ("scipy", "SciPy"),
    ("pandas", "Pandas"),
    ("sklearn", "Scikit-learn"),
    ("chromadb", "ChromaDB"),
    ("onnxruntime", "ONNX Runtime"),
    ("cpuinfo", "CPUInfo"),
    ("watchdog", "Watchdog"),
    ("websockets", "WebSockets"),
    ("langgraph", "LangGraph"),
]

failed = []

print("=" * 70)
print("PYTHON CORE IMPORT VALIDATION")
print("=" * 70)

for module, name in modules:
    try:
        m = importlib.import_module(module)
        version = getattr(m, "__version__", "loaded")
        print(f"[OK]   {name:<20} {version}")
    except Exception as exc:
        print(f"[FAIL] {name:<20} {type(exc).__name__}: {exc}")
        failed.append(name)

print("=" * 70)

if failed:
    print("FAILED:", ", ".join(failed))
    raise SystemExit(1)

print("ALL CORE IMPORTS PASSED")
PY

    if grep -q "ALL CORE IMPORTS PASSED" "$IMPORT_RESULT"; then
        pass "Python core imports passed"
    else
        fail "Python core imports failed"
    fi

fi

# ============================================================
# 17. TARGETED PYTEST COLLECTION
# ============================================================

section "17. TARGETED PYTEST COLLECTION"

log "IMPORTANT:"
log "Application pytest collection is NOT treated as a Ruflo failure."
log "Generated/binary artifacts are excluded where possible."

if [[ -n "$PYTHON_BIN" ]] && command -v pytest >/dev/null 2>&1; then

    TARGETS=()

    [[ -d "$PROJECT/tests" ]] && TARGETS+=("$PROJECT/tests")
    [[ -d "$PROJECT/backend/tests" ]] && TARGETS+=("$PROJECT/backend/tests")

    if (( ${#TARGETS[@]} > 0 )); then

        set +e

        "$PYTHON_BIN" -m pytest \
            --collect-only \
            -q \
            "${TARGETS[@]}" \
            > "$PYTEST_REPORT" 2>&1

        PYTEST_RC=$?

        set -e

        if [[ "$PYTEST_RC" -eq 0 ]]; then
            pass "Targeted pytest collection completed successfully"
        else

            if grep -q "UnicodeDecodeError" "$PYTEST_REPORT"; then
                warn "Pytest collection encountered binary/non-test text artifacts"
            else
                warn "Pytest collection encountered application test-code errors"
            fi

            info "Pytest result is WARN only and does not fail Ruflo"
        fi

    else
        warn "No application test directories found"
    fi

else
    warn "Targeted pytest collection skipped"
fi

# ============================================================
# 18. LARGE FILE DETECTION
# ============================================================

section "18. LARGE FILE DETECTION"

: > "$LARGE_FILES"

info "Scanning project files while excluding dependency/build/cache directories."

find "$PROJECT" -type f \
    -not -path "$PROJECT/.git/*" \
    -not -path "$PROJECT/node_modules/*" \
    -not -path "$PROJECT/backend/venv/*" \
    -not -path "$PROJECT/venv/*" \
    -not -path "$PROJECT/.venv/*" \
    -not -path "$PROJECT/agent-rust/target/*" \
    -not -path "$PROJECT/rust_agent/target/*" \
    -not -path "$PROJECT/.claude/worktrees/*" \
    -not -path "$PROJECT/ruflo-test-report-*/*" \
    -size +500M \
    -printf '%s %p\n' 2>/dev/null \
    | sort -nr \
    | numfmt --field=1 --to=iec \
    | head -30 \
    | tee "$LARGE_FILES"

if [[ -s "$LARGE_FILES" ]]; then
    warn "Large files above 500MB detected; see large-files.txt"
else
    pass "No files larger than 500MB detected outside excluded directories"
fi

# ============================================================
# 19. LOG / JSONL SIZE
# ============================================================

section "19. LOG / JSONL SIZE"

: > "$LARGE_LOGS"

find "$PROJECT" -type f \
    \( -name '*.log' -o -name '*.jsonl' -o -name '*.json' \) \
    -not -path "$PROJECT/.git/*" \
    -not -path "$PROJECT/node_modules/*" \
    -not -path "$PROJECT/backend/venv/*" \
    -not -path "$PROJECT/venv/*" \
    -not -path "$PROJECT/.claude/worktrees/*" \
    -not -path "$PROJECT/ruflo-test-report-*/*" \
    -size +100M \
    -printf '%s %p\n' 2>/dev/null \
    | sort -nr \
    | numfmt --field=1 --to=iec \
    | head -30 \
    | tee "$LARGE_LOGS"

if [[ -s "$LARGE_LOGS" ]]; then
    warn "Oversized log/JSON files detected; see large-logs.txt"
else
    pass "No oversized log/json files detected"
fi

# ============================================================
# 20. AUDIT REPORT STORAGE
# ============================================================

section "20. AUDIT REPORT STORAGE"

if [[ -d "$PROJECT/audit-reports" ]]; then

    AUDIT_SIZE="$(du -sh "$PROJECT/audit-reports" 2>/dev/null | awk '{print $1}')"

    log "audit-reports size: ${AUDIT_SIZE:-unknown}"

    if find "$PROJECT/audit-reports" -type f \
        \( -name '*.log' -o -name '*.json' -o -name '*.jsonl' -o -name '*.txt' \) \
        -size +1G \
        -print -quit 2>/dev/null | grep -q .; then

        warn "audit-reports contains files larger than 1GB"

    else
        pass "audit-reports has no individual files larger than 1GB"
    fi

else
    info "audit-reports directory does not exist"
fi

# ============================================================
# 21. GIT STATUS
# ============================================================

section "21. GIT STATUS"

if git rev-parse --is-inside-work-tree >/dev/null 2>&1; then

    pass "Git repository detected"

    BRANCH="$(git branch --show-current 2>/dev/null || true)"

    if [[ -n "$BRANCH" ]]; then
        log "Branch: $BRANCH"
    else
        warn "Detached HEAD or branch name unavailable"
    fi

    CHANGES="$(git status --porcelain 2>/dev/null | wc -l)"

    if (( CHANGES == 0 )); then
        pass "Git working tree is clean"
    elif (( CHANGES < 100 )); then
        warn "Git working tree has $CHANGES changed/untracked entries"
    else
        warn "Git working tree has $CHANGES changed/untracked entries"
    fi

else
    warn "Git repository not detected"
fi

# ============================================================
# 22. PERMISSION AUDIT
# ============================================================

section "22. PERMISSION AUDIT"

if [[ -d "$PROJECT/backend/venv" ]]; then

    if [[ -w "$PROJECT/backend/venv/lib/python3.12/site-packages" ]]; then
        pass "Backend virtualenv site-packages is writable"
    else
        warn "Backend virtualenv site-packages is not writable by current user"
    fi

fi

if [[ -d "$PROJECT/node_modules" ]]; then

    if [[ -w "$PROJECT/node_modules" ]]; then
        pass "node_modules is writable"
    else
        warn "node_modules is not writable by current user"
    fi

fi

# ============================================================
# 23. DISK SAFETY
# ============================================================

section "23. DISK SAFETY"

DISK_USE="$(df -P "$PROJECT" | awk 'NR==2 {gsub("%","",$5); print $5}')"

if [[ "$DISK_USE" =~ ^[0-9]+$ ]]; then

    log "Filesystem usage: ${DISK_USE}%"

    if (( DISK_USE < 80 )); then
        pass "Filesystem usage is below 80%"
    elif (( DISK_USE < 90 )); then
        warn "Filesystem usage is between 80% and 90%"
    else
        fail "Filesystem usage is above 90%"
    fi

else
    warn "Unable to determine filesystem usage"
fi

# ============================================================
# 24. PROJECT SIZE
# ============================================================

section "24. PROJECT SIZE"

PROJECT_SIZE="$(du -sh "$PROJECT" 2>/dev/null | awk '{print $1}')"

log "Project size: ${PROJECT_SIZE:-unknown}"

log ""
log "Top-level directories:"

du -sh "$PROJECT"/* "$PROJECT"/.[!.]* 2>/dev/null \
    | sort -h \
    | tail -30 \
    | tee -a "$REPORT"

# ============================================================
# 25. FINAL ASSESSMENT
# ============================================================

section "FINAL RESULT"

log ""
log "PASS : $PASS_COUNT"
log "WARN : $WARN_COUNT"
log "FAIL : $FAIL_COUNT"

log ""
log "Report:"
log "$REPORT"

log ""
log "Additional diagnostics:"
log "  Summary       : $SUMMARY"
log "  Ruflo CLI     : $RUFLO_REPORT"
log "  Python        : $PYTHON_REPORT"
log "  Python imports: $REPORT_DIR/python-imports.txt"
log "  Pip check     : $REPORT_DIR/pip-check.txt"
log "  Pytest        : $PYTEST_REPORT"
log "  Large files   : $LARGE_FILES"
log "  Large logs    : $LARGE_LOGS"
log "  Config        : $CONFIG_REPORT"
log "  Processes     : $PROCESS_REPORT"
log "  State         : $STATE_REPORT"

# ------------------------------------------------------------
# Summary file
# ------------------------------------------------------------

cat > "$SUMMARY" <<EOF_SUMMARY
RUFLO ENTERPRISE TEST v2 SUMMARY

Project: $PROJECT
Date: $(date)
Host: $(hostname)

Ruflo: $RUFLO_VERSION

PASS: $PASS_COUNT
WARN: $WARN_COUNT
FAIL: $FAIL_COUNT

Main report:
$REPORT

Ruflo CLI:
$RUFLO_REPORT

Python validation:
$PYTHON_REPORT

Pytest:
$PYTEST_REPORT

Large files:
$LARGE_FILES

Large logs:
$LARGE_LOGS
EOF_SUMMARY

# ============================================================
# FINAL DECISION
# ============================================================

log ""

if (( FAIL_COUNT > 0 )); then

    log "============================================================"
    log "RESULT: FAILED"
    log "============================================================"

    exit 1

elif (( WARN_COUNT > 0 )); then

    log "============================================================"
    log "RESULT: PASS WITH WARNINGS"
    log "============================================================"

    exit 0

else

    log "============================================================"
    log "RESULT: HEALTHY"
    log "============================================================"

    exit 0
fi

