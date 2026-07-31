# Phase 40: Rust Agent Modernization & Session Reliability - Pattern Map

**Mapped:** 2026-07-20
**Files analyzed:** 5 (2 Rust/config edits, 2 Python edits, 1 new test)
**Analogs found:** 5 / 5

This phase is almost entirely "edit existing files, following the exact pattern already used 6 prior times" — there is very little genuinely new code. Every pattern assignment below points to an analog *within the same file being edited* (or an immediately adjacent one), because RESEARCH.md already identified the precise existing precedent for each change.

## File Classification

| New/Modified File | Role | Data Flow | Closest Analog | Match Quality |
|--------------------|------|-----------|-----------------|----------------|
| `agent-install/omni-agent-rs/Cargo.toml` | config | request-response (HTTP client feature flags) | `agent-install/omni-agent-rs/Cargo.toml` line 31 (`tokio-tungstenite` already pins `native-tls`) | exact (same file, sibling line) |
| `backend/agent_heartbeat_endpoints.py` (version constant) | config | request-response | `backend/agent_heartbeat_endpoints.py` line 132 itself, prior commit `fc0d41c` | exact (identical one-line pattern, repeated 6 times in git history) |
| `backend/database.py` (index block) | model | CRUD (index/schema definition) | `backend/database.py` lines 280-283 (`software_inventory` unique compound index) | exact — same file, same pattern shape (`create_index(..., unique=True, background=True)`) |
| `backend/static/omni-agent-2.1.3-windows.exe` (+ optional `.b64`) | build artifact | file-I/O | prior release artifacts `backend/static/omni-agent-2.1.2-windows.exe` | exact (build-and-commit process, not source code) |
| `backend/tests/test_authentication.py` (new concurrent-refresh test, or new `test_auth_refresh_race.py`) | test | CRUD / integration (live Mongo) | `backend/tests/test_evidence_review.py` lines 406-459 (`test_evidence_propagation_query_does_not_corrupt_unrelated_evidence_item`) | role-match — only existing live-Mongo (non-mocked) regression test pattern in the test suite |

## Pattern Assignments

### `agent-install/omni-agent-rs/Cargo.toml` (config, D-01 TLS pin)

**Analog:** same file, line 31 — `tokio-tungstenite` already correctly pins `native-tls`

**Current state** (line 18, to be edited):
```toml
reqwest = { version = "0.13", features = ["json", "blocking"] }
```

**Sibling pattern to copy the shape of** (line 31, already correct):
```toml
tokio-tungstenite = { version = "0.30", features = ["native-tls"] }
```

**Target edit:**
```toml
reqwest = { version = "0.13", features = ["json", "blocking", "native-tls"] }
```

**Also required in the same commit** (line 3):
```toml
[package]
version = "2.1.2"   # -> bump to "2.1.3" — see Pitfall 1 in RESEARCH.md; do NOT reuse "2.1.0"
```

---

### `backend/agent_heartbeat_endpoints.py` (config/service, version-gate constant)

**Analog:** same file, line 132, following the exact pattern of prior commit `fc0d41c` (2026-07-16)

**Historical diff pattern to replicate** (from `git log -p`):
```python
# commit fc0d41c — 2026-07-16 21:32
-    _LATEST_AGENT_VERSION = "2.1.1"
+    _LATEST_AGENT_VERSION = "2.1.2"
```

**Target edit (this phase):**
```python
_LATEST_AGENT_VERSION = "2.1.3"   # was "2.1.2"
```

**Rule:** This edit MUST land in the same commit as the new `backend/static/omni-agent-2.1.3-windows.exe` artifact — every one of the last 3 version bumps did both in one commit (verified via `git log -p`).

---

### `backend/database.py` (model, missing unique index — SESS-01 Mechanism A)

**Analog:** same file, lines 280-283 — `software_inventory` compound unique index, the only other `unique=True, background=True` precedent in the file

**Imports pattern:** none needed — this is inside the existing `async def` that already has `mongodb.db` in scope (see surrounding lines 224-303).

