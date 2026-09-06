#!/usr/bin/env bash
set -Eeuo pipefail

# enterprise-ruflo-audit-fix.sh
# Purpose:
#   1) Diagnose/fix the known NumPy CPU-wheel incompatibility without bypassing tests.
#   2) Validate Python dependencies.
#   3) Resolve the frontend Vitest coverage provider using the project's Vitest version.
#   4) Run frontend/backend tests with coverage.
#   5) Inventory and classify skipped tests.
#   6) Run lint/typecheck when scripts exist.
#   7) Launch a read-only RuFlo enterprise audit.
#
# Important:
#   - Does NOT use --force or --legacy-peer-deps.
#   - Does NOT delete/disable/weaken/bypass tests.
#   - Does NOT modify application/production source code.
#   - Creates backups of package.json/package-lock.json and requirements files before changes.
#   - Review the generated report before applying any production-code remediation.

ROOT="${ROOT:-$HOME/enterprise-omni-agent-ai-platform}"
cd "$ROOT"

TS="$(date +%Y%m%d_%H%M%S)"
REPORT_DIR="$ROOT/audit-reports/$TS"
LOG="$REPORT_DIR/run.log"
REPORT="$REPORT_DIR/ENTERPRISE_AUDIT_REPORT.md"
mkdir -p "$REPORT_DIR"

exec > >(tee -a "$LOG") 2>&1

PASS=0
FAIL=0
WARN=0

ok(){ echo "PASS: $*"; PASS=$((PASS+1)); }
warn(){ echo "WARN: $*"; WARN=$((WARN+1)); }
fail(){ echo "FAIL: $*"; FAIL=$((FAIL+1)); }
section(){ printf '\n===== %s =====\n' "$*"; }

trap 'echo; fail "Unexpected command failure at line $LINENO: $BASH_COMMAND"; exit 1' ERR

section "Environment"
echo "Project: $ROOT"
echo "Date: $(date -Is)"
echo "Kernel: $(uname -a)"
echo "CPU: $(lscpu | grep -E "^(Architecture|Model name|Flags):" | head -3 || true)"
echo "Node: $(node --version 2>/dev/null || echo missing)"
echo "npm: $(npm --version 2>/dev/null || echo missing)"
echo "Python: $("$ROOT/backend/venv/bin/python" --version 2>/dev/null || echo missing)"
echo "RuFlo: $(npx ruflo@latest --version 2>/dev/null || echo unavailable)"

section "Safety backup"
mkdir -p "$REPORT_DIR/backups"
for f in package.json package-lock.json backend/requirements.txt backend/requirements-dev.txt backend/requirements-ml.txt backend/requirements-eval.txt backend/pyproject.toml; do
  if [[ -f "$f" ]]; then cp -a "$f" "$REPORT_DIR/backups/$(basename "$f").$TS"; fi
done
ok "Configuration backups created in $REPORT_DIR/backups"

section "Initial dependency evidence"
grep -nEi 'vitest|coverage-v8|numpy|chromadb|onnxruntime|scipy|pandas|scikit' \
  package.json package-lock.json backend/requirements*.txt backend/pyproject.toml 2>/dev/null || true

section "Python CPU compatibility diagnosis"
PY="$ROOT/backend/venv/bin/python"
PIP="$PY -m pip"

if [[ ! -x "$PY" ]]; then
  fail "backend virtualenv Python not found: $PY"
  exit 1
fi

echo "--- pip check (before) ---"
$PIP check || warn "pip check reports issues; see log."

echo "--- NumPy import (before) ---"
if $PY -c 'import numpy; print(numpy.__version__, numpy.__file__)'; then
  ok "NumPy imports before repair."
else
  warn "NumPy import failed; checking CPU baseline."
fi

CPU_FLAGS="$(lscpu 2>/dev/null | awk -F: '/Flags/ {print $2; exit}' || true)"
if grep -qw 'avx2' <<<"$CPU_FLAGS" && grep -qw 'avx' <<<"$CPU_FLAGS"; then
  CPU_V2="yes"
else
  CPU_V2="no"
fi

