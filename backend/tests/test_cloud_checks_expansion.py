"""Tests for CHK-01 — Cloud Checks Execution Gaps (Phase 25).

Exercises cloud_checks_service.run_checks() directly for the kubernetes and
digitalocean providers, whose checks are already catalogued in CLOUD_CHECKS
but were previously never evaluated because RUNNABLE_PROVIDERS hard-gated
on ("aws", "azure", "gcp").
"""
import sys; import os; sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from unittest.mock import AsyncMock, MagicMock, patch
import cloud_checks_service as m


def _chain(result):
    c = MagicMock()
    c.to_list = AsyncMock(return_value=result)
    return c


def _mkdb(account, findings=None):
    # cloud_checks_service.run_checks() accesses db.cloud_accounts /
    # db.cloud_findings / db.cloud_check_results directly with NO db._db
    # prefix (unlike iac_scanner_service, which uses db._db).
    db = MagicMock()
    db.cloud_accounts = MagicMock()
    db.cloud_accounts.find_one = AsyncMock(return_value=account)
    db.cloud_findings = MagicMock()
    db.cloud_findings.find = MagicMock(return_value=_chain(findings if findings is not None else []))
    db.cloud_check_results = MagicMock()
    captured_docs = []
    async def _capture(filter, update, upsert=False):
        captured_docs.append(update.get("$set", {}))
        return MagicMock(modified_count=1)
    db.cloud_check_results.update_one = AsyncMock(side_effect=_capture)
    db._captured = captured_docs
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


async def test_run_checks_evaluates_microsoft365():
    account = {"id": "acct-1", "tenantId": "tenant-a", "provider": "microsoft365"}
    db = _mkdb(account)
    with patch("database.get_database", return_value=db):
        result = await m.cloud_checks_service.run_checks("acct-1", "microsoft365", "tenant-a")
    assert result.get("error") is None, f"Got {result}"
    assert result["ran"] == 6, f"Got {result}" # M365_CHECKS has 6 entries


async def test_run_checks_evaluates_mongodb_atlas():
    account = {"id": "acct-1", "tenantId": "tenant-a", "provider": "mongodb_atlas"}
    db = _mkdb(account)
    with patch("database.get_database", return_value=db):
        result = await m.cloud_checks_service.run_checks("acct-1", "mongodb_atlas", "tenant-a")
    assert result.get("error") is None, f"Got {result}"
    assert result["ran"] == 6, f"Got {result}" # MONGODB_ATLAS_CHECKS has 6 entries


async def test_no_imported_findings_means_not_checked_never_pass():
    account = {"id": "acct-1", "tenantId": "tenant-a", "provider": "kubernetes"}
    db = _mkdb(account, findings=[])
    with patch("database.get_database", return_value=db):
        result = await m.cloud_checks_service.run_checks("acct-1", "kubernetes", "tenant-a")
    docs = db._captured
    assert len(docs) == 20 and result["notChecked"] == 20 and result["reason"] == "no_findings"
    for d in docs:
        assert d["result"] == "SKIP", f"expected SKIP, got {d['result']}"
        assert d["detail"] == m.NOT_CHECKED_DETAIL
        assert d.get("simulated") is False


async def test_simulated_flag_false_when_findings_present():
    account = {"id": "acct-1", "tenantId": "tenant-a", "provider": "kubernetes"}
    findings = [{"severity": "high", "title": "Some Finding", "checkId": "k8s-001"}]
    db = _mkdb(account, findings=findings)
    with patch("database.get_database", return_value=db):
        await m.cloud_checks_service.run_checks("acct-1", "kubernetes", "tenant-a")
    docs = db._captured
    assert len(docs) > 0
    for d in docs:
        assert d.get("simulated") is False, f"expected simulated=False, got {d.get('simulated')}"


async def test_no_regression_for_existing_providers():
    account = {"id": "acct-1", "tenantId": "tenant-a", "provider": "kubernetes"}
    db = _mkdb(account, findings=[])
    with patch("database.get_database", return_value=db):
        result = await m.cloud_checks_service.run_checks("acct-1", "kubernetes", "tenant-a")
    assert result["ran"] == 20
    docs = db._captured
    assert not any(d["result"] == "PASS" for d in docs)


async def test_with_findings_a_matched_check_fails_and_the_rest_pass():
    account = {"id": "acct-1", "tenantId": "tenant-a", "provider": "kubernetes"}
    first = m.K8S_CHECKS[0]["id"]
    db = _mkdb(account, findings=[{"severity": "high", "title": "zz", "checkId": first}])
    with patch("database.get_database", return_value=db):
        result = await m.cloud_checks_service.run_checks("acct-1", "kubernetes", "tenant-a")
    by_id = {d["checkId"]: d["result"] for d in db._captured}
    assert by_id[first] == "FAIL" and "notChecked" not in result
    assert set(by_id.values()) <= {"PASS", "FAIL"}


