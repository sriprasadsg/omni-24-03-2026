#!/usr/bin/env bash
# RUFLO ENTERPRISE TEST v3
# Accurate PASS/WARN/FAIL validation.
set -u
set -o pipefail

PROJECT_DIR="${PROJECT_DIR:-$(pwd)}"
PROJECT_DIR="$(cd "$PROJECT_DIR" 2>/dev/null && pwd)" || exit 2
TS="$(date '+%Y%m%d_%H%M%S')"
R="$PROJECT_DIR/ruflo-test-report-$TS"
mkdir -p "$R"
LOG="$R/ruflo-enterprise-test-v3.log"
SUMMARY="$R/summary.txt"
PY="$R/python-validation.txt"
PT="$R/pytest-validation.txt"
CLI="$R/ruflo-cli.txt"
NPM="$R/npm-validation.txt"
CFG="$R/config-validation.txt"
STATE="$R/state-validation.txt"
LF="$R/large-files.txt"
LL="$R/large-logs.txt"
: >"$LOG"; : >"$PY"; : >"$PT"; : >"$CLI"; : >"$NPM"; : >"$CFG"; : >"$STATE"; : >"$LF"; : >"$LL"

PASS=0; WARN=0; FAIL=0
pass(){ PASS=$((PASS+1)); echo "[PASS] $*" | tee -a "$LOG"; }
warn(){ WARN=$((WARN+1)); echo "[WARN] $*" | tee -a "$LOG"; }
fail(){ FAIL=$((FAIL+1)); echo "[FAIL] $*" | tee -a "$LOG"; }
section(){ printf '\n============================================================\n%s\n============================================================\n' "$*" | tee -a "$LOG"; }
size(){ du -sh "$1" 2>/dev/null | awk '{print $1}'; }

cd "$PROJECT_DIR" || exit 2

{
echo "RUFLO ENTERPRISE TEST v3"
echo "Project : $PROJECT_DIR"
echo "Date    : $(date)"
echo "Host    : $(hostname)"
echo "User    : $(id -un)"
echo "Kernel  : $(uname -r)"
echo "Report  : $LOG"
} | tee -a "$LOG"

section "1. SYSTEM HEALTH"
echo "CPU Model : $(lscpu 2>/dev/null | awk -F: '/Model name/{sub(/^[ \t]+/,"",$2);print $2;exit}')" | tee -a "$LOG"
echo "CPU Cores : $(nproc 2>/dev/null || echo unknown)" | tee -a "$LOG"
free -h 2>/dev/null | tee -a "$LOG"
df -h "$PROJECT_DIR" | tee -a "$LOG"
df -Pi "$PROJECT_DIR" | tee -a "$LOG"
USE="$(df -P "$PROJECT_DIR" | awk 'NR==2{gsub("%","",$5);print $5}')"
INO="$(df -Pi "$PROJECT_DIR" | awk 'NR==2{gsub("%","",$5);print $5}')"
if [ "${USE:-100}" -ge 90 ]; then fail "Filesystem is ${USE}% used"; elif [ "${USE:-100}" -ge 80 ]; then warn "Filesystem is ${USE}% used"; else pass "Filesystem capacity healthy (${USE}% used)"; fi
if [ "${INO:-100}" -ge 90 ]; then fail "Inodes are ${INO}% used"; elif [ "${INO:-100}" -ge 80 ]; then warn "Inodes are ${INO}% used"; else pass "Inode usage healthy (${INO}%)"; fi

section "2. REQUIRED COMMANDS"
for c in bash node npm npx git python3 find awk sed grep du df sort head tail; do
  command -v "$c" >/dev/null 2>&1 && pass "$c available: $(command -v "$c")" || fail "$c is missing"
done
command -v jq >/dev/null 2>&1 && pass "jq available" || warn "jq not installed; Python JSON validation will be used"

section "3. RUNTIME VERSIONS"
NODE="$(node --version 2>/dev/null || true)"
echo "Node : $NODE"; echo "npm  : $(npm --version 2>/dev/null || true)"
echo "npx  : $(npx --version 2>/dev/null || true)"
echo "Git  : $(git --version 2>/dev/null || true)"
echo "Py3  : $(python3 --version 2>/dev/null || true)"
MAJOR="$(echo "$NODE" | sed -E 's/^v([0-9]+).*/\1/')"
if [ -n "$MAJOR" ] && [ "$MAJOR" -ge 20 ]; then pass "Node.js major version is $MAJOR"; elif [ -n "$MAJOR" ] && [ "$MAJOR" -ge 18 ]; then warn "Node.js major version is $MAJOR"; else fail "Node.js is missing or too old: $NODE"; fi

