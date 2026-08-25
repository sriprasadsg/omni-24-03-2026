---
purpose: runbook
for: 66-VERIFICATION.md "Human Verification Required" items 1 and 2
written: 2026-08-25
status: not yet executed
---

# Phase 66 — Live-Agent Test Runbook

Closes the two remaining open items in `66-VERIFICATION.md`'s "Human Verification
Required" section (item 3, the D-01 override, was already resolved separately —
see that file). Both items below need a real running agent process, not static
analysis, which is why they were never automated.

## What's already confirmed (2026-08-25 session)

- Backend is up and healthy in this environment at `http://localhost:5000`.
- The Rust agent binary is already built:
  `agent-install/omni-agent-rs/target/release/omni-agent` (31.5MB, Linux).
- Agent config lives at `config.yaml` next to the binary
  (`agent-install/omni-agent-rs/target/release/config.yaml`), loaded via
  `src/config.rs::load()`. Fields: `api_base_url`, `tenant_id`, `agent_id`,
  `agent_token`, `registration_key`, `interval_seconds`, `max_cpu_percent`,
  `agentic_mode_enabled`, `accept_invalid_certs`, `fim_paths`.
- **The existing `config.yaml` is NOT usable as-is** — its `api_base_url` is
  `https://192.168.10.70`, a different, unreachable deployment. It has a real
  `agent_id`/`agent_token` for that other backend, not this one.

## Step 1 — Get the agent talking to this backend

Two paths, pick one:

**A. Fresh self-enrollment (probably simpler):**
1. Confirmed this session: registration flow is `src/registration.rs::ensure_registered()`
   -> `POST {api_base_url}/api/agents/register`, handled by
   `backend/agent_registry_endpoints.py`. Body shape (from the existing helper
   script `backend/trigger_register.py`): `{hostname, registrationKey,
   platform, ipAddress, macAddress, version, meta}`.
2. **Not yet found:** what `registrationKey` value is actually valid for this
   tenant/deployment — read `backend/agent_registry_endpoints.py`'s handler to
   see what it validates against (a stored tenant setting? a fixed dev key?).
3. Write a new `config.yaml` next to the binary with `api_base_url:
   http://localhost:5000`, the valid `registration_key`, and leave
   `agent_id`/`agent_token` blank — the agent should self-register on first run
   (confirm this is how `src/main.rs`/`registration.rs` actually behaves).

**B. Reuse the existing `agent_id`, repointed:**
1. Check whether an agent document with `agent_id:
   agent-1ba27cf216b94d71b4f18a2791dc9b8b` already exists in this backend's
   Mongo (`db.agents` or similar collection) — if yes, its `agent_token` may
   still work once `api_base_url` is changed; if no, this path won't work,
   use A instead.

Either way: run the binary in a terminal (`./omni-agent` from its directory,
or with `RUST_LOG=debug` for verbose output) and confirm it connects
successfully (heartbeat/registration log line, no auth errors) before going
further.

## Step 2 — Get a signed feed bundle cached

- Look at `backend/agent_security_feed_service.py` — it builds the signed
  SQLite bundle and seeds `_YARA_RULES` (the example rule mentioned in
  `66-VERIFICATION.md`'s Data-Flow Trace table: `Sample_Eicar_String`, matching
  the literal string `EICAR-STANDARD-ANTIVIRUS-TEST-FILE`).
- Confirm this tenant already has a bundle cached, or trigger whatever
  generates/pushes one (check for an endpoint or scheduled task in that
  service file).
- The agent reads it via `feed_bundle::open_cache()` in the Rust tree
  (referenced in `66-VERIFICATION.md`'s Key Link Verification table) —
  confirm the cache path/location the agent expects matches where the backend
  writes it.

## Step 3 — Item 1: dispatch `scan_file`, read the verdict

- Instruction dispatch mechanism: **not fully confirmed this session** —
  likely the `agent_instructions` Mongo queue (referenced generally
  elsewhere in this project's history), but the exact API/endpoint to enqueue
  one and how the agent polls/receives it needs confirming against
  `src/instructions.rs` (the dispatch match arm for `"scan_file" |
  "scan_url" | "scan_hash" | "scan_ip"`, per `66-VERIFICATION.md`'s Key Link
  Verification table, `instructions.rs:135`) and whatever backend endpoint
  writes to that queue.
- **Test A (match):** dispatch `scan_file` for a file containing the string
  `EICAR-STANDARD-ANTIVIRUS-TEST-FILE`.
  **Expected:** `{"verdict":"Malicious","confidence":0.9,"matched":["Sample_Eicar_String"],"sha256":...,"engine":"native"}`
- **Test B (no match):** dispatch `scan_file` for a file matching no rule.
  **Expected:** `{"verdict":"Clean","confidence":1.0,...}`
- Relevant source: `agent-install/omni-agent-rs/src/capabilities/security_scan.rs`
  (`scan_file`, `match_patterns`, `compiled_rules` — lines ~68-181 per prior
  reads this session, re-check line numbers as the file may have moved).

## Step 4 — Item 2: cache invalidates on feed update

- `compiled_rules()` (`security_scan.rs:154-181`) is a process-wide
  `OnceLock<Mutex<Option<(u64, Arc<Rules>)>>>` keyed on a hash of
  `(name, source)` pairs across all cached rules.
- With the same agent process still running from Step 3 (don't restart it —
  the whole point is testing in-process cache invalidation):
  1. Trigger one scan (any file) to populate the cache.
  2. Update the feed bundle's `yara_rules` content via the backend (add or
     change a rule) so the hash changes.
  3. Trigger a second scan with bytes that only the *new* rule matches.
  **Expected:** the second scan matches the new rule — proves the cache
  rebuilt rather than serving stale compiled rules. A long-running agent
  silently keeping stale rules after a feed update is the security-relevant
  failure mode this item exists to catch.

## When done

Update `66-VERIFICATION.md`: replace items 1 and 2 in "Human Verification
Required" with the actual results (pass/fail, exact JSON observed, log
excerpts). If both pass cleanly, this phase can likely move from
`status: gaps_found` to `status: passed` — but re-run a full `gsd-verifier`
pass rather than hand-editing the status field, per this session's own
experience with stale/self-contradictory verification docs on this exact
phase and on phases 32/71/64 earlier the same day.