if ! $PY -c 'import numpy' >/dev/null 2>&1; then
  echo "Known failure pattern detected. Reinstalling a broadly compatible NumPy 1.26 wheel."
  echo "Reason: current NumPy wheel requires x86-64-v2, while this VM does not expose x86-64-v2."
  echo "This is a dependency/environment repair, not a production-code change."

  # NumPy 1.26.4 supports CPython 3.12 and uses the older x86-64 baseline.
  $PIP install --upgrade --force-reinstall --no-cache-dir 'numpy==1.26.4'
  if $PY -c 'import numpy; print("NumPy", numpy.__version__)'; then
    ok "NumPy 1.26.4 imports successfully."
  else
    fail "NumPy still cannot import after repair."
    exit 1
  fi
else
  ok "NumPy import is healthy; no NumPy repair required."
fi

echo "--- pip check (after NumPy repair) ---"
if $PIP check; then
  ok "Python dependency graph is consistent."
else
  warn "Python dependency graph has conflicts; captured above."
fi

echo "--- ChromaDB import ---"
if $PY -c 'import chromadb; print("ChromaDB", chromadb.__version__)'; then
  ok "ChromaDB imports successfully."
else
  fail "ChromaDB still fails to import."
  exit 1
fi

section "Frontend Vitest coverage provider"
VITEST_VERSION="$(
  node -e '
    const p=require("./package.json");
    const v=(p.devDependencies||{}).vitest || (p.dependencies||{}).vitest || "";
    process.stdout.write(v)
  ' 2>/dev/null || true
)"
echo "Declared Vitest: ${VITEST_VERSION:-not found}"

if [[ -z "$VITEST_VERSION" ]]; then
  warn "Vitest not declared in package.json; frontend coverage setup requires manual review."
else
  # Resolve the installed Vitest major/minor and require the matching coverage-v8 major/minor.
  INSTALLED_VITEST="$(
    node -e 'try { console.log(require("vitest/package.json").version) } catch(e) { process.exit(1) }' 2>/dev/null || true
  )"
  if [[ -z "$INSTALLED_VITEST" ]]; then
    echo "Installing existing project dependencies first."
    npm install
    INSTALLED_VITEST="$(
      node -e 'console.log(require("vitest/package.json").version)' 2>/dev/null || true
    )"
  fi

  echo "Installed Vitest: ${INSTALLED_VITEST:-unknown}"

  if [[ "$INSTALLED_VITEST" =~ ^([0-9]+)\.([0-9]+)\. ]]; then
    V_MAJOR="${BASH_REMATCH[1]}"
    V_MINOR="${BASH_REMATCH[2]}"
    COVERAGE_VERSION="${V_MAJOR}.${V_MINOR}.0"

    echo "Checking matching @vitest/coverage-v8@$V_MAJOR.$V_MINOR.x"
    if npm view "@vitest/coverage-v8@${V_MAJOR}.${V_MINOR}.x" version >/dev/null 2>&1; then
      echo "Installing matching coverage provider: @vitest/coverage-v8@${V_MAJOR}.${V_MINOR}.x"
      npm install -D "@vitest/coverage-v8@${V_MAJOR}.${V_MINOR}.x"
      ok "Matching Vitest coverage provider configured."
    else
      warn "No @vitest/coverage-v8 ${V_MAJOR}.${V_MINOR}.x found in registry."
      echo "Do NOT use --force or --legacy-peer-deps."
      echo "Inspect package-lock/package.json and choose a compatible Vitest/coverage pair."
    fi
  else
    warn "Could not determine installed Vitest version."
  fi
fi

section "npm dependency validation"
if npm install; then
  ok "npm install completed without ERESOLVE."
else
  fail "npm install failed. No peer-dependency bypass was used."
fi

if npm ls vitest @vitest/coverage-v8 --depth=0; then
  ok "Vitest/coverage provider dependency tree is valid."
else
  warn "Vitest coverage dependency tree needs review."
fi

section "Frontend tests with coverage"
FRONTEND_COVERAGE=0
if npm run test:coverage; then
  ok "Frontend coverage suite passed."
  FRONTEND_COVERAGE=1
else
  fail "Frontend coverage suite failed."
fi

