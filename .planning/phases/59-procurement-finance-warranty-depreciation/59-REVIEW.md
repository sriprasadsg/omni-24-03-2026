---
phase: 59-procurement-finance-warranty-depreciation
reviewed: 2026-08-06T11:33:14Z
depth: standard
files_reviewed: 15
files_reviewed_list:
  - backend/app_startup.py
  - backend/itam_finance_endpoints.py
  - backend/itam_finance_service.py
  - backend/itam_models.py
  - backend/notification_endpoints.py
  - backend/notification_service.py
  - backend/router_registry.py
  - backend/tests/itam_finance_sweep_test_support.py
  - backend/tests/itam_finance_test_support.py
  - backend/tests/test_itam_finance.py
  - backend/tests/test_itam_finance_bookvalue.py
  - backend/tests/test_itam_finance_sweep.py
  - backend/tests/test_itam_finance_sweep_resilience.py
  - backend/tests/test_itam_finance_warranty.py
  - backend/tests/test_itam_warranty_notify.py
findings:
  critical: 1
  warning: 4
  info: 2
  total: 7
status: fixed_partial
resolution:
  fixed: [CR-01, WR-02, WR-03]
  deferred: [WR-01, WR-04, IN-01, IN-02]
---

# Phase 59: Code Review Report

**Reviewed:** 2026-08-06T11:33:14Z
**Depth:** standard
**Files Reviewed:** 15
**Status:** issues_found

## Summary

Reviewed the Phase 59 procurement/finance/warranty slice: pure computation
functions (`compute_book_value`, `compute_warranty_status`, `_add_months`),
the request-scoped read/write endpoints, and the background warranty-alert
sweep (`run_warranty_alert_pass` / `start_warranty_alert_scheduler`) plus its
test suite (105 tests, all passing locally).

The sweep's own tenant-isolation discipline is genuinely solid: every read
extracts `tenantId` from the document being processed (never from ambient
context), the update filter carries both `id` and `tenantId`, and the raw,
unwrapped database handle is threaded through correctly per the module's
stated contract (confirmed no `get_database()` call anywhere in the module).
Depreciation and warranty-expiry date arithmetic (`_add_months`,
`compute_warranty_status`, `compute_book_value`) is well covered by unit
tests, including leap-year and boundary cases.

