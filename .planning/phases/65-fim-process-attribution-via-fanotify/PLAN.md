---
phase: 65-fim-process-attribution-via-fanotify
plan: 01
type: execute
wave: 1
depends_on: []
files_modified:
  - src/capabilities/fim_fanotify_watcher.rs
  - src/capabilities/fim_process_mapper.rs
  - tests/fim_fanotify_test.rs
  - Cargo.toml
autonomous: true
requirements: [FIM-02]

must_haves:
  truths:
    - The system can successfully capture fanotify file events.
    - The system can extract the Process ID (PID) associated with a file event.
    - A basic process name can be retrieved from a PID.
  artifacts:
    - src/capabilities/fim_fanotify_watcher.rs (Rust module for fanotify interaction)
    - src/capabilities/fim_process_mapper.rs (Rust module for basic PID lookup)
    - tests/fim_fanotify_test.rs (Unit test for fanotify watcher)
  key_links:
    - Successful initialization of the fanotify API and event stream.
    - Accurate extraction of PID and file path from raw fanotify events.
    - Correct mapping of PIDs to process names via /proc filesystem.
    - Robust error handling for ephemeral PIDs and /proc access.
    - End-to-end integration test (`fim_fanotify_test`) passes.
---

<objective>
This plan establishes the foundational components for FIM process attribution:
1. Initialize a fanotify listener to capture file system events.
2. Extract the Process ID (PID) from these events.
3. Implement a basic function to retrieve the command name for a given PID.

Purpose: To create the minimal end-to-end "tracer" path for fanotify event capture and initial process identification, proving the core mechanism works before expanding.
Output: Rust modules for fanotify watching and basic PID-to-name mapping, along with a passing unit test.
</objective>

<execution_context>
@/home/user/enterprise-omni-agent-ai-platform/.claude/gsd-core/workflows/execute-plan.md
@/home/user/enterprise-omni-agent-ai-platform/.claude/gsd-core/templates/summary.md
</execution_context>

<context>
@.planning/PROJECT.md
@.planning/ROADMAP.md
@.planning/STATE.md
@.planning/phases/65-fim-process-attribution-via-fanotify/RESEARCH.md
</context>

<tasks>

<task type="tracer">
  <name>End-to-end Fanotify Event Capture and Basic PID Extraction</name>
  <files>
    src/capabilities/fim_fanotify_watcher.rs
    src/capabilities/fim_process_mapper.rs
    tests/fim_fanotify_test.rs
    Cargo.toml
  </files>
  <action>
    Create a new Rust project or module structure for fanotify integration.
    Implement `fim_fanotify_watcher.rs` to:
    1. Call `fanotify_init` with `FAN_CLOEXEC | FAN_CLASS_CONTENT` flags and `O_RDONLY | O_NONBLOCK`.
    2. Call `fanotify_mark` for a test directory (e.g., `/tmp/fim_test_dir`) to watch for `FAN_OPEN_PERM | FAN_MODIFY | FAN_CLOSE_WRITE` events.
    3. Read fanotify events from the file descriptor.
    4. For each event, extract the `pid` and the file path.
    Implement `fim_process_mapper.rs` with a function `get_process_name(pid: u32) -> Option<String>` that reads `/proc/<pid>/cmdline` or `/proc/<pid>/comm` to get the process name.
    Write a unit test in `tests/fim_fanotify_test.rs` that:
    1. Creates a temporary test directory.
    2. Initializes the fanotify watcher and marks the directory.
    3. Spawns a child process that opens and writes to a file in the marked directory.
    4. Reads the fanotify event, extracts the PID, and verifies `get_process_name` returns a non-empty string.
    5. Ensure `fanotify-rs` crate is added to `Cargo.toml`.
  </action>
  <verify>
    <automated>cargo test --test fim_fanotify_test -- --nocapture</automated>
  </verify>
  <done>
    A minimal Rust program successfully captures a fanotify event, extracts the PID, and retrieves a basic process name from it. The test passes.
  </done>
</task>

