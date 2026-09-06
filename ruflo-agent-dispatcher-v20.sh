#!/usr/bin/env bash
set -u
set -o pipefail

VERSION="v20"
PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$PROJECT_DIR" || exit 1
TIMESTAMP="$(date '+%Y%m%d_%H%M%S')"
RUN_DIR="$PROJECT_DIR/ruflo-agent-dispatcher-${VERSION}-${TIMESTAMP}"
LOGS_DIR="$RUN_DIR/logs"; RESULTS_DIR="$RUN_DIR/results"; STATE_DIR="$RUN_DIR/state"
mkdir -p "$LOGS_DIR" "$RESULTS_DIR" "$STATE_DIR"
DISPATCHER_LOG="$RUN_DIR/dispatcher.log"
SUMMARY="$RUN_DIR/summary.txt"
REPORT_JSON="$RUN_DIR/report.json"
DEBUG_REPORT="$RUN_DIR/DEBUG-REPORT.md"

WORKER_TIMEOUT="${WORKER_TIMEOUT:-420}"
WORKER_RETRIES="${WORKER_RETRIES:-2}"
MIN_RESULT_BYTES="${MIN_RESULT_BYTES:-250}"
MAX_TURNS="${MAX_TURNS:-8}"

log(){ printf '[%s] [%s] %s\n' "$(date '+%Y-%m-%d %H:%M:%S')" "$1" "${*:2}" | tee -a "$DISPATCHER_LOG"; }
info(){ log INFO "$@"; }; pass(){ log PASS "$@"; }; warn(){ log WARN "$@"; }; fail(){ log FAIL "$@"; }

cat > "$RUN_DIR/prompts.json" <<'JSON'
{
"architect":"You are the architecture reviewer. Inspect the current repository directly in READ-ONLY mode. Do not create, edit, delete, rename, or modify files. Analyze overall architecture, frontend, backend, services, databases, APIs, integrations, authentication, data flow, deployment architecture, and major architectural risks. Return concise factual findings directly to stdout.",
"researcher":"You are the repository researcher. Inspect the current repository directly in READ-ONLY mode. Do not modify files. Identify project type, languages, frameworks, dependencies, infrastructure, configuration, major components, and external services. Return factual findings directly to stdout.",
"code-analyzer":"You are the code quality reviewer. Inspect the repository directly in READ-ONLY mode. Do not modify files. Analyze organization, duplication, coupling, error handling, maintainability, type safety, dead code, and architectural smells. Return concise findings with paths where useful.",
"security":"You are the security reviewer. Inspect the current repository directly in READ-ONLY mode. Do not modify files. Review authentication, authorization, secrets exposure, API security, injection risks, dependency risks, tenant isolation, filesystem access, command execution, XSS, SSRF, and insecure configuration. Return severity and affected paths where identifiable.",
"tester":"You are the testing reviewer. Inspect the repository directly in READ-ONLY mode. Do not modify files. Identify test frameworks, coverage structure, missing tests, CI test execution, flaky-risk areas, and important untested behavior. Return concise factual findings.",
"reviewer":"You are the senior engineering reviewer. Inspect the repository directly in READ-ONLY mode. Do not modify files. Review architecture, implementation quality, security, operational readiness, maintainability, and major design risks. Return prioritized findings and recommendations.",
"performance":"You are the performance reviewer. Inspect the repository directly in READ-ONLY mode. Do not modify files. Identify likely frontend, backend, database, API, concurrency, caching, memory, I/O, and scalability bottlenecks. Return evidence-based findings.",
"qa":"You are the QA and production-readiness reviewer. Inspect the repository directly in READ-ONLY mode. Do not modify files. Assess reliability, error handling, observability, deployment readiness, configuration, recovery, validation, and release risks. Return concise prioritized findings."
}
JSON

extract_result(){
python3 - "$1" <<'PY'
import json,sys
raw=open(sys.argv[1],encoding="utf-8",errors="replace").read().strip()
try:
    x=json.loads(raw)
except Exception:
    x=None
if isinstance(x,dict):
    r=x.get("result")
    if isinstance(r,str): print(r); raise SystemExit
print("")
PY
}