section "Backend test collection"
COLLECT_LOG="$REPORT_DIR/backend-collect.log"
if $PY -m pytest backend/tests/ --co -q >"$COLLECT_LOG" 2>&1; then
  ok "Backend test collection succeeded."
else
  warn "Backend test collection has errors. See $COLLECT_LOG"
fi

section "Backend tests with coverage"
BACKEND_TEST_LOG="$REPORT_DIR/backend-tests.log"
if $PY -m pytest backend/tests/ \
    --cov=backend \
    --cov-report=term-missing \
    --cov-report="html:$REPORT_DIR/backend-htmlcov" \
    --cov-report="xml:$REPORT_DIR/backend-coverage.xml" \
    --tb=short 2>&1 | tee "$BACKEND_TEST_LOG"; then
  ok "Backend test suite passed."
else
  fail "Backend test suite has failures/errors."
fi

section "Skipped-test inventory"
SKIP_LOG="$REPORT_DIR/skipped-tests.txt"
if grep -Eio '([0-9]+) skipped' "$BACKEND_TEST_LOG" | tail -1 >"$SKIP_LOG" 2>/dev/null; then
  cat "$SKIP_LOG"
fi
grep -RInE '(^|[^[:alnum:]_])(pytest\.skip|@pytest\.mark\.skip|@pytest\.mark\.skipif|skip\(|xfail\()' \
  backend/tests 2>/dev/null | tee "$REPORT_DIR/skip-source-inventory.txt" || true
grep -RInE '(^|[^[:alnum:]_])(describe\.skip|it\.skip|test\.skip|test\.todo|it\.todo|describe\.todo)' \
  . --exclude-dir=node_modules --exclude-dir=.git --exclude-dir=backend/venv \
  2>/dev/null | tee "$REPORT_DIR/frontend-skip-source-inventory.txt" || true

warn "Skipped tests are inventoried. They must be classified by evidence; this script never silently enables or deletes them."

section "Lint"
LINT_RAN=0
if node -e 'const p=require("./package.json"); process.exit((p.scripts&&p.scripts.lint)?0:1)' 2>/dev/null; then
  LINT_RAN=1
  if npm run lint; then ok "Frontend lint passed."; else fail "Frontend lint failed."; fi
else
  warn "No npm lint script found."
fi

section "TypeScript"
if node -e 'const p=require("./package.json"); process.exit((p.scripts&&p.scripts.typecheck)?0:1)' 2>/dev/null; then
  if npm run typecheck; then ok "TypeScript check passed."; else fail "TypeScript check failed."; fi
else
  if npx tsc --noEmit; then ok "TypeScript check passed via tsc --noEmit."; else fail "TypeScript check failed."; fi
fi

section "Dependency security evidence"
if command -v npm >/dev/null 2>&1; then
  npm audit --omit=dev >"$REPORT_DIR/npm-audit.txt" 2>&1 || warn "npm audit reports vulnerabilities; see $REPORT_DIR/npm-audit.txt"
fi
$PIP list --outdated >"$REPORT_DIR/python-outdated.txt" 2>&1 || true

section "Static security / code review evidence"
if command -v git >/dev/null 2>&1; then
  git status --short >"$REPORT_DIR/git-status.txt" || true
  git diff --check >"$REPORT_DIR/git-diff-check.txt" || warn "Git whitespace/errors detected."
  git ls-files | grep -Ei '(^|/)(\.env|.*secret.*|.*credential.*|.*token.*|id_rsa|.*\.pem$)' \
    >"$REPORT_DIR/sensitive-file-inventory.txt" || true
fi

# Lightweight secret-pattern scan. Findings require manual validation.
grep -RInE \
  'AKIA[0-9A-Z]{16}|BEGIN (RSA|OPENSSH|EC|PRIVATE) KEY|sk-[A-Za-z0-9_-]{20,}|ANTHROPIC_API_KEY[[:space:]]*=' \
  . --exclude-dir=.git --exclude-dir=node_modules --exclude-dir=backend/venv \
  >"$REPORT_DIR/secret-pattern-scan.txt" || true

