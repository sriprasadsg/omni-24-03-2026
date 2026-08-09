---
phase: 46-public-ip-asn-vpn-enrichment-location-history-audit
plan: 01
subsystem: api
tags: [geoip, maxminddb, asn, vpn-detection, bisect, ipaddress]

# Dependency graph
requires: []
provides:
  - "backend/agent_asn_service.py — lazy GeoLite2-ASN + X4BNet VPN CIDR heuristic lookup module, clone of geoip_service.py's pattern"
  - "backend/data/vpn_ranges/x4bnet_vpn_ipv4.txt — vendored, source-controlled X4BNet public-VPN IPv4 CIDR snapshot"
  - "GEOIP_ASN_DB_PATH env var contract (D-11)"
  - ".gitignore fix allowing backend/data/vpn_ranges/ to be tracked despite the blanket data/ ignore rule"
affects: [47-agent-scoped-geo-security-detectors, 46-02, 46-03]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Second independent lazy-singleton resource in one module (thread-locked, single-attempt-then-cache, never retries) — same shape as geoip_service._get_reader but for a bundled CIDR-range text file instead of an .mmdb"
    - "stdlib bisect over sorted (start_int, end_int) tuples for O(log n) CIDR-range membership testing"

key-files:
  created:
    - backend/agent_asn_service.py
    - backend/tests/test_agent_asn_service.py
    - backend/data/vpn_ranges/x4bnet_vpn_ipv4.txt
  modified:
    - .gitignore

key-decisions:
  - "Reused geoip_service._is_public() directly via import rather than duplicating the 6-line private/public IP classifier"
  - "lookup() omits the 'asn' key entirely (rather than setting it to None) when the ASN reader is absent or the record lacks both fields — keeps the never-raises contract's output shape minimal and matches the plan's acceptance criteria (assert 'asn' not in result)"
  - "vpn_heuristic key is only included in the result dict when the VPN-ranges file was actually loaded (ranges list non-empty) — this is how lookup() distinguishes 'file present, IP just isn't in any range' (returns explicit False) from 'file absent entirely' (contributes nothing, falls through to None if ASN was also absent)"

requirements-completed: [GAUD-01]

coverage:
  - id: D1
    description: "agent_asn_service.lookup() gracefully degrades to None (never raises) when both the GeoLite2-ASN .mmdb and the X4BNet snapshot are absent"
    requirement: "GAUD-01"
    verification:
      - kind: unit
        ref: "backend/tests/test_agent_asn_service.py::TestBothAbsent"
        status: pass
    human_judgment: false
  - id: D2
    description: "lookup() returns vpn_heuristic=true for an IP inside a bundled CIDR range and vpn_heuristic=false for one outside every range"
    requirement: "GAUD-01"
    verification:
      - kind: unit
        ref: "backend/tests/test_agent_asn_service.py::TestVpnRangeMembership"
        status: pass
    human_judgment: false
  - id: D3
    description: "lookup() returns None for private/loopback/reserved IPs without ever touching the ASN reader or VPN-range loader"
    requirement: "GAUD-01"
    verification:
      - kind: unit
        ref: "backend/tests/test_agent_asn_service.py::TestPrivateIp"
        status: pass
    human_judgment: false
  - id: D4
    description: "X4BNet VPN CIDR snapshot is bundled as a source-controlled repo file (not runtime-fetched); no network calls anywhere in the module"
    requirement: "GAUD-01"
    verification:
      - kind: unit
        ref: "grep -nE 'requests\\.|httpx|urllib|aiohttp|socket\\.' backend/agent_asn_service.py (returns nothing)"
        status: pass
    human_judgment: false

duration: ~20min
completed: 2026-07-29
status: complete
---

# Phase 46 Plan 01: ASN/VPN Enrichment Foundation Summary

**`agent_asn_service.py` — GeoLite2-ASN + bundled X4BNet VPN CIDR heuristic lookup, cloned from `geoip_service.py`'s lazy-singleton pattern, with a real vendored 2000+-CIDR VPN snapshot committed to the repo**

## Performance

- **Duration:** ~20 min
- **Completed:** 2026-07-29
- **Tasks:** 2/2 completed
- **Files modified:** 4 (3 created, 1 modified — `.gitignore`)

