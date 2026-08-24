# Phase 66 - User Acceptance Testing (UAT)
## Full YARA-rule engine for native scan

**Superseded 2026-08-24.** The two tests originally recorded here exercised `run_yara_scan`
(`agent-rust/src/caps.rs:309` / `agent-rust/src/yara_scan.rs:40`) — the legacy, unshipped Rust
tree. That function does not exist in `agent-install/omni-agent-rs/`, the canonical tree every
installer actually packages, and the recorded output shape (`{"status":"detected","matches":[...]}`)
doesn't even match the shipped engine's verdict shape (`{"verdict","confidence","matched","sha256"}`).
Both original results are void as acceptance evidence for the shipped agent — see
`66-VERIFICATION.md` gap 3 for the full finding. Replaced below with evidence against the
shipped path (`agent-install/omni-agent-rs/src/capabilities/security_scan.rs`).

### Test 1: A hex-wildcard YARA pattern compiles and matches (real YARA semantics, not literal substring matching)
- **Description:** `compiles_and_matches_hex_wildcard_pattern` — compiles a rule with a hex byte
  pattern containing a wildcard nibble (`{ 4D 5A ?? 00 03 00 00 00 }`), scans matching and
  non-matching byte buffers.
- **Command:** `cargo test --lib security_scan` (in `agent-install/omni-agent-rs`)
- **Status:** PASSED
- **Expected Result:** Matching buffer → 1 rule match. Non-matching buffer → 0 matches.
- **Actual Result:** Both assertions pass — this is the exact capability Phase 66 exists to add;
  aho-corasick literal matching (what Phase 50 shipped as a stopgap) cannot express a wildcard nibble.

### Test 2: A boolean YARA condition (`$a and $b`) compiles and matches
- **Description:** `compiles_and_matches_boolean_condition` — a rule requiring two distinct string
  markers both present.
- **Command:** `cargo test --lib security_scan`
- **Status:** PASSED
- **Expected Result:** Buffer with both markers → 1 match. Buffer with only one → 0 matches.
- **Actual Result:** Both assertions pass.

### Test 3: A malformed rule in the feed is skipped, not fatal to the whole batch
- **Description:** `match_patterns_skips_malformed_rule_without_aborting_others` — one invalid YARA
  source string alongside one valid rule; the valid rule still compiles and matches.
- **Command:** `cargo test --lib security_scan`
- **Status:** PASSED
- **Expected Result:** The good rule still matches; the bad rule does not abort compilation of the batch.
- **Actual Result:** Matches `["Good"]` only, as expected.

### Test 4: The canonical crate cross-compiles for Windows with the engine linked
- **Description:** `agent-install/omni-agent-rs` builds for `x86_64-pc-windows-gnu` with yara-x
  compiled in, and the linked binary actually contains yara-x, not just type-checks.
- **Command:** `cargo check --target x86_64-pc-windows-gnu`; `file` + `strings` on the release binary.
- **Status:** PASSED
- **Expected Result:** Clean cross-compile; built `.exe` contains yara-x symbols.
- **Actual Result:** `Finished` (9 pre-existing dead-code warnings, 0 errors). Built
  `target/x86_64-pc-windows-gnu/release/omni-agent.exe` is a real `PE32+ executable ... for MS
  Windows`, 31,485,952 bytes, containing 198 yara-x strings (including the literal SQL
  `SELECT name, severity, source FROM yara_rules`) and 460 wasmtime/cranelift strings — the
  engine is linked into the binary that ships, not merely present in source.

### Test 5: Full lib suite is green
- **Command:** `cargo test --lib` (in `agent-install/omni-agent-rs`)
- **Status:** PASSED
- **Actual Result:** 97 passed, 0 failed, 0 ignored.

---

## Outstanding — genuinely requires a live agent, not re-testable from this session

### Pending: `scan_file` instruction → real verdict, end-to-end
- **Description:** With a signed feed bundle actually cached on disk at the agent's real config
  path, send a live agent a `scan_file` instruction for a file containing
  `EICAR-STANDARD-ANTIVIRUS-TEST-FILE` (matches the feed's seeded `Sample_Eicar_String` rule —
  see `backend/agent_security_feed_service.py:40-43`), and a second file matching nothing.
- **Expected:** Match → `{"verdict":"Malicious","confidence":0.9,"matched":["Sample_Eicar_String"],"sha256":...,"engine":"native"}`.
  Non-match → `{"verdict":"Clean","confidence":1.0,...}`.
- **Why not closed this session:** `feed_bundle::open_cache()` reads from a fixed path derived
  from `crate::config::config_path()` — there is no test-injectable override, so a hermetic
  automated test would need to write a real SQLite DB to the agent's actual config directory or
  refactor `feed_bundle.rs` for dependency injection. Both are real code changes beyond a
  documentation/evidence cleanup pass and risk being done carelessly under time pressure; the
  dispatch wiring itself (`src/instructions.rs:135-158` → `security_scan::scan_file`) is
  confirmed present and unchanged. Tracked as `behavior_unverified` in `66-VERIFICATION.md`.

### Pending: compiled-rule cache invalidates when feed content changes
- **Description:** Scan once, update the feed's `yara_rules` content, scan again with bytes only
  the new rules match — confirms the process-wide cache rebuilds rather than serving stale rules.
- **Why not closed this session:** Same constraint — needs a live/long-running agent process and
  a real feed update, not reproducible as a fast hermetic unit test without refactoring the cache
  for injectable state. Security-relevant if it silently doesn't fire (stale-rule risk after a
  feed update). Tracked as `behavior_unverified` in `66-VERIFICATION.md`.
