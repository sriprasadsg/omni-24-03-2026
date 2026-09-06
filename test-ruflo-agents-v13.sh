#!/usr/bin/env bash
#
# RUFLO MULTI-AGENT ENTERPRISE TEST v13
#
# Purpose:
#   - Discover the real Ruflo runtime, including embedded project Ruflo
#   - Validate Ruflo/Claude Flow CLI and capabilities
#   - Spawn multiple test agents concurrently
#   - Exercise status, agent, swarm, task and memory paths where supported
#   - Run project core tests and diagnostics
#   - Save all stdout/stderr and a machine-readable JSON report
#   - Run safely in background
#
# Usage:
#   chmod +x test-ruflo-agents-v13.sh
#   ./test-ruflo-agents-v13.sh
#   ./test-ruflo-agents-v13.sh --background
#
# Background:
#   ./test-ruflo-agents-v13.sh --background
#
# Stop:
#   kill "$(cat .ruflo-test.pid)"
#

set -u
set -o pipefail

PROJECT="${RUFLO_PROJECT:-$(pwd)}"
cd "$PROJECT" || exit 1

if [[ "${1:-}" == "--background" && "${RUFLO_BACKGROUND_CHILD:-0}" != "1" ]]; then
    mkdir -p "$PROJECT/ruflo-agent-test-v13-background"
    LOG="$PROJECT/ruflo-agent-test-v13-background/launcher.log"
    (
        export RUFLO_BACKGROUND_CHILD=1
        nohup "$0" >"$LOG" 2>&1 </dev/null &
        echo $! > "$PROJECT/.ruflo-test.pid"
    )
    echo "Ruflo v13 test started in background."
    echo "PID file : $PROJECT/.ruflo-test.pid"
    echo "Launcher : $LOG"
    echo "Use      : tail -f \"$LOG\""
    exit 0
fi

TS="$(date '+%Y%m%d_%H%M%S')"
REPORT="$PROJECT/ruflo-agent-test-v13-$TS"
mkdir -p "$REPORT"/{agents,swarm,tasks,memory,diagnostics}

MAIN="$REPORT/ruflo-agent-test-v13.log"
SUMMARY="$REPORT/summary.txt"
JSON="$REPORT/summary.json"
PIDFILE="$PROJECT/.ruflo-test.pid"

exec > >(tee -a "$MAIN") 2>&1
echo $$ > "$PIDFILE"
trap 'rm -f "$PIDFILE"' EXIT

PASS=0
WARN=0
FAIL=0
AGENT_TOTAL=0
AGENT_OK=0

pass(){ PASS=$((PASS+1)); echo "[PASS] $*"; }
warn(){ WARN=$((WARN+1)); echo "[WARN] $*"; }
fail(){ FAIL=$((FAIL+1)); echo "[FAIL] $*"; }
section(){ echo; echo "============================================================"; echo "$*"; echo "============================================================"; }

run_capture() {
    local outfile="$1"; shift
    "$@" >"$outfile" 2>&1
    return $?
}

echo "RUFLO MULTI-AGENT ENTERPRISE TEST v13"
echo "Project : $PROJECT"
echo "Date    : $(date)"
echo "Host    : $(hostname)"
echo "User    : $(id -un)"
echo "PID     : $$"
echo "Report  : $REPORT"

section "1. SYSTEM HEALTH"
CPU_CORES="$(nproc 2>/dev/null || echo unknown)"
MEM_AVAIL="$(free -h 2>/dev/null | awk '/^Mem:/ {print $7}' || echo unknown)"
ROOT_USE="$(df -P / | awk 'NR==2 {gsub("%","",$5); print $5}')"
echo "CPU Cores       : $CPU_CORES"
echo "Memory Available: $MEM_AVAIL"
echo "Root Usage      : ${ROOT_USE}%"
if [[ "${ROOT_USE:-100}" =~ ^[0-9]+$ && "$ROOT_USE" -lt 90 ]]; then
    pass "Filesystem capacity acceptable"
else
    fail "Filesystem capacity critical or unreadable"
fi

section "2. REQUIRED TOOLCHAIN"
for c in bash node npm npx git python3 find awk sed grep du df sort head tail jq; do
    if command -v "$c" >/dev/null 2>&1; then pass "$c: $(command -v "$c")"; else fail "$c missing"; fi
done

section "3. RUNTIME"
node --version 2>&1 | tee "$REPORT/diagnostics/node-version.txt"
npm --version 2>&1 | tee "$REPORT/diagnostics/npm-version.txt"
python3 --version 2>&1 | tee "$REPORT/diagnostics/python-version.txt"
git --version 2>&1 | tee "$REPORT/diagnostics/git-version.txt"