## Accomplishments
- `backend/agent_asn_service.py`: `lookup(ip)` returns `{"asn": {"number", "org"}, "vpn_heuristic": bool}` or `None`, never raises, reads `GEOIP_ASN_DB_PATH` (D-11), reuses `geoip_service._is_public` for the private/public gate
- Second independent lazy resource `_load_vpn_ranges()` + `_is_known_vpn_range()` — bisect-based O(log n) CIDR membership test over the bundled X4BNet snapshot
- `backend/data/vpn_ranges/x4bnet_vpn_ipv4.txt` vendored with source repo/commit/date recorded in a header comment (T-46-01-A mitigation) — a real ~2100-CIDR snapshot, not a placeholder
- `backend/tests/test_agent_asn_service.py`: 10 hermetic tests covering none/empty input, private-IP skip (with spy assertions proving no reader/loader access), ASN-absent+VPN-present degrade, in-range/out-of-range membership, and both-absent graceful degrade with warning logging
- Fixed a `.gitignore` gap that would have silently kept the vendored snapshot untracked forever, defeating its entire "bundled for air-gapped deployment" purpose

## Task Commits

Each task was committed atomically:

1. **Task 1: Vendor X4BNet snapshot + write graceful-degrade test scaffold** - `fdcdd9c` (test)
2. **Task 2: Implement agent_asn_service.py (ASN reader + X4BNet VPN heuristic)** - `2343849` (feat)

_Note: Both tasks are tagged `tdd="true"`; `fdcdd9c` is the RED-equivalent scaffold commit (test file + fixture data), `2343849` is GREEN (all 10 tests pass)._

## Files Created/Modified
- `backend/agent_asn_service.py` - ASN + VPN-heuristic lookup module (197 lines)
- `backend/data/vpn_ranges/x4bnet_vpn_ipv4.txt` - vendored X4BNet public-VPN IPv4 CIDR snapshot (~2100 CIDRs, source commit dea5d13a62239494ce6428eb826b80c3571c1448 dated 2026-07-29)
- `backend/tests/test_agent_asn_service.py` - hermetic test suite, 10 tests
- `.gitignore` - scoped re-include for `backend/data/vpn_ranges/` under the blanket `data/` ignore rule