However, tracing the sweep's "guaranteed in-app" delivery path across module
boundaries (`itam_finance_service.py` → `notification_service.py` →
`database.py`'s tenant-isolation wrapper) surfaces a real defect: because the
sweep intentionally hands `NotificationService` the **raw, unwrapped** db
handle (by design — that's the whole point of Plan 59-04), the automatic
`tenantId` field injection that `TenantIsolatedCollection.insert_one`
normally performs never runs, and `send_alert`'s own insert uses the field
name `tenant_id` (snake_case) rather than `tenantId` (camelCase). The result:
every notification the sweep writes via its "guaranteed" path has no
`tenantId` field at all, so it is invisible to every reader in
`notification_endpoints.py` (the notification bell: list / mark-read /
delete). This is exactly the kind of raw-handle misuse the review was asked
to watch for — it is real, it is silent, and the test suite does not catch
it because it only asserts `insert_one` was awaited, never the shape of what
was inserted. See CR-01.

The three-way split of the sweep tests (`test_itam_finance_sweep.py`,
`test_itam_finance_sweep_resilience.py`, `itam_finance_sweep_test_support.py`)
was checked for dropped/duplicated coverage: no duplicate test names or
classes across the two test files, and the file-header docstrings' claimed
task breakdown matches what's actually present. One pre-existing coverage
gap survived the split (not introduced by it) — see WR-02.

## Critical Issues

### CR-01: Sweep's "guaranteed in-app" warranty alerts are invisible to every tenant (tenantId/tenant_id mismatch + raw-handle bypass)

**File:** `backend/itam_finance_service.py:342-363` (call site), `backend/notification_service.py:80-84` (root cause), `backend/notification_endpoints.py:64-114` (broken readers)

**Issue:**
`run_warranty_alert_pass` calls path one like this:

```python
# itam_finance_service.py:350-363
await get_notification_service(db).send_alert(
    title=title,
    message=message,
    severity="warning",
    recipients=recipients,
    tenant_id=tenant_id,
    channels=[],
    ...
)
```

`db` here is deliberately the **raw, unwrapped** Motor handle — that's the
documented, tested design of this module (`_RawSweepDb` tests confirm it).
`NotificationService.__init__` stores it verbatim (`self.db = db`), and
`send_alert` writes the notification directly to the raw collection:

```python
# notification_service.py:80-84
await self.db.notifications.insert_one({
    **results,
    "tenant_id": tenant_id,   # snake_case
    "metadata": metadata
})
```

Because `self.db` is raw (not a `TenantIsolatedCollection`), none of
`database.py`'s automatic `document["tenantId"] = tenant_id` injection runs
(that only happens inside `TenantIsolatedCollection.insert_one`, which this
call path bypasses by design). Combined with `send_alert` itself writing
`"tenant_id"` rather than `"tenantId"`, the resulting document has **no
`tenantId` field whatsoever**.

Every reader of this collection in `notification_endpoints.py` — the actual
notification-bell endpoints a tenant admin uses — filters by `tenantId`
(camelCase):

```python
# notification_endpoints.py:66-69 (list)
notifications = await db.notifications.find({"tenantId": tenant_id}, {"_id": 0})...
# :77-79 (mark read), :100 (mark all read), :111 (delete) — all filter on "tenantId"
```

So a document with no `tenantId` field can never be listed, marked read, or
deleted through that router — it is permanently invisible to the tenant it
was meant to alert. (For contrast, `approval_service.py:168-175` and
`itdr_service.py:179-188`, which also write to `db.notifications`, both set
`"tenantId"` explicitly — this module is the outlier.) This directly
undermines the module's own docstring claim (`itam_finance_service.py:342`):
*"Path one, guaranteed in-app... NotificationService stores whatever handle
it is given and writes self.db.notifications.insert_one(...) directly"* — the
write succeeds, but the record it produces is orphaned data no tenant can
ever see or act on.

This is not caught by `test_itam_warranty_notify.py`'s
`test_raw_db_contract_send_alert_works_without_db_unwrap` because that test
only asserts `raw.notifications.insert_one.assert_awaited_once()` — it never
inspects the field names of the inserted document.

**Fix:** Make `send_alert`'s notification write include the field every
reader actually depends on, regardless of whether the caller's `db` is
wrapped or raw:

```python
# notification_service.py — send_alert()
await self.db.notifications.insert_one({
    **results,
    "tenantId": tenant_id,     # canonical field notification_endpoints.py/database.py rely on
    "tenant_id": tenant_id,    # keep for reporting_endpoints.py's existing query (backward-compat)
    "metadata": metadata
})
```
Then add an assertion in `test_itam_warranty_notify.py` and
`test_itam_finance_sweep_resilience.py`'s raw-db tests that the captured
notification document contains `tenantId == tenant_id`, so this regression
cannot silently return.

## Warnings

### WR-01: `compute_book_value` can report a book value above the asset's own purchase cost

**File:** `backend/itam_finance_service.py:99-107`

**Issue:** `usefulLifeYears`/`salvageValueCents` live on the asset **Model**
(shared across many assets), while `purchaseCostCents` lives on the
individual **Asset** — there is no way to validate `salvageValueCents <=
purchaseCostCents` at write time on either schema (`itam_models.py`'s
`AssetModelCreate`/`AssetModelUpdate` only constrain `salvageValueCents` to
`ge=0`, independently of any asset's cost). When a Model's configured
salvage value exceeds a particular asset's purchase cost,
`annual_depreciation_cents` goes negative and the salvage floor
(`max(book_value_cents, salvage_value_cents)`) produces a book value
*greater* than what was actually paid — e.g. `compute_book_value("2023-01-01",
50000, 3, 100000, now)` returns `bookValueCents == 100000` on day one, twice
the purchase price. The docstring's guarantee ("never negative and never
below salvage") is technically true but doesn't rule out this
above-purchase-cost outcome, and it isn't tested.

**Fix:** In `get_asset_book_value` (`itam_finance_endpoints.py`), add an
explicit guard before calling `compute_book_value` and return a structured
reason instead of a nonsensical number:
```python
if model_doc["salvageValueCents"] > asset["purchaseCostCents"]:
    return {**base, "bookValueCents": None, "reason": "invalid_depreciation_policy"}
```

### WR-02: Sweep never exercises the "EXPIRING" (not-yet-expired, in-window) alert branch at integration level

**File:** `backend/tests/test_itam_finance_sweep.py:46-69`, `backend/tests/test_itam_finance_sweep_resilience.py` (all "alerted" fixtures)

**Issue:** Every sweep test that expects an alert uses a `purchaseDate` far
enough in the past (or, in the one case that computes it, exactly at the
expiry boundary) that `compute_warranty_status` returns
`WARRANTY_STATUS_EXPIRED`, never `WARRANTY_STATUS_EXPIRING`. The test named
`test_sweep_core_expiring_asset_alerted_and_marked`
(`test_itam_finance_sweep.py:46`) even documents this in its own leftover
comment: *"Let's use 7 months warranty → expires 2026-08-01 (EXPIRED)"* —
the test's name promises "expiring" coverage but its data produces "expired"
coverage instead, and the dead exploratory comment (lines 57-60, discussing
an 8-month/31-day scenario that was abandoned) was left in place. The sweep's
own `if status_result["warrantyStatus"] not in (WARRANTY_STATUS_EXPIRING,
WARRANTY_STATUS_EXPIRED): continue` branch is therefore only proven for the
`EXPIRED` half at the integration (whole-pass) level — `EXPIRING` is only
unit-tested via `compute_warranty_status` directly in
`test_itam_finance_warranty.py`, never through an actual
`run_warranty_alert_pass` call. This gap predates the three-way file split
(it is not something the split dropped), but it's worth closing.

**Fix:** Add a sweep-level fixture with a `purchaseDate` placing the asset
inside the alert window but not yet expired (e.g. `warrantyMonths` computed
so `daysToExpiry` is positive and `<= window`), assert `count == 1` and that
`send_alert`'s `metadata["warrantyStatus"] == "expiring"`; clean up or
rename the misleading dead comment in the existing test.

### WR-03: Final marker-write in the sweep isn't isolated per-asset like the two delivery attempts around it

**File:** `backend/itam_finance_service.py:394-397`

**Issue:** Both delivery paths (lines 347-367 and 374-392) are individually
wrapped in their own `try/except Exception`, explicitly to guarantee one
asset's failure never blocks the rest of the pass. The marker write
immediately after them is not:
```python
await db.assets.update_one(
    {"id": asset["id"], "tenantId": tenant_id},
    {"$set": {"warrantyAlertSentAt": datetime.now(timezone.utc).isoformat()}},
)
```
Every other per-asset access in this function uses `.get(...)` defensively
(`asset.get("tenantId")`, `asset.get("assetTag")`, `asset.get("id")` for the
label). This line uses `asset["id"]` (bracket access) with no local
try/except: a document that somehow reaches this point without an `id` key
raises `KeyError` here, uncaught locally, which propagates to the
function-level `except Exception as exc: logger.error(...)` and terminates
the `async for` loop for the *entire pass* — silently dropping every
not-yet-processed asset in that cycle (they'll still be retried next hour,
so it's not data loss, but it does defeat the per-asset isolation this
module otherwise guarantees).

**Fix:** Wrap the marker write in its own try/except mirroring the two
delivery attempts, or at minimum use `asset.get("id")` consistently with the
rest of the function so a malformed document degrades gracefully instead of
aborting the pass.

### WR-04: `REASON_NO_DEPRECIATION_POLICY` is also returned for a corrupt `purchaseDate`, mislabeling the actual failure

**File:** `backend/itam_finance_endpoints.py:148-157`

**Issue:**
```python
try:
    result = compute_book_value(...)
except ValueError:
    return {**base, "bookValueCents": None, "reason": REASON_NO_DEPRECIATION_POLICY}
```
`compute_book_value` raises `ValueError` for two distinct causes: an invalid
`useful_life_years` (already excluded earlier by the `model_doc.get(...) is
None` checks) and an unparseable `purchase_date`. Only the latter can
actually reach this `except` block in practice, but the reason returned to
the client is `"no_depreciation_policy_assigned"` — which is wrong; the
Model's policy is fine, the Asset's own `purchaseDate` is corrupt. This is
low-likelihood (every write path validates `purchaseDate` via
`_validate_iso8601_date`), reachable only through legacy/pre-validator or
directly-written data, but the response would actively mislead an admin
trying to diagnose it (they'd go looking at the Model, not the Asset).

**Fix:** Catch the case earlier with an explicit check, or introduce a
distinct reason constant (e.g. `REASON_INVALID_PURCHASE_DATE`) so the
`except ValueError` branch reports what's actually wrong.

## Info

### IN-01: Floor-division rounding leaves the final year's book value slightly above salvage

**File:** `backend/itam_finance_service.py:99-102`

**Issue:** `annual_depreciation_cents = (purchase_cost_cents -
salvage_value_cents) // useful_life_years` floors, so when the difference
doesn't divide evenly by the useful life (e.g. cost=100000, salvage=15000,
life=3 → `85000 // 3 == 28333`), the book value at `years_elapsed ==
useful_life_years` is `100000 - 3*28333 == 15001`, one cent above the
configured salvage value rather than exactly equal to it. All existing test
fixtures use evenly-divisible numbers, so this drift is untested. Cosmetic
only (the salvage floor still holds, "never below salvage" is satisfied) —
noted for awareness, not requiring action.

### IN-02: `_tenant_admin_emails`'s bare `except Exception: pass` gives no signal when the recipient lookup itself fails

**File:** `backend/itam_finance_service.py:255-262`

**Issue:** The comment documents this as an intentional best-effort lookup
("never blocks an alert"), which is a reasonable design choice, but a
transient DB error here is indistinguishable in the logs from "this tenant
genuinely has zero admin users" — both silently produce `recipients == []`
and skip the in-app alert. Every other failure path in this module logs a
warning; this is the one exception. Consider `logger.debug(...)` inside the
`except` so a real outage is at least traceable, without changing the
non-blocking behavior.

---

## Resolution (2026-08-06, same session as phase close-out)

**Fixed:**
- **CR-01** — `notification_service.py`'s `send_alert` now writes `tenantId` (camelCase) explicitly alongside the pre-existing `tenant_id` (snake_case), so a raw/unwrapped db handle no longer produces an orphaned, unreadable notification. Regression assertions added in `test_itam_warranty_notify.py::test_raw_db_contract_send_alert_works_without_db_unwrap` and `test_itam_finance_sweep_resilience.py::TestSweepRawDbNoCrash`. Full suite re-run clean (1805 passed, same 3 pre-existing unrelated failures).
- **WR-03** — the marker-write in `run_warranty_alert_pass` is now wrapped in its own `try/except` (matching the two delivery attempts) and uses `asset.get("id")` instead of `asset["id"]`, so a malformed document degrades gracefully instead of aborting the pass for every not-yet-processed asset. New test: `TestSweepResilienceAndTenantScope::test_sweep_resilience_marker_write_raise_does_not_abort_pass`.
- **WR-02** — `test_sweep_core_expiring_asset_alerted_and_marked` now genuinely exercises the EXPIRING (not-yet-expired) branch (was accidentally testing EXPIRED, per its own leftover comment) and asserts `metadata["warrantyStatus"] == "expiring"` explicitly. Dead exploratory comment removed.

**Deferred (out of Plan 59-04's scope — belong to Plan 59-01's `compute_book_value`/ITAM-FIN-03, already shipped):**
- WR-01 (book value can exceed purchase cost under a misconfigured Model), WR-04 (mislabeled error reason for a corrupt purchase date), IN-01 (floor-division rounding drift), IN-02 (silent recipient-lookup failure). None block ITAM-FIN-02; flagged for a future pass over the Model/depreciation surface.

**Side effect noted, not fixed:** `notification_service.py` was already 557 lines (over the CLAUDE.md 500-line limit) before this session touched it for an unrelated reason; the CR-01 fix added 4 net lines. Splitting this shared, multi-consumer file (used by `approval_service.py`, `itdr_service.py`, `reporting_endpoints.py`, `itam_finance_service.py`, `control_comments`, and others) is a real refactor outside this phase's scope — flagged for a dedicated cleanup pass, not attempted here.

---

_Reviewed: 2026-08-06T11:33:14Z_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
