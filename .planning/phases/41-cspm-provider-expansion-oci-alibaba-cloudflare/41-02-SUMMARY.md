---
phase: 41-cspm-provider-expansion-oci-alibaba-cloudflare
plan: 02
subsystem: infra
tags: [oci, cloudflare, alibaba-cloud, pip, backend-venv, cspm, supply-chain]

# Dependency graph
requires:
  - phase: 41-01
    provides: CSPM provider expansion research and plan scaffolding
provides:
  - "oci, cloudflare, and the 4 alibabacloud_* V2 SDK packages installed and importable in backend/venv"
  - "backend/requirements.txt pinned with alibabacloud_config20200907, alibabacloud_sas20181203, alibabacloud_tea_openapi, alibabacloud_credentials"
affects: [cspm-provider-expansion, oci-posture-ingest, alibaba-posture-ingest, cloudflare-posture-ingest]

# Tech tracking
tech-stack:
  added: [oci==2.182.0, cloudflare==5.5.0, alibabacloud_config20200907==4.2.3, alibabacloud_sas20181203==9.3.3, alibabacloud_tea_openapi==0.4.5, alibabacloud_credentials==1.0.10]
  patterns: ["Blocking human-verify checkpoint for SUS-flagged third-party packages before install (package-legitimacy gate)"]

key-files:
  created: []
  modified: [backend/requirements.txt]

key-decisions:
  - "Human verified all 4 SUS-flagged alibabacloud_* V2 SDK packages resolve to the official github.com/aliyun org before install (checkpoint approved)"
  - "Pinned cryptography==49.0.0 and pyOpenSSL==26.3.0 to resolve a transitive dependency conflict the oci install introduced (it downgraded both, breaking webauthn's hard >=49.0.0/>=26.3.0 requirement); verified alibabacloud_tea_openapi's stale cryptography<49.0.0 metadata pin is functionally compatible with 49.0.0 via a direct RSA sign/verify smoke test and full Client instantiation"

patterns-established: []

requirements-completed: [CSPM-02]

coverage:
  - id: D1
    description: "Four SUS-flagged alibabacloud_* V2 SDK packages human-verified as legitimate (official aliyun org) before install"
    requirement: CSPM-02
    verification:
      - kind: manual_procedural
        ref: "checkpoint:human-verify Task 1 — user reviewed independently-verified PyPI metadata for all 4 packages and replied approving install"
        status: pass
    human_judgment: false
  - id: D2
    description: "oci, cloudflare, and the 4 alibabacloud_* packages installed and importable in backend/venv; requirements.txt pinned"
    requirement: CSPM-02
    verification:
      - kind: other
        ref: "backend/venv/bin/python -c \"import oci, cloudflare, alibabacloud_config20200907, alibabacloud_sas20181203, alibabacloud_tea_openapi, alibabacloud_credentials\" — exits 0"
        status: pass
      - kind: unit
        ref: "backend/tests/test_passkey_auth.py — 6/6 pass (regression check after cryptography/pyOpenSSL version resolution)"
        status: pass
    human_judgment: false

duration: 15min
completed: 2026-07-21
status: complete
---

# Phase 41 Plan 02: CSPM Cloud SDK Package Gate + Install Summary

**Human-verified and installed all 7 cloud SDK packages (oci, cloudflare, 4 new alibabacloud_* V2 SDKs) into backend/venv, resolving a transitive cryptography/pyOpenSSL conflict with webauthn along the way.**

## Performance

- **Duration:** ~15 min (this continuation session; Task 1 checkpoint was reached and resolved in a prior session)
- **Completed:** 2026-07-21T01:01:41+05:30
- **Tasks:** 2/2
- **Files modified:** 1 (`backend/requirements.txt`)

## Accomplishments
- Task 1 (blocking human-verify checkpoint): user confirmed all 4 SUS-flagged `alibabacloud_*` V2 SDK packages (`alibabacloud_config20200907`, `alibabacloud_sas20181203`, `alibabacloud_tea_openapi`, `alibabacloud_credentials`) resolve to the official `github.com/aliyun/*` org via independently-verified PyPI metadata — approved.
- Task 2: added 4 new pins to `backend/requirements.txt` and installed all 7 cloud SDK packages (`oci`, `cloudflare`, `aliyun-python-sdk-core-v3` was already pinned, plus the 4 new alibabacloud packages) into `backend/venv`. All packages import cleanly.
- Discovered and fixed (Rule 1) a transitive dependency conflict the `oci` install caused: it silently downgraded `cryptography` to 48.0.1 and `pyOpenSSL` to 26.2.0, which broke `webauthn`'s hard `cryptography>=49.0.0`/`pyOpenSSL>=26.3.0` requirement (Phase 34 passkey auth). Re-pinned `cryptography==49.0.0`/`pyOpenSSL==26.3.0`, which satisfies both `oci` (`<50.0.0`) and `webauthn`; confirmed `alibabacloud_tea_openapi`'s pip-metadata pin of `cryptography<49.0.0` is stale/overly conservative — the actual cryptography APIs it imports (`hashes`, `padding`, `load_pem_private_key`) are stable across 48→49, verified via a direct RSA sign/verify smoke test and full `alibabacloud_tea_openapi.client.Client` instantiation. Re-ran `backend/tests/test_passkey_auth.py` (6/6 pass) to confirm no regression.