<task type="auto">
  <name>Refine Fanotify Watcher for Event Handling</name>
  <files>
    src/capabilities/fim_fanotify_watcher.rs
  </files>
  <action>
    Enhance `src/capabilities/fim_fanotify_watcher.rs`:
    - Create a `FanotifyEvent` struct to represent normalized events (pid, path, event_type).
    - Refactor the event reading loop to parse all relevant `FAN_OPEN_PERM | FAN_MODIFY | FAN_CLOSE_WRITE` flags into a structured `FanotifyEvent`.
    - Implement a method to return a stream or iterator of `FanotifyEvent`s.
    - Add error handling for fanotify API calls and event parsing.
  </action>
  <verify>
    <automated>cargo test --test fim_fanotify_test -- --nocapture</automated>
  </verify>
  <done>
    The `src/capabilities/fim_fanotify_watcher.rs` module can correctly parse multiple fanotify event types into a structured `FanotifyEvent` enum/struct. Existing tests pass.
  </done>
</task>

<task type="auto">
  <name>Basic Process Tree Resolution</name>
  <files>
    src/capabilities/fim_process_mapper.rs
  </files>
  <action>
    Enhance `src/capabilities/fim_process_mapper.rs`:
    - Add a function `get_parent_pid(pid: u32) -> Option<u32>` which reads `/proc/<pid>/status` for `PPid` or `/proc/<pid>/stat` (field 4) to find the parent PID.
    - Create a function `get_process_tree(pid: u32) -> Vec<ProcessInfo>` where `ProcessInfo` is a struct containing `{ pid: u32, name: String }`. This function should recursively call `get_parent_pid` and `get_process_name` to build the full process hierarchy from the given PID up to the root (init process).
    - Ensure robust error handling for non-existent PIDs or `/proc` file access issues.
  </action>
  <verify>
    <automated>cargo test --test fim_fanotify_test::test_process_tree_resolution -- --nocapture</automated>
  </verify>
  <done>
    The `src/capabilities/fim_process_mapper.rs` module can successfully build a basic parent-child process tree for a given PID, returning a list of `ProcessInfo` structs. Existing tests pass.
  </done>
</task>

</tasks>

<threat_model>
## Trust Boundaries

| Boundary | Description |
|----------|-------------|
| Kernel→Fanotify Watcher | Untrusted file events from kernel are processed. |
| Fanotify Watcher→/proc | PID information from kernel is used to query /proc filesystem. |

## STRIDE Threat Register

| Threat ID | Category | Component | Severity | Disposition | Mitigation Plan |
|-----------|----------|-----------|----------|-------------|-----------------|
| T-65-01 | Tampering | Fanotify Events | high | mitigate | Input validation on `pid` and `path` before processing; privilege separation for fanotify watcher (run with minimal necessary capabilities). |
| T-65-02 | Information Disclosure | /proc filesystem reads | medium | mitigate | Restrict access to `fim_process_mapper.rs` to only necessary components; sanitize or abstract raw `/proc` data before external use. |
| T-65-03 | Denial of Service | High event volume/malformed events | high | mitigate | Implement event rate limiting and queueing; robust error handling for malformed kernel events; resource limits on `fim_fanotify_watcher`. |
| T-65-SC | Tampering | Cargo/Rust installs | high | mitigate | slopcheck + blocking human checkpoint for [ASSUMED]/[SUS] crates before `cargo build/run/test`. |
</threat_model>

<verification>
The `fim_fanotify_test` integration test suite successfully captures a file modification event, extracts the PID, traces its parent process chain, and verifies the core fanotify and process mapping functionality. Specifically:
- `cargo test --test fim_fanotify_test::test_fanotify_event_capture` verifies event capture.
- `cargo test --test fim_fanotify_test::test_process_name_resolution` verifies PID to name mapping.
- `cargo test --test fim_fanotify_test::test_process_tree_resolution` verifies parent chain tracing.
</verification>

<success_criteria>
- The `src/capabilities/fim_fanotify_watcher.rs` module compiles successfully.
- The `src/capabilities/fim_process_mapper.rs` module compiles successfully.
- All tests in the `fim_fanotify_test` suite (`cargo test --test fim_fanotify_test`) pass without errors.
- The output of the tests demonstrates successful fanotify event capture, accurate process name retrieval, and correct parent PID tracing for test processes.
</success_criteria>

<output>
Create .planning/phases/65-fim-process-attribution-via-fanotify/65-01-SUMMARY.md when done
</output>
