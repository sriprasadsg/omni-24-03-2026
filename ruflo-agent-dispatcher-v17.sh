#!/usr/bin/env bash
###############################################################################
# RUFLO MULTI-AGENT DISPATCHER v17
# Ruflo v3.38.12 / Claude Code 2.x
# Controlled READ-ONLY repository audit.
###############################################################################

set -u
set -o pipefail

VERSION="v17"
PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$PROJECT_DIR" || exit 1

TIMESTAMP="$(date '+%Y%m%d_%H%M%S')"
RUN_DIR="$PROJECT_DIR/ruflo-agent-dispatcher-v17-${TIMESTAMP}"
AGENTS_DIR="$RUN_DIR/agents"
TASKS_DIR="$RUN_DIR/tasks"
WORKERS_DIR="$RUN_DIR/workers"
LOGS_DIR="$RUN_DIR/logs"
RESULTS_DIR="$RUN_DIR/results"
STATE_DIR="$RUN_DIR/state"

mkdir -p "$AGENTS_DIR" "$TASKS_DIR" "$WORKERS_DIR" "$LOGS_DIR" "$RESULTS_DIR" "$STATE_DIR"

DISPATCHER_LOG="$RUN_DIR/dispatcher.log"
SUMMARY="$RUN_DIR/summary.txt"
REPORT_JSON="$RUN_DIR/report.json"
DEBUG_REPORT="$RUN_DIR/DEBUG-REPORT.md"
PID_FILE="$STATE_DIR/dispatcher.pid"

TIMEOUT_MINUTES="${RUFLO_DISPATCH_TIMEOUT_MINUTES:-30}"
TIMEOUT_SECONDS=$((TIMEOUT_MINUTES * 60))

ROLES=(architect researcher code-analyzer security tester reviewer performance qa)

log() {
    local level="$1"; shift
    printf '[%s] [%s] %s\n' "$(date '+%Y-%m-%d %H:%M:%S')" "$level" "$*" | tee -a "$DISPATCHER_LOG"
}
pass() { log PASS "$*"; }
warn() { log WARN "$*"; }
fail() { log FAIL "$*"; }

cleanup() {
    rm -f "$PID_FILE" 2>/dev/null || true
}
trap cleanup EXIT INT TERM

echo "$$" > "$PID_FILE"

cat > "$DISPATCHER_LOG" <<HEADER
============================================================
RUFLO MULTI-AGENT DISPATCHER $VERSION
============================================================
Project : $PROJECT_DIR
Date    : $(date '+%Y-%m-%d %H:%M:%S %Z')
Host    : $(hostname)
PID     : $$
Report  : $RUN_DIR
Timeout : ${TIMEOUT_MINUTES}m
Mode    : READ-ONLY
============================================================
HEADER

log INFO "Dispatcher started"

check_cmd() {
    local name="$1"
    local path
    path="$(command -v "$name" 2>/dev/null || true)"
    if [[ -n "$path" ]]; then
        pass "$name: $path"
    else
        fail "$name: not found"
    fi
}

for cmd in bash node npm npx git python3 jq; do
    check_cmd "$cmd"
done

CLAUDE_BIN="$(command -v claude 2>/dev/null || true)"
if [[ -z "$CLAUDE_BIN" ]]; then
    fail "Claude Code executable not found"
    exit 1
fi
pass "Claude: $CLAUDE_BIN"
"$CLAUDE_BIN" --version 2>&1 | tee -a "$DISPATCHER_LOG" || true

RUFLO=(npx --no-install claude-flow)
RUFLO_VERSION="$("${RUFLO[@]}" --version 2>&1 || true)"
if [[ "$RUFLO_VERSION" == *"ruflo"* ]]; then
    pass "Ruflo runtime: $RUFLO_VERSION"
else
    fail "Ruflo unavailable"
    printf '%s\n' "$RUFLO_VERSION" | tee -a "$DISPATCHER_LOG"
    exit 1
fi

log INFO "Collecting project snapshot"
{
    echo "Project: $PROJECT_DIR"
    echo "Timestamp: $(date -Is)"
    echo
    echo "Git status:"
    git status --short 2>&1 || true
    echo
    echo "Top-level entries:"
    find . -maxdepth 1 -mindepth 1 -printf '%f\n' 2>/dev/null | sort || true
    echo
    echo "Package manifests:"
    find . -type f \( \
        -name package.json -o -name package-lock.json -o \
        -name requirements.txt -o -name pyproject.toml -o \
        -name go.mod -o -name Cargo.toml -o -name pom.xml \
    \) -not -path './.git/*' -print 2>/dev/null | sort || true
} > "$RUN_DIR/project-snapshot.txt"