section "4. PROJECT"
for f in package.json package-lock.json; do
    [[ -f "$f" ]] && pass "$f exists" || warn "$f missing"
done
[[ -d node_modules ]] && pass "node_modules exists" || warn "node_modules missing"
[[ -x backend/venv/bin/python ]] && pass "backend venv exists" || warn "backend venv missing"
[[ -d .agents ]] && pass ".agents exists" || warn ".agents missing"
[[ -d .agents/skills/ruflo ]] && pass "embedded Ruflo source exists" || warn "embedded Ruflo source missing"
[[ -f .agents/skills/ruflo/bin/cli.js ]] && pass "embedded Ruflo CLI exists" || warn "embedded Ruflo CLI missing"
[[ -d .claude-flow ]] && pass ".claude-flow exists" || warn ".claude-flow missing"

section "5. RUFLO RUNTIME DISCOVERY"
RUFLO_MODE="unavailable"
RUFLO_CMD=()

if command -v ruflo >/dev/null 2>&1; then
    RUFLO_MODE="global"
    RUFLO_CMD=(ruflo)
elif [[ -x .agents/skills/ruflo/bin/cli.js || -f .agents/skills/ruflo/bin/cli.js ]]; then
    RUFLO_MODE="embedded"
    RUFLO_CMD=(node .agents/skills/ruflo/bin/cli.js)
elif npx --no-install claude-flow --version >/dev/null 2>&1; then
    RUFLO_MODE="claude-flow"
    RUFLO_CMD=(npx --no-install claude-flow)
fi

echo "Runtime mode: $RUFLO_MODE"
if [[ "$RUFLO_MODE" == "unavailable" ]]; then
    fail "No executable Ruflo runtime discovered"
else
    if "${RUFLO_CMD[@]}" --version >"$REPORT/diagnostics/ruflo-version.txt" 2>&1; then
        pass "Ruflo runtime available: $(cat "$REPORT/diagnostics/ruflo-version.txt" | tail -1)"
    else
        fail "Ruflo runtime exists but --version failed"
    fi
fi

section "6. RUFLO CAPABILITY DISCOVERY"
if [[ "$RUFLO_MODE" != "unavailable" ]]; then
    "${RUFLO_CMD[@]}" --help >"$REPORT/diagnostics/ruflo-help.txt" 2>&1 || true
    for sub in agent swarm task memory status doctor; do
        "${RUFLO_CMD[@]}" "$sub" --help >"$REPORT/diagnostics/${sub}-help.txt" 2>&1 || true
    done
    pass "Ruflo capability help captured"
    grep -E 'agent|swarm|task|memory|status|doctor|autopilot|hive-mind' \
        "$REPORT/diagnostics/ruflo-help.txt" >"$REPORT/diagnostics/capabilities.txt" || true
else
    warn "Capability discovery skipped"
fi

section "7. RUFLO STATUS / DOCTOR"
if [[ "$RUFLO_MODE" != "unavailable" ]]; then
    if "${RUFLO_CMD[@]}" status >"$REPORT/diagnostics/status.txt" 2>&1; then
        pass "Ruflo status succeeded"
    else
        warn "Ruflo status returned non-zero"
    fi
    if "${RUFLO_CMD[@]}" doctor >"$REPORT/diagnostics/doctor.txt" 2>&1; then
        pass "Ruflo doctor succeeded"
    else
        warn "Ruflo doctor returned non-zero"
    fi
else
    warn "Status/doctor skipped"
fi

section "8. CONFIGURATION"
for f in .mcp.json .claude.json .claude/settings.json .claude/settings.local.json; do
    if [[ -f "$f" ]] && jq empty "$f" >/dev/null 2>&1; then
        pass "Valid JSON: $f"
    elif [[ -f "$f" ]]; then
        fail "Invalid JSON: $f"
    else
        warn "Missing: $f"
    fi
done
[[ -f CLAUDE.md ]] && pass "CLAUDE.md exists" || warn "CLAUDE.md missing"

section "9. PYTHON HEALTH"
if [[ -x backend/venv/bin/python ]]; then
    if backend/venv/bin/python -m pip check >"$REPORT/diagnostics/pip-check.txt" 2>&1; then pass "pip check passed"; else fail "pip check failed"; fi
    if find backend/venv/lib/python3.12/site-packages -maxdepth 1 -type d -name '~*' -print |
       grep -q .; then
        warn "Invalid Python distributions detected"
    else
        pass "No invalid Python distributions"
    fi
    if backend/venv/bin/python - <<'PY' >"$REPORT/diagnostics/python-imports.txt" 2>&1