section "4. NODE PROJECT"
[ -f package.json ] && pass "package.json exists" || fail "package.json missing"
if [ -f package.json ]; then
  python3 - "$PROJECT_DIR/package.json" >>"$NPM" 2>&1 <<'PY'
import json,sys
json.load(open(sys.argv[1],encoding="utf-8"))
print("package.json: valid JSON")
PY
  [ $? -eq 0 ] && pass "package.json is valid JSON" || fail "package.json is invalid JSON"
fi
[ -f package-lock.json ] && pass "package-lock.json exists" || warn "package-lock.json missing"
if [ -d node_modules ]; then pass "node_modules exists ($(size node_modules))"; else fail "node_modules missing"; fi
if [ -f package-lock.json ] && [ -d node_modules ]; then
  npm ls --depth=0 --omit=optional >>"$NPM" 2>&1 && pass "npm top-level dependency tree is healthy" || warn "npm dependency tree has issues; see $NPM"
fi

section "5. RUFLO / CLAUDE-FLOW CLI"
[ -x node_modules/.bin/ruflo ] && LOCAL_R="$PROJECT_DIR/node_modules/.bin/ruflo" || LOCAL_R=""
RUFLO_OK=0
if [ -n "$LOCAL_R" ]; then
  "$LOCAL_R" --version >"$CLI" 2>&1
  if grep -qi ruflo "$CLI"; then pass "Local Ruflo works: $(head -1 "$CLI")"; RUFLO_OK=1; else warn "Local Ruflo exists but --version failed"; fi
fi
if [ "$RUFLO_OK" -eq 0 ] && [ -d node_modules ]; then
  if npx --no-install ruflo --version >"$CLI" 2>&1; then
    pass "Ruflo works through npx --no-install: $(head -1 "$CLI")"; RUFLO_OK=1
  else
    echo "npx --no-install ruflo failed" >>"$CLI"
  fi
fi
command -v ruflo >/dev/null 2>&1 && pass "Global Ruflo: $(command -v ruflo)" || warn "No global Ruflo executable"
if [ "$RUFLO_OK" -eq 0 ]; then fail "Ruflo CLI is not executable from this project"; fi
if [ -x node_modules/.bin/claude-flow ]; then
  node_modules/.bin/claude-flow --version >>"$CLI" 2>&1 && pass "Local claude-flow works" || warn "Local claude-flow exists but failed"
elif npx --no-install claude-flow --version >>"$CLI" 2>&1; then
  pass "claude-flow works through npx --no-install"
else
  warn "claude-flow command unavailable; may be normal for Ruflo-only projects"
fi

section "6. RUFLO PACKAGE DISCOVERY"
if [ -f package.json ]; then
  python3 - "$PROJECT_DIR/package.json" >>"$CLI" 2>&1 <<'PY'
import json,sys
d=json.load(open(sys.argv[1],encoding="utf-8")); x={}
for k in ("dependencies","devDependencies"): x.update(d.get(k,{}) or {})
h={k:v for k,v in x.items() if any(s in k.lower() for s in ("ruflo","claude-flow","flow-nexus"))}
print("Related packages:", h)
print("COUNT:",len(h))
PY
  COUNT="$(awk -F: '/^COUNT:/{gsub(/ /,"",$2);print $2}' "$CLI" | tail -1)"
  [ "${COUNT:-0}" -gt 0 ] && pass "Ruflo-related package declared" || warn "No Ruflo-related package declared in package.json"
fi

section "7. RUFLO PROJECT STRUCTURE"
for d in .agents .agents/skills .agents/skills/ruflo .claude-flow .claude; do
  [ -d "$d" ] && pass "Exists: $d ($(size "$d"))" || warn "Missing: $d"
done
for d in .hive-mind .swarm; do
  [ -d "$d" ] && pass "Optional state directory exists: $d ($(size "$d"))" || warn "Optional state directory missing: $d"
done

section "8. CONFIGURATION VALIDATION"
for f in .mcp.json .claude.json .claude/settings.json .claude/settings.local.json; do
  if [ -f "$f" ]; then
    python3 - "$f" >>"$CFG" 2>&1 <<'PY'