declare -A AGENT_ID

log INFO "Spawning Ruflo agents"
for role in "${ROLES[@]}"; do
    spawn_out="$AGENTS_DIR/${role}-spawn.log"
    if "${RUFLO[@]}" agent spawn -t "$role" >"$spawn_out" 2>&1; then
        id="$(grep -Eo 'agent-[0-9]+-[a-z0-9]+' "$spawn_out" | tail -1 || true)"
        if [[ -n "$id" ]]; then
            AGENT_ID["$role"]="$id"
            pass "$role spawned: $id"
        else
            warn "$role spawned but no agent ID was returned"
        fi
    else
        warn "$role spawn failed"
    fi
done

declare -A TASK_TYPE=(
    [architect]=research
    [researcher]=research
    [code-analyzer]=research
    [security]=security
    [tester]=testing
    [reviewer]=review
    [performance]=optimization
    [qa]=testing
)

declare -A TASK_ID

create_task() {
    local role="$1"
    local type="${TASK_TYPE[$role]}"
    local agent="${AGENT_ID[$role]:-}"
    local desc="$2"
    local out="$TASKS_DIR/${role}-task-create.log"

    [[ -z "$agent" ]] && {
        warn "$role has no Ruflo agent ID; task metadata skipped"
        return 0
    }

    if "${RUFLO[@]}" task create -t "$type" -d "$desc" -p high >"$out" 2>&1; then
        local task
        task="$(grep -Eo 'task-[0-9]+-[a-z0-9]+' "$out" | tail -1 || true)"
        if [[ -n "$task" ]]; then
            TASK_ID["$role"]="$task"
            pass "$role task created: $task"
            if "${RUFLO[@]}" task assign "$task" --agent "$agent" >>"$out" 2>&1; then
                pass "$role task assigned to $agent"
            else
                warn "$role task assignment failed; Claude worker still runs"
            fi
        else
            warn "$role task created but task ID was not detected"
        fi
    else
        warn "$role task creation failed; Claude worker still runs"
    fi
}

create_task architect "Read-only architecture analysis. Inspect architecture, components, dependencies and major design risks. Do not modify files."
create_task researcher "Read-only repository research. Map technologies, project structure, configuration, integrations and important implementation patterns. Do not modify files."
create_task code-analyzer "Read-only code analysis. Identify modules, code quality concerns, complexity, duplication, error handling and maintainability risks. Do not modify files."
create_task security "Read-only security audit. Inspect authentication, authorization, secrets, APIs, MCP configuration, dependencies and security risks. Do not modify files."
create_task tester "Read-only testing audit. Inspect tests, configuration, coverage gaps, build/test commands and reliability risks. Do not modify files."
create_task reviewer "Read-only senior code review. Identify correctness, maintainability, architectural and operational risks. Do not modify files."
create_task performance "Read-only performance audit. Inspect likely bottlenecks, frontend/backend performance, I/O, concurrency and scalability risks. Do not modify files."
create_task qa "Read-only QA audit. Inspect build/deployment readiness, observability, configuration quality and major quality risks. Do not modify files."

write_prompt() {
    local role="$1"
    local task="$2"

    cat > "$WORKERS_DIR/${role}.prompt" <<PROMPT
You are the ${role} specialist in a controlled software audit.

Repository: $PROJECT_DIR

STRICT READ-ONLY MODE:
- Do NOT create, edit, delete, rename, move, chmod, chown, install, uninstall, commit, checkout, reset, stash, or otherwise modify any project file.
- Do NOT write reports into the repository.
- Do NOT modify Git state.
- Return complete findings directly in your response.
- Inspect the repository and provide concrete findings; do not merely describe what you would inspect.
- Cite file paths, configuration names, package names, commands, or code locations when available.
- If something cannot be verified, explicitly say so.

TASK:
$task

Final response:
1. Executive summary
2. Findings with severity: Critical/High/Medium/Low/Info
3. Evidence
4. Risk/impact
5. Recommended remediation
6. Validation steps

Do not modify the repository.
PROMPT
}

