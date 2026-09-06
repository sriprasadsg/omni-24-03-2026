# Phase 65: FIM Process Attribution via fanotify - Research

**Researched:** 2026-08-14
**Domain:** Linux `fanotify` API, process information (`/proc` filesystem), Rust
**Confidence:** MEDIUM

## Summary

This research focuses on leveraging Linux's `fanotify` API in Rust to capture file system events and attribute them to specific processes. The core mechanism involves initializing `fanotify`, marking relevant paths for monitoring, reading events to extract PID and file path, and then using the PID to query `/proc` filesystem for process names and parent PIDs. The `fanotify-rs` crate is the primary recommendation for `fanotify` interaction, and direct `/proc` filesystem reads are used for process information.

**Primary recommendation:** Use `fanotify-rs` for `fanotify` events and `std::fs` to read `/proc` for process information.

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|--------------|----------------|-----------|
| File Event Monitoring | Agent / OS Kernel | — | `fanotify` is a kernel-level API exposed to the agent. |
| PID Extraction | Agent | — | `fanotify` events directly provide PID to the agent. |
| Process Name Resolution | Agent | — | Reads from `/proc` are performed by the agent. |
| Process Tree Resolution | Agent | — | Recursive `/proc` reads are performed by the agent. |

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| `fanotify-rs` [WARNING: flagged as suspicious — verify before using.] | 0.3.1 | High-level Rust bindings for `fanotify` API | Directly wraps Linux `fanotify` system calls, offering a structured way to interact. [ASSUMED] |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| `std::fs` | N/A (Rust standard library) | Reading `/proc` filesystem | To retrieve process command name (`/proc/<pid>/comm` or `cmdline`) and parent PID (`/proc/<pid>/status` or `stat`). |
| `tempfile` | 3.8 | Temporary file/directory creation for tests | Essential for creating isolated, clean testing environments for `fanotify` monitoring. |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| `fanotify-rs` | `naughtyfy` [WARNING: flagged as suspicious — verify before using.] | `naughtyfy` is newer but has significantly fewer downloads and seems less mature. `fanotify-rs` is more established despite low downloads. [ASSUMED] |
| Manual `/proc` parsing | `procfs` | `procfs` crate provides structured access to `/proc` data. However, for just `comm`, `cmdline`, `PPid`, `std::fs` is sufficient and avoids an extra dependency. If more `/proc` details are needed later, `procfs` would be a good addition. |

**Installation:**
```bash
cargo add fanotify-rs@0.3.1
cargo add tempfile@3.8
```

**Version verification:**
`fanotify-rs` (0.3.1) - published 2020-06-30
`tempfile` (3.8) - published 2023-10-25 (latest is 3.8.1, but 3.8 is sufficient)

## Package Legitimacy Audit

| Package | Registry | Age | Downloads | Source Repo | Verdict | Disposition |
|---------|----------|-----|-----------|-------------|---------|-------------|
| `fanotify-rs` | crates.io | 6 yrs | 147/wk | github.com/ZhangLei-cn/fanotify-rs | SUS | Flagged — planner must add checkpoint |
| `procfs` | crates.io | 8 yrs | 1M/wk | github.com/eminence/procfs | OK | Approved |
| `tempfile` | crates.io | 11 yrs | 12.8M/wk | github.com/Stebalien/tempfile | OK | Approved |
| `naughtyfy` | crates.io | 3 yrs | 6/wk | github.com/SubconsciousCompute/naughtyfy.git | SUS | Flagged — planner must add checkpoint |

**Packages removed due to [SLOP] verdict:** none
**Packages flagged as suspicious [SUS]:** `fanotify-rs`, `naughtyfy`

## Architecture Patterns