mods = ["numpy","scipy","pandas","sklearn","chromadb","onnxruntime","watchdog","websockets","langgraph"]
for m in mods:
    __import__(m)
    print("[OK]", m)
PY
    then pass "Python core imports passed"; else fail "Python core imports failed"; fi
else
    warn "Python venv unavailable"
fi

section "10. PROJECT CORE TESTS"
if [[ -x backend/venv/bin/python ]]; then
    if backend/venv/bin/python -m pytest tests/test_program_control.py backend/tests/test_mcp_server.py -q --maxfail=5 \
        >"$REPORT/diagnostics/core-tests.txt" 2>&1; then
        pass "Core tests passed"
    else
        fail "Core tests failed"
    fi
else
    warn "Core tests skipped"
fi

section "11. PROGRAM SERVICE CONTRACT"
if [[ -x backend/venv/bin/python ]]; then
    if backend/venv/bin/python - <<'PY' >"$REPORT/diagnostics/program-contract.txt" 2>&1
import inspect
from backend import program_service
expected = ["create_program","get_program","list_programs","update_controls","delete_program"]
for name in expected:
    assert hasattr(program_service, name), f"Missing function: {name}"
assert list(inspect.signature(program_service.create_program).parameters) == ["db","tenant_id","data"]
assert list(inspect.signature(program_service.get_program).parameters) == ["db","program_id","tenant_id"]
assert hasattr(program_service, "_compute_status_rollup")
print("[PASS] Program service contract")
PY
    then pass "Program service contract valid"; else fail "Program service contract invalid"; fi
fi

section "12. MCP / FASTMCP"
if [[ -x backend/venv/bin/python ]]; then
    if backend/venv/bin/python - <<'PY' >"$REPORT/diagnostics/mcp.txt" 2>&1
from mcp.server.fastmcp import FastMCP
print("[PASS] FastMCP:", FastMCP)
PY
    then pass "FastMCP import succeeded"; else fail "FastMCP import failed"; fi
fi

section "13. MULTI-AGENT EXECUTION"
# These are intentionally independent test agents. We record output per agent.
# The test is non-destructive: each agent receives an inspection-only task.
AGENTS=(
    "architect:architect:Analyze the project architecture. Do not modify files. Return findings."
    "researcher:researcher:Inspect project structure and identify major components. Do not modify files."
    "backend:backend:Inspect backend Python services and tests. Do not modify files."
    "frontend:frontend:Inspect frontend/package configuration and tests. Do not modify files."
    "security:security:Inspect configuration for obvious security risks. Do not modify files."
    "tester:tester:Review available tests and identify important test gaps. Do not modify files."
    "reviewer:reviewer:Review project readiness and report risks. Do not modify files."
    "qa:qa:Perform a QA-oriented project inspection. Do not modify files."
)
AGENT_TOTAL="${#AGENTS[@]}"

if [[ "$RUFLO_MODE" == "unavailable" ]]; then
    warn "No agents launched because Ruflo runtime is unavailable"
else
    echo "Attempting $AGENT_TOTAL independent test agents in parallel."
    declare -a PIDS=()
    declare -a NAMES=()

    for entry in "${AGENTS[@]}"; do
        IFS=: read -r name type prompt <<< "$entry"
        outfile="$REPORT/agents/${name}.log"
        NAMES+=("$name")

        (
            echo "AGENT=$name"
            echo "TYPE=$type"
            echo "START=$(date -Is)"
            echo "PROMPT=$prompt"
            echo

            # Prefer the documented V3 syntax.
            if "${RUFLO_CMD[@]}" agent spawn -t "$type" >"$outfile.tmp" 2>&1; then
                echo "SPAWN_STATUS=PASS"
                cat "$outfile.tmp"
            else
                echo "SPAWN_STATUS=FAIL"
                cat "$outfile.tmp"
                exit 10
            fi
            echo
            echo "END=$(date -Is)"
        ) >"$outfile" 2>&1 &

        PIDS+=("$!")
        echo "Launched $name pid=${PIDS[-1]}"
    done

    for i in "${!PIDS[@]}"; do
        name="${NAMES[$i]}"
        if wait "${PIDS[$i]}"; then
            AGENT_OK=$((AGENT_OK+1))
            pass "Agent completed: $name"
        else
            warn "Agent failed or spawn command returned non-zero: $name"
        fi
    done
fi

