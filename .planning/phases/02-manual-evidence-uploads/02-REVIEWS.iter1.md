---
phase: 2
reviewers: [claude]
reviewed_at: 2026-07-28T00:00:00Z
plans_reviewed: [02-01-PLAN.md, 02-02-PLAN.md]
note: >
  Only the `claude` CLI was available on this host (gemini, codex, opencode,
  qwen, cursor, antigravity all missing). Per the independence rule the running
  Claude Code session normally skips `claude`, but with no other CLI installed
  the review was run through `claude -p` in a separate, fresh-context session so
  an independent pass could still be produced. Treat as single-reviewer.
---

# Cross-AI Plan Review — Phase 2: Manual Evidence Uploads

## Claude Review

# Cross-AI Plan Review — Phase 2: Manual Evidence Uploads

Reviewed both plans against actual current code (`compliance_evidence_endpoints.py`, `compliance_artifacts_endpoints.py`, `AssetComplianceList.tsx`, `conftest.py`). Note: this phase already shipped and evolved past these plans — review judges the plans on their own merit as plans.

---

## 02-01-PLAN.md (Backend)

### Summary
Well-scoped gap-closing plan. Four requirements (size cap, metadata, delete RBAC, magic bytes) mapped cleanly to TDD tasks with a RED-first gate. Threat model is real, not decorative. Two verification commands are logically broken, and two isolation edge cases (missing-tenant non-super caller, limiter/`Request` test friction) go unaddressed — all three later fixed in the shipped code, confirming the gaps were real.

### Strengths
- TDD wave-0 scaffold before implementation — every later task has an automated gate.
- STRIDE register maps each threat to a concrete code mitigation and requirement ID.
- Correctly forbids new source files/packages; stdlib-only magic check is right call (no libmagic).
- `systemGenerated` guard before any `$pull` — prevents deleting automated records. Real anti-pattern caught.
- Single `file.read()` + validate-before-write ordering explicit (RESEARCH Pitfall 6).
- UUID evidence IDs kill the same-millisecond collision risk.

### Concerns
- **HIGH — Task 0 RED gate is falsifiable.** Verify: `grep -Eq 'failed|error' && echo RED-OK`. A *collection/import* error satisfies this gate, yet `<done>` demands "collects without import errors." A broken test file passes the gate while violating the done criterion. Gate should assert `failed` specifically and separately assert clean collection (`--collect-only` exit 0).
- **MEDIUM — limiter + `Request` param friction unaddressed.** Handler carries `@limiter.limit(...)` and `request: Request`. Task 0 says "target handler functions directly with AsyncMock DB" — but slowapi needs `request.app.state.limiter`. Calling the decorated coroutine directly will trip on the limiter unless mocked. Plan never says how. Real setup cost hidden.
- **MEDIUM — missing-tenant non-super caller not covered.** Delete logic branches on `is_super` + owner + tenant, but no rule for a non-super caller with empty `tenant_id`. Shipped code added exactly this (`if not is_super and not caller_tenant -> 403`, WR-02). Plan gap.
- **MEDIUM — file served from public `/static` mount not in threat model.** Plan writes `url: /static/evidence/{uuid}` and RESEARCH says served via public `StaticFiles`. Storing user uploads under a public mount is the classic stored-XSS/served-payload risk; magic check limits disguise but doesn't stop a valid-but-hostile file being fetched unauthenticated. Shipped code moved `UPLOAD_DIR` OUT of static (`private_uploads/`, CR-02) — the plan should have. T-02-SC hand-waves this as "N/A."
- **LOW — `$pull` update not re-scoped by tenant.** Lookup is tenant-scoped, but the follow-up `update_one` filters only `{assetId, evidence.id}`. Benign TOCTOU window; tighten by carrying the tenant filter into the update too.
- **LOW — docx/xlsx magic is just `PK\x03\x04`.** Any zip renamed `.docx` passes. Acceptable for scope, worth a one-line ack.

### Suggestions
- Fix RED gate: `pytest ... | grep -q 'failed'` AND a separate `--collect-only` exit-0 assert.
- State the limiter test strategy (mock `request.app.state.limiter`, or `app.dependency_overrides` + TestClient).
- Add the empty-`tenant_id` non-super 403 case to Task 2 behaviors.
- Move `UPLOAD_DIR` off the public static mount, or explicitly document why served-file risk is accepted.

### Risk: **MEDIUM** — logic is sound and TDD-gated, but two verify commands don't actually gate and one security decision (public static) is under-modeled.

---

## 02-02-PLAN.md (Frontend)

