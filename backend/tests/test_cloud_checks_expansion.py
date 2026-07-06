"""Tests for CHK-01 — Cloud Checks Execution Gaps (Phase 25).

Exercises cloud_checks_service.run_checks() directly for the kubernetes and
digitalocean providers, whose checks are already catalogued in CLOUD_CHECKS
but were previously never evaluated because RUNNABLE_PROVIDERS hard-gated
on ("aws", "azure", "gcp").
"""
import sys, os; sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from unittest.mock import AsyncMock, MagicMock, patch
import cloud_checks_service as m


def _chain(result):
    c = MagicMock()
    c.to_list = AsyncMock(return_value=result)
    return c


def _mkdb(account):
    # cloud_checks_service.run_checks() accesses db.cloud_accounts /
    # db.cloud_findings / db.cloud_check_results directly with NO db._db
    # prefix (unlike iac_scanner_service, which uses db._db).
    db = MagicMock()
    db.cloud_accounts = MagicMock()
    db.cloud_accounts.find_one = AsyncMock(return_value=account)
    db.cloud_findings = MagicMock()
    db.cloud_findings.find = MagicMock(return_value=_chain([]))
    db.cloud_check_results = MagicMock()
    db.cloud_check_results.update_one = AsyncMock(return_value=MagicMock(modified_count=1))
    return db


async def test_run_checks_evaluates_kubernetes():
    account = {"id": "acct-1", "tenantId": "tenant-a", "provider": "kubernetes"}
    db = _mkdb(account)
    with patch("database.get_database", return_value=db):
        result = await m.cloud_checks_service.run_checks("acct-1", "kubernetes", "tenant-a")
    assert result.get("error") is None, f"Got {result}"
    assert result["ran"] == 20, f"Got {result}"


async def test_run_checks_evaluates_digitalocean():
    account = {"id": "acct-1", "tenantId": "tenant-a", "provider": "digitalocean"}
    db = _mkdb(account)
    with patch("database.get_database", return_value=db):
        result = await m.cloud_checks_service.run_checks("acct-1", "digitalocean", "tenant-a")
    assert result.get("error") is None, f"Got {result}"
    assert result["ran"] == 10, f"Got {result}"


async def test_coverage_denominator_includes_new_providers():
    from cloud_checks_service import RUNNABLE_PROVIDERS, _RUNNABLE_CHECKS_COUNT, CLOUD_CHECKS
    assert "kubernetes" in RUNNABLE_PROVIDERS, f"Got {RUNNABLE_PROVIDERS}"
    assert "digitalocean" in RUNNABLE_PROVIDERS, f"Got {RUNNABLE_PROVIDERS}"
    assert _RUNNABLE_CHECKS_COUNT == len(CLOUD_CHECKS), (
        f"Denominator {_RUNNABLE_CHECKS_COUNT} != total catalogued checks {len(CLOUD_CHECKS)}"
    )
