# Phase 40: Rust Agent Modernization & Session Reliability - Research

**Researched:** 2026-07-20
**Domain:** (a) Rust crate dependency modernization + build/rollout pipeline for a Windows-service endpoint agent; (b) JWT refresh-token race condition in a FastAPI/Motor auth backend
**Confidence:** HIGH — every claim below is grounded in direct reads of this repository's actual source, `git log`, and a live `cargo check --offline` run performed during this research session, not general framework/ecosystem advice. This phase required almost no external research: both RUST-01 and SESS-01 are "read the actual code and find the actual gap" problems, and the milestone-level research (`STACK.md`/`PITFALLS.md`/`ARCHITECTURE.md`) already covers the crate-bump ecosystem facts.

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

**D-01 — TLS backend:** Use `native-tls`, explicitly pinned as a `reqwest` feature. reqwest 0.13 defaults to `rustls`, a silent behavior change from pre-0.13 — must not ship without an explicit choice. `native-tls` matches current behavior and uses the OS/Windows cert store, which existing endpoint deployments behind corporate proxies with custom root CAs rely on.

**D-02 — Rollout mechanism:** 2.1.0 reaches already-registered agents via the existing update pipeline (`agent_download_endpoints.py`/`update_endpoints.py`) — auto-push, not manual/opt-in. The plan must verify the existing pipeline actually supports this before assuming it (check version-gating logic, download endpoint behavior).

**D-03 — 401 fix scope:** Narrow fix only. Root-cause and fix the specific refresh-token race; do not add broader session-resilience hardening (silent retry-on-401, refresh-margin tuning) in this phase — that would be scope creep beyond what HANDOFF task 10 asked for. If the root-cause investigation surfaces a different/additional defect, fix that too, but stay within "why does 401 happen intermittently," not "make auth generally more resilient."

### Claude's Discretion
- Exact TLS pin syntax in `Cargo.toml` (default-features = false + explicit `native-tls` feature, or equivalent) — implementation detail.
- Whether the update pipeline needs a code change to push 2.1.0, or whether it already auto-serves the latest built executable — verify against actual pipeline code during planning/research, don't assume. **Answered below: no code change needed; see "RUST-01 Rollout Mechanism" section.**
- Test/verification strategy for confirming the 401 race is actually fixed (e.g., concurrent-refresh regression test). **Recommendation below: `asyncio.gather` two concurrent `/refresh` calls against a real test-Mongo instance, assert exactly one 200 + one 401.**

### Deferred Ideas (OUT OF SCOPE)
- Broader auth-session hardening (silent retry-on-401, refresh-margin tuning) — deferred per D-03; revisit only if the 401 root-cause investigation shows it's genuinely needed, as a separate future phase/todo, not folded into this one.
- None else — discussion stayed within phase scope otherwise.
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| RUST-01 | Rust endpoint agent builds/ships on reqwest 0.13, sysinfo 0.39, tokio-tungstenite 0.30, rusqlite 0.40, hostname 0.4, serde_yaml→serde_norway; explicit TLS-backend decision; rebuilt as "the 2.1.0 executable" | Crate bumps already staged & verified compiling (this session re-confirmed via `cargo check --offline`). TLS decision resolved by D-01 — needs one `Cargo.toml` feature-list edit. **Critical correction: the target version cannot literally be "2.1.0"** — that version number was already shipped to `backend/static/omni-agent-2.1.0-windows.exe` on 2026-07-19 (commit `7f05ab5`) and superseded by 2.1.1/2.1.2 the same day; `Cargo.toml`'s `[package].version` is already `"2.1.2"`. See "Versioning" section for the concrete recommendation (bump to 2.1.3). |
| SESS-01 | Root-cause and fix the intermittent 401 (lead: refresh-token double-consume race in `authentication_endpoints.py::refresh_access_token`) | Two verified, code-grounded candidate mechanisms found — see "SESS-01 Root Cause" section. Primary, in-scope, narrowly-targeted fix identified: a missing MongoDB unique index that the code's own comment claims exists but doesn't. |
</phase_requirements>

## Summary

This is two fully independent, small, well-scoped fixes, both close to "commit correctly documented work" rather than "build something new."