async def test_summary_leaves_not_checked_out_of_the_pass_rate():
    rows = ([{"result": "SKIP", "provider": "aws", "severity": "high", "service": "s3"}] * 8
            + [{"result": "PASS", "provider": "aws", "severity": "high", "service": "s3"}]
            + [{"result": "FAIL", "provider": "aws", "severity": "high", "service": "s3"}])
    with patch.object(m.cloud_checks_service, "get_results", AsyncMock(return_value=rows)):
        s = await m.cloud_checks_service.get_summary("tenant-a", "Tenant Admin")
    assert (s["total"], s["pass"], s["fail"], s["notChecked"], s["passPct"]) == (10, 1, 1, 8, 50)
    assert s["byProvider"]["aws"] == {"pass": 1, "fail": 1}


async def test_run_checks_evaluates_oci():
    from cloud_checks_oci import OCI_CHECKS
    account = {"id": "acct-1", "tenantId": "tenant-a", "provider": "oci"}
    db = _mkdb(account)
    with patch("database.get_database", return_value=db):
        result = await m.cloud_checks_service.run_checks("acct-1", "oci", "tenant-a")
    assert result.get("error") is None, f"Got {result}"
    assert result["ran"] == len(OCI_CHECKS), f"Got {result}"


async def test_run_checks_evaluates_alibaba():
    from cloud_checks_alibaba import ALIBABA_CHECKS
    account = {"id": "acct-1", "tenantId": "tenant-a", "provider": "alibaba"}
    db = _mkdb(account)
    with patch("database.get_database", return_value=db):
        result = await m.cloud_checks_service.run_checks("acct-1", "alibaba", "tenant-a")
    assert result.get("error") is None, f"Got {result}"
    assert result["ran"] == len(ALIBABA_CHECKS), f"Got {result}"


async def test_run_checks_evaluates_cloudflare():
    from cloud_checks_cloudflare import CLOUDFLARE_CHECKS
    account = {"id": "acct-1", "tenantId": "tenant-a", "provider": "cloudflare"}
    db = _mkdb(account)
    with patch("database.get_database", return_value=db):
        result = await m.cloud_checks_service.run_checks("acct-1", "cloudflare", "tenant-a")
    assert result.get("error") is None, f"Got {result}"
    assert result["ran"] == len(CLOUDFLARE_CHECKS), f"Got {result}"


async def test_all_gates_accept_microsoft365_and_mongodb_atlas():
    """microsoft365 and mongodb_atlas must pass through all four CSPM gates in lockstep."""
    from cloud_account_endpoints import _VALID_PROVIDERS
    from cloud_checks_service import RUNNABLE_PROVIDERS
    assert "microsoft365" in _VALID_PROVIDERS
    assert "mongodb_atlas" in _VALID_PROVIDERS
    assert "microsoft365" in RUNNABLE_PROVIDERS
    assert "mongodb_atlas" in RUNNABLE_PROVIDERS


async def test_registration_gates_accept_oci_alibaba_cloudflare_now_runnable():
    """oci/alibaba/cloudflare pass through the registration/validation gates AND are now runnable."""
    from cloud_account_endpoints import _VALID_PROVIDERS
    from cloud_checks_service import RUNNABLE_PROVIDERS
    assert "oci" in _VALID_PROVIDERS
    assert "alibaba" in _VALID_PROVIDERS
    assert "cloudflare" in _VALID_PROVIDERS
    assert "oci" in RUNNABLE_PROVIDERS
    assert "alibaba" in RUNNABLE_PROVIDERS
    assert "cloudflare" in RUNNABLE_PROVIDERS


async def test_coverage_denominator_includes_new_providers():
    from cloud_checks_service import RUNNABLE_PROVIDERS, _RUNNABLE_CHECKS_COUNT, CLOUD_CHECKS
    assert "kubernetes" in RUNNABLE_PROVIDERS, f"Got {RUNNABLE_PROVIDERS}"
    assert "digitalocean" in RUNNABLE_PROVIDERS, f"Got {RUNNABLE_PROVIDERS}"
    assert "microsoft365" in RUNNABLE_PROVIDERS, f"Got {RUNNABLE_PROVIDERS}"
    assert "mongodb_atlas" in RUNNABLE_PROVIDERS, f"Got {RUNNABLE_PROVIDERS}"
    assert _RUNNABLE_CHECKS_COUNT == len(CLOUD_CHECKS), (
        f"Denominator {_RUNNABLE_CHECKS_COUNT} != total catalogued checks {len(CLOUD_CHECKS)}"
    )