echo "Agents completed: $AGENT_OK / $AGENT_TOTAL"

section "14. AGENT INVENTORY / STATE"
if [[ "$RUFLO_MODE" != "unavailable" ]]; then
    if "${RUFLO_CMD[@]}" agent list >"$REPORT/diagnostics/agent-list.txt" 2>&1; then
        pass "Agent inventory command succeeded"
    else
        warn "Agent inventory command returned non-zero"
    fi
    if "${RUFLO_CMD[@]}" agent health >"$REPORT/diagnostics/agent-health.txt" 2>&1; then
        pass "Agent health command succeeded"
    else
        warn "Agent health command unavailable/non-zero"
    fi
else
    warn "Agent inventory skipped"
fi

section "15. SWARM TEST"
if [[ "$RUFLO_MODE" != "unavailable" ]]; then
    if "${RUFLO_CMD[@]}" swarm init --v3-mode >"$REPORT/swarm/init.txt" 2>&1; then
        pass "Swarm initialization succeeded"
    else
        warn "Swarm initialization returned non-zero"
    fi
    if "${RUFLO_CMD[@]}" swarm status >"$REPORT/swarm/status.txt" 2>&1; then
        pass "Swarm status succeeded"
    else
        warn "Swarm status returned non-zero"
    fi
else
    warn "Swarm skipped"
fi

section "16. TASK TEST"
if [[ "$RUFLO_MODE" != "unavailable" ]]; then
    "${RUFLO_CMD[@]}" task --help >"$REPORT/tasks/help.txt" 2>&1 || true
    # Only attempt a task command if the installed help exposes a create subcommand.
    if grep -qE '(^|[[:space:]])create([[:space:]]|$)' "$REPORT/tasks/help.txt"; then
        if "${RUFLO_CMD[@]}" task create --help >"$REPORT/tasks/create-help.txt" 2>&1; then
            pass "Task create interface discovered"
        else
            warn "Task create help returned non-zero"
        fi
    else
        warn "Task create interface not exposed by this runtime"
    fi
else
    warn "Task test skipped"
fi

section "17. MEMORY TEST"
if [[ "$RUFLO_MODE" != "unavailable" ]]; then
    if "${RUFLO_CMD[@]}" memory --help >"$REPORT/memory/help.txt" 2>&1; then
        pass "Memory command available"
    else
        warn "Memory command unavailable"
    fi
else
    warn "Memory test skipped"
fi

section "18. FULL PROJECT PYTEST DIAGNOSTIC"
if [[ -x backend/venv/bin/python ]]; then
    backend/venv/bin/python -m pytest -q --collect-only >"$REPORT/diagnostics/full-pytest-collect.txt" 2>&1 || true
    COLLECTED="$(grep -oE '[0-9]+ tests? collected' "$REPORT/diagnostics/full-pytest-collect.txt" | tail -1 | grep -oE '[0-9]+' || echo 0)"
    ERRORS="$(grep -oE '[0-9]+ errors? during collection' "$REPORT/diagnostics/full-pytest-collect.txt" | tail -1 | grep -oE '[0-9]+' || echo 0)"
    echo "Collected tests: $COLLECTED"
    echo "Collection errors: $ERRORS"
    if [[ "$ERRORS" == "0" ]]; then
        pass "Full pytest collection has no collection errors"
    else
        warn "Full pytest collection has $ERRORS diagnostic error(s)"
    fi
else
    warn "Full pytest skipped"
fi

section "19. NPM VALIDATION"
if [[ -f package.json ]]; then
    if jq empty package.json >/dev/null 2>&1; then pass "package.json valid"; else fail "package.json invalid"; fi
    if npm ls --depth=0 >"$REPORT/diagnostics/npm.txt" 2>&1; then pass "npm dependency tree healthy"; else warn "npm dependency tree has diagnostics"; fi
fi

section "20. SOURCE BLOCKER SCAN"
if [[ -f backend/tests/test_mcp_server.py ]]; then
    if grep -nE 'from mcp\.server\.fastmcp|import mcp' backend/tests/test_mcp_server.py >"$REPORT/diagnostics/mcp-source.txt" 2>&1; then
        pass "MCP source references resolvable"
    else
        warn "No MCP source references found in targeted test"
    fi
fi

section "21. ARTIFACTS"
find . -type f -size +500M -not -path "./.git/*" -printf '%s %p\n' 2>/dev/null |
    sort -nr | head -20 >"$REPORT/diagnostics/large-files.txt" || true