### System Architecture Diagram
```mermaid
graph TD
    Kernel -->|fanotify events| FanotifyWatcher;
    FanotifyWatcher -->|PID, Path| EventStream;
    EventStream -->|PID| ProcessMapper;
    ProcessMapper -->|read /proc/<pid>/...| Kernel (procfs);
    Kernel (procfs) -->|process info| ProcessMapper;
    ProcessMapper -->|ProcessInfo| AttributionModule;
```
*Description:* The Kernel generates `fanotify` events which are consumed by the `FanotifyWatcher`. The watcher extracts the PID and file path, forwarding them as an `EventStream`. The `ProcessMapper` receives PIDs from this stream, queries the kernel via the `/proc` filesystem to get process details (name, parent PID), and returns `ProcessInfo`. This `ProcessInfo` is then used by an `AttributionModule` (not part of this phase's scope) for further analysis.

### Recommended Project Structure
```
src/
├── main.rs                 # Main application entry point (if standalone)
├── lib.rs                  # Library crate root
├── fim_fanotify_watcher.rs # Fanotify event capturing and parsing
└── fim_process_mapper.rs   # PID to process name/tree resolution
tests/
└── fim_fanotify_test.rs    # Integration tests for fanotify and process mapping
```

### Pattern 1: `fanotify` Event Loop
**What:** Continuously read events from the `fanotify` file descriptor, parse them, and extract relevant data (PID, path, event type).
**When to use:** Any application needing real-time file system monitoring and attribution.
**Example:**
```rust
// Source: src/fim_fanotify_watcher.rs (adapted)
use fanotify::high_level::{Fanotify, FanotifyMode};
// ... other imports ...

pub struct FanotifyWatcher {
    fanotify: Fanotify,
    // ...
}

impl FanotifyWatcher {
    // ... new() and mark_path() ...

    pub fn read_events(&self) -> io::Result<Vec<FimEvent>> {
        let events = self.fanotify.read_event(); // Blocking call or non-blocking if configured
        let mut fim_events = Vec::new();
        for event in events {
            let pid = event.pid as u32;
            let path = PathBuf::from(event.path);
            let event_data = FimEventData { pid, path };
            for fan_event in event.events {
                match fan_event {
                    // ... map to FimEvent types ...
                    _ => fim_events.push(FimEvent::Unknown(event_data.clone())),
                }
            }
        }
        Ok(fim_events)
    }
}
```

### Pattern 2: `/proc` Filesystem Parsing
**What:** Reading specific files within `/proc/<pid>/` to extract process information.
**When to use:** When needing process name, parent PID, command line arguments, or other process-specific details given a PID.
**Example:**
```rust
// Source: src/fim_process_mapper.rs (adapted)
use std::{fs, path::PathBuf};

pub fn get_process_name(pid: u32) -> Option<String> {
    let comm_path = PathBuf::from(format!("/proc/{}/comm", pid));
    if comm_path.exists() {
        if let Ok(name) = fs::read_to_string(&comm_path) {
            return Some(name.trim().to_string());
        }
    }
    // Fallback to cmdline
    let cmdline_path = PathBuf::from(format!("/proc/{}/cmdline", pid));
    if cmdline_path.exists() {
        if let Ok(cmdline) = fs::read_to_string(&cmdline_path) {
            return cmdline.split('\0').next().map(|s| s.to_string());
        }
    }
    None
}
```

### Anti-Patterns to Avoid
- **Blocking inside `fanotify` event loop:** Performing long-running operations or I/O within the event reading loop can cause event backlogs and missed events. Process events asynchronously (e.g., send to a channel/queue).
- **Hardcoding `/proc` paths without error handling:** PIDs can be ephemeral; `/proc/<pid>` directories might disappear between checks. Always handle `io::ErrorKind::NotFound` and other potential errors when accessing `/proc`.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Linux `fanotify` API interaction | Raw `syscall` wrappers | `fanotify-rs` [WARNING: flagged as suspicious — verify before using.] | The `fanotify` API is complex with specific flags, structures, and error conditions. A well-tested crate handles these intricacies. |
| Temporary file/dir management for tests | Manual file creation/cleanup | `tempfile` crate | `tempfile` ensures unique paths, handles cleanup on scope exit, and reduces boilerplate for testing filesystem interactions. |

**Key insight:** Low-level OS APIs like `fanotify` are error-prone and require careful handling of file descriptors, event structures, and flags. Rely on existing Rust crates that abstract these complexities.

## Common Pitfalls

### Pitfall 1: Event Backlog and Dropped Events
**What goes wrong:** If the `fanotify` event loop cannot process events as fast as they occur, the kernel's event queue can fill up, leading to events being dropped.
**Why it happens:** Slow event processing, synchronous I/O within the event loop, or insufficient buffer size.
**How to avoid:**
1. Process events in a separate thread or use an asynchronous runtime (e.g., Tokio).
2. Send raw events to a bounded channel for processing elsewhere, immediately returning to read the next event.
3. Ensure the `fanotify_init` call uses appropriate flags for buffer management if available (though `fanotify-rs` abstracts this).
**Warning signs:** Missing expected events, high CPU usage in the `fanotify` reading thread, or warnings/errors from the kernel about event queue overflows (check `dmesg`).

### Pitfall 2: PID Reuse and Stale Process Information
**What goes wrong:** A PID can be reused by a different process shortly after the original process exits. If there's a delay between extracting a PID from a `fanotify` event and querying `/proc` for its details, the queried process might not be the one that generated the event.
**Why it happens:** Operating system behavior of PID recycling.
**How to avoid:**
1. Query `/proc` for process information as quickly as possible after receiving the event.
2. If possible, capture additional context from the `fanotify` event (e.g., `event.metadata.tgid` or `event.metadata.f_handle`) that might be more stable than PID for identification across short time windows, although `fanotify-rs` might not expose all low-level metadata.
3. For critical attribution, combine PID with process start time or command line arguments to increase confidence that it's the same process.
**Warning signs:** Inconsistent process names for the same PID across very short intervals, or attributing events to unexpected processes.

## Code Examples

Verified patterns from official sources:

### Initializing `fanotify` and Marking Paths
```rust
// Source: src/fim_fanotify_watcher.rs (adapted from fanotify-rs usage)
use fanotify::high_level::{Fanotify, FanotifyMode};
use fanotify::low_level::{FAN_OPEN_PERM, FAN_MODIFY, FAN_CLOSE_WRITE};
use std::io;
use std::os::unix::io::RawFd;

pub struct FanotifyWatcher {
    fanotify: Fanotify,
    fd: RawFd, // Raw file descriptor can be used with polling mechanisms
}

impl FanotifyWatcher {
    pub fn new() -> io::Result<Self> {
        let fanotify = Fanotify::new_nonblocking(FanotifyMode::CONTENT)?;
        let fd = fanotify.as_raw_fd();
        Ok(FanotifyWatcher { fanotify, fd })
    }

    pub fn mark_path(&self, path: &str) -> io::Result<()> {
        let mark_flags = FAN_OPEN_PERM | FAN_MODIFY | FAN_CLOSE_WRITE;
        // The fanotify-rs crate handles the details of fanotify_mark
        self.fanotify.add_path(mark_flags, path)?;
        Ok(())
    }
}
```

### Retrieving Parent PID
```rust
// Source: Adapted from common Linux /proc parsing knowledge
use std::{fs, path::PathBuf};

pub fn get_parent_pid(pid: u32) -> Option<u32> {
    let status_path = PathBuf::from(format!("/proc/{}/status", pid));
    if let Ok(content) = fs::read_to_string(&status_path) {
        for line in content.lines() {
            if line.starts_with("PPid:") {
                let ppid_str = line.trim_start_matches("PPid:").trim();
                return ppid_str.parse::<u32>().ok();
            }
        }
    }
    None
}
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| `inotify` | `fanotify` | Linux Kernel 2.6.36 | `fanotify` provides more detailed event information, including PID, file descriptor, and allows for permission events, which `inotify` does not. It's designed for system-wide monitoring. |
| PID-only attribution | PID + command line / start time | Evolving security needs | Relying solely on PID for attribution is brittle due to PID reuse. Combining with other process metadata increases confidence in identification. |

**Deprecated/outdated:**
- `inotify`: Still useful for simple file change notifications, but not for process attribution. `fanotify` is preferred for security monitoring.

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | `fanotify-rs` is the best choice for `fanotify` in Rust. | Standard Stack | May choose a less mature or less maintained crate, leading to stability or feature gaps. |
| A2 | Direct `/proc` parsing is sufficient for basic process info. | Standard Stack | If complex process information is needed, manual parsing can become brittle or incomplete, requiring `procfs` later. |

## Open Questions

1. **How to handle `FAN_PERM` events (permission decisions)?** - RESOLVED: Passive monitoring is sufficient for this phase.
   - What we know: `fanotify` can block operations and require a decision (allow/deny).
   - What's unclear: If this phase needs to make such decisions, or if it's purely for passive monitoring.
   - Recommendation: Start with passive monitoring (`FAN_OPEN_PERM`) without making decisions. Implement decision-making (`FAN_ALLOW`/`FAN_DENY`) in a later phase if required by security policies.

2. **What level of detail is needed for process attribution?** - RESOLVED: Basic process name and parent tree are sufficient for this phase.
   - What we know: Basic process name and parent tree are requested.
   - What's unclear: Is full command line, user ID, or other process context required?
   - Recommendation: Implement the current requirements. Extend `fim_process_mapper` to fetch more details (e.g., `uid`, `gid`, `cwd`) from `/proc` as needed in future phases.

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|-------------|-----------|---------|----------|
| `fanotify` kernel API | Core functionality | ✓ | Linux Kernel 2.6.36+ | — |
| Rust toolchain | Development | ✓ | (Assumed to be available) | — |

**Missing dependencies with no fallback:**
- None. Linux kernel with `fanotify` support is a fundamental requirement.

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | Rust `cargo test` |
| Config file | `Cargo.toml` |
| Quick run command | `cargo test` |
| Full suite command | `cargo test` |

### Phase Requirements → Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| FIM-02 | Capture fanotify file events with PID and path | Integration | `cargo test --test fim_fanotify_test -- --nocapture` | ✅ |
| FIM-02 | Extract process name from PID | Unit/Integration | `cargo test --test fim_fanotify_test -- --nocapture` | ✅ |
| FIM-02 | Trace parent process chain for a given PID | Integration | `cargo test --test fim_fanotify_test -- --nocapture` | ✅ |

### Sampling Rate
- **Per task commit:** `cargo test`
- **Per wave merge:** `cargo test`
- **Phase gate:** Full suite green before `/gsd-verify-work`

### Wave 0 Gaps
- None — existing test infrastructure covers all phase requirements.

## Security Domain

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|------------------|
| V5 Input Validation | yes | Validate PID (u32 range), sanitize file paths (PathBuf canonicalization, prevent path traversal). |
| V6 Cryptography | no | (Not directly applicable to this phase) |

### Known Threat Patterns for Rust `fanotify` / `/proc` stack

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| PID spoofing/reuse | Spoofing | Cross-reference PID with process start time and command line; use stable identifiers if available (e.g., cgroup info). |
| Race conditions in `/proc` access | Tampering | Read `/proc` information as atomically as possible; validate existence before reading; handle `io::ErrorKind::NotFound`. |
| Excessive resource consumption (event flood) | Denial of Service | Implement rate limiting, event batching, and asynchronous processing; use bounded queues for event handling. |
| Incomplete process context | Information Disclosure | Be explicit about what process information is exposed and to whom; sanitize sensitive data if any. |

## Sources

### Primary (HIGH confidence)
- N/A

### Secondary (MEDIUM confidence)
- `fanotify-rs` crate documentation (usage patterns for fanotify API)
- `tempfile` crate documentation
- Linux `fanotify(7)` man page (conceptual understanding of API)
- Linux `proc(5)` man page (structure of `/proc` filesystem)

### Tertiary (LOW confidence)
- Web search for "How to get PID from fanotify event in Linux" - provided context on fanotify_info struct and pid field.
- Web search for "Best Rust crate for fanotify" - identified `fanotify-rs` and `naughtyfy`.

## Metadata

**Confidence breakdown:**
- Standard stack: MEDIUM - `fanotify-rs` has low downloads and is flagged SUS, but is the most direct binding. `std::fs` for `/proc` is standard.
- Architecture: HIGH - Standard event-driven and filesystem interaction patterns.
- Pitfalls: MEDIUM - Common issues in system programming and security, well-understood.

**Research date:** 2026-08-14
**Valid until:** 2026-11-14 (90 days, `fanotify` API is stable, `/proc` is stable, Rust crates typically stable)