**RUST-01:** The dependency bump (reqwest 0.13, sysinfo 0.39, tokio-tungstenite 0.30, rusqlite 0.40, hostname 0.4, serde_norway) is already staged, uncommitted, in `agent-install/omni-agent-rs/Cargo.toml`/`Cargo.lock` on this branch. `cargo check --offline` passes clean (re-verified this session — 4 pre-existing unrelated warnings, 0 errors). The only code change actually required is the TLS-feature pin (D-01: add `"native-tls"` to reqwest's feature list). The rollout mechanism (D-02) already works today, end-to-end, with **zero code changes** — it has been used successfully for every prior version bump from 2.0.1 through 2.1.2. What's actually required is executing that pipeline's 3-step manual process correctly for a **new version number** (recommend `2.1.3`, not `2.1.0` — see below for why reusing "2.1.0" would silently break the auto-push for already-registered agents).

**SESS-01:** `refresh_access_token`'s atomic-consume logic (`find_one_and_update` + `$setOnInsert` + `upsert=True`) is *already implemented* — it replaced a naive read-then-write race back on 2026-06-04 (commit `695f8ae`/`ae3ca86`). But its own inline comment says the guarantee depends on "a unique index on jti" — **that index does not exist anywhere in `database.py`**. This is a concrete, verifiable, narrowly-scoped bug: the code's stated safety net for the exact "double-consume race" HANDOFF flagged was never actually wired up at the database layer. Adding the missing index is the primary recommended fix. A second, independent, code-verified contributing mechanism (multi-tab/cloned-tab sessionStorage divergence racing the *same* stale refresh token) is documented as an Open Question for the planner to decide whether it's in scope under D-03.

**Primary recommendation:** For RUST-01, pin `native-tls`, bump `Cargo.toml`'s version to `2.1.3` (not `2.1.0`), cross-compile, and commit the binary to `backend/static/omni-agent-2.1.3-windows.exe` while bumping `_LATEST_AGENT_VERSION` in `agent_heartbeat_endpoints.py` to `"2.1.3"` — no endpoint code changes needed. For SESS-01, add `await mongodb.db.revoked_tokens.create_index("jti", unique=True, background=True)` to `database.py`'s index block, and add a concurrent-refresh regression test that didn't exist before.

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| Rust agent dependency/build | Endpoint agent (native Windows binary, own toolchain) | — | Entirely outside the web app tiers; a separate Rust binary shipped and self-updating independently. |
| Agent version-gated auto-push | API / Backend | Endpoint agent (client side of the update) | Backend (`agent_heartbeat_endpoints.py`) decides *when* to push (comparing reported vs. latest version); the agent (`agent_update.rs`) executes the download+swap. Both sides already exist and already work together. |
| Refresh-token consumption / rotation | API / Backend | Database / Storage | `authentication_endpoints.py::refresh_access_token` owns the logic; the atomicity guarantee it claims depends on a MongoDB unique index that must live in `database.py`'s index-creation block — a Database/Storage-tier fix, not an API-tier code-logic fix. |
| Concurrent-refresh de-duplication (client) | Frontend Server (SSR) / Browser Client | — | `services/apiService.ts`'s `refreshPromise` singleton mutex is a browser-tab-scoped in-memory guard; it does not and cannot span multiple tabs (see SESS-01 Open Question). |

## Standard Stack

No new libraries are introduced by this phase. The Rust crate versions were already researched and verified in the milestone-level `.planning/research/STACK.md` (HIGH confidence — verified via local `cargo check`/`cargo build`, RustSec advisories, and crate changelogs). This phase's job is to *finish and ship* that already-decided stack, not choose a new one. Summary table reproduced here for planner convenience, all `[VERIFIED: local cargo check + Cargo.lock, re-confirmed this session]`:

### Core
| Library | Version (Cargo.lock resolved) | Purpose | Why Standard |
|---------|------|---------|--------------|
| `reqwest` | 0.13.4 | HTTP client (heartbeat, registration, update-check, update-download) | Already the codebase's only HTTP client; 0.13 is current major |
| `sysinfo` | 0.39.6 | Process/CPU/memory telemetry | Already in use across 16 files under `src/capabilities/`; zero breaking-API usage found |
| `tokio-tungstenite` | 0.30.0 | WebSocket (remote access capability) | Only consumer is `src/capabilities/remote_access.rs`; already pins `native-tls` feature explicitly (unlike reqwest) |
| `rusqlite` | 0.40.1 (`libsqlite3-sys` 0.38.1, `bundled`) | Local offline buffer (`src/buffer.rs`) | Only uses `Connection`/`params` — zero VTab API usage, so the 0.32→0.40 breaking changes (concentrated in VTab) are inert here |
| `hostname` | 0.4.2 | Hostname resolution for heartbeat/registration | Single call site (`src/heartbeat.rs`), unchanged API surface |
| `serde_norway` | 0.9.42 | YAML config (replaces `serde_yaml`) | `serde_yaml` is archived/unmaintained; `serde_norway` is the maintained fork with source-compatible `from_str`/`to_string` — already migrated in `src/config.rs` |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| `serde_norway` | `serde_yml` | **Do not use** — flagged unsound/unmaintained per RustSec `RUSTSEC-2025-0068` (already ruled out in milestone STACK.md, not a fresh decision) |
| `native-tls` (D-01, locked) | rustls (reqwest 0.13's new default) | Only viable if every deployment target is confirmed to need no corporate/internal CA — not verifiable from this repo alone; D-01 already resolved this in favor of `native-tls` |

**Installation:** No new packages to install — this is a `Cargo.toml` edit (add `"native-tls"` to reqwest's feature list) plus committing the already-resolved `Cargo.lock`.

```toml
# agent-install/omni-agent-rs/Cargo.toml — the one code change RUST-01 needs
reqwest = { version = "0.13", features = ["json", "blocking", "native-tls"] }
```

**Version verification:** Re-run this session, 2026-07-20 — `cd agent-install/omni-agent-rs && cargo check --offline` → `Finished dev profile ... in 0.34s`, 4 pre-existing unrelated warnings (unused import in `system_patching.rs`, unused var in `remote_access.rs`, unnecessary `mut` in `sbom.rs`, dead code in `chat_ui.rs` — none touched by this phase), 0 errors. `git status` confirms `Cargo.toml`/`Cargo.lock` are still modified-but-uncommitted on this branch.

## Package Legitimacy Audit

No new packages are introduced by this phase (both RUST-01's crates and SESS-01's fix use only stdlib/already-installed dependencies — `pymongo`/`motor` for the index call, already a direct dependency). The 6 crates above were already vetted in `.planning/research/STACK.md` this same day (2026-07-20) via `cargo check`/`cargo build --release --offline` (i.e., resolved against the real crates.io index) plus RustSec advisory cross-checks — re-auditing here would be redundant. All are long-established, high-download crates with real GitHub source repos (`seanmonstar/reqwest`, `GuillaumeGomez/sysinfo`, `snapview/tokio-tungstenite`, `rusqlite/rusqlite`, the `hostname` crate on crates.io, and `serde_norway`, the actively-maintained fork of `serde_yaml`). No `[SLOP]` or `[SUS]` verdicts applicable.

**Packages removed due to [SLOP] verdict:** none
**Packages flagged as suspicious [SUS]:** none

## Architecture Patterns

### System Architecture Diagram — RUST-01 rollout (existing, working, no code change)

```
[Rust agent, running v2.1.2]
      │  heartbeat every interval_seconds (POST /api/agents/heartbeat)
      │  payload includes "version": env!("CARGO_PKG_VERSION")   ← compiled-in from Cargo.toml
      ▼
[backend/agent_heartbeat_endpoints.py]
      │  reported_version != _LATEST_AGENT_VERSION ("2.1.2" today)
      │  AND platform == "Windows"
      │  AND reported_version parses >= (2,0,5)  (min self-update-capable version)
      │  AND no pending/sent "agent_update" instruction already queued
      ▼
      insert db.agent_instructions {instruction: "agent_update", status: "pending"}
      │
      │  (next poll cycle)
      ▼
[Rust agent — instructions.rs dispatch]
      "apply_agent_update" | "check_agent_update" | "agent_update" | "update_agent"
      ▼
[src/capabilities/agent_update.rs :: apply_update()]
      │  GET {api_base_url}/api/agent-updates/latest?platform=windows   ← update_endpoints.py, NOT agent_download_endpoints.py
      ▼
[backend/update_endpoints.py :: get_latest_version()]
      │  glob backend/static/omni-agent-*.exe, pick max(mtime)
      │  parse version from filename "omni-agent-{version}-windows.exe"
      │  return {version, filename, url: /api/agent-updates/download/{filename}}
      ▼
[Rust agent] compares returned version to CURRENT_VERSION (== CARGO_PKG_VERSION)
      │  if different: GET /api/agent-updates/download/{filename}
      ▼
[backend/update_endpoints.py :: download_agent_binary()]
      │  serves backend/static/{filename} as-is
      ▼
[Rust agent] validates response is a real Windows PE (>1MB, starts "MZ") — aborts loudly otherwise
      │  writes omni-agent.new.exe next to itself
      │  spawns a detached PowerShell script: resolve own service by binary path (Win32_Service.PathName),
      │  stop → wait → Move-Item (retry until unlocked) → Set-Service Automatic → Start-Service (retry) → self-delete
      ▼
[Rust agent, now running the new version — reports it on the next heartbeat]
```

**Important correction to the phase brief's framing:** `agent_download_endpoints.py`'s `/api/agent/download/{tenant_id}/rust-binary` and `/rust-exe` routes are a **separate, unrelated path** — they exist for a human downloading a *fresh install* package (built on-demand from source via `agent_rust_builder.py::_ensure_rust_binary`, which compiles straight from `agent-install/omni-agent-rs/target/.../release/omni-agent.exe`). The Rust agent's own self-updater (`agent_update.rs`) **never calls this route** — it only calls `update_endpoints.py`'s glob-based `/latest` + `/download/{filename}`, which read from `backend/static/omni-agent-{version}-windows.exe`, a manually-committed, version-named artifact. Both files named in CONTEXT.md's D-02 (`agent_download_endpoints.py`/`update_endpoints.py`) are real and both matter to this phase, but for different reasons: `update_endpoints.py` is the auto-push mechanism itself (must get a correctly-named/versioned file); `agent_download_endpoints.py` is the fresh-install path (should ideally also reflect the new build, but is not what makes D-02's auto-push work).

### Pattern 1: The 3-step manual release lockstep (already proven 6 times: 2.0.1→2.1.2)

**What:** Every prior Rust agent version bump in this repo's history followed the identical 3-step pattern, confirmed via `git log -p -- backend/agent_heartbeat_endpoints.py` and the corresponding source/`backend/static/` commits:
1. Bump `agent-install/omni-agent-rs/Cargo.toml`'s `[package].version`.
2. Cross-compile for Windows (`cargo build --release --target x86_64-pc-windows-gnu`, using the mingw toolchain already present in this environment — confirmed `x86_64-w64-mingw32-gcc` and the `x86_64-pc-windows-gnu` rustup target are both installed) and commit the resulting `.exe` into `backend/static/omni-agent-{version}-windows.exe` (each prior bump also committed a `.b64` companion file of the same name — no code path in this repo was found that reads `.b64` files; treat it as either a legacy artifact from a since-removed browser-embed flow or dead weight, and confirm with the user/planner whether it's still needed before spending time regenerating it).
3. Bump `_LATEST_AGENT_VERSION` in `backend/agent_heartbeat_endpoints.py` (currently line 132) to the new version string, in the *same* commit as step 2 (verified: `git log -p` shows every one of the last 3 bumps changed this line and the `backend/static/` binary in one commit).

**When to use:** Every Rust agent release, including this one. No new automation needs to be built — the existing pattern already delivers exactly what D-02 asks for (auto-push to registered agents via the existing pipeline).

**Example (from git history, `agent_heartbeat_endpoints.py`):**
```python
# commit fc0d41c — 2026-07-16 21:32
-    _LATEST_AGENT_VERSION = "2.1.1"
+    _LATEST_AGENT_VERSION = "2.1.2"
```

### Pattern 2: Atomic single-use consumption via `find_one_and_update` + `$setOnInsert` (correct shape, missing enforcement)

**What:** `refresh_access_token` uses MongoDB's `find_one_and_update({"jti": jti}, {"$setOnInsert": {...}}, upsert=True, return_document=False)` and checks whether the returned pre-image is `None` (this request "won" — no prior document existed) or not-`None` (already consumed — reject with 401). This is the textbook-correct pattern *given a unique index exists* on the query field.

**When to use:** Any "consume exactly once" semantics against a MongoDB collection under concurrent access — already the intended pattern here, just missing its enforcement layer.

**Example (current code, `authentication_endpoints.py:415-437`):**
```python
# Atomically consume this refresh token's JTI — prevents double-use under concurrency.
# find_one_and_update with $setOnInsert + a unique index on jti guarantees only one
# request wins; the second sees inserted_id=None and gets a 401.
if jti:
    try:
        existing = await db._db.revoked_tokens.find_one_and_update(
            {"jti": jti},
            {"$setOnInsert": {
                "jti": jti,
                "type": "refresh",
                "revoked_at": datetime.datetime.now(timezone.utc).isoformat(),
            }},
            upsert=True,
            return_document=False,
        )
        if existing is not None:
            raise HTTPException(status_code=401, detail="Could not validate credentials")
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(status_code=401, detail="Could not validate credentials")
```

The comment's claim ("a unique index on jti guarantees...") is **not currently true** — see SESS-01 Root Cause below.

### Anti-Patterns to Avoid
- **Reusing an already-shipped version number for the modernized build:** `Cargo.toml`'s version is already `"2.1.2"`, and `backend/static/omni-agent-2.1.2-windows.exe` already exists (built 2026-07-16, pre-modernization). If the plan rebuilds with the new dependency stack but leaves the version string at `"2.1.2"` and simply overwrites the file, `_LATEST_AGENT_VERSION` (already `"2.1.2"`) will never trigger an auto-push for agents already reporting `"2.1.2"` — D-02's entire purpose (auto-push to already-registered agents) silently fails. The version number **must** advance.
- **Assuming `agent_download_endpoints.py`'s `/rust-binary` route is "the" update mechanism:** It is not consulted by the self-updater at all (see diagram above). Don't spend plan effort wiring version-awareness into that route unless there's a separate, explicit reason to (e.g., keeping the manual "download latest for a fresh install" path in sync is good hygiene but is not what makes D-02 work).
- **Trusting the `find_one_and_update` comment at face value:** the code *looks* like it already has atomic single-use protection. It does not, until the missing index is added — see below.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Atomic "consume once" semantics for a token jti | A custom in-memory lock, a distributed mutex, or a second collection/flag scheme | A single `create_index("jti", unique=True)` on the existing `revoked_tokens` collection | The application code (`find_one_and_update` + `$setOnInsert`) is already correct — the *only* missing piece is the index. Building new coordination logic around the existing (nearly-correct) code would be solving an already-solved problem in the wrong layer. |
| Windows service self-update / binary swap | A new update mechanism | The existing `agent_update.rs`/heartbeat auto-push pattern, already handling PE-header validation, service-name resolution by binary path, retry loops for file-lock release, and detached-process execution | This is already a mature, defensive implementation (guards against web-filter HTML block pages, service-name drift between `OmniAgent`/`OmniAgentRust` installs, and file-lock races) — re-implementing any part of it for this phase would be pure regression risk for zero benefit. |

**Key insight:** Both RUST-01 and SESS-01 are cases where the "hard part" was already built correctly by a previous session/commit. The actual phase work is: (1) one dependency-feature edit + a disciplined repeat of an already-proven 3-step release process with a **new** version number, and (2) one missing database index. Resist the temptation to build new machinery for either.

## Common Pitfalls

### Pitfall 1: Shipping RUST-01 under the version number "2.1.0" silently breaks the auto-push requirement (D-02)

**What goes wrong:** The plan/task text literally says "rebuilt as the 2.1.0 executable." If a plan takes that literally — sets `Cargo.toml` version back to (or leaves it at, if someone mistakenly reverts) `"2.1.0"` — the build will succeed, but `backend/static/omni-agent-2.1.0-windows.exe` **already exists** (committed 2026-07-19, commit `7f05ab5`, pre-dating the persistence_detection/pii_scanner features that landed in 2.1.1/2.1.2). Two version-2.1.0 binaries with different capabilities and dependency stacks would collide on the exact same filename. Worse: even if the collision were resolved, `_LATEST_AGENT_VERSION` is already `"2.1.2"` — a rebuild that reports itself as `"2.1.0"` would look *older* than the current latest to the heartbeat comparison, and would never be auto-pushed to anyone (agents already on 2.1.2 would never be told to "downgrade" to 2.1.0).

**Why it happens:** The phase requirement text was written when "2.1.0" was the planned next version; feature work (persistence_detection, pii_scanner) landed and consumed 2.1.0/2.1.1/2.1.2 before this phase's dependency-modernization work got its own release.

**How to avoid:** Bump `Cargo.toml`'s `[package].version` to a genuinely new number not yet used anywhere in this repo's history — **`2.1.3`** is the correct next value (confirmed via `git log --all --diff-filter=A -- 'backend/static/omni-agent-*-windows.exe'`: 2.0.1 through 2.1.2 are all already committed, nothing after 2.1.2 exists yet). Update `_LATEST_AGENT_VERSION` in `agent_heartbeat_endpoints.py` to `"2.1.3"` in the same commit as the new binary.

**Warning signs:** `ls backend/static/omni-agent-*-windows.exe` shows a file matching whatever version the plan is about to build; `grep _LATEST_AGENT_VERSION backend/agent_heartbeat_endpoints.py` shows a value already ≥ the version the plan intends to ship.

### Pitfall 2: The `.b64` files may or may not be load-bearing — verify before skipping them

**What goes wrong:** Every prior release committed both `omni-agent-{version}-windows.exe` and `omni-agent-{version}.b64` (a base64-encoded copy, judging by the size ratio — roughly 4/3 the .exe size, consistent with base64 encoding overhead). No code path anywhere in `backend/*.py`, `agent/installer/*.ps1`, or `agent-install/*.nsi` was found (via grep) that reads a `.b64` file. If it's genuinely dead, skipping it saves effort; if some undiscovered path (e.g., a manual runbook, a browser-based install flow, or tooling outside this repo) depends on it, skipping it silently breaks that flow.

**How to avoid:** Grep one more time at plan/execute time (`grep -rn "\.b64" --include="*.py" --include="*.ps1" --include="*.nsi" --include="*.ts" --include="*.tsx" .`) and, if still nothing found, either skip generating it or generate it for parity/safety at near-zero cost (`base64 omni-agent.exe > omni-agent-2.1.3.b64`) — cheap insurance either way.

### Pitfall 3: The atomic-consume fix looks done — don't skip the index because the code "already looks correct"

**What goes wrong:** A quick read of `refresh_access_token` (correct `find_one_and_update` + `$setOnInsert` pattern, a reassuring comment claiming atomicity) could lead someone to conclude "SESS-01 is already fixed, nothing to do here" and move on to writing a regression test that (without a real race) will pass regardless of whether the index exists — giving false confidence.

**Why it happens:** The code's shape is genuinely correct MongoDB idiom; the bug is an *absence* (no index), not a wrong line of code, so `grep`-level or read-level review doesn't surface it — it requires cross-referencing `database.py`'s index list against the comment's claim, exactly as this research did.

**How to avoid:** Confirm the index doesn't exist (`grep -n "revoked_tokens" backend/database.py` — currently only shows a TTL index on `revoked_at`, nothing on `jti`), add it, and write the regression test against a **real** test-Mongo instance (not a mock, which would happily allow duplicate inserts and never expose this class of bug) so the test actually exercises the index's uniqueness constraint.

**Warning signs:** A "regression test" that mocks `db._db.revoked_tokens.find_one_and_update` instead of hitting a live Mongo test instance will pass whether or not the fix is applied — it tests the mock, not the actual atomicity guarantee.

### Pitfall 4: Pre-existing, unrelated test failure in the Rust-adjacent test suite — do not attempt to fix it under this phase

**What goes wrong:** `pytest backend/tests/test_rust_heartbeat_parity.py` (re-run this session) shows 1 failure: `test_rust02_and_rust03_db_calls` — asserts `agent_type == "rust"` on a `$push.evidence` array entry that currently has no `agent_type` key at all. This is unrelated to both RUST-01 (dependency bumps) and SESS-01 (auth) — it concerns evidence-writing metadata, not agent version or session/auth logic — and per multiple `STATE.md` session notes, this failure pre-dates this branch and was explicitly logged as "unrelated to this plan's files."

**How to avoid:** Confirm via `git blame`/the same STATE.md notes that this is pre-existing before investigating it as if it were caused by this phase's changes. Do not fold a fix for it into RUST-01/SESS-01's scope (per CLAUDE.md's "do what has been asked; nothing more, nothing less" and the phase's own D-03 narrow-scope instruction) — flag it for a separate cleanup task if desired.

## Runtime State Inventory

Not applicable in the strict "rename/refactor" sense (this phase is not renaming any identifiers), but the RUST-01 rollout genuinely does touch **live runtime state that lives outside git**, so the same discipline is warranted:

| Category | Items Found | Action Required |
|----------|-------------|------------------|
| Stored data | None — no database schema/collection renames in this phase. `revoked_tokens` gets a new index (additive, not a rename) — safe to add without a data migration; existing documents are unaffected by a new index. | None |
| Live service config | `_LATEST_AGENT_VERSION` in `agent_heartbeat_endpoints.py` is effectively live "registry" state controlling which agents get auto-updated — it is a hardcoded Python string constant checked into git (not an external DB/dashboard config), so a normal code commit is sufficient; no out-of-band config to touch. | Code edit only |
| OS-registered state | The already-registered `OmniAgent`/`OmniAgentRust` Windows services on endpoint machines are the actual target of the auto-push — they are **not** touched by this phase's git changes directly; they will only update themselves once they poll and receive the `agent_update` instruction. No manual re-registration needed — this is the whole point of the self-update capability. | None (self-updates via existing mechanism) |
| Secrets/env vars | None affected — `JWT_SECRET_KEY`/`agent_token` auth mechanisms are unchanged by either RUST-01 or SESS-01. | None |
| Build artifacts | `backend/static/omni-agent-*-windows.exe`/`.b64` files are committed binary build artifacts, not generated at deploy time — the new `2.1.3` build must be committed the same way prior versions were (see Pitfall 1/2). The Linux `cargo build --release --target x86_64-pc-windows-gnu` output under `agent-install/omni-agent-rs/target/` is gitignored working-tree state, not committed. | Build + commit the new versioned artifact |

## Common Pitfalls (SESS-01 continued)

### Pitfall 5 (SESS-01 detail): Two distinct, independently-verified 401 mechanisms — pick the primary fix deliberately

See "SESS-01 Root Cause" below for the full writeup; summarized here as a pitfall because conflating the two candidate mechanisms (or fixing only one while assuming it explains 100% of reports) is a real risk:

- **Mechanism A (backend, concrete code+schema gap):** missing unique index on `revoked_tokens.jti` — `[VERIFIED]` via direct read of `database.py`'s full index-creation block (no `jti` index anywhere) cross-referenced against the code comment's explicit claim that one exists.
- **Mechanism B (frontend, architectural, session-storage-scoped):** `sessionStorage` is per-browsing-context; a duplicated/cloned tab (Ctrl+T-duplicate or `window.open` from the same origin) starts with an *identical copy* of the original tab's `refresh_token`, then diverges. Each tab runs its own independent `startTokenRefreshCycle()` timer computed off the same original token's expiry — so both tabs' proactive-refresh timers fire around the same time, both racing to consume the *same* (at that point, stale-for-one-of-them) refresh token. `[VERIFIED]` via direct read of `services/apiService.ts` (the `refreshPromise` mutex is a module-level variable — scoped per JS execution context / per tab, does not span tabs).

## SESS-01 Root Cause (detailed)

**Investigation performed this session (code-grounded, not simulated):**
1. Read `authentication_endpoints.py::refresh_access_token` in full (lines 382–450).
2. Confirmed via `git log -p -L 382,451:backend/authentication_endpoints.py` that the atomic `find_one_and_update` pattern replaced a naive `find_one` (check) + `insert_one` (write) two-step — a textbook TOCTOU race — on 2026-06-04/05 (commits `ae3ca86`/`695f8ae`). So the *obvious* version of "double-consume race" (a non-atomic check-then-write) was already fixed over a month before this phase.
3. Cross-referenced the fix's own inline comment ("a unique index on jti guarantees only one request wins") against `database.py`'s full index-creation block. Found: `mongodb.db.revoked_tokens.create_index("revoked_at", expireAfterSeconds=86400)` is the *only* index on this collection — a TTL index on a different field, providing zero uniqueness guarantee on `jti`. **The atomicity the current code depends on for its "only one request wins" claim does not exist at the database layer.**
4. Verified `create_access_token`/`create_refresh_token` (`authentication_service.py:50-66`) each independently generate a fresh `uuid.uuid4().hex` for `jti` — no jti reuse/collision between access and refresh tokens, ruling out a simpler jti-collision explanation.
5. Read `services/apiService.ts`'s full refresh/auth-fetch flow (lines 80–247). Found a **correctly implemented** same-tab mutex (`refreshPromise` singleton + `_canAttemptRefresh()` backoff + `_expireSession()` on hard failure) — concurrent calls to `refreshAccessToken()` *within one tab* are properly de-duplicated onto a single in-flight HTTP request. This rules out same-tab double-firing as a cause.
6. Identified that `sessionStorage` (used for both `token` and `refresh_token`) is scoped per browsing context — a cloned/duplicated tab or a same-origin `window.open()` starts with a copy of the opener's `sessionStorage` at creation time, then the two copies diverge independently. Two tabs that both hold (initially) the same refresh token, each running their own independent proactive-refresh timer, is a plausible, reproducible mechanism for exactly the symptom reported ("intermittent 401 Unauthorized error during normal sessions").

**Recommended primary fix (in scope, narrow, matches D-03):**
```python
# backend/database.py — add next to the existing revoked_tokens TTL index
await mongodb.db.revoked_tokens.create_index("jti", unique=True, background=True)
```
This is the exact same pattern already used in this file for `software_inventory` (`create_index([("agent_id", 1), ("name", 1)], unique=True, background=True)`) — no new pattern, no new library, one line. It makes the existing `find_one_and_update` code's own stated guarantee actually true. `background=True` avoids blocking other operations while the index builds (matches the existing precedent, and the collection is TTL-bounded at 24h so it should be small).

**Open Question for the planner (Mechanism B):** Is the multi-tab/cloned-tab scenario in scope? Arguments for treating a minimal fix as still "the specific refresh-token race" (not the excluded "broader session-resilience hardening"): it's the *same* race (concurrent consumption attempts of one refresh token), just triggered cross-tab instead of same-process. A narrowly-scoped fix, if the planner/user wants one, would be a `storage` event listener in `apiService.ts` that lets a sibling tab adopt a freshly-rotated token pair written by another tab, instead of attempting its own (now-losing) refresh — this is meaningfully narrower than "silent retry-on-401" or "refresh-margin tuning," which D-03 explicitly excludes. Recommend surfacing this as an explicit yes/no decision during planning (or via `/gsd-discuss-phase` follow-up) rather than silently in-or-out of scope.

**Test/verification strategy (Claude's Discretion in CONTEXT.md, answered):** No existing test (`backend/tests/test_authentication.py`, `test_auth_mfa.py`, `test_api_key_auth.py`, `test_passkey_auth.py`) exercises `/auth/refresh` concurrency at all — confirmed via grep, only 2 refresh-related tests exist and both check token *shape* (`type` claim, 7-day expiry), not the consume-once behavior. Recommend a new test that:
- Uses a **real** test-Mongo instance (this repo has live-Mongo test precedent — e.g. `test_trust_center.py` — do not mock `db._db.revoked_tokens`, since a mock would trivially "pass" whether or not the unique index exists, defeating the point of the test).
- Issues a real login (or seeds a valid refresh token directly), then fires two concurrent `POST /api/auth/refresh` calls with the identical refresh token via `asyncio.gather(...)`.
- Asserts: exactly one call returns 200 with fresh `access_token`/`refresh_token`; the other returns 401; `db.revoked_tokens` contains exactly one document for that `jti` (proves the unique index actually rejected the duplicate insert attempt, not merely that application logic happened to serialize them).

## Code Examples

### RUST-01: TLS feature pin (the one Cargo.toml change needed)
```toml
# Source: this repo's Cargo.toml, current state (native-tls feature absent from reqwest today)
[dependencies]
reqwest = { version = "0.13", features = ["json", "blocking", "native-tls"] }
# tokio-tungstenite already correctly pins native-tls — no change needed there:
tokio-tungstenite = { version = "0.30", features = ["native-tls"] }
```

### RUST-01: version bump + release commit shape (matches the 6 prior releases in this repo's history)
```toml
# Cargo.toml
[package]
name = "omni-agent"
version = "2.1.3"   # was "2.1.2" — advance past every version already in backend/static/
```
```python
# backend/agent_heartbeat_endpoints.py, line ~132
_LATEST_AGENT_VERSION = "2.1.3"   # was "2.1.2"
```
```bash
# Build + commit, mirroring every prior release commit in this repo's git history
cd agent-install/omni-agent-rs
cargo build --release --target x86_64-pc-windows-gnu
cp target/x86_64-pc-windows-gnu/release/omni-agent.exe \
   ../../backend/static/omni-agent-2.1.3-windows.exe
```

### SESS-01: the missing index (the one database.py change needed)
```python
# Source: backend/database.py — add adjacent to the existing revoked_tokens TTL index
# (existing line, for context — do not remove):
await mongodb.db.revoked_tokens.create_index("revoked_at", expireAfterSeconds=86400)
# NEW — closes the atomicity gap refresh_access_token's own comment assumes exists:
await mongodb.db.revoked_tokens.create_index("jti", unique=True, background=True)
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|---------------|--------|
| `refresh_access_token`: `find_one` check then `insert_one` (TOCTOU race) | `find_one_and_update` + `$setOnInsert` + `upsert=True` (atomic *if* backed by a unique index) | Commit `695f8ae`/`ae3ca86`, 2026-06-04/05 | The obvious race was already closed over a month before this phase; the *remaining* gap is the missing index, a subtler defect requiring cross-file verification to find |
| reqwest implicit native-tls default (pre-0.13) | reqwest 0.13 defaults to rustls unless a TLS feature is explicitly selected | reqwest 0.13 release | Silent behavior change if not pinned — D-01 already resolved this |
| `serde_yaml` (archived) | `serde_norway` (maintained fork) | Already migrated in `src/config.rs`, uncommitted on this branch | No further action needed beyond committing |

**Deprecated/outdated:** `serde_yaml` and `serde_yml` (RUSTSEC-2025-0068) — both correctly avoided in the already-staged work; no action needed.

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | The `.b64` companion files in `backend/static/` are not read by any code path in this repo and can be treated as low-priority/optional to regenerate | Pitfall 2 | Low — if some external/undiscovered tool does read them, skipping generation only affects that tool, not the auto-push mechanism itself (which reads the `.exe` only) |
| A2 | The next available, never-before-used Rust agent version number is `2.1.3` | Pitfall 1, Code Examples | Low-medium — verified via exhaustive `git log --all --diff-filter=A` over `backend/static/omni-agent-*-windows.exe`, but if an uncommitted/unmerged branch elsewhere in the org already claimed 2.1.3, there'd be a future collision; easy to re-verify at execute time with one `ls`/`git log` command |
| A3 | The multi-tab/cloned-tab sessionStorage divergence (Mechanism B) is a real, reproducible contributor to the reported "intermittent 401" symptom, not just a theoretical possibility | SESS-01 Root Cause | Medium — this is inferred from code structure (sessionStorage semantics + independent per-tab timers), not from a live reproduction or user telemetry; the planner should treat it as a secondary/optional fix, not assume it explains every reported instance |

## Open Questions

1. **Is Mechanism B (multi-tab session divergence) in scope for SESS-01, or purely Mechanism A (missing index)?**
   - What we know: Both are real, code-verified gaps that could each independently produce "intermittent 401 during normal sessions." Mechanism A is unambiguously in scope (it's literally the "refresh-token double-consume race" the HANDOFF task named). Mechanism B is a plausible *additional* contributor.
   - What's unclear: Whether the actual field-reported symptom (whatever prompted HANDOFF task 10) was ever correlated with multi-tab usage. No telemetry/bug-report artifact was found in this repo to confirm or rule this out.
   - Recommendation: Ship Mechanism A's fix unconditionally (near-zero risk, directly matches the requirement). Flag Mechanism B explicitly to the user during planning/discussion as an optional, narrowly-scoped follow-on (a `storage`-event cross-tab token sync) — let the user decide if it's in scope under D-03's "if investigation surfaces a different/additional defect, fix that too" allowance, rather than silently including or excluding it.

2. **Are the `.b64` files in `backend/static/` still needed?**
   - What we know: Every prior release committed one; no code path reads one.
   - What's unclear: Whether an external tool, runbook, or manual process outside this repo depends on them.
   - Recommendation: Ask the user, or generate one anyway (near-zero cost: `base64 omni-agent.exe > omni-agent-2.1.3.b64`) for parity/safety rather than spending time investigating further.

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| `cargo` (Rust toolchain) | RUST-01 build | Yes | 1.97.0 | — |
| `rustc` | RUST-01 build | Yes | 1.97.0 | — |
| `x86_64-pc-windows-gnu` rustup target | RUST-01 cross-compile | Yes (`rustup target list --installed` confirms it) | — | — |
| `x86_64-w64-mingw32-gcc` (mingw cross-linker) | RUST-01 cross-compile | Yes (`/usr/bin/x86_64-w64-mingw32-gcc`) | — | — |
| `makensis` (NSIS) | Fresh-install EXE packaging (`agent_rust_builder.py`, not required for the auto-push path itself) | Yes (`/usr/bin/makensis`) | — | — |
| `mongod` | SESS-01 test verification, general backend runtime | Yes, running (pid confirmed) | — | — |
| `backend/venv/bin/pytest` | SESS-01 regression test | Yes | pytest 9.1.0 (per last run) | — |
| Node/npm | Frontend build (if Mechanism B fix touches `apiService.ts`) | Yes | node v20.20.2, npm 10.8.2 | — |

**Missing dependencies with no fallback:** none — everything both tracks need is already installed in this environment.

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework (Python/backend) | pytest 9.1.0 + pytest-asyncio (`asyncio_mode = auto`) |
| Config file | `pytest.ini` (repo root) |
| Framework (Rust) | **None exists** — `grep -rln "#\[test\]\|#\[cfg(test)\]" agent-install/omni-agent-rs/src/*.rs` returns zero files. `cargo check`/`cargo build --release` are the only automated gates for the Rust side today. |
| Quick run command (backend) | `cd backend && venv/bin/python -m pytest tests/test_authentication.py -q` |
| Quick run command (Rust) | `cd agent-install/omni-agent-rs && cargo check --offline` |
| Full suite command (backend) | `cd backend && venv/bin/python -m pytest -q` (baseline per STATE.md: ~1104 passed / 23 skipped / 2 pre-existing unrelated failures as of the last full run) |
| Full suite command (Rust) | `cd agent-install/omni-agent-rs && cargo build --release --target x86_64-pc-windows-gnu` |

### Phase Requirements → Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| RUST-01 | Crate bumps compile clean with TLS feature pinned | build/smoke | `cargo check --offline` | ✅ (no new file needed — already verifiable) |
| RUST-01 | Cross-compiled Windows binary produces a valid PE, correct version string | build/smoke | `cargo build --release --target x86_64-pc-windows-gnu` then inspect `CARGO_PKG_VERSION` embed | ✅ (no new file needed) |
| RUST-01 | Heartbeat auto-push actually fires for an agent reporting the old version | integration, manual-only | No automated harness exists for live heartbeat→instruction→self-update round-trip (requires a running Windows endpoint) | ❌ — Wave 0 gap, but likely acceptable as manual-only given no Windows test runner exists in this Linux sandbox |
| SESS-01 | Concurrent refresh: exactly one of two simultaneous `/refresh` calls with the same token succeeds | unit/integration | `pytest backend/tests/test_authentication.py -k concurrent_refresh -x` (new test, name illustrative) | ❌ Wave 0 gap — see below |
| SESS-01 | `revoked_tokens.jti` unique index actually exists and rejects duplicate inserts | integration | Same new test as above, or a dedicated index-assertion test hitting real Mongo | ❌ Wave 0 gap |

### Sampling Rate
- **Per task commit:** `cargo check --offline` (Rust track) / `pytest backend/tests/test_authentication.py -q` (auth track)
- **Per wave merge:** `cargo build --release --target x86_64-pc-windows-gnu` (Rust) / full backend suite (auth)
- **Phase gate:** Both full suites green (or only the 2 pre-existing, documented-unrelated backend failures) before `/gsd-verify-work`

### Wave 0 Gaps
- [ ] New test file/test case for concurrent `/refresh` race — likely added to `backend/tests/test_authentication.py` (or a new `test_auth_refresh_race.py` if it stays under the 500-line CLAUDE.md limit better as its own file — `test_authentication.py` is currently well under 500 lines, so adding to it is fine unless the new test needs substantial live-Mongo fixture scaffolding not already present there).
- [ ] No Rust unit-test framework exists — not a gap this phase needs to close (RUST-01 is a pure dependency/build task with no new logic to unit-test); `cargo check`/`cargo build` remain the correct automated gate.

## Security Domain

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-------------------|
| V2 Authentication | Yes (SESS-01) | JWT-based session tokens (`authentication_service.py`), already HS256-only enforced (`_ALLOWED_JWT_ALGORITHMS`), already blocks startup without `JWT_SECRET_KEY` outside dev — unaffected by this phase, existing controls remain in place |
| V3 Session Management | Yes (SESS-01) — this **is** the category the fix lives in | Single-use refresh-token rotation via `jti` tracking — the missing unique index is precisely a V3 gap (session token reuse prevention was intended but not fully enforced); adding it directly strengthens V3 compliance, no new control needed beyond the index itself |
| V4 Access Control | No direct change | Unaffected — RBAC/tenant-scoping logic untouched by either RUST-01 or SESS-01 |
| V5 Input Validation | Marginally (RUST-01) | `agent_update.rs`'s existing PE-header + minimum-size validation on downloaded binaries (already present, unmodified by this phase) is the relevant control — no new input-validation surface introduced |
| V6 Cryptography | No | TLS backend choice (D-01, `native-tls`) is a transport-security decision, not a cryptographic-primitive decision — reqwest/native-tls delegates to the OS cert store, never hand-rolled |

### Known Threat Patterns for this stack

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|----------------------|
| Refresh-token replay / reuse after rotation | Spoofing / Elevation of Privilege | Single-use `jti` enforcement via unique index (this phase's fix) — without it, a captured-but-rotated refresh token could theoretically still be replayed if the attacker's request races the legitimate holder's, since without the index both could "succeed" |
| MITM on agent update download (compromised/spoofed update server) | Tampering | Already mitigated: `agent_update.rs` validates the response is a real Windows PE (MZ header + minimum size) before ever writing/executing it, and downloads are Bearer-token-authenticated (`cfg.agent_token`) — unaffected, unmodified by this phase; `native-tls`/OS cert store (D-01) is the relevant transport-layer control, already the existing/intended behavior |
| TLS downgrade / cert-validation bypass from an unintended default TLS backend | Tampering / Information Disclosure | D-01's explicit `native-tls` feature pin — prevents reqwest 0.13's new implicit rustls default from silently changing the trust-anchor behavior in TLS-inspecting corporate-proxy environments |

## Sources

### Primary (HIGH confidence)
- Direct source reads, this repository, branch `feat/rust-agent-2.1.0-and-fixes`, 2026-07-20: `agent-install/omni-agent-rs/Cargo.toml`, `Cargo.lock`, `src/config.rs`, `src/capabilities/agent_update.rs`, `src/instructions.rs`, `src/heartbeat.rs`, `src/registration.rs`; `backend/agent_heartbeat_endpoints.py`, `backend/agent_tasks_endpoints.py`, `backend/agent_download_endpoints.py`, `backend/agent_rust_builder.py`, `backend/update_endpoints.py`, `backend/authentication_endpoints.py`, `backend/authentication_service.py`, `backend/database.py`, `services/apiService.ts`, `backend/tests/test_authentication.py`, `backend/tests/test_rust_heartbeat_parity.py`, `backend/tests/conftest.py`.
- Live command execution, this session: `cargo check --offline` (agent-install/omni-agent-rs), `git status`/`git diff HEAD`/`git log -p` (multiple files), `git log --all --diff-filter=A -- 'backend/static/omni-agent-*-windows.exe'`, `ls -la backend/static/`, `pytest backend/tests/test_rust_heartbeat_parity.py -q`, environment probes (`cargo --version`, `rustc --version`, `rustup target list --installed`, `which x86_64-w64-mingw32-gcc`, `which makensis`, `which mongod`/`pgrep mongod`).
- `.planning/research/STACK.md`, `.planning/research/PITFALLS.md`, `.planning/research/ARCHITECTURE.md` — milestone-level research from the same day, already HIGH confidence, cross-referenced rather than re-derived.
- `.planning/phases/40-rust-agent-modernization-session-reliability/40-CONTEXT.md` — locked decisions D-01/D-02/D-03.
- `.planning/REQUIREMENTS.md`, `.planning/STATE.md` — requirement text, project history, prior session notes on the pre-existing `test_rust_heartbeat_parity.py` failure.

### Secondary (MEDIUM confidence)
- None used directly for this phase — no external web research was performed (all `.planning/config.json` search-provider flags are `false`, and the questions in scope were answerable authoritatively from this repo's own source/git history, which is a stronger source than external docs for "what does this codebase's pipeline actually do").

### Tertiary (LOW confidence)
- None.

## Metadata

**Confidence breakdown:**
- RUST-01 stack/versions: HIGH — locally verified `cargo check --offline`, cross-referenced against milestone STACK.md
- RUST-01 rollout mechanism: HIGH — fully traced end-to-end through actual source (heartbeat → instruction → agent_update.rs → update_endpoints.py → backend/static/), confirmed against 6 prior real release commits in git history
- RUST-01 versioning correction (2.1.0 → 2.1.3): HIGH — directly confirmed via `Cargo.toml`, `_LATEST_AGENT_VERSION`, and `git log --diff-filter=A` over `backend/static/`
- SESS-01 Mechanism A (missing unique index): HIGH — directly confirmed via `database.py`'s full index list plus the code's own comment claiming otherwise
- SESS-01 Mechanism B (multi-tab): MEDIUM — code-structure-verified and plausible, but not confirmed via live reproduction or field telemetry; correctly flagged as an Open Question rather than asserted as the/a confirmed cause

**Research date:** 2026-07-20
**Valid until:** Short-lived — this research is tied to exact current file states (`Cargo.toml` version, `_LATEST_AGENT_VERSION` value, `backend/static/` directory contents) that will change the moment any part of this phase is executed. If planning is delayed more than a few days, re-verify the version-number findings (Pitfall 1) before trusting them, since another commit could land in the meantime.

---
*Phase: 40-rust-agent-modernization-session-reliability*
*Research completed: 2026-07-20*
