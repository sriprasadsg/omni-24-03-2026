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

## CONFIRMED (2026-08-25, fifth check-in) — real production bug, not a test artifact

`grep -n "agent_instruction_endpoints\|agent_tasks_endpoints\|deployment_result_endpoints" backend/router_registry.py`
returns **exactly one hit**: `_load(app, "deployment_result_endpoints", "router")`.

`agent_instruction_endpoints.py` and `agent_tasks_endpoints.py` are **never
loaded into the app at all** — dead files, their routes don't exist in the
running backend regardless of what's written in them.

The only live handler for `GET /api/agents/{X}/instructions` is
`deployment_result_endpoints.py:40`, which expects `{X}` to be `agent_id`.
The Rust agent (`instructions.rs:7-11`) sends `hostname` in that slot.

**This means: no agent, real or test, can ever receive an instruction
through this path, in this deployment, as currently wired.** The mismatch
isn't specific to `scan_file` or to this test — it's the entire instruction
delivery mechanism for every instruction type the Rust agent supports.

This reframes phase 66's original "Human Verification Required #1" item:
it was never really a "needs a live agent to prove it" gap — it's a real
wiring bug that a live agent test was always going to surface, which is
exactly what happened.

**Not yet done, and NOT attempted this session (ran out of budget):**
- Decide the actual fix: repoint the Rust client to send `agent_id`
  instead of `hostname` (need `agent_id` available in `Config` at poll
  time — it should be, since it's already in `config.yaml` post-registration),
  OR fix `deployment_result_endpoints.py`'s handler to resolve hostname→agent_id
  before querying, OR register `agent_tasks_endpoints.py`'s hostname-keyed
  route instead/first. Each has different blast radius — this needs a real
  decision, not a guess, before touching code. **Do not just pick one and
  ship it without checking what else depends on the current (broken)
  behavior of `deployment_result_endpoints.py`'s handler** — it may be used
  elsewhere for a different, working purpose.
- Confirm whether `agent_instruction_endpoints.py`/`agent_tasks_endpoints.py`
  are simply unfinished/abandoned alternate implementations (like the
  phase-64/65 dead drafts found earlier this session) or were deliberately
  disabled for some reason not yet found.
- Once fixed, re-run the live test from Step 3.

## CORRECTION (2026-08-25, sixth check-in) — the "confirmed bug" above was wrong

Read `deployment_result_endpoints.py:40-56`'s actual function body (the
prior check-in only looked at the route decorator + param name, not the
body — a real mistake, flagging it plainly rather than leaving it standing).
It already does exactly the right thing:

```python
@router.get("/api/agents/{agent_id}/instructions")
async def get_agent_instructions(agent_id: str, caller: dict = Depends(_get_caller)):
    agent = await db.agents.find_one(
        {"$or": [{"id": agent_id}, {"hostname": agent_id}]}, {"id": 1},
    )
    actual_id = agent["id"] if agent else agent_id
    instructions = await db.agent_instructions.find(
        {"agent_id": actual_id, "status": "pending"}
    ).to_list(length=100)
```

It deliberately resolves **either** `id` **or** `hostname` (comment in the
source: "agent may pass its hostname"). The test instruction was created
with `agent_id: "agent-310ee2eca93f47d2ae60efdd16ac70c4"` — the real,
correct id for the registered agent — and the Rust client sends its
`hostname` (`security-test-vm`) in the URL. If the agent's `db.agents`
document has `hostname: "security-test-vm"` stored correctly (should be
true, that's what registration wrote), this `$or` lookup should resolve to
the right `actual_id` and the query should have found the pending
instruction. **It's not the hostname/agent_id mismatch — that part of the
system is fine.**

**Retracted:** the "no agent can ever receive an instruction" claim and the
"real production bug" framing from the two check-ins above. Also retracted:
`agent_instruction_endpoints.py`/`agent_tasks_endpoints.py` being dead code
is still true (confirmed via `router_registry.py`), but that fact alone
doesn't establish a bug given `deployment_result_endpoints.py` already
covers the case correctly.

**Real root cause still unknown.** Candidates for next session, none
confirmed:
1. `_get_caller` auth dependency rejecting the request silently (need to
   check what it validates and whether `bearer_auth(&cfg.agent_token)`
   satisfies it — the token is a real JWT from registration, should be
   fine, but not verified).
2. The `db.agents` document's actual stored `hostname` field not matching
   what the Rust client sends (case sensitivity? trailing whitespace?
   verify by reading the actual stored document, not assuming).
3. The request never actually reaching the server in the test window (90s
   was 2 heartbeat cycles at 30s interval — but heartbeat and
   instruction-poll might not be the same cycle/timing; check `lib.rs`'s
   `agent_loop` to see if `instructions::poll()` runs on every loop
   iteration or a separate, slower cadence).
4. An exception in the handler being swallowed somewhere before reaching
   the query (add temporary server-side logging, or just watch
   `uvicorn`'s own request log for a hit on this path at all during the
   next live test — first check: did the request even arrive?).

**Recommended next step:** before touching any code, re-run the live test
with the backend's request log visible (uvicorn already logs at
`--log-level info`) and watch for a `GET /api/agents/security-test-vm/instructions`
line — that alone answers candidate 3 and narrows the rest fast. Don't
guess further without that observation.