**Core pattern to copy** (lines 280-283):
```python
# software_inventory: compound unique index so per-heartbeat upserts are O(1) not O(n)
await mongodb.db.software_inventory.create_index(
    [("agent_id", 1), ("name", 1)], unique=True, background=True
)
```

**Existing sibling index for the SAME collection, to place the new index next to** (line 297):
```python
# revoked_tokens: only needs to outlive the longest possible access-token TTL (24 h)
await mongodb.db.revoked_tokens.create_index("revoked_at", expireAfterSeconds=86400)
```

**Target new line (insert directly after line 297):**
```python
# revoked_tokens: unique index on jti enforces the single-use guarantee that
# refresh_access_token's find_one_and_update + $setOnInsert pattern depends on
# (SESS-01 — closes the gap between the code's comment and actual DB enforcement)
await mongodb.db.revoked_tokens.create_index("jti", unique=True, background=True)
```

**Do not modify** `backend/authentication_endpoints.py::refresh_access_token` (lines 415-437) — its `find_one_and_update`/`$setOnInsert` logic is already correct per RESEARCH.md; only the missing index needs to be added. Read the existing block for context before touching adjacent code:
```python
# backend/authentication_endpoints.py:415-437 (DO NOT CHANGE — for context only)
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

---

### `backend/static/omni-agent-2.1.3-windows.exe` (+ optional `.b64`) (build artifact, file-I/O)

**Analog:** prior release process (no source-code analog — this is a build+commit workflow, confirmed via `git log` over `backend/static/omni-agent-*-windows.exe`)

**Process to replicate:**
```bash
cd agent-install/omni-agent-rs
cargo build --release --target x86_64-pc-windows-gnu
cp target/x86_64-pc-windows-gnu/release/omni-agent.exe \
   ../../backend/static/omni-agent-2.1.3-windows.exe
# optional, cheap parity with prior releases (Pitfall 2 — verify grep first):
base64 backend/static/omni-agent-2.1.3-windows.exe > backend/static/omni-agent-2.1.3.b64
```

Verify `.b64` is still unused before generating it:
```bash
grep -rn "\.b64" --include="*.py" --include="*.ps1" --include="*.nsi" --include="*.ts" --include="*.tsx" .
```

---

### `backend/tests/test_authentication.py` (or new `test_auth_refresh_race.py`) (test, CRUD/integration)

**Analog:** `backend/tests/test_evidence_review.py` lines 406-459 — the only existing live-MongoDB (non-mocked) regression test in the suite; structurally required here because a mocked `find_one_and_update` would pass regardless of whether the unique index exists (RESEARCH.md Pitfall 3 explicitly warns against this).

**Imports/setup pattern** (from `test_evidence_review.py` lines 412-420):
```python
import motor.motor_asyncio

mongo_uri = os.environ.get("MONGODB_URI") or os.environ.get("MONGO_URI", "mongodb://localhost:27017")

async def _run():
    client = motor.motor_asyncio.AsyncIOMotorClient(
        mongo_uri, serverSelectionTimeoutMS=1500
    )
    try:
        await client.admin.command("ping")
    except Exception:
        client.close()
        import pytest
        if os.environ.get("CI"):
            pytest.fail(
                f"No live MongoDB reachable at {mongo_uri} for ... regression "
                f"test — CI environments must provide MONGODB_URI/MONGO_URI so "
                f"this test actually runs instead of silently skipping"
            )
        pytest.skip(f"No live MongoDB reachable at {mongo_uri} for ... regression test")
        return
```

**Cleanup pattern** (lines 461-463, adapt collection names to `revoked_tokens`):
```python
try:
    await motor_db.asset_compliance.delete_many({"tenantId": "tenant-cr01"})
    await motor_db.evidence_reviews.delete_many({"tenantId": "tenant-cr01"})
    ...
finally:
    await motor_db.asset_compliance.delete_many({"tenantId": "tenant-cr01"})
    await motor_db.evidence_reviews.delete_many({"tenantId": "tenant-cr01"})