section "Read-only RuFlo enterprise audit"
RUFLO_OBJECTIVE="$(cat <<'EOF'
Perform a complete READ-ONLY enterprise software audit of this project.

Execute actual frontend tests with coverage and actual backend tests using backend/venv/bin/python.
Analyze every skipped test and classify it as legitimate, configuration-dependent,
missing implementation, broken, or obsolete. Never delete, disable, weaken, or bypass tests.
Do not modify production source code during this initial audit.

Review:
code quality, security, APIs, database, authentication, RBAC, multi-tenant isolation,
AI/LLM security, RAG/vector database security, agent/tool execution and authorization,
prompt injection, secrets, command execution, SSRF, XSS, CSRF, IDOR, privilege escalation,
dependencies/supply chain, performance, architecture, DevOps, configuration, documentation,
and Git/repository hygiene.

Every finding must include evidence, file path and line number where possible, severity,
impact, root cause, and remediation. Do not fabricate test results or coverage.
Produce a consolidated report with PASS/PASS WITH WARNINGS/FAIL and an overall score.
EOF
)"

if npx ruflo@latest hive-mind spawn --objective "$(printf '%s' "$RUFLO_OBJECTIVE")" \
   >"$REPORT_DIR/ruflo-spawn.log" 2>&1; then
  ok "RuFlo audit worker/hive accepted objective."
else
  warn "RuFlo hive spawn command failed; see $REPORT_DIR/ruflo-spawn.log"
fi

if npx ruflo@latest hive-mind status >"$REPORT_DIR/ruflo-status.txt" 2>&1; then
  cat "$REPORT_DIR/ruflo-status.txt"
else
  warn "Could not read RuFlo hive status."
fi

section "Consolidated evidence report"
cat >"$REPORT" <<EOF
# Enterprise Audit Run

- Date: $(date -Is)
- Project: $ROOT
- Report directory: $REPORT_DIR

## Execution status

| Area | Status |
|---|---|
| NumPy import | $( $PY -c 'import numpy; print("PASS " + numpy.__version__)' 2>/dev/null || echo FAIL ) |
| ChromaDB import | $( $PY -c 'import chromadb; print("PASS " + chromadb.__version__)' 2>/dev/null || echo FAIL ) |
| npm install | See run.log |
| Frontend coverage | $([[ "$FRONTEND_COVERAGE" == 1 ]] && echo PASS || echo FAIL) |
| Backend coverage | See backend-tests.log |
| Lint | See run.log |
| TypeScript | See run.log |
| RuFlo audit | See ruflo-spawn.log and ruflo-status.txt |

## Skipped tests

Source inventories:
- backend: skip-source-inventory.txt
- frontend: frontend-skip-source-inventory.txt
- backend execution: backend-tests.log

Each skip must be manually classified from its reason and environment evidence.
No skip was deleted or weakened by this script.

## Dependency evidence

- Python pip check: see run.log
- npm audit: npm-audit.txt
- Python outdated packages: python-outdated.txt
- NumPy/ChromaDB diagnosis: see run.log

## Security evidence

- Secret-pattern scan: secret-pattern-scan.txt
- Git status: git-status.txt
- Git diff check: git-diff-check.txt

## RuFlo

The RuFlo audit was requested in read-only mode. Its final findings must be taken from
the completed hive/worker output; this script does not invent or synthesize findings.

## Result counters

- Script PASS checks: $PASS
- Script WARN checks: $WARN
- Script FAIL checks: $FAIL

## Final decision

This script intentionally does not declare an enterprise PASS based only on infrastructure
checks. Final PASS / PASS WITH WARNINGS / FAIL requires the completed RuFlo audit plus
actual frontend/backend test and coverage evidence.
EOF

section "DONE"
echo "Report: $REPORT"
echo "Logs:   $REPORT_DIR"
echo "RuFlo status: $REPORT_DIR/ruflo-status.txt"
echo "Backend coverage HTML: $REPORT_DIR/backend-htmlcov/index.html"
echo
echo "IMPORTANT: Keep this terminal/output. If RuFlo is still active, monitor with:"
echo "  npx ruflo@latest hive-mind status"
echo
echo "To inspect the report:"
echo "  less '$REPORT'"