## Task Commits

Each task was committed atomically:

1. **Task 1: Human-verify the 4 SUS Alibaba V2 SDK packages before install** - checkpoint, no code changes/commit (approved in prior session, resolved at the start of this continuation)
2. **Task 2: Pin and install cloud SDK packages into backend/venv** - `66233c6` (feat)

**Plan metadata:** (this commit, following)

## Files Created/Modified
- `backend/requirements.txt` - Added 4 new pins: `alibabacloud_config20200907>=4.2.3`, `alibabacloud_sas20181203>=9.3.3`, `alibabacloud_tea_openapi>=0.4.5`, `alibabacloud_credentials>=1.0.10`, placed next to the existing `oci`/`aliyun-python-sdk-core-v3`/`cloudflare` pins. The `aliyun-python-sdk-core-v3` pin was left untouched (backs the existing SIEM path).

## Decisions Made
- All 4 SUS-flagged `alibabacloud_*` packages verified legitimate (official aliyun org) before install — no substitutions, no auto-approval bypass.
- Resolved the cryptography/pyOpenSSL/webauthn/alibabacloud_tea_openapi four-way pin conflict by choosing `cryptography==49.0.0`/`pyOpenSSL==26.3.0` (satisfies oci's `<50.0.0` and webauthn's `>=49.0.0`/`>=26.3.0` hard requirements) over downgrading, since `alibabacloud_tea_openapi`'s `<49.0.0` upper bound was confirmed functionally unnecessary (stable cryptography.hazmat APIs, verified via a live sign/verify roundtrip) rather than a real incompatibility.
- Did not pin `cryptography`/`pyOpenSSL` explicitly in `requirements.txt` — left them to resolve naturally from the installed set; `pip check` still surfaces the `alibabacloud-tea-openapi` metadata warning (documented as a known, functionally-verified-safe false positive) plus one pre-existing unrelated `opentelemetry-sdk` version mismatch.
- A pre-existing, unrelated uncommitted change to `backend/requirements.txt` (`anthropic>=0.28.0,<2.0.0` → `anthropic==0.28.0`) was found already present in the working tree before this task started. Left untouched and excluded from this task's commit via `git add -p` (out of scope per the deviation-rules scope boundary — not caused by this task).

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Resolved cryptography/pyOpenSSL downgrade breaking webauthn**
- **Found during:** Task 2 (installing oci/cloudflare/alibabacloud packages)
- **Issue:** `pip install oci ...` silently resolved and installed `cryptography==48.0.1` and `pyOpenSSL==26.2.0` (oci's dependency resolution picked versions satisfying its own bounds without regard for other installed packages), which violated `webauthn==3.0.0`'s hard requirement of `cryptography>=49.0.0`/`pyOpenSSL>=26.3.0` — a real, functioning feature (Phase 34 passkey auth) would have broken at import/runtime.
- **Fix:** Explicitly installed `cryptography==49.0.0` and `pyOpenSSL==26.3.0`, the highest mutually-compatible versions satisfying oci's `<50.0.0` cap and webauthn's `>=49.0.0`/`>=26.3.0` floor. Verified `alibabacloud_tea_openapi`'s resulting `pip check` warning (`cryptography<49.0.0` pin violated) is a stale/overly-conservative metadata bound, not a real incompatibility, via a direct functional test of the exact cryptography APIs it imports (RSA key load, sign, verify) plus full `Client` instantiation.
- **Files modified:** None beyond the venv install (no requirements.txt pin added for cryptography/pyOpenSSL — left to natural resolution).
- **Verification:** `backend/venv/bin/python -c "import oci, cloudflare, alibabacloud_config20200907, alibabacloud_sas20181203, alibabacloud_tea_openapi, alibabacloud_credentials"` exits 0; `backend/tests/test_passkey_auth.py` 6/6 pass (webauthn regression check).
- **Committed in:** `66233c6` (Task 2 commit)

---

**Total deviations:** 1 auto-fixed (1 bug — dependency conflict introduced by this task's own install)
**Impact on plan:** Necessary for correctness — an unresolved conflict would have silently broken Phase 34 passkey auth the next time cryptography was touched. No scope creep; fix was confined to package versions, not code.

## Issues Encountered
None beyond the dependency conflict documented above.

## User Setup Required
None - no external service configuration required beyond the completed Task 1 human-verification gate (already resolved).

## Next Phase Readiness
- All 7 cloud SDKs (oci, cloudflare, aliyun-python-sdk-core-v3, 4x alibabacloud_* V2) are installed and importable in `backend/venv` — ready for the OCI/Alibaba/Cloudflare posture-ingest implementation plans (CSPM-02/CSPM-01/CSPM-03) that consume them.
- No blockers. `pip check` shows two pre-existing/verified-safe warnings (alibabacloud_tea_openapi's stale cryptography pin, unrelated opentelemetry-sdk version mismatch) — neither blocks further work.

---
*Phase: 41-cspm-provider-expansion-oci-alibaba-cloudflare*
*Completed: 2026-07-21*