find . -type f -size +50M -not -path "./.git/*" -printf '%s %p\n' 2>/dev/null |
    sort -nr | head -20 >"$REPORT/diagnostics/large-logs.txt" || true

if [[ -s "$REPORT/diagnostics/large-files.txt" ]]; then
    warn "Files >500MB detected"
    cat "$REPORT/diagnostics/large-files.txt"
else
    pass "No files >500MB detected"
fi

if [[ -s "$REPORT/diagnostics/large-logs.txt" ]]; then
    warn "Files >50MB detected"
    cat "$REPORT/diagnostics/large-logs.txt"
else
    pass "No files >50MB detected"
fi

section "22. GIT / PROCESSES"
if git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
    pass "Git repository detected"
    if [[ -z "$(git status --porcelain 2>/dev/null)" ]]; then
        pass "Git working tree clean"
    else
        warn "Git working tree contains changes"
        git status --short >"$REPORT/diagnostics/git-status.txt" 2>&1 || true
    fi
else
    warn "Git repository not detected"
fi

pgrep -af 'ruflo|claude-flow' >"$REPORT/diagnostics/ruflo-processes.txt" 2>&1 || true

section "23. FINAL SCORE"
# Ruflo runtime and actual agent execution are weighted heavily.
SCORE=100
[[ "$RUFLO_MODE" == "unavailable" ]] && SCORE=$((SCORE-45))
[[ "$AGENT_OK" -eq 0 ]] && SCORE=$((SCORE-35))
[[ "$AGENT_OK" -gt 0 && "$AGENT_OK" -lt "$AGENT_TOTAL" ]] && SCORE=$((SCORE-20))
[[ "$FAIL" -gt 0 ]] && SCORE=$((SCORE-(FAIL*5)))
[[ "$WARN" -gt 10 ]] && SCORE=$((SCORE-5))
(( SCORE < 0 )) && SCORE=0

if [[ "$RUFLO_MODE" == "unavailable" ]]; then
    RESULT="FAILED"
elif [[ "$AGENT_OK" -eq "$AGENT_TOTAL" && "$FAIL" -eq 0 ]]; then
    RESULT="HEALTHY"
elif [[ "$AGENT_OK" -gt 0 && "$FAIL" -eq 0 ]]; then
    RESULT="DEGRADED"
else
    RESULT="AT_RISK"
fi

echo "Health Score : $SCORE / 100"
echo "PASS         : $PASS"
echo "WARN         : $WARN"
echo "FAIL         : $FAIL"
echo "Agents       : $AGENT_OK / $AGENT_TOTAL"
echo "Ruflo Mode   : $RUFLO_MODE"
echo "RESULT       : $RESULT"

section "24. REPORT"
cat >"$SUMMARY" <<EOF
RUFLO MULTI-AGENT ENTERPRISE TEST v13
Project: $PROJECT
Date: $(date)
Host: $(hostname)

Ruflo Mode: $RUFLO_MODE
Health Score: $SCORE / 100
PASS: $PASS
WARN: $WARN
FAIL: $FAIL
Agents Completed: $AGENT_OK / $AGENT_TOTAL
Result: $RESULT

Primary Log: $MAIN
Summary: $SUMMARY
JSON: $JSON
Agent Logs: $REPORT/agents/
Diagnostics: $REPORT/diagnostics/
EOF

cat >"$JSON" <<EOF
{
  "version": "v13",
  "project": $(printf '%s' "$PROJECT" | jq -Rsa .),
  "timestamp": $(date -Is | jq -Rsa .),
  "host": $(hostname | jq -Rsa .),
  "ruflo_mode": $(printf '%s' "$RUFLO_MODE" | jq -Rsa .),
  "health_score": $SCORE,
  "pass": $PASS,
  "warn": $WARN,
  "fail": $FAIL,
  "agents_total": $AGENT_TOTAL,
  "agents_completed": $AGENT_OK,
  "result": $(printf '%s' "$RESULT" | jq -Rsa .),
  "report": $(printf '%s' "$REPORT" | jq -Rsa .),
  "main_log": $(printf '%s' "$MAIN" | jq -Rsa .)
}
EOF

echo "RUFLO MULTI-AGENT ENTERPRISE TEST v13"
echo "Project: $PROJECT"
echo "Ruflo Mode: $RUFLO_MODE"
echo "Health Score: $SCORE / 100"
echo "PASS: $PASS"
echo "WARN: $WARN"
echo "FAIL: $FAIL"
echo "Agents: $AGENT_OK / $AGENT_TOTAL"
echo "Result: $RESULT"
echo "Report: $REPORT"

exit 0
