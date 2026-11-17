---
phase: 78
fixed_at: 2026-11-17T00:00:00Z
review_path: /home/azureuser/enterprise-omni-agent-ai-platform/.planning/phases/78-organization-endpoint-cost-api/78-REVIEW.md
iteration: 1
findings_in_scope: 1
fixed: 1
skipped: 0
status: all_fixed
---

# Phase 78: Code Review Fix Report

**Fixed at:** 2026-11-17
**Source review:** /home/azureuser/enterprise-omni-agent-ai-platform/.planning/phases/78-organization-endpoint-cost-api/78-REVIEW.md
**Iteration:** 1

**Summary:**
- Findings in scope: 1
- Fixed: 1
- Skipped: 0

## Fixed Issues

### WR-08: Book-value route echoes the raw unreadable cost, and FinancePanel pre-fills the Purchase Cost field from it

**Files modified:** `backend/itam_finance_endpoints.py`, `backend/tests/test_itam_cost_parity.py`
**Commit:** 6b9351f63
**Status:** fixed
**Applied fix:** In `get_asset_book_value`, `cost = asset.get("purchaseCostCents")` is now read before `base` is built, and `base["purchaseCostCents"]` is `cost if is_cents(cost) else None`, matching the cost row (`itam_cost_service.py:126`). The duplicate `cost = ...` line below `base` was removed. The `reason: unreadable_purchase_cost` branch is unchanged, so the operator is still told the stored cost cannot be read, and the response no longer carries the garbage value.

Tests, in `backend/tests/test_itam_cost_parity.py`:
- `test_route_reason_matches_row_for_every_unvalued_asset` now asserts the route's `purchaseCostCents` equals the list row's for every unvalued asset, plus an explicit `purchaseCostCents is None` for `N-MALCOST`.
- `test_book_value_route_matches_list` now asserts the same route/row cost parity for every active asset, so a valid cost is still echoed for the valued assets.

Fails-then-passes check: with the new assertions in place and the route unchanged, `test_book_value_route_matches_list` and `test_route_reason_matches_row_for_every_unvalued_asset` both failed (`assert '1000' == None` for `N-MALCOST`; 2 failed, 7 passed in `test_itam_cost_parity.py`). After the route fix they pass.

**Frontend:** no change needed and none made. `FinancePanel.tsx:61` does `String(bv.purchaseCostCents / 100)`. The route now returns only `number | null` for `purchaseCostCents`, which matches `types.ts:1143`. A null cost leaves the Purchase Cost field empty, so the `/ 100` pre-fill is safe for every shape the route can return. No frontend build was run.

## Verification

Run in the main checkout. `workflow.use_worktrees` is `false` in `.planning/config.json`, so no worktree was created. Command, foreground, named files only:

`backend/venv/bin/python -m pytest backend/tests/test_itam_cost_parity.py backend/tests/test_itam_finance_bookvalue.py backend/tests/test_itam_finance.py backend/tests/test_itam_audit.py backend/tests/test_itam_finance_warranty.py backend/tests/test_itam_cost_service.py backend/tests/test_itam_cost_assets.py -q -p no:cacheprovider -rs`

Result: 196 passed, 0 failed, 0 skipped. The Python syntax check of `itam_finance_endpoints.py` passed.

## User WIP check

- Neither edited file had user WIP: `git diff HEAD --numstat` for both was empty before editing.
- Staged by explicit path only, and committed with explicit pathspec. No `-a`, stash, checkout, restore or reset was used.
- The commit (`6b9351f63`) contains exactly the two files above (10 insertions, 4 deletions). The subject is `fix(78): WR-08 book-value route echoes purchaseCostCents only when readable`. There is no `Co-Authored-By` trailer, no `--no-verify`, and no push.
- After the commit `git diff --cached` is empty, and `git diff --numstat` is identical to the snapshot `/tmp/claude-1000/-home-azureuser-enterprise-omni-agent-ai-platform/4d2b54c2-72df-448a-a2d6-1a2e61c984ba/scratchpad/wip-numstat-before-78fix4.txt`, which was also identical before the edits.
- The live `omni_platform` database was not touched. No restart or deploy.

---

_Fixed: 2026-11-17_
_Fixer: Claude (gsd-code-fixer)_
_Iteration: 1_