write_prompt architect "Analyze overall architecture, frontend/backend boundaries, major components, data flow, APIs, external integrations, MCP configuration, deployment architecture and major design risks."
write_prompt researcher "Map repository structure, languages, frameworks, dependencies, configuration files, runtime services, integrations and important implementation patterns."
write_prompt code-analyzer "Analyze code organization, coupling, complexity, duplication, error handling, type safety, dead code indicators, maintainability and technical debt."
write_prompt security "Perform a defensive security audit covering authentication, authorization, secrets, environment/configuration, API exposure, MCP configuration, dependency risk, injection risks, unsafe defaults and sensitive data handling."
write_prompt tester "Audit test strategy: unit/integration/e2e tests, configuration, coverage indicators, missing critical tests, build validation and reliability risks."
write_prompt reviewer "Perform a senior engineering review of correctness, maintainability, architecture, operational readiness, error handling and reliability."
write_prompt performance "Perform a read-only performance/scalability review covering frontend rendering, backend request paths, database/I/O, concurrency, network calls, memory/CPU risks and caching."
write_prompt qa "Perform a read-only QA/release-readiness audit covering build configuration, environment handling, observability, logging, deployment readiness and configuration consistency."

cat > "$RUN_DIR/README.md" <<README
# Ruflo Dispatcher v17

Controlled read-only multi-agent audit.

Ruflo agent/task state is orchestration metadata only.
Actual analysis is performed by Claude Code workers launched with claude -p.
Claude stdout is captured under results/.
README

declare -A WORKER_PID

start_worker() {
    local role="$1"
    local prompt_file="$WORKERS_DIR/${role}.prompt"
    local stdout="$RESULTS_DIR/${role}.md"
    local stderr="$LOGS_DIR/${role}.stderr.log"
    local combined="$LOGS_DIR/${role}.combined.log"
    local rcfile="$STATE_DIR/${role}.exit"

    rm -f "$stdout" "$stderr" "$combined" "$rcfile"

    (
        "$CLAUDE_BIN" -p "$(cat "$prompt_file")" --output-format text >"$stdout" 2>"$stderr"
        rc=$?
        printf '%s\n' "$rc" > "$rcfile"
        {
            echo "===== STDERR ====="
            cat "$stderr" 2>/dev/null || true
            echo
            echo "===== STDOUT ====="
            cat "$stdout" 2>/dev/null || true
        } > "$combined"
        exit "$rc"
    ) &

    WORKER_PID["$role"]=$!
    pass "$role worker started PID=${WORKER_PID[$role]}"
}

log INFO "Starting real Claude Code workers in parallel"
for role in "${ROLES[@]}"; do
    start_worker "$role"
done

log INFO "Monitoring workers (timeout ${TIMEOUT_MINUTES} minutes)"
START_EPOCH="$(date +%s)"

while :; do
    now="$(date +%s)"
    elapsed=$((now - START_EPOCH))
    running=0

    for role in "${ROLES[@]}"; do
        pid="${WORKER_PID[$role]:-}"
        [[ -z "$pid" ]] && continue
        if kill -0 "$pid" 2>/dev/null; then
            running=$((running + 1))
        fi
    done

    (( running == 0 )) && break

    if (( elapsed >= TIMEOUT_SECONDS )); then
        warn "Timeout reached; terminating remaining workers"
        for role in "${ROLES[@]}"; do
            pid="${WORKER_PID[$role]:-}"
            if [[ -n "$pid" ]] && kill -0 "$pid" 2>/dev/null; then
                kill "$pid" 2>/dev/null || true
                sleep 1
                kill -9 "$pid" 2>/dev/null || true
                echo "TIMEOUT" > "$STATE_DIR/${role}.exit"
            fi
        done
        break
    fi

    sleep 5
done

for role in "${ROLES[@]}"; do
    pid="${WORKER_PID[$role]:-}"
    [[ -n "$pid" ]] && wait "$pid" 2>/dev/null || true
done

completed=0
failed=0
timeout=0
malformed=0
empty=0

cat > "$DEBUG_REPORT" <<DEBUG
# RUFLO DISPATCHER v17 DEBUG REPORT

Generated: $(date -Is)

## Worker outcomes

DEBUG

