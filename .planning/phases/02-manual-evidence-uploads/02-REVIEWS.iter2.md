---
phase: 2
cycle: 2
reviewers: [claude]
reviewed_at: 2026-07-28T00:00:00Z
plans_reviewed: [02-01-PLAN.md, 02-02-PLAN.md]
revised_commit: a9399a9
prior_cycle: 02-REVIEWS.iter1.md
note: >
  Convergence cycle 2. Plans were revised in commit a9399a9 to address cycle 1's
  2 HIGH (falsely-green verify gates) and the actionable MEDIUM/LOW findings.
  Only the `claude` CLI is available on this host (gemini, codex, opencode, qwen,
  cursor, antigravity all missing). Per the independence rule the running Claude
  Code session normally skips `claude`, but with no other CLI installed the pass
  was run through `claude -p` in a separate fresh-context session, cross-checked
  against the actual source (compliance_evidence_endpoints.py,
  compliance_artifacts_endpoints.py, apiService.ts, AssetComplianceList.tsx).
  Treat as single-reviewer.
---

# Cross-AI Plan Review — Phase 2: Manual Evidence Uploads (Cycle 2)

This cycle assesses the CURRENT (revised) plan state only. It does not re-count
findings that commit a9399a9 already incorporated or explicitly dispositioned.
Prior cycle: `02-REVIEWS.iter1.md`.

## Claude Review

### Disposition of cycle-1 findings (verified against revised plan text + code)

| Cycle-1 finding | Severity | Status in revised plan | Verification |
|-----------------|----------|------------------------|--------------|
| Task 0 RED gate falsifiable (`grep -Eq 'failed\|error'` passed on collection error) | HIGH | RESOLVED | Gate now `--collect-only` exit-0 (short-circuits before the run) `&&` `grep -Eq '[0-9]+ failed'` (matches the summary count, not the word "error"). A run-phase *error* prints "errors" not "failed", so it also fails to emit RED-OK — stricter, correct. |
| Both `tsc` gates inverted (`grep -Eqv "error"` returns OK with errors) | HIGH | RESOLVED | Both tasks now `! (npx tsc --noEmit 2>&1 \| grep -v node_modules \| grep -q "error TS")`. Keys on the real diagnostic prefix; any hit flips the gate to fail; clean tree emits nothing = pass. |
| slowapi limiter/`Request` test friction | MEDIUM | RESOLVED | Task 0 action now states the limiter strategy explicitly (Request-like with `app.state.limiter` MagicMock, or TestClient + `dependency_overrides`), and requires it be pinned in a module docstring. |
| Fragile `grep -A6` Content-Type window | MEDIUM | RESOLVED | Replaced with a body-scoped `awk` range over the `uploadComplianceEvidence` function. Confirmed sound against the real declaration `export const uploadComplianceEvidence = async (…)`: f=1 at the start line (not self-terminated because `!/uploadComplianceEvidence/` guards the reset), next top-level `const\|export` closes the window. |
| `$pull` not tenant-scoped (TOCTOU) | LOW | RESOLVED | Task 2 now carries `tenantId: caller_tenant` into the `update_one` filter when `not is_super and caller_tenant`. |
| docx/xlsx magic is generic `PK\x03\x04` | LOW | ACKNOWLEDGED | Task 1 documents the accepted stdlib-only ZIP-magic limitation with a required one-line code comment. |
| Client description length guard | LOW | RESOLVED | Task 2 adds `maxLength={1000}` mirroring the server `Form(max_length=1000)`. |
| Missing-tenant non-super 403 (WR-02) | MEDIUM | DEFERRED (explicit) | `review_resolution` documents it as ALREADY RESOLVED in shipped code — not re-planned. Confirmed: owner/tenant guards present in `compliance_evidence_endpoints.py`. |
| Uploads on public static mount (CR-02) | MEDIUM | DEFERRED (explicit) | Confirmed in code: `UPLOAD_DIR = "private_uploads/evidence"` (off the public mount). |
| Unused `controlId` param | LOW | REJECTED (by design) | Retained for caller symmetry; documented in Task 1 action. |