### Summary
Tight two-file frontend plan: kill the multipart Content-Type bug, add description + source badge + delete button, wrap the DELETE call, gated by a blocking human-verify checkpoint. Correct dependency on 02-01. The automated verification commands are unreliable — one is outright inverted and would pass a broken build.

### Strengths
- Correctly identifies and removes the `Content-Type: multipart/form-data` boundary bug — genuine defect.
- Backend stays authoritative; UI hides delete on automated/non-owned rows as UX only (T-02-08 disposition honest).
- Blocking human-verify checkpoint with concrete steps incl. the `.js`-renamed-`.pdf` negative case.
- `depends_on: ["02-01"]` correct — needs the DELETE route + metadata fields.

### Concerns
- **HIGH — `tsc` verify is inverted, gates nothing.** `npx tsc --noEmit 2>&1 | grep -v node_modules | grep -Eqv "error" && echo OK`. `grep -qv "error"` exits 0 if *any* line lacks "error" — a build **with** errors still prints OK. This never fails on type errors. Both tasks use it. Replace with: `! (npx tsc --noEmit 2>&1 | grep -v node_modules | grep -q "error")`.
- **MEDIUM — `grep -A6` window may miss the header.** Content-Type check greps 6 lines after `uploadComplianceEvidence = async`; if the `headers` line sits past line 6 the guard silently passes. Anchor on the function body, not a fixed window.
- **LOW — `onDeleteEvidence(controlId)` kept but unused by route.** "Caller symmetry" — minor dead param; acceptable but flag as intentional.
- **LOW — client description has no length guard** while server caps at 1000. UX-only mismatch; harmless (server truncates/rejects) but worth a maxLength on the input.

### Suggestions
- Rewrite both `tsc` gates to fail on presence of "error", not absence.
- Widen/replace the `-A6` grep with a body-scoped match.
- Add `maxLength={1000}` to the description input to mirror the server.

### Risk: **MEDIUM** — feature logic and sequencing are correct, but the automated gates give false green; only the human checkpoint actually catches regressions.

---

## Cross-Plan Notes
- **Dependency ordering: correct.** 02-01 (backend routes + metadata) → 02-02 (frontend consumers). No circularity.
- **No scope creep** — both stay in the 4 named files + 1 test module; no new packages. Good discipline.
- **Recurring weakness: shell verify commands.** Three of the automated gates (02-01 RED grep, both 02-02 `tsc` greps) are logically unsound. The plans' *intent* is right; the *gates don't enforce it*. This is the single highest-leverage fix across both.
- **Validation:** shipped code fixed exactly the gaps flagged (WR-02 tenant guard, CR-02 static-mount move) — evidence the concerns are real, not stylistic.

**Overall milestone risk: MEDIUM.** Designs achieve the phase goal (EVID-01..05); the human checkpoint backstops the broken automated gates. Fix the verify commands and add the missing-tenant + public-static cases and this drops to LOW.

---

## Consensus Summary

Single reviewer (claude) this cycle — "consensus" reflects one independent pass. The
review is unusually well-grounded because it cross-checked the plans against the
actually-shipped code and confirmed which flagged gaps were later fixed.

### Agreed Strengths
- Clean requirement→task→threat mapping with a TDD RED-first gate.
- Correct dependency ordering (02-01 backend → 02-02 frontend) and no scope creep.
- `systemGenerated`-before-`$pull` guard and stdlib-only magic-byte check are the right calls.

### Agreed Concerns
- **HIGH (02-01):** Task 0 RED gate `grep -Eq 'failed|error'` is falsifiable — an import/collection error also passes it, contradicting the `<done>` "collects without import errors" criterion.
- **HIGH (02-02):** Both `tsc` verify gates use `grep -Eqv "error"`, which is logically inverted and returns OK even when the build has type errors — the gate never fails.
- **MEDIUM:** slowapi limiter/`Request` test friction (02-01) and fragile `grep -A6` Content-Type window (02-02) not addressed.
- **MEDIUM (already resolved in shipped code):** missing-tenant non-super 403 (WR-02) and moving uploads off the public static mount (CR-02).

### Divergent Views
None — single reviewer.

### Disposition of concerns vs. shipped code
- **Resolved in shipped code (not requiring replan):** missing-tenant non-super 403 (WR-02); public-static-mount → `private_uploads/` (CR-02).
- **Still open against the plan text:** the two HIGH verify-gate defects; the limiter test-strategy MEDIUM; the `grep -A6` fragility MEDIUM; the docx/xlsx magic-weakness LOW; the client `maxLength` LOW.
- **Intentional / rejected by design:** unused `controlId` param kept for caller symmetry.