## Progress (2026-08-25, seventh check-in — one more data point, still inconclusive)

Couldn't tail the backend's live log directly — its stdout/stderr go to a
pts terminal (`/proc/{pid}/fd/1` → `/dev/pts/6`), not a regular file, so
grepping it non-invasively wasn't straightforward in the time available.
Used the DB record itself as the observable signal instead (equivalent
value: did `status` flip from `pending` to `delivered`).

Reset the test instruction to `status: "pending"`, ran the agent fresh
(`timeout 40 ./omni-agent`, exit 124 — clean SIGTERM this time, not the
SIGKILL seen earlier). Result:
- One heartbeat fired (`Heartbeat -> 200`, ~10s in, after a 5s CPU-throttle
  delay). Only one cycle completed in the 40s window.
- **`instructions::poll()` produced zero log output** — no line
  confirming it ran, no error, nothing at INFO level. Can't distinguish
  "ran and found nothing to deliver" from "didn't run this cycle at all."
- Instruction is still `status: "pending"` after the run.

**This doesn't confirm or rule out any of the 4 candidates from the
correction above.** It does add one new fact: `poll()` appears to log
nothing on either success-empty or the paths it takes before reaching a
response — worth checking if it has any `log::info!`/`log::debug!` calls
at all, or if it's genuinely silent by design (in which case, the request
log — not the agent's own stdout — is still the right thing to check next,
via a less time-pressured method than this session had budget for: e.g.
redirect uvicorn's own log to a file by restarting it with output
redirection, or use `strace`/an eBPF trace, or add a temporary log line to
the handler and restart the backend).

**Stopping the live-test line of investigation here for this session** —
context ran out before a conclusive answer. Next session: get a real view
into either the backend's request log or the agent's `poll()` internals
before running the agent again; running it blind a fourth time without
better observability isn't likely to add new information.

## Progress (2026-08-25, eighth check-in — RUST_LOG=debug tried, still inconclusive)

Found via source read (no run needed for this part): `poll()`'s non-success
paths log at `log::debug!`, not `log::info!` — `instructions.rs`:
```rust
Ok(r) => log::debug!("Instructions poll -> {}", r.status()),
Err(e) => log::debug!("Instructions poll error: {e}"),
```
All prior runs used no `RUST_LOG` or `RUST_LOG=info`, which would filter
these out — plausible full explanation for "zero log output" in every
prior run.

**Tried `RUST_LOG=debug timeout 40 ./omni-agent`. Zero debug lines
appeared** — same single heartbeat, then killed (SIGKILL again, not
`timeout`'s own SIGTERM — the same external-killer pattern seen
throughout this session on long-running foreground commands too, not just
backgrounded ones).

**Two live possibilities, not distinguished yet:**
1. The logger needs a crate-scoped filter (e.g. `RUST_LOG=omni_agent=debug`
   or whatever the actual crate/binary name is — check `Cargo.toml`'s
   `[package] name` and whatever logger init call is in `main.rs` to see
   what scope it expects) rather than the bare `debug` tried here.
2. `poll()` genuinely isn't reached within one heartbeat-interval window —
   check `lib.rs`'s `agent_loop` directly to see the actual ordering/timing
   between the heartbeat call and the `instructions::poll()` call at line
   121 (already located, not yet read in context). If they're sequenced
   with a delay, or gated on something not yet found, a single ~30-40s
   window may complete the heartbeat but never reach the poll call before
   getting killed.