```

**New logic this test needs (no direct analog — construct from RESEARCH.md's spec):**
```python
# 1. Ensure the jti-unique index actually exists on a real test-Mongo collection
#    (create it explicitly in test setup, mirroring database.py's new line, OR
#    call the real init_db()/create_indexes path if already exposed for tests).
# 2. Seed or mint one valid refresh token (reuse authentication_service.create_refresh_token).
# 3. Fire two concurrent POST /api/auth/refresh calls with the SAME token via
#    asyncio.gather(...) — using httpx.AsyncClient or FastAPI's async TestClient
#    against the real app, not a mock of authentication_endpoints.refresh_access_token.
# 4. Assert: exactly one 200 (fresh access_token/refresh_token), exactly one 401;
#    db.revoked_tokens has exactly ONE document for that jti (proves the unique
#    index rejected the duplicate insert, not just that app logic serialized them).
```

**Existing non-live companion tests for shape/naming conventions** (`test_authentication.py`, module-level fixture pattern, lines 8-21):
```python
import os
import sys
import importlib
import pytest
from unittest.mock import patch

@pytest.fixture(scope="module", autouse=True)
# ... module isolation fixture — see file for full body if adding to this file
# rather than creating a new test_auth_refresh_race.py
```

Existing refresh-token-related tests for context (do not duplicate, they test shape not concurrency):
```python
# test_authentication.py
def test_refresh_token_has_type_claim(self): ...   # line 243
def test_refresh_token_expiry_is_7_days(self): ...  # line 254
def test_jti_is_unique_across_tokens(self): ...      # line 131
```

**File placement decision:** `test_authentication.py` is well under the 500-line CLAUDE.md limit — adding the new test there is fine unless it needs substantial live-Mongo fixture scaffolding not already present, in which case create `backend/tests/test_auth_refresh_race.py` following `test_evidence_review.py`'s self-contained live-Mongo pattern.

---

## Shared Patterns

### Live-Mongo (non-mocked) regression test pattern
**Source:** `backend/tests/test_evidence_review.py` lines 406-459
**Apply to:** The new SESS-01 concurrent-refresh regression test — this is the ONLY correct pattern for testing a database-level uniqueness/atomicity guarantee; a mock-based test would pass unconditionally and give false confidence (explicitly warned against in RESEARCH.md Pitfall 3).

### `unique=True, background=True` index-creation pattern
**Source:** `backend/database.py` lines 280-283 (`software_inventory`)
**Apply to:** The new `revoked_tokens.jti` index — identical call shape, just a single-field key instead of a compound key.

### Version-bump-in-lockstep-with-artifact-commit pattern
**Source:** `backend/agent_heartbeat_endpoints.py` line 132 + `agent-install/omni-agent-rs/Cargo.toml` line 3 + `backend/static/omni-agent-{version}-windows.exe`, all three changed together in every prior release commit (verified via `git log -p`)
**Apply to:** RUST-01's version bump — all three files/artifacts must change in the same commit; the plan should treat this as one atomic unit of work, not three separate tasks.

## No Analog Found

None — every file in scope for this phase has a direct or near-direct analog already identified above. This phase's own RESEARCH.md notes the "hard part" (atomic consume logic, self-update pipeline) was already built correctly in prior sessions; the actual work is small, targeted edits to existing, well-precedented patterns.

## Metadata

**Analog search scope:** `agent-install/omni-agent-rs/Cargo.toml`, `backend/agent_heartbeat_endpoints.py`, `backend/database.py`, `backend/authentication_endpoints.py`, `backend/tests/test_authentication.py`, `backend/tests/test_evidence_review.py`, `backend/tests/test_rust_heartbeat_parity.py`, `backend/static/` (git history), `git log -p` over the above.
**Files scanned:** 8 direct reads + git log/grep searches (no additional analog search needed beyond what RESEARCH.md already pinpointed — this phase's research was unusually code-grounded, so pattern mapping mostly confirms and extracts exact line ranges rather than searching broadly).
**Pattern extraction date:** 2026-07-20