classify(){
  local f="$1" rc="$2" s
  s="$(cat "$f" 2>/dev/null || true)"
  if [ "$rc" -eq 124 ] || [ "$rc" -eq 137 ]; then echo TIMEOUT
  elif grep -qiE 'Prompt is too long|Request too large' <<<"$s"; then echo PROMPT_TOO_LONG
  elif grep -qiE 'empty or malformed response|malformed response|HTTP 200' <<<"$s"; then echo GATEWAY_ERROR
  elif [ "$rc" -ne 0 ]; then echo CLI_ERROR
  else echo INVALID_RESULT
  fi
}

valid(){
  [ -s "$1" ] || return 1
  [ "$(wc -c < "$1" | tr -d ' ')" -ge "$MIN_RESULT_BYTES" ] || return 1
  ! grep -qiE '^(Ready\.?|What task\??|How can I help\??|Caveman mode active)' "$1"
}

worker(){
  local role="$1" prompt raw out err meta attempt rc status bytes
  prompt="$(python3 - "$role" "$RUN_DIR/prompts.json" <<'PY'
import json,sys
print(json.load(open(sys.argv[2]))[sys.argv[1]])
PY
)"
  raw="$LOGS_DIR/$role.raw"; out="$RESULTS_DIR/$role.md"; err="$LOGS_DIR/$role.stderr.log"; meta="$STATE_DIR/$role.json"
  info "$role worker starting"

  for attempt in $(seq 1 "$((WORKER_RETRIES+1))"); do
    : > "$raw"; : > "$err"; : > "$out"
    set +e
    timeout --kill-after=10s "$WORKER_TIMEOUT" \
      claude -p --bare --permission-mode plan \
      --disallowedTools "Edit" "Write" "NotebookEdit" "Bash" \
      --max-turns "$MAX_TURNS" --output-format json "$prompt" \
      >"$raw" 2>"$err"
    rc=$?
    set -e 2>/dev/null || true

    if [ "$rc" -eq 0 ]; then extract_result "$raw" > "$out"; else cat "$raw" > "$out"; fi
    if valid "$out"; then
      bytes="$(wc -c < "$out" | tr -d ' ')"
      printf '{"role":"%s","status":"SUCCESS","attempt":%s,"exit_code":%s,"bytes":%s}\n' "$role" "$attempt" "$rc" "$bytes" > "$meta"
      pass "$role completed (${bytes} bytes, attempt $attempt)"
      return 0
    fi

    status="$(classify "$raw" "$rc")"
    bytes="$(wc -c < "$out" 2>/dev/null | tr -d ' ')"
    warn "$role attempt $attempt failed: $status (rc=$rc, result=${bytes} bytes)"
    [ "$status" = PROMPT_TOO_LONG ] && break
    [ "$attempt" -lt "$((WORKER_RETRIES+1))" ] && sleep "$((attempt*5))"
  done

  {
    echo "[WORKER FAILED]"
    echo "Failure classification: ${status:-UNKNOWN}"
    echo
    echo "Raw CLI output:"
    cat "$raw" 2>/dev/null || true
    echo
    echo "STDERR:"
    cat "$err" 2>/dev/null || true
  } > "$out"
  bytes="$(wc -c < "$out" | tr -d ' ')"
  printf '{"role":"%s","status":"%s","attempt":%s,"exit_code":%s,"bytes":%s}\n' "$role" "${status:-UNKNOWN}" "$attempt" "$rc" "$bytes" > "$meta"
  fail "$role failed: ${status:-UNKNOWN}"
  return 1
}

info "Ruflo Dispatcher $VERSION started"
info "Project: $PROJECT_DIR"
info "Run directory: $RUN_DIR"

for bin in bash node npm npx git python3 jq; do
  p="$(command -v "$bin" 2>/dev/null || true)"
  [ -n "$p" ] && pass "$bin: $p" || { fail "$bin unavailable"; exit 1; }
done

CLAUDE="$(command -v claude 2>/dev/null || true)"
[ -n "$CLAUDE" ] || { fail "Claude unavailable"; exit 1; }
pass "Claude: $CLAUDE"
CLAUDE_VERSION="$("$CLAUDE" --version 2>&1 | head -1)"
info "Claude version: $CLAUDE_VERSION"