**Recommended next step, in order, cheapest first:**
1. Read `lib.rs`'s `agent_loop` function in full — settles possibility 2
   directly from source, no run needed.
2. If poll() IS supposed to run every cycle, fix the `RUST_LOG` scope
   (check `main.rs`'s logger init, e.g. `env_logger::init()` vs
   `SimpleLogger` vs something with an explicit default filter) and retry
   with the correct scoped value.
3. Only after both of those: consider whether the mystery SIGKILL pattern
   itself needs separate investigation (it's now hit 3+ long-running
   foreground commands this session, not just backgrounded ones as
   originally assumed — worth checking `dmesg`/OOM killer logs, or simply
   whether something in this environment has a hard wall-clock limit on
   any single command regardless of foreground/background).

Not attempted this session: reading `lib.rs::agent_loop` (next session's
first move, cheapest and most informative given it needs no test run).

## Progress (2026-08-25, ninth check-in — mystery solved, question reframed)

Read `lib.rs::agent_loop` in full. The loop body, in order, each iteration:
```rust
if agent_cpu > cfg.max_cpu_percent {
    log::warn!("...throttling 5s");
    tokio::time::sleep(...).await;
    continue;  // skips heartbeat AND poll entirely for this iteration
}
let payload = heartbeat::build_payload(&cfg, &sys, &cap_mgr);
heartbeat::send(&cfg, payload, &buf, &client).await;
instructions::poll(&cfg, &client).await;  // same iteration, right after heartbeat, no gap
```

**`poll()` runs unconditionally, same iteration, immediately after every
successful heartbeat send.** Every test run this session logged
`Heartbeat -> 200`, which means `poll()` necessarily ran too, every time.

**And `poll()`'s success branch logs nothing on an empty result**, by
design — its only log line inside the success match arm is
`log::info!("Instruction received: {action}")`, which sits *inside* the
`for item in items` loop, so it only fires per-delivered-item. A `200 OK`
with an empty JSON array produces zero log output at any level. Not a
debug/info filtering bug, not a "didn't run" bug — correct behavior for
"ran, got nothing back."

**The real open question flips back to the server side:** the test
instruction's `agent_id` field
(`agent-310ee2eca93f47d2ae60efdd16ac70c4`) matches the real, registered
agent — so why does the handler's query return empty? New concrete
suspect, not yet checked: **this session ran agent registration multiple
times** (at least twice — once early, once after the `agentic_mode_enabled`
investigation reset the config). `deployment_result_endpoints.py`'s handler
resolves hostname→id via `db.agents.find_one({"$or": [{"id": agent_id}, {"hostname": agent_id}]}, {"id": 1})`
— a bare `find_one` with no sort, so if multiple `agents` documents exist
for hostname `security-test-vm` (plausible if each registration created a
new doc rather than upserting), Mongo could return an OLDER one whose `id`
doesn't match what's currently in `config.yaml` / what the test instruction
was tagged with.

**Recommended next step, cheapest first, no agent run needed:**
1. Query `db.getSiblingDB("omni_platform").agents.find({hostname: "security-test-vm"})`
   directly — if more than one document comes back, that's very likely the
   actual root cause. Confirm which `id` the *current* `config.yaml`'s
   `agent_token` JWT actually corresponds to (decode the JWT's `sub` claim,
   or check which `id` was most recently written).
