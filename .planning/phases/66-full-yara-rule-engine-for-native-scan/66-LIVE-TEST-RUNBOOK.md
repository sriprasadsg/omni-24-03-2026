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

## Progress (2026-08-25, second session)

**Registration: DONE and confirmed working.** Local Mongo `omni_platform.tenants`
has tenant `platform-admin` with a real `registrationKey`
(`Hcqj3peK4ukFs4lSEFgwvEsdWSRSf5bCVpmI3grMVUs` — a local dev credential, not
secret in the usual sense, but treat normally anyway). Wrote
`agent-install/omni-agent-rs/target/release/config.yaml` with
`api_base_url: http://localhost:5000` and that `registration_key`, blank
`agent_id`/`agent_token`. Ran the binary once — it self-registered via
`POST /api/agents/register` and rewrote `config.yaml` with a real
`agent_id` (`agent-310ee2eca93f47d2ae60efdd16ac70c4`) and JWT `agent_token`.
Confirmed real heartbeats (`Heartbeat -> 200`) with live telemetry
(vulnerability_scanning results etc.) posted to the backend.

**Instruction dispatch: found the shape, but agent never picked it up.**
Instructions go in Mongo `omni_platform.agent_instructions`, shape (from
`backend/compliance_scans_endpoints.py`'s existing dispatch calls):
```js
{ agent_id, instruction: "scan_file", parameters: {target: "<path>", path: "<path>"}, status: "pending", created_at, created_by, priority }
```
(Rust side: `src/instructions.rs:135` matches on the `instruction` string,
`:482` reads `parameters.target`.) Inserted a real instruction (id
`6a8ce75f12e698ced33d2477`, target `/tmp/eicar_test.txt` containing the
EICAR string) and ran the agent through **two full heartbeat cycles**
(~90s, interval_seconds=30) — the instruction stayed `status: "pending"`
the whole time. The agent never touched it.

**Leading suspect, not yet confirmed:** `config.yaml`'s
`agentic_mode_enabled: false` — this session left it at the default. If
that flag gates whether the agent polls/executes `agent_instructions` at
all, that's the whole explanation. **Next step: check what
`agentic_mode_enabled` actually gates in the Rust source
(`src/main.rs`/wherever the instruction-poll loop lives), and if it's
this, flip it to `true` in config.yaml and re-run.** If that's not it,
check whether `instructions.rs`'s poll loop queries `agent_instructions`
by a different filter than plain `status: "pending"` (e.g. a specific
`created_by` allowlist, or a different collection/endpoint entirely —
worth checking if there's a `GET /api/agents/{id}/instructions`-style
pull endpoint instead of the agent reading Mongo directly).

Also note: `timeout 90 ./omni-agent` was killed with SIGKILL (exit 137,
not the SIGTERM `timeout` normally sends) — matches the same "something in
this environment kills backgrounded/long-running processes" pattern seen
elsewhere this session with backgrounded `pytest` runs. Not agent-specific,
environmental. Foreground `timeout` calls have otherwise worked reliably
all session; this one just happened to hit the same killer.

**Cleanup done:** no `omni-agent` process left running after this session.
`config.yaml` still has the real registered credentials — reusable next
time, no need to re-register.

## Progress (2026-08-25, third check-in — `agentic_mode_enabled` disproven)

Checked the leading suspect from above. It's wrong, but the real cause is
narrower and cheaper to fix:

1. **`agentic_mode_enabled` is dead code.** `grep -rn agentic_mode_enabled
   src/*.rs` finds exactly one hit — the field declaration in
   `config.rs:27`. Nothing reads it. Not a gate on anything.
2. **The instruction-poll loop runs unconditionally.** `lib.rs:121` calls
   `instructions::poll(&cfg, &client).await` every cycle inside
   `agent_loop`, no flag around it.
3. **`poll()` is an HTTP GET to a backend endpoint**
   (`instructions.rs:5,14` — `pub async fn poll(...)`, `.get(&url)`), **not
   a direct Mongo query.** The prior test session inserted the test
   instruction straight into Mongo's `agent_instructions` collection,
   bypassing whatever the real endpoint filters on. Both the inserted
   instruction doc and the agent's own `config.yaml` have `tenant_id: ''`
   (empty) — if the backend endpoint tenant-scopes its query, an
   empty/missing `tenant_id` on either side would make the instruction
   invisible to `poll()` regardless of `status: "pending"` being correct.

**Next step, concretely:** find the exact URL `poll()`'s `.get(&url)`
targets (read the rest of `instructions.rs::poll()`, specifically how `url`
is constructed from `cfg.api_base_url`), then find that route's handler in
`backend/*.py` and read its actual query filter — likely needs a real
`tenant_id` set on both the agent's config and the instruction document.
Once found, either re-insert the test instruction with the correct
`tenant_id` (check what the `agents` collection's own document is scoped
under — the earlier registration response likely returned/assigned one), or
better: trigger the instruction through the real backend endpoint that
inserts it correctly (mirroring `backend/compliance_scans_endpoints.py`'s
pattern) rather than a raw Mongo insert, so the test exercises the real
path end-to-end rather than working around it.

This is a test-setup/insertion-path problem, not evidence of an agent-side
bug — narrows the remaining unknown considerably from where this runbook
started.

## Progress (2026-08-25, fourth check-in — found the real root cause, may be a REAL bug not just test setup)

Read `instructions.rs::poll()` in full. Confirmed:
```rust
let url = format!("{}/api/agents/{}/instructions", cfg.api_base_url.trim_end_matches('/'), hostname);
```
**Keyed by `hostname`, not `agent_id`.** (`hostname_str()` — this run logged
host `security-test-vm`.) Uses `bearer_auth(&cfg.agent_token)`.

Grepped for the matching backend route and found **three different files**
registering a route matching this exact path shape:
- `agent_instruction_endpoints.py:22` — `@router.get("/api/agents/{agent_id}/instructions")` — param is `agent_id`
- `agent_tasks_endpoints.py:21` — `@router.get("/{hostname}/instructions")` — param is `hostname` (prefix presumably `/api/agents`, not confirmed)
- `deployment_result_endpoints.py:40` — `@router.get("/api/agents/{agent_id}/instructions")` — **duplicate of the first**, also `agent_id`

**This may be a real, shippable bug, not just a test-setup gap.** The Rust
agent sends a hostname in that URL slot. If FastAPI/`router_registry.py`'s
load order resolves the path to one of the `agent_id`-keyed handlers rather
than the `hostname`-keyed one in `agent_tasks_endpoints.py`, then:
1. The query filter would look up instructions by `agent_id ==
   "security-test-vm"` — which will never match any real `agent_id` value
   (real ones look like `agent-310ee2eca93f47d2ae60efdd16ac70c4`).
2. **Every real agent's instruction poll could be silently broken this way**,
   not just this test — worth checking if this is why 66-VERIFICATION.md's
   original "Human Verification Required #1" (scan_file end-to-end) was
   never actually provable: maybe nobody could get an instruction delivered
   at all, for any instruction type, not just scan_file specifically.

**Next step, concretely, in this order:**
1. Read `backend/router_registry.py` to find the actual registration order
   for `agent_instruction_endpoints`, `agent_tasks_endpoints`, and
   `deployment_result_endpoints` — FastAPI resolves path conflicts by
   registration order (first match wins), so this determines which handler
   is actually live.
2. Read whichever handler wins — confirm its exact query filter (does it
   query by `agent_id` field value against the hostname string sent, or
   does something translate hostname->agent_id first?).
3. If confirmed broken: this becomes a real fix (dedupe the 3 competing
   routes, make the Rust client and the winning handler agree on
   hostname-vs-agent_id), not just a test workaround. Scope that properly
   before touching it — 3 files with the same route path smells like
   accreted debt, not a quick one-line fix.
4. Once instructions can actually reach the agent (whichever way that gets
   fixed), re-run the `scan_file` test from Step 3 above.

Not yet confirmed which handler wins — this is the very next thing to check.

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