for role in "${ROLES[@]}"; do
    stdout="$RESULTS_DIR/${role}.md"
    stderr="$LOGS_DIR/${role}.stderr.log"
    rcfile="$STATE_DIR/${role}.exit"
    rc="$(cat "$rcfile" 2>/dev/null || echo UNKNOWN)"
    bytes="$(wc -c < "$stdout" 2>/dev/null || echo 0)"
    status="FAILED"

    if [[ "$rc" == "TIMEOUT" ]]; then
        status="TIMEOUT"
        timeout=$((timeout + 1))
    elif [[ "$rc" == "0" ]] && (( bytes > 0 )); then
        status="COMPLETED"
        completed=$((completed + 1))
    elif (( bytes == 0 )); then
        status="FAILED_EMPTY"
        failed=$((failed + 1))
        empty=$((empty + 1))
    else
        status="FAILED($rc)"
        failed=$((failed + 1))
    fi

    if grep -qiE 'API Error:.*empty or malformed response|HTTP 200.*malformed|proxy or gateway intercepting' "$stdout" "$stderr" 2>/dev/null; then
        malformed=$((malformed + 1))
        status="FAILED_PROXY_OR_GATEWAY"
    fi

    log INFO "$role => $status (${bytes} bytes)"

    {
        echo "### $role"
        echo "- Status: $status"
        echo "- Exit: $rc"
        echo "- Output bytes: $bytes"
        echo "- Stdout: $stdout"
        echo "- Stderr: $stderr"
        echo
    } >> "$DEBUG_REPORT"
done

log INFO "Collecting diagnostics"
{
    echo "===== RUFLO AGENTS ====="
    "${RUFLO[@]}" agent list 2>&1 || true
    echo
    echo "===== RUFLO TASKS ====="
    "${RUFLO[@]}" task list --all 2>&1 || true
    echo
    echo "===== RUFLO AGENT METRICS ====="
    "${RUFLO[@]}" agent metrics 2>&1 || true
    echo
    echo "===== RUFLO STATUS ====="
    "${RUFLO[@]}" status 2>&1 || true
} > "$RUN_DIR/ruflo-diagnostics.txt"

cat > "$SUMMARY" <<SUMMARY
============================================================
RUFLO MULTI-AGENT DISPATCHER v17 SUMMARY
============================================================
Project        : $PROJECT_DIR
Run directory  : $RUN_DIR
Configured     : ${#ROLES[@]}
Completed      : $completed
Failed         : $failed
Timeout        : $timeout
Malformed API  : $malformed
Empty output   : $empty

Ruflo agent/task state is orchestration metadata only.
Claude stdout is the evidence of actual worker execution.
No worker was instructed to modify repository files.

Results:
SUMMARY

for role in "${ROLES[@]}"; do
    printf '%-16s %s\n' "$role" "$RESULTS_DIR/${role}.md" >> "$SUMMARY"
done

if (( malformed > 0 )); then
    cat >> "$SUMMARY" <<WARNING

WARNING:
One or more Claude workers received an empty/malformed HTTP 200 response.
This points to a Claude API/proxy/gateway response problem rather than
a Ruflo task-assignment problem.

Inspect:
$LOGS_DIR
WARNING
fi

if command -v jq >/dev/null 2>&1; then
    jq -n \
        --arg version "$VERSION" \
        --arg project "$PROJECT_DIR" \
        --arg run "$RUN_DIR" \
        --arg timestamp "$(date -Is)" \
        --argjson configured "${#ROLES[@]}" \
        --argjson completed "$completed" \
        --argjson failed "$failed" \
        --argjson timeout "$timeout" \
        --argjson malformed "$malformed" \
        --argjson empty "$empty" \
        --argjson readonly true \
        '{
          version:$version,
          project:$project,
          run_directory:$run,
          timestamp:$timestamp,
          read_only:$readonly,
          configured:$configured,
          completed:$completed,
          failed:$failed,
          timeout:$timeout,
          malformed_api_responses:$malformed,
          empty_outputs:$empty
        }' > "$REPORT_JSON"
else
    printf '{"version":"%s","project":"%s","run_directory":"%s"}\n' \
        "$VERSION" "$PROJECT_DIR" "$RUN_DIR" > "$REPORT_JSON"
fi

cat <<FINAL

============================================================
RUFLO MULTI-AGENT DISPATCH COMPLETE
============================================================
Configured : ${#ROLES[@]}
Completed  : $completed
Failed     : $failed
Timeout    : $timeout
Malformed  : $malformed
Empty      : $empty

Run directory : $RUN_DIR
Summary       : $SUMMARY
Debug         : $DEBUG_REPORT
JSON          : $REPORT_JSON
Results       : $RESULTS_DIR
Live log      : $DISPATCHER_LOG
Diagnostics   : $RUN_DIR/ruflo-diagnostics.txt
============================================================
FINAL

exit 0