import json,sys
json.load(open(sys.argv[1],encoding="utf-8")); print("VALID",sys.argv[1])
PY
    [ $? -eq 0 ] && pass "Valid JSON: $f" || fail "Invalid JSON: $f"
  else warn "Missing configuration: $f"; fi
done
[ -f CLAUDE.md ] && pass "CLAUDE.md exists" || warn "CLAUDE.md missing"

section "9. RUFLO STATE / PROCESSES"
pgrep -af 'ruflo|claude-flow|claude' >"$STATE" 2>&1 && pass "Ruflo/Claude-related process information collected" || warn "No active Ruflo/Claude process"
FOUND=0
for d in .claude-flow .agents .hive-mind .swarm; do
  if [ -d "$d" ]; then N="$(find "$d" -type f 2>/dev/null | wc -l)"; echo "$d: $N files" >>"$STATE"; [ "$N" -gt 0 ] && FOUND=1; fi
done
[ "$FOUND" -eq 1 ] && pass "Ruflo-related state contains files" || warn "No Ruflo state files found"

section "10. PYTHON ENVIRONMENT"
if [ -x backend/venv/bin/python ]; then PYBIN="$PROJECT_DIR/backend/venv/bin/python"; elif [ -x venv/bin/python ]; then PYBIN="$PROJECT_DIR/venv/bin/python"; else PYBIN="$(command -v python3 || true)"; fi
echo "Python: $PYBIN" | tee -a "$PY"
if [ -n "$PYBIN" ] && [ -x "$PYBIN" ]; then
  "$PYBIN" --version | tee -a "$PY"
  "$PYBIN" -m pip check >>"$PY" 2>&1
  if [ $? -eq 0 ]; then pass "Python pip check passed"; else warn "Python pip check has issues; see $PY"; fi
  "$PYBIN" - <<'PY' >>"$PY" 2>&1
import importlib
mods=[("numpy","NumPy"),("scipy","SciPy"),("pandas","Pandas"),("sklearn","Scikit-learn"),("chromadb","ChromaDB"),("onnxruntime","ONNX Runtime"),("cpuinfo","CPUInfo"),("watchdog","Watchdog"),("websockets","WebSockets"),("langgraph","LangGraph")]
bad=[]
for m,n in mods:
 try:
  x=importlib.import_module(m); print("[OK]",n,getattr(x,"__version__","loaded"))
 except Exception as e: print("[FAIL]",n,type(e).__name__,e); bad.append(n)
print("FAILED:",",".join(bad) if bad else "NONE")
raise SystemExit(bool(bad))
PY
  if grep -q '^FAILED: NONE$' "$PY"; then pass "Python core imports passed"; else fail "Python core imports failed; see $PY"; fi
else fail "No usable Python interpreter found"; fi

section "11. PYTEST VALIDATION"
# Collection ignores generated binary/text artifacts and unrelated vendored/worktree
# trees. Genuine source import errors are NOT ignored.
ARGS=(--collect-only -q
  --ignore=agent/test_output.txt --ignore=agent/test_output_2.txt
  --ignore=agent/test_output_3.txt --ignore=agent/test_output_6.txt
  --ignore=agent/capabilities/test_output.txt --ignore=test_dir
  --ignore=code-review-graph-main --ignore=.claude --ignore=.claude/worktrees
  --ignore=agent-rust --ignore=agent-install)
[ "${RUN_FULL_PYTEST:-0}" = "1" ] && ARGS=("${ARGS[@]/--collect-only/}")
if [ -n "${PYBIN:-}" ] && [ -x "${PYBIN:-}" ]; then
  "$PYBIN" -m pytest "${ARGS[@]}" >"$PT" 2>&1; PRC=$?
  if [ "$PRC" -eq 0 ]; then
    C="$(grep -Eo '[0-9]+ tests? collected' "$PT" | tail -1)"
    pass "Pytest validation passed${C:+: $C}"
  else
    fail "Pytest has genuine collection/test errors; see $PT"
  fi
else fail "Pytest unavailable because Python is unavailable"; fi

section "12. SOURCE-LEVEL BLOCKERS"
if [ -f tests/test_program_control.py ] && [ -f backend/program_service.py ] &&
   grep -q get_program_status tests/test_program_control.py &&
   ! grep -qE '^[[:space:]]*(async[[:space:]]+)?def[[:space:]]+get_program_status[[:space:]]*\(' backend/program_service.py; then
  fail "tests/test_program_control.py imports get_program_status, but backend/program_service.py does not define it"
