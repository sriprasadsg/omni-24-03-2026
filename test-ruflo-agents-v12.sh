#!/usr/bin/env bash
set -u -o pipefail
PROJECT="${PROJECT:-$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)}"
cd "$PROJECT" || exit 1
if [[ "${1:-}" == "--help" ]]; then sed -n '1,35p' "$0"; exit 0; fi
if [[ "${1:-}" == "--background" && "${RUFLO_V11_DAEMONIZED:-0}" != 1 ]]; then
  L="$PROJECT/ruflo-agent-test-v11-launch"; mkdir -p "$L"; T=$(date +%Y%m%d_%H%M%S)
  export RUFLO_V11_DAEMONIZED=1
  nohup "$0" >"$L/launch-$T.log" 2>&1 < /dev/null & echo "PID: $!"; echo "LOG: $L/launch-$T.log"; exit 0
fi
T=$(date +%Y%m%d_%H%M%S); REPORT="$PROJECT/ruflo-agent-test-v11-$T"; mkdir -p "$REPORT"/{agents,tests,swarm,diagnostics,commands}
MASTER="$REPORT/ruflo-agent-test-v11.log"; SUMMARY="$REPORT/summary.txt"; JSON="$REPORT/summary.json"; echo $$ > "$REPORT/test.pid"
PASS=0; WARN=0; FAIL=0; AGENT_TOTAL=8; AGENT_OK=0
say(){ printf '%s\n' "$*" | tee -a "$MASTER"; }; section(){ say ""; say "============================================================"; say "$1"; say "============================================================"; }; pass(){ PASS=$((PASS+1)); say "[PASS] $*"; }; warn(){ WARN=$((WARN+1)); say "[WARN] $*"; }; fail(){ FAIL=$((FAIL+1)); say "[FAIL] $*"; }
section "RUFLO AGENT ENTERPRISE TEST v11"; say "Project : $PROJECT"; say "Date : $(date)"; say "Host : $(hostname)"; say "PID : $$"; say "Report : $REPORT"
section "1. SYSTEM HEALTH"; CPU=$(nproc 2>/dev/null || echo unknown); MEM=$(free -h 2>/dev/null|awk '/^Mem:/{print $7}'); USE=$(df -P "$PROJECT"|awk 'NR==2{print $5}'|tr -d '%'); say "CPU Cores : $CPU"; say "Memory Available : ${MEM:-unknown}"; say "Root Usage : ${USE}%"; [[ "$USE" =~ ^[0-9]+$ && $USE -lt 85 ]] && pass "Filesystem capacity acceptable" || warn "Filesystem usage elevated"
df -h "$PROJECT" >"$REPORT/diagnostics/disk.log" 2>&1 || true; free -h >"$REPORT/diagnostics/memory.log" 2>&1 || true
section "2. REQUIRED TOOLCHAIN"; for c in bash node npm npx git python3 find awk sed grep du df sort head tail jq; do command -v "$c" >/dev/null 2>&1 && pass "$c: $(command -v "$c")" || fail "$c missing"; done
section "3. RUNTIME"; node --version 2>&1|tee -a "$MASTER"; npm --version 2>&1|tee -a "$MASTER"; python3 --version 2>&1|tee -a "$MASTER"; git --version 2>&1|tee -a "$MASTER"
section "4. PROJECT"; [[ -f package.json ]] && pass "package.json exists" || fail "package.json missing"; [[ -f package-lock.json ]] && pass "package-lock.json exists" || warn "package-lock.json missing"; [[ -d node_modules ]] && pass "node_modules exists" || warn "node_modules missing"; [[ -x backend/venv/bin/python ]] && pass "backend venv exists" || warn "backend venv missing"; for d in .agents .agents/skills/ruflo .claude-flow .claude; do [[ -d "$d" ]] && pass "$d exists" || warn "$d missing"; done
section "5. RUFLO RUNTIME"; RUFLO=(); if command -v ruflo >/dev/null 2>&1; then RUFLO=(ruflo); elif [[ -x node_modules/.bin/ruflo ]]; then RUFLO=(node_modules/.bin/ruflo); elif npx --no-install ruflo --version >"$REPORT/commands/ruflo-version.log" 2>&1; then RUFLO=(npx --no-install ruflo); fi
if ((${#RUFLO[@]})); then "${RUFLO[@]}" --version 2>&1|tee "$REPORT/commands/ruflo-version.log"|tee -a "$MASTER"; "${RUFLO[@]}" --help >"$REPORT/commands/ruflo-help.log" 2>&1 || true; pass "Ruflo runtime available"; else fail "Ruflo runtime unavailable"; fi
section "6. RUFLO CAPABILITIES"; if ((${#RUFLO[@]})); then H=$(cat "$REPORT/commands/ruflo-help.log" 2>/dev/null); for x in agent agents swarm task tasks memory status health; do grep -Eiq "(^|[[:space:]])$x([[:space:]]|$)" <<<"$H" && pass "Ruflo exposes $x" || warn "No obvious $x command"; done; else warn "Capability discovery skipped"; fi
run_ruflo(){ local o="$1"; shift; ("${RUFLO[@]}" "$@") >"$o" 2>&1; }
section "7. STATUS / HEALTH"; if ((${#RUFLO[@]})) && { run_ruflo "$REPORT/commands/status.log" status || run_ruflo "$REPORT/commands/system-status.log" system status || run_ruflo "$REPORT/commands/health.log" health; }; then pass "Ruflo status/health command succeeded"; else warn "No supported status/health command succeeded"; fi
section "8. CONFIG"; for f in .mcp.json .claude.json .claude/settings.json .claude/settings.local.json; do if [[ -f "$f" ]] && jq empty "$f" >/dev/null 2>&1; then pass "Valid JSON: $f"; elif [[ -f "$f" ]]; then fail "Invalid JSON: $f"; else warn "Missing: $f"; fi; done; [[ -f CLAUDE.md ]] && pass "CLAUDE.md exists" || warn "CLAUDE.md missing"
section "9. PYTHON"; PY=python3; [[ -x backend/venv/bin/python ]] && PY=backend/venv/bin/python; "$PY" -m pip check >"$REPORT/diagnostics/pip-check.log" 2>&1 && pass "pip check passed" || fail "pip check failed"; if find backend/venv/lib/python3.12/site-packages -maxdepth 1 -type d -name '~*' -print -quit 2>/dev/null|grep -q .; then fail "Invalid Python distributions detected"; else pass "No invalid Python distributions"; fi
"$PY" - <<'PY' >"$REPORT/diagnostics/python-imports.log" 2>&1
for m in ('numpy','scipy','pandas','sklearn','chromadb','onnxruntime','watchdog','websockets','langgraph','mcp'): __import__(m); print('[OK]',m)
from mcp.server.fastmcp import FastMCP; print('[OK] FastMCP')
PY
if grep -q '^\[OK\]' "$REPORT/diagnostics/python-imports.log" && ! grep -q 'Traceback\|Error' "$REPORT/diagnostics/python-imports.log"; then pass "Python core imports passed"; else fail "Python core imports failed"; fi
section "10. CORE TESTS"; TESTS=(); [[ -f tests/test_program_control.py ]] && TESTS+=(tests/test_program_control.py); [[ -f backend/tests/test_mcp_server.py ]] && TESTS+=(backend/tests/test_mcp_server.py); if ((${#TESTS[@]})); then "$PY" -m pytest -q "${TESTS[@]}" --maxfail=10 >"$REPORT/tests/core-tests.log" 2>&1 && pass "Core tests passed" || fail "Core tests failed"; else warn "Core tests not found"; fi
section "11. PROGRAM SERVICE"; if [[ -f tests/test_program_control.py ]]; then "$PY" -m pytest -q tests/test_program_control.py >"$REPORT/tests/program-control.log" 2>&1 && pass "Program service tests passed" || fail "Program service tests failed"; fi
section "12. MCP"; "$PY" - <<'PY' >"$REPORT/tests/mcp.log" 2>&1
from mcp.server.fastmcp import FastMCP
import mcp
print('[OK] FastMCP', FastMCP); print('[OK] mcp', mcp)
PY
 grep -q 'FastMCP' "$REPORT/tests/mcp.log" && pass "FastMCP import succeeded" || fail "FastMCP import failed"
section "13. FULL PYTEST DIAGNOSTIC"; "$PY" -m pytest --collect-only -q >"$REPORT/tests/pytest-collection.log" 2>&1 || true; grep -E 'collected|ERROR collecting|errors?' "$REPORT/tests/pytest-collection.log"|tail -20|tee -a "$MASTER"; grep -q 'ERROR collecting\|UnicodeDecodeError\|ConnectError\|URLError' "$REPORT/tests/pytest-collection.log" && warn "Full pytest has collection/environment diagnostics" || pass "No obvious collection diagnostics"
section "14. MULTI-AGENT EXECUTION"; declare -a PIDS NAMES; AGENTS=("architect|architecture review" "researcher|dependency and configuration review" "backend|backend service review" "frontend|frontend build review" "security|security configuration review" "tester|test strategy and failure review" "reviewer|overall release blocker review" "qa|independent QA review")
spawn(){ local n="$1"; local task="$2"; local o="$REPORT/agents/$n.log"; { echo "AGENT=$n"; echo "TASK=$task"; echo "START=$(date)"; if ((${#RUFLO[@]}==0)); then echo '[RUFLO_UNAVAILABLE]'; exit 127; fi; if "${RUFLO[@]}" agent spawn --type "$n" --name "ruflo-v11-$n" --task "$task"; then echo '[SPAWN_OK]'; exit 0; fi; if "${RUFLO[@]}" agent spawn --name "ruflo-v11-$n" --type "$n" --task "$task"; then echo '[SPAWN_OK]'; exit 0; fi; if "${RUFLO[@]}" agents create --name "ruflo-v11-$n" --type "$n" --task "$task"; then echo '[SPAWN_OK]'; exit 0; fi; echo '[SPAWN_FAILED]'; exit 1; } >"$o" 2>&1; }
if ((${#RUFLO[@]})); then for a in "${AGENTS[@]}"; do n="${a%%|*}"; t="${a#*|}"; spawn "$n" "$t" & PIDS+=("$!"); NAMES+=("$n"); done; for i in "${!PIDS[@]}"; do if wait "${PIDS[$i]}"; then AGENT_OK=$((AGENT_OK+1)); pass "Agent completed: ${NAMES[$i]}"; else warn "Agent failed: ${NAMES[$i]}"; fi; done; else warn "No agents launched because Ruflo runtime is unavailable"; fi; say "Agents completed: $AGENT_OK / $AGENT_TOTAL"
section "15. AGENT EVIDENCE"; for a in "${AGENTS[@]}"; do n="${a%%|*}"; if grep -q '\[SPAWN_OK\]' "$REPORT/agents/$n.log" 2>/dev/null; then pass "$n spawn evidence recorded"; else warn "$n has no successful spawn evidence"; fi; done
section "16. SWARM / TASK / MEMORY"; if ((${#RUFLO[@]})); then run_ruflo "$REPORT/swarm/status.log" swarm status || true; run_ruflo "$REPORT/swarm/tasks.log" task list || run_ruflo "$REPORT/swarm/tasks2.log" tasks list || true; run_ruflo "$REPORT/swarm/memory.log" memory list || true; pass "Swarm/task/memory diagnostics captured"; else warn "Swarm/task/memory skipped"; fi
section "17. NPM"; jq empty package.json >/dev/null 2>&1 && pass "package.json valid" || fail "package.json invalid"; if [[ -f package-lock.json ]]; then npm ls --depth=0 >"$REPORT/tests/npm.log" 2>&1 && pass "npm dependency tree healthy" || warn "npm dependency diagnostics present"; fi
section "18. SOURCE BLOCKERS"; if "$PY" - <<'PY' >"$REPORT/diagnostics/source-imports.log" 2>&1
from mcp.server.fastmcp import FastMCP
from backend.program_service import create_program,get_program,list_programs,update_controls,delete_program
print('[OK] core source imports')
PY
then pass "Core source imports resolvable"; else fail "Core source import blocker"; fi
section "19. ARTIFACTS"; find "$PROJECT" -path "$PROJECT/backend/venv" -prune -o -path "$PROJECT/node_modules" -prune -o -type f -size +500M -printf '%s %p\n' 2>/dev/null|sort -nr >"$REPORT/diagnostics/large-files.txt"; find "$PROJECT" -path "$PROJECT/backend/venv" -prune -o -path "$PROJECT/node_modules" -prune -o -type f -size +50M \( -name '*.log' -o -name '*.out' \) -printf '%s %p\n' 2>/dev/null|sort -nr >"$REPORT/diagnostics/large-logs.txt"; [[ -s "$REPORT/diagnostics/large-files.txt" ]] && warn "Files >500MB detected" || pass "No files >500MB"; [[ -s "$REPORT/diagnostics/large-logs.txt" ]] && warn "Logs >50MB detected" || pass "No logs >50MB"
section "20. GIT / PROCESSES"; git rev-parse --is-inside-work-tree >/dev/null 2>&1 && pass "Git repository detected" || warn "Git repository not detected"; git status --short >"$REPORT/diagnostics/git-status.log" 2>&1 || true; [[ -s "$REPORT/diagnostics/git-status.log" ]] && warn "Git working tree contains changes" || pass "Git working tree clean"; ps -eo pid,ppid,stat,etime,cmd >"$REPORT/diagnostics/processes.log" 2>&1 || true
section "21. HEALTH SCORE"; SCORE=$((100-FAIL*15-WARN*2-(AGENT_TOTAL-AGENT_OK)*5)); ((SCORE<0))&&SCORE=0; if ((FAIL>0)); then RESULT=FAILED; elif ((AGENT_OK<AGENT_TOTAL)); then RESULT=DEGRADED; elif ((SCORE<80)); then RESULT=AT_RISK; else RESULT=HEALTHY; fi; say "Health Score : $SCORE / 100"; say "PASS : $PASS"; say "WARN : $WARN"; say "FAIL : $FAIL"; say "Agents : $AGENT_OK / $AGENT_TOTAL"; say "RESULT : $RESULT"
section "22. REPORT"; cat >"$SUMMARY" <<EOF2
RUFLO AGENT ENTERPRISE TEST v11
Project: $PROJECT
Date: $(date)
Host: $(hostname)
Ruflo: ${RUFLO[*]:-unavailable}
Health Score: $SCORE / 100
PASS: $PASS
WARN: $WARN
FAIL: $FAIL
Agents: $AGENT_OK / $AGENT_TOTAL
Result: $RESULT
Report: $REPORT
EOF2
python3 - "$JSON" <<PY
import json
p='$JSON'
json.dump({'version':'v11','project':'$PROJECT','score':$SCORE,'pass':$PASS,'warn':$WARN,'fail':$FAIL,'agents':{'requested':$AGENT_TOTAL,'completed':$AGENT_OK},'result':'$RESULT','report_directory':'$REPORT'},open(p,'w'),indent=2)
PY
cat "$SUMMARY" | tee -a "$MASTER"; rm -f "$REPORT/test.pid"; section "RUFLO AGENT ENTERPRISE TEST v11 COMPLETE"; say "PASS: $PASS  WARN: $WARN  FAIL: $FAIL  SCORE: $SCORE / 100  AGENTS: $AGENT_OK/$AGENT_TOTAL  RESULT: $RESULT"; say "Summary: $SUMMARY"; say "JSON: $JSON"; say "Report: $MASTER"; exit 0