CF_VERSION="$(node -p "try{require('./node_modules/claude-flow/package.json').version}catch(e){''}" 2>/dev/null || true)"
if [ -n "$CF_VERSION" ]; then info "Local claude-flow package: $CF_VERSION"; else warn "claude-flow unavailable; direct Claude mode only"; fi

{
 echo "RUFLO DISPATCHER $VERSION"
 echo "Project: $PROJECT_DIR"
 echo "Run: $RUN_DIR"
 echo "Workers: 8"
 echo
} > "$SUMMARY"

roles=(architect researcher code-analyzer security tester reviewer performance qa)
declare -A pids
for role in "${roles[@]}"; do
  worker "$role" &
  pids["$role"]=$!
done

completed=0; failed=0; timeouts=0; prompts=0; gateways=0
for role in "${roles[@]}"; do
  wait "${pids[$role]}" || true
  meta="$STATE_DIR/$role.json"
  status="$(jq -r '.status // "UNKNOWN"' "$meta" 2>/dev/null || echo UNKNOWN)"
  case "$status" in
    SUCCESS) completed=$((completed+1));;
    TIMEOUT) timeouts=$((timeouts+1)); failed=$((failed+1));;
    PROMPT_TOO_LONG) prompts=$((prompts+1)); failed=$((failed+1));;
    GATEWAY_ERROR) gateways=$((gateways+1)); failed=$((failed+1));;
    *) failed=$((failed+1));;
  esac
done

python3 - "$REPORT_JSON" "$PROJECT_DIR" "$RUN_DIR" "$completed" "$failed" "$timeouts" "$prompts" "$gateways" "${roles[@]}" <<'PY'
import json,sys,os
out,project,run,completed,failed,timeouts,prompts,gateway,*roles=sys.argv[1:]
workers=[]
for r in roles:
 p=os.path.join(run,"state",r+".json")
 workers.append(json.load(open(p)) if os.path.exists(p) else {"role":r,"status":"UNKNOWN"})
json.dump({"version":"v20","project":project,"run":run,"completed":int(completed),
"failed":int(failed),"timeouts":int(timeouts),"prompt_too_long":int(prompts),
"gateway_errors":int(gateway),"workers":workers},open(out,"w"),indent=2)
PY

{
 echo "Completed : $completed"
 echo "Failed    : $failed"
 echo "Timeout   : $timeouts"
 echo "PromptTooLong : $prompts"
 echo "GatewayErrors : $gateways"
 echo
 echo "Worker status:"
 for role in "${roles[@]}"; do
   printf '  %-16s %s\n' "$role" "$(jq -r '.status // "UNKNOWN"' "$STATE_DIR/$role.json" 2>/dev/null || echo UNKNOWN)"
 done
} >> "$SUMMARY"

{
 echo "# Dispatcher v20 Debug Report"
 echo
 echo "- Claude: $CLAUDE_VERSION"
 echo "- claude-flow: ${CF_VERSION:-unavailable}"
 echo
 for role in "${roles[@]}"; do
   echo "## $role"
   echo
   cat "$RESULTS_DIR/$role.md" 2>/dev/null || echo "No result."
   echo
 done
} > "$DEBUG_REPORT"

info "Dispatcher complete: completed=$completed failed=$failed timeout=$timeouts"
echo
echo "============================================================"
echo "RUFLO MULTI-AGENT DISPATCHER $VERSION COMPLETE"
echo "============================================================"
echo "Run directory : $RUN_DIR"
echo "Summary       : $SUMMARY"
echo "Debug         : $DEBUG_REPORT"
echo "JSON          : $REPORT_JSON"
echo "Results       : $RESULTS_DIR"
echo "Live log      : $DISPATCHER_LOG"
echo "Completed     : $completed"
echo "Failed        : $failed"
echo "Timeout       : $timeouts"
echo "Prompt errors : $prompts"
echo "Gateway errors: $gateways"
echo "============================================================"

[ "$completed" -gt 0 ]