All cycle-1 HIGH and actionable findings are resolved, incorporated, or explicitly
dispositioned in the revised plans. Both falsely-green verify gates are genuinely
fixed.

### 02-01-PLAN.md (Backend) — verdict: PASS
The RED-gate and `$pull` fixes are correct; threat model, TDD sequencing, and
stdlib-only discipline remain sound. No unresolved HIGH.

### 02-02-PLAN.md (Frontend) — verdict: PASS
The `tsc` and body-scoped Content-Type gates are correct; maxLength mirror,
badges, confirm-guarded delete, and blocking human checkpoint are intact. No
unresolved HIGH.

### New concerns raised this cycle

- **LOW/MEDIUM (actionable) — 02-01 verify gates invoke a nonexistent `python`.**
  All three 02-01 automated gates run `cd backend && python -m pytest …`. On this
  host `python` is not a command (`python3` only; the real runner is
  `backend/venv/bin/python`, where the deps live). As written the gates error at
  invocation and can **never** emit `RED-OK` / pass, regardless of test state.
  This fails *closed* (it will not green-light broken code — unlike the cycle-1
  HIGHs), so it is not HIGH, but it will stall the TDD loop / force an executor
  deviation. Fix: change the gate binary to `backend/venv/bin/python -m pytest`
  (or `python3` with deps confirmed) in both 02-01 Task 0/1/2 `<automated>` blocks
  and the `<verification>` section. **This is the one actionable item still needed
  in PLAN.md.**

- **LOW (non-actionable) — mawk `\s` in the 02-02 awk gate.** Default awk here is
  mawk 1.3.4, which treats `\s` as literal `s`. The gate's `/^\s*(const|export)…/`
  therefore matches `/^s*(const|export)…/`. Because every top-level decl in
  `apiService.ts` sits at column 0, `s*` matches zero occurrences and the window
  still closes on the next `export const`, so the gate does **not** misfire on the
  actual file. Latent portability nit only; no PLAN.md change required.

- **LOW (non-actionable) — awk window unbounded at EOF.** Would over-run only if
  `uploadComplianceEvidence` were the last declaration in the file. It is at
  L701 of a 4861-line file with many later decls, so the window closes well
  before EOF. No misfire on the actual file.

### Risk
**LOW.** Both plans achieve EVID-01..05 with correct, now-functional automated
gates and a backstopping human checkpoint. The single residual actionable item
(python binary in the 02-01 gates) fails safe and is a one-token fix.

---

## Consensus Summary

Single reviewer (claude), cross-checked against live source. Both cycle-1 HIGH
verify-gate defects are genuinely fixed; every actionable cycle-1 MEDIUM/LOW is
either folded into the revised plan or explicitly deferred/rejected in the plan's
`review_resolution` section.

### Agreed Strengths
- The two falsely-green gates (pytest RED, tsc) are correctly re-implemented and
  now enforce what their `<done>` criteria claim.
- Tenant-scoped `$pull`, docx/xlsx ack, limiter strategy, and client `maxLength`
  are all present in the revised text.
- WR-02 / CR-02 dispositions verified against shipped code (tenant guards present;
  `UPLOAD_DIR = private_uploads/evidence`).

### Agreed Concerns (current)
- **LOW/MEDIUM (actionable):** 02-01 automated gates call `python`, which does not
  exist on this host — gates fail closed and never pass as written. Switch to
  `backend/venv/bin/python` (or verified `python3`).
- **LOW (non-actionable):** mawk `\s` and EOF-unbounded awk are latent nits that do
  not misfire on the actual `apiService.ts`.

### Divergent Views
None — single reviewer.

### Disposition
- **Resolved / incorporated:** both HIGH verify gates, limiter strategy, `grep -A6`
  fragility, `$pull` tenant scope, docx/xlsx ack, client `maxLength`.
- **Explicitly deferred (shipped code):** WR-02 missing-tenant 403, CR-02
  private-uploads mount.
- **Rejected by design:** unused `controlId` param.
- **Still open (actionable):** 02-01 verify gates invoke nonexistent `python`
  (fail-closed) — needs the runner binary corrected in PLAN.md.

**Overall milestone risk: LOW.**
