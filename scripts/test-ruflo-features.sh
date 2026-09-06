#!/usr/bin/env bash
# Smoke-tests every ruflo (claude-flow v3) feature area against this project
# and writes a gap report. Read-only / non-destructive probes only.
set -uo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

BIN="./node_modules/.bin/claude-flow"
if [[ ! -x "$BIN" ]]; then
  BIN="npx --yes @claude-flow/cli@latest"
fi

TIMESTAMP="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
OUT_DIR="${ROOT_DIR}/reports/ruflo"
LOG_DIR="${OUT_DIR}/logs"
REPORT="${OUT_DIR}/ruflo-feature-report.md"
mkdir -p "$LOG_DIR"

PASS=0
FAIL=0
declare -a ROWS=()

run_test() {
  local name="$1" cmd="$2"
  local slug logfile exit_code duration_s start end
  slug="$(echo "$name" | tr '[:upper:] ' '[:lower:]-' | tr -cd 'a-z0-9-')"
  logfile="${LOG_DIR}/${slug}.log"

  start=$(date +%s)
  # shellcheck disable=SC2086
  timeout 45s $BIN $cmd > "$logfile" 2>&1
  exit_code=$?
  end=$(date +%s)
  duration_s=$((end - start))

  local status snippet
  if [[ $exit_code -eq 0 ]]; then
    status="PASS"; PASS=$((PASS+1))
  elif [[ $exit_code -eq 124 ]]; then
    status="TIMEOUT"; FAIL=$((FAIL+1))
  else
    status="FAIL"; FAIL=$((FAIL+1))
  fi
  snippet="$(tail -n 3 "$logfile" | tr '\n' ' ' | sed 's/|/\\|/g' | cut -c1-160)"
  ROWS+=("| ${name} | \`${cmd}\` | ${status} | ${exit_code} | ${duration_s}s | ${snippet} |")
  echo "[${status}] ${name} (${duration_s}s, exit ${exit_code})"
}

echo "== ruflo feature sweep : ${TIMESTAMP} =="
echo "binary: ${BIN}"
echo

# --- PRIMARY COMMANDS ---
run_test "init (dry check)"        "init --help"
run_test "start (help)"            "start --help"
run_test "status"                  "status"
run_test "agent list"              "agent list"
run_test "swarm status"            "swarm status"
run_test "memory search"           "memory search -q test"
run_test "task list"               "task list"
run_test "session list"            "session list"
run_test "mcp status"              "mcp status"
run_test "hooks list"              "hooks list"

# --- ADVANCED COMMANDS ---
run_test "neural status"           "neural status"
run_test "security scan (help)"    "security --help"
run_test "policy status"           "policy status"
run_test "performance metrics"     "performance metrics"
run_test "embeddings status"       "embeddings --help"
run_test "hive-mind status"        "hive-mind status"
run_test "ruvector status"         "ruvector status"
run_test "guidance status"         "guidance --help"
run_test "autopilot status"        "autopilot status"

# --- UTILITY COMMANDS ---
run_test "config list"             "config list"
run_test "doctor"                  "doctor"
run_test "daemon status"           "daemon status"
run_test "completions (help)"      "completions --help"
run_test "migrate (help)"          "migrate --help"
run_test "workflow list"           "workflow list"

# --- ANALYSIS COMMANDS ---
run_test "analyze (help)"          "analyze --help"
run_test "route (help)"            "route --help"
run_test "progress"                "progress"

# --- MANAGEMENT COMMANDS ---
run_test "providers list"          "providers list"
run_test "plugins list"            "plugins list"
run_test "deployment list"         "deployment list"
run_test "claims list"             "claims list"
run_test "issues list"             "issues list"
run_test "update check"            "update check"
run_test "process list"            "process list"
run_test "appliance list"          "appliance list"
run_test "cleanup (dry-run)"       "cleanup --dry-run"

# --- write report ---
{
  echo "# Ruflo Feature Test Report"
  echo
  echo "- Project: enterprise-omni-agent-ai-platform"
  echo "- Run at (UTC): ${TIMESTAMP}"
  echo "- Binary: \`${BIN}\`"
  echo "- Pass: ${PASS}  Fail/Timeout: ${FAIL}  Total: $((PASS+FAIL))"
  echo
  echo "| Feature | Command | Status | Exit | Time | Last output |"
  echo "|---|---|---|---|---|---|"
  for r in "${ROWS[@]}"; do echo "$r"; done
  echo
  echo "## Gaps"
  echo
  any_fail=0
  for r in "${ROWS[@]}"; do
    if echo "$r" | grep -qE '\| (FAIL|TIMEOUT) \|'; then
      any_fail=1
      echo "- ${r}"
    fi
  done
  if [[ $any_fail -eq 0 ]]; then
    echo "None — all probed features returned exit 0."
  fi
  echo
  echo "Full logs: \`reports/ruflo/logs/*.log\`"
} > "$REPORT"

echo
echo "Report written to: ${REPORT}"
echo "PASS=${PASS} FAIL=${FAIL}"