fi
if [ -f backend/mcp_server.py ] && grep -q 'mcp\.server\.fastmcp' backend/mcp_server.py; then
  "$PYBIN" -c 'from mcp.server.fastmcp import FastMCP' >/dev/null 2>&1 && pass "FastMCP import is available" || fail "backend/mcp_server.py requires mcp.server.fastmcp but import is unavailable"
fi

section "13. LARGE FILES / LOGS"
LMB="${LARGE_FILE_MB:-500}"
find "$PROJECT_DIR" -type f -size +"${LMB}"M \
  -not -path "$PROJECT_DIR/node_modules/*" -not -path "$PROJECT_DIR/backend/venv/*" \
  -not -path "$PROJECT_DIR/venv/*" -not -path "$PROJECT_DIR/.git/*" \
  -not -path "$PROJECT_DIR/.claude/worktrees/*" \
  -printf '%s %p\n' 2>/dev/null | sort -nr | head -100 | numfmt --field=1 --to=iec >"$LF" 2>/dev/null || true
if [ -s "$LF" ]; then warn "Files larger than ${LMB} MB detected; see $LF"; cat "$LF" | tee -a "$LOG"; else pass "No files larger than ${LMB} MB detected"; fi
find "$PROJECT_DIR" -type f \( -name '*.log' -o -name '*.jsonl' -o -name 'run.log' \) -size +50M \
  -not -path "$PROJECT_DIR/node_modules/*" -not -path "$PROJECT_DIR/backend/venv/*" \
  -not -path "$PROJECT_DIR/venv/*" -not -path "$PROJECT_DIR/.git/*" \
  -printf '%s %p\n' 2>/dev/null | sort -nr | head -100 | numfmt --field=1 --to=iec >"$LL" 2>/dev/null || true
if [ -s "$LL" ]; then warn "Logs larger than 50 MB detected; see $LL"; cat "$LL" | tee -a "$LOG"; else pass "No logs larger than 50 MB detected"; fi

section "14. AUDIT REPORT HYGIENE"
if [ -d audit-reports ]; then
  AB="$(du -sb audit-reports 2>/dev/null | awk '{print $1}')"
  echo "audit-reports: $(size audit-reports)" | tee -a "$LOG"
  if [ "${AB:-0}" -ge $((50*1024*1024*1024)) ]; then warn "audit-reports exceeds 50 GiB"
  elif [ "${AB:-0}" -ge $((10*1024*1024*1024)) ]; then warn "audit-reports exceeds 10 GiB"
  else pass "audit-reports size is within normal bounds"; fi
else warn "audit-reports directory does not exist"; fi

section "15. GIT"
if git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
  pass "Git repository detected"
  git diff --quiet && git diff --cached --quiet && pass "No tracked working-tree/index modifications" || warn "Git working tree has changes"
else warn "Not a Git working tree"; fi

section "16. FINAL RESULT"
if [ "$FAIL" -gt 0 ]; then RESULT="FAILED"; elif [ "$WARN" -gt 0 ]; then RESULT="PASS WITH WARNINGS"; else RESULT="PASS"; fi
{
echo "RUFLO ENTERPRISE TEST v3 SUMMARY"
echo "Project: $PROJECT_DIR"
echo "Date: $(date)"
echo "Host: $(hostname)"
echo
echo "PASS: $PASS"
echo "WARN: $WARN"
echo "FAIL: $FAIL"
echo
echo "Main report: $LOG"
echo "Ruflo CLI: $CLI"
echo "Python validation: $PY"
echo "Pytest validation: $PT"
echo "NPM validation: $NPM"
echo "Config validation: $CFG"
echo "State validation: $STATE"
echo "Large files: $LF"
echo "Large logs: $LL"
echo
echo "RESULT: $RESULT"
} | tee "$SUMMARY" | tee -a "$LOG"
echo
echo "RUFLO ENTERPRISE TEST v3 COMPLETE"
echo "PASS : $PASS"
echo "WARN : $WARN"
echo "FAIL : $FAIL"
echo "Summary: $SUMMARY"
echo "Report : $LOG"
[ "$FAIL" -gt 0 ] && exit 1 || exit 0
