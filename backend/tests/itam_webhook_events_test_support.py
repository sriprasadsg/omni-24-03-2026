"""Shared test support for the Plan 73-03 background-sweep webhook tests
(asset.warranty_expiring / license.expiring_soon): the fixtures and
in-memory db stubs reused across the warranty-sweep, licence-sweep, and
mixed-tenant regression test classes in test_itam_webhook_events.py.

Split out to keep that module closer to the CLAUDE.md 500-line limit —
mirrors itam_finance_sweep_test_support.py's own split for Plan 59-04's
warranty sweep tests. The main test file remains the sole place these
fixtures are exercised (its own -k warranty_expiring / -k license_expiring /
-k tenant_context_background selectors), per this plan's own <verify>
commands pinning every task to that one file path.

This module is deliberately not named `test_*.py` so pytest does not try to
collect it directly.
"""
from datetime import datetime, timezone
from unittest.mock import patch

from tests.itam_finance_sweep_test_support import _AsyncCursor, _asset

# Fail-closed sentinel TenantIsolatedCollection._inject_tenant_id substitutes
# when no ambient tenant is set — a dispatch that ever observes this value
# proves the bracketing was bypassed, not merely absent.
FAIL_CLOSED_TENANT_SENTINEL = "NON_EXISTENT_TENANT_ISOLATION_EMERGENCY"


def _expiring_asset(**overrides):
    """Purchased 2026-01-01, 8-month warranty -> expires 2026-09-01. Against
    a mocked "now" of 2026-08-15 that is 17 days out: inside the default
    30-day alert window and not yet past expiry, so this is genuinely the
    EXPIRING branch, not EXPIRED."""
    return _asset(purchaseDate="2026-01-01T00:00:00Z", warrantyMonths=8, **overrides)


def _mock_now_2026_08_15():
    return patch("itam_finance_service.datetime", **{
        "now.return_value": datetime(2026, 8, 15, tzinfo=timezone.utc),
        "fromisoformat.side_effect": datetime.fromisoformat,
    })


def _license(**overrides):
    doc = {
        "id": "lic-1",
        "tenantId": "tenant-a",
        "name": "Photoshop",
        "expiryDate": "2026-08-20T00:00:00+00:00",  # 5 days from mocked now, in-window
    }
    doc.update(overrides)
    return doc


def _license_matches(doc, filter_spec):
    for k, v in filter_spec.items():
        if isinstance(v, dict):
            if "$exists" in v:
                exists = k in doc and doc.get(k) is not None
                if v["$exists"] != exists:
                    return False
            if "$ne" in v:
                if doc.get(k) == v["$ne"]:
                    return False
        else:
            if doc.get(k) != v:
                return False
    return True


class _LicensesCollection:
    def __init__(self, db):
        self._db = db

    def find(self, filter_spec, projection=None):
        self._db.captured_find_filters.append(filter_spec)
        matched = [d for d in self._db._docs.values() if _license_matches(d, filter_spec)]
        return _AsyncCursor(matched)

    async def find_one_and_update(self, filter_spec, update):
        self._db.captured_claim_filters.append(filter_spec)
        doc_id = filter_spec.get("id")
        tenant_id = filter_spec.get("tenantId")
        doc = self._db._docs.get(doc_id)
        if doc is None or doc.get("tenantId") != tenant_id:
            return None
        for k, v in filter_spec.items():
            if isinstance(v, dict) and v.get("$exists") is False and k in doc:
                return None  # already claimed by another pass
        for k, v in update.get("$set", {}).items():
            doc[k] = v
        return dict(doc)


class _RawLicenseSweepDb:
    """Minimal stateful raw-db stub for the licence expiry sweep, mirroring
    itam_finance_sweep_test_support._RawSweepDb's shape for assets: an
    in-memory licenses collection supporting find() with $exists/$ne
    filtering and an atomic find_one_and_update() claim."""

    def __init__(self, licenses=None):
        self._docs = {d["id"]: dict(d) for d in (licenses or [])}
        self.captured_find_filters = []
        self.captured_claim_filters = []
        self.licenses = _LicensesCollection(self)


def _mock_license_now_2026_08_15():
    return patch("itam_event_sweeps.datetime", **{
        "now.return_value": datetime(2026, 8, 15, tzinfo=timezone.utc),
        "fromisoformat.side_effect": datetime.fromisoformat,
    })