2. If duplicates exist: either delete the stale ones, or re-point the test
   instruction's `agent_id` at whichever one the handler's `find_one`
   actually returns (query it the same way the handler does, no `.sort()`,
   to see what Mongo's natural order gives back).
3. Only then re-run the live test — this time with a real, evidence-backed
   reason to expect it to work, not another blind attempt.

## FIXED (2026-08-25, eleventh check-in) — commit b74c5b689

Read `agent_registry_endpoints.py`'s register handler in full first, as
planned. **Registration itself is not buggy** — it already scopes
`{"hostname": hostname, "tenantId": tenant["id"]}` and reuses the existing
`id` when found. The two docs found live were two legitimate, separate
registrations under two different tenants (this session's `platform-admin`
vs. an older `tenant_9f5d80ac64d0` from before this session) that happen to
share a hostname — not duplication, correct multi-tenant behavior.

The actual bug was squarely in `get_agent_instructions`'s hostname/id
resolution query — **no tenant filter at all**:
```python
agent = await db.agents.find_one({"$or": [{"id": agent_id}, {"hostname": agent_id}]}, {"id": 1})
```
Fixed by scoping it with `caller["tenant_id"]` (from the agent's own
verified JWT, not client-suppliable):
```python
caller_tenant_id = caller.get("tenant_id")
agent = await db.agents.find_one(
    {"$or": [{"id": agent_id}, {"hostname": agent_id}], "tenantId": caller_tenant_id}, {"id": 1},
)
```
This is a real fix for a real bug class, not specific to this test
environment: any hostname collision across tenants (not rare — think
`localhost`, generic VM names, demo environments) could previously resolve
an agent's instruction poll to a different tenant's agent document,
silently breaking delivery (what happened here) or, in principle, a worse
cross-tenant resolution depending on what else keys off that resolved id.

**New test:** `backend/tests/test_agent_instruction_poll_tenant_scoping.py`,
2/2 pass — proves same-hostname-different-tenant resolves to the caller's
own tenant's doc, and documents the pre-fix ambiguous-resolution failure
mode directly.

**Not verified this session (budget ran out immediately after the fix):**
- Full backend test suite (only the new test file was run, not the full
  ~2400-test suite this project normally gates on before considering a fix
  complete). **Run it before considering this fully done.**
- The actual live-agent `scan_file` test was never re-run after the fix —
  the original goal of this whole runbook is still technically open. The
  fix is logically sound and unit-tested, but "does the real agent now
  actually receive and execute the instruction end-to-end" was not
  re-confirmed live.
- Whether anything else in the codebase relies on the old, unscoped
  behavior of `get_agent_instructions` (unlikely given it's a narrow
  single-purpose poll endpoint, but not explicitly checked).

## CONFIRMED ROOT CAUSE (2026-08-25, tenth check-in)

```js
db.getSiblingDB("omni_platform").agents.find({hostname: "security-test-vm"})
```
returns **two documents**:
```js
{ id: 'agent-1ba27cf216b94d71b4f18a2791dc9b8b', tenantId: 'tenant_9f5d80ac64d0', hostname: 'security-test-vm' }
{ id: 'agent-310ee2eca93f47d2ae60efdd16ac70c4', tenantId: 'platform-admin',      hostname: 'security-test-vm' }
```
Doc 1 is **pre-existing, from before this session** — matches the original
`config.yaml` this runbook found at the very start, which pointed at a
different, unreachable host (`192.168.10.70`) under a different tenant.
Doc 2 is the one registered this session, the one the test instruction's
`agent_id` correctly targets.

`deployment_result_endpoints.py`'s handler does
`db.agents.find_one({"$or": [{"id": agent_id}, {"hostname": agent_id}]}, {"id": 1})`
— **no sort**. With two docs sharing the hostname, this can return either
one depending on Mongo's natural/insertion order (commonly, but not
guaranteed, the older one). If it returns doc 1, `actual_id` resolves to
`agent-1ba27...`, and the subsequent
`db.agent_instructions.find({"agent_id": actual_id, "status": "pending"})`
searches for the WRONG agent_id — the test instruction's `agent_id` is
`agent-310ee2...`. Zero match, every time. **This fully explains the
result across every run this session, with no ambiguity left.**

This is very likely a **real, if narrow, production bug class**: any
tenant/host where an agent got re-registered without the old document
being cleaned up (re-imaged VM keeping its hostname, a stale test/demo
registration, etc.) would have the same silent-failure mode — instructions
queued correctly, agent polling correctly, but silently resolving to a
stale sibling document and never receiving anything. Worth flagging
separately from "this test's setup was wrong," since it's a real gap in
`get_agent_instructions`'s hostname-resolution query, not specific to this
test environment.

**Not yet done (next session):**
1. Confirm the actual resolution order Mongo returns (query it the exact
   same way the handler does, or just delete/rename doc 1 to remove the
   ambiguity for this test — doc 1 looks like leftover cruft from a
   different, now-irrelevant deployment anyway, but confirm it's not used
   by anything else before touching it).
2. Once resolved, re-run the live `scan_file` test — first time with an
   actual evidence-backed reason to expect success.
3. If confirmed as a real gap, consider whether `get_agent_instructions`
   should add `.sort([("_id", -1)])` (most-recent) or otherwise disambiguate,
   or whether agent registration should be upserting on hostname instead of
   always inserting a new doc — that's the real fix decision, not attempted
   this session (ran out of budget after finding the cause).

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