## Decisions Made
- Reused `geoip_service._is_public()` via direct import rather than duplicating the classifier (key_link in plan's must_haves)
- `lookup()`'s result dict only ever contains the `"asn"` key when a record with at least one of `autonomous_system_number`/`autonomous_system_organization` was actually resolved — never a placeholder `None` value under that key
- `lookup()`'s result dict only ever contains `"vpn_heuristic"` when the VPN-ranges file was actually loaded (non-empty `ranges` list) — this is the mechanism that distinguishes "loaded file, IP just isn't in any range" (explicit `False`) from "file entirely absent" (key omitted, falls through to `None` overall if ASN was also absent)

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Prior uncommitted draft of `agent_asn_service.py` had undefined module globals**
- **Found during:** Task 2 (before writing the final module)
- **Issue:** The working tree already contained an untracked, in-progress draft of `agent_asn_service.py` and `test_agent_asn_service.py` from an earlier interrupted session. The draft's `_load_vpn_ranges()` referenced `_vpn_ranges`, `_vpn_load_attempted`, `_vpn_warned_missing`, `_vpn_ranges_lock` via `global` statements, but none of these were ever declared at module scope — causing a `NameError` on first real invocation (5 of 10 tests failed with `NameError: name '_vpn_load_attempted' is not defined`).
- **Fix:** Rewrote the module cleanly with all lazy-load state (`_vpn_ranges`, `_vpn_ranges_lock`, `_vpn_load_attempted`, `_vpn_warned_missing`) properly declared at module scope, mirroring the ASN reader's own already-correct pattern.
- **Files modified:** `backend/agent_asn_service.py`
- **Verification:** `pytest tests/test_agent_asn_service.py -q` → all pass
- **Committed in:** `2343849` (Task 2 commit)

**2. [Rule 1 - Bug] Plan's suggested RFC 5737 test fixture CIDRs are misclassified as private by Python's stdlib**
- **Found during:** Task 2, while debugging 3 remaining test failures after the NameError fix
- **Issue:** The plan (and RESEARCH.md's code example) suggested using the RFC 5737 documentation ranges `203.0.113.0/24` and `198.51.100.0/24` as fixture "known VPN" CIDRs. Python's `ipaddress.IPv4Address.is_private` classifies these TEST-NET blocks as `is_private=True` (they're in CPython's internal `_private_networks` table alongside RFC 1918 ranges), so `geoip_service._is_public()` — which this module correctly reuses per the plan's own key_link requirement — filtered every fixture IP out before the VPN-range lookup ever ran, silently defeating every assertion built on them (`result is None` when the test expected a populated dict).
- **Fix:** Swapped the fixture CIDRs to two genuinely public, non-special-purpose ranges (`93.184.216.0/24`, `185.199.108.0/24`) and updated the corresponding test IPs (`93.184.216.42`, `185.199.108.7`) across all 4 affected test cases (asn-absent-vpn-present, in-range membership, both-absent-with-warning, both-absent-never-raises).
- **Files modified:** `backend/tests/test_agent_asn_service.py`
- **Verification:** All 10 tests pass; confirmed via a direct `ipaddress` module check that the new fixture ranges are not private/reserved/loopback/link-local/multicast
- **Committed in:** `fdcdd9c` (Task 1 commit)

**3. [Rule 2 - Missing Critical] `.gitignore`'s blanket `data/` rule silently excluded the vendored VPN snapshot from version control**
- **Found during:** Task 1, before attempting to stage the snapshot file
- **Issue:** `.gitignore` line 57 (`data/`, no leading slash) ignores any directory named `data` at any depth, which matches `backend/data/` and everything under it — including the newly-vendored `x4bnet_vpn_ipv4.txt`. This is a source-controlled, vendored reference file (not runtime output), and the whole point of "bundling" it (D-12, air-gapped deployment) is defeated if it can never be committed. `git check-ignore -v` confirmed it was silently excluded; a plain `git add` would have no-op'd without `-f`.
- **Fix:** Added scoped negation patterns (`!backend/data/`, `backend/data/*`, `!backend/data/vpn_ranges/`, `!backend/data/vpn_ranges/**`) that re-include only the `vpn_ranges/` subtree while explicitly re-excluding everything else directly under `backend/data/` (confirmed `local_repo/` — 227MB of vendored installer binaries — and `langgraph_checkpoints.sqlite` both remain ignored via `git add -n` dry-run).
- **Files modified:** `.gitignore`
- **Verification:** `git add -n backend/data/vpn_ranges/x4bnet_vpn_ipv4.txt` succeeds; `git add -n backend/data/local_repo backend/data/langgraph_checkpoints.sqlite` reports both still ignored
- **Committed in:** `fdcdd9c` (Task 1 commit)

---

**Total deviations:** 3 auto-fixed (2 Rule 1 bug fixes, 1 Rule 2 missing-critical-functionality fix)
**Impact on plan:** All three fixes were necessary for the plan's own stated goal (a working, testable, actually-committed vendored snapshot) — no scope creep. None touch files outside this plan's declared `files_modified` list except the pre-existing, unrelated `.gitignore`, which required a minimal, precisely-scoped fix.

## Issues Encountered
- The working tree already contained substantial pre-existing uncommitted changes across ~90 unrelated files (other Phase 46 plans' in-progress work, prior session artifacts) at the start of this execution. Scope was kept strictly to this plan's 3 declared files plus the `.gitignore` fix — no unrelated files were touched, staged, or committed.

## User Setup Required
None for this plan — `GEOIP_ASN_DB_PATH`/`GeoLite2-ASN.mmdb` supply is documented in the plan's `user_setup` frontmatter as an out-of-band, optional dependency (graceful no-op when absent, confirmed by this plan's own tests). No action required to complete Plan 01 itself.

## Next Phase Readiness
- `agent_asn_service.lookup(ip)` is ready to be wired into `agent_heartbeat_endpoints.py`/`agent_registry_endpoints.py` (Plan 46-02+, per RESEARCH.md Integration Point 2) immediately after the existing `geoip_service.lookup()` call
- No blockers. The module is fully self-contained (no DB, no request context) and independently testable, as designed.

---
*Phase: 46-public-ip-asn-vpn-enrichment-location-history-audit*
*Completed: 2026-07-29*

## Self-Check: PASSED

- FOUND: `backend/agent_asn_service.py`
- FOUND: `backend/tests/test_agent_asn_service.py`
- FOUND: `backend/data/vpn_ranges/x4bnet_vpn_ipv4.txt`
- FOUND: `.planning/phases/46-public-ip-asn-vpn-enrichment-location-history-audit/46-01-SUMMARY.md`
- FOUND commit: `fdcdd9c` (test scaffold + vendored snapshot)
- FOUND commit: `2343849` (module implementation)
- FOUND commit: `ac7c589` (this SUMMARY)
