"""Tests for Phase 20 — Multi-Account Cloud Scanning."""
import sys, os; sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from unittest.mock import AsyncMock, MagicMock, patch
from fastapi import FastAPI
from fastapi.testclient import TestClient

def _mkuser(t="tenant-a", r="admin"):
    u = MagicMock(); u.tenant_id = t; u.role = r; return u

def _chain(result):
    """Build a cursor-like mock that supports any combination of
    .sort()/.skip()/.limit() before .to_list(), all resolving to `result`.
    Needed because list_accounts() chains .find().sort().skip().limit().to_list()
    while get_results() chains .find().sort().to_list() directly."""
    m = MagicMock()
    m.to_list = AsyncMock(return_value=result)
    m.sort = MagicMock(return_value=m)
    m.skip = MagicMock(return_value=m)
    m.limit = MagicMock(return_value=m)
    return m

def _mkdb():
    db = MagicMock()
    # DB-F10: set before the loop below so setattr(db._db, col, c) attaches
    # onto `db` itself, not a separate auto-vivified mock that would be
    # discarded by assigning db._db afterward.
    db._db = db
    for col in ("cloud_accounts", "cloud_check_results"):
        c = MagicMock()
        c.insert_one = AsyncMock(return_value=MagicMock(inserted_id="x"))
        c.find = MagicMock(return_value=_chain([]))
        c.find_one = AsyncMock(return_value=None)
        c.update_one = AsyncMock(return_value=MagicMock(modified_count=1))
        c.count_documents = AsyncMock(return_value=0)
        setattr(db._db, col, c)
    db.cloud_check_results.find = MagicMock(return_value=_chain([]))
    db.cloud_check_results.find_one = AsyncMock(return_value=None)
    db.cloud_check_results.count_documents = AsyncMock(return_value=0)
    # rbac_service.get_user_permissions falls back to its in-memory default_roles
    # table for any non-super-admin role as long as the DB lookup resolves to None.
    db.roles = MagicMock()
    db.roles.find_one = AsyncMock(return_value=None)
    return db

def _build(db, u):
    import cloud_account_endpoints as m
    from authentication_service import get_current_user
    app = FastAPI(); app.include_router(m.router)
    app.dependency_overrides[get_current_user] = lambda: u
    patcher = patch("cloud_account_endpoints.get_database", return_value=db); patcher.start()
    rbac_patcher = patch("rbac_service.get_database", return_value=db); rbac_patcher.start()
    return TestClient(app, raise_server_exceptions=False)

def test_register_aws_account():
    db = _mkdb(); c = _build(db, _mkuser())
    r = c.post("/api/cloud-accounts", json={"provider": "aws", "account_id": "123456789012", "account_name": "Prod", "environment": "prod"})
    assert r.status_code == 200, f"Got {r.status_code}"
    assert "credentials_ref" not in r.json()["account"]

def test_register_gcp_account():
    db = _mkdb(); c = _build(db, _mkuser())
    r = c.post("/api/cloud-accounts", json={"provider": "gcp", "account_id": "project-123", "account_name": "GCP Prod"})
    assert r.status_code == 200

def test_register_kubernetes_account():
    db = _mkdb(); c = _build(db, _mkuser())
    r = c.post("/api/cloud-accounts", json={"provider": "kubernetes", "account_id": "cluster-1", "account_name": "K8s Prod"})
    assert r.status_code == 200, f"Got {r.status_code}"

def test_register_digitalocean_account():
    db = _mkdb(); c = _build(db, _mkuser())
    r = c.post("/api/cloud-accounts", json={"provider": "digitalocean", "account_id": "do-123", "account_name": "DO Prod"})
    assert r.status_code == 200, f"Got {r.status_code}"

def test_list_accounts():
    db = _mkdb(); c = _build(db, _mkuser())
    r = c.get("/api/cloud-accounts")
    assert r.status_code == 200

def test_scan_sets_status():
    db = _mkdb()
    account = {"id": "acct-1", "tenantId": "tenant-a", "provider": "aws"}
    db._db.cloud_accounts.find_one = AsyncMock(return_value=account)
    c = _build(db, _mkuser())
    fake_run_checks = AsyncMock(return_value={"ran": 3, "accountId": "acct-1", "provider": "aws"})
    with patch("cloud_checks_service.cloud_checks_service.run_checks", new=fake_run_checks):
        r = c.post("/api/cloud-accounts/acct-1/scan")
    assert r.status_code == 200
    statuses = [
        call.args[1]["$set"].get("scan_status")
        for call in db._db.cloud_accounts.update_one.call_args_list
    ]
    assert statuses == ["scanning", "idle"], f"Got {statuses}"
    # every write must be scoped to the account's tenant, not just its id
    for call in db._db.cloud_accounts.update_one.call_args_list:
        assert call.args[0].get("tenantId") == "tenant-a"

def test_scan_nonexistent_account_returns_404():
    db = _mkdb()  # cloud_accounts.find_one defaults to returning None
    c = _build(db, _mkuser())
    r = c.post("/api/cloud-accounts/does-not-exist/scan")
    assert r.status_code == 404

def test_get_results():
    db = _mkdb(); c = _build(db, _mkuser())
    r = c.get("/api/cloud-accounts/acct-1/results")
    assert r.status_code == 200

def test_summary():
    db = _mkdb(); c = _build(db, _mkuser())
    r = c.get("/api/cloud-accounts/summary")
    assert r.status_code == 200

def test_discover_org():
    db = _mkdb(); c = _build(db, _mkuser())
    r = c.post("/api/cloud-accounts/discover-org", json={"provider": "aws", "management_account_id": "111111111111"})
    assert r.status_code == 200
    assert "discovered" in r.json()

def test_discover_org_requires_management_account_id():
    db = _mkdb(); c = _build(db, _mkuser())
    r = c.post("/api/cloud-accounts/discover-org", json={"provider": "aws"})
    assert r.status_code == 400

def test_insufficient_permission_rejected():
    # security_analyst has neither view:cloud_security nor manage:settings —
    # this is the regression test for WR-07 (endpoints previously had zero
    # permission gate, so any authenticated role could register/scan accounts).
    db = _mkdb()
    u = _mkuser("tenant-a", "security_analyst")
    c = _build(db, u)
    r_list = c.get("/api/cloud-accounts")
    assert r_list.status_code == 403, f"Got {r_list.status_code}"
    r_register = c.post("/api/cloud-accounts", json={"provider": "aws", "account_id": "123456789012"})
    assert r_register.status_code == 403, f"Got {r_register.status_code}"

def test_register_preserves_credentials_ref_when_omitted():
    # IN-05: regression test for CR-01 — re-registering an existing
    # (tenantId, provider, account_id) without resending credentials_ref
    # (the shipped UI form never sends this field) must preserve the
    # previously-stored encrypted value rather than blanking it.
    db = _mkdb(); c = _build(db, _mkuser())
    r1 = c.post("/api/cloud-accounts", json={
        "provider": "aws", "account_id": "123456789012",
        "credentials_ref": "arn:aws:iam::123456789012:role/scanner",
    })
    assert r1.status_code == 200, f"Got {r1.status_code}"
    first_doc = db._db.cloud_accounts.update_one.call_args_list[0].args[1]["$set"]
    assert first_doc["credentials_ref"], "first registration must store an encrypted credentials_ref"

    # Second call simulates the stored doc now being found via find_one,
    # and omits credentials_ref entirely — exactly what the shipped UI does.
    db._db.cloud_accounts.find_one = AsyncMock(return_value=first_doc)
    r2 = c.post("/api/cloud-accounts", json={
        "provider": "aws", "account_id": "123456789012", "account_name": "Prod",
    })
    assert r2.status_code == 200, f"Got {r2.status_code}"
    second_doc = db._db.cloud_accounts.update_one.call_args_list[1].args[1]["$set"]
    assert second_doc["credentials_ref"] == first_doc["credentials_ref"], (
        "credentials_ref must be preserved when omitted on re-registration"
    )

def test_list_accounts_total_count_reflects_count_accounts():
    # IN-05: regression test for WR-03 — total_count in the GET
    # /api/cloud-accounts response must reflect count_accounts()'s return
    # value, independent of how many items the current page returns.
    db = _mkdb()
    db._db.cloud_accounts.count_documents = AsyncMock(return_value=137)
    c = _build(db, _mkuser())
    r = c.get("/api/cloud-accounts?limit=10")
    assert r.status_code == 200, f"Got {r.status_code}"
    body = r.json()
    assert body["total_count"] == 137, f"Got {body}"
    assert body["count"] == 0, "count reflects the (empty, mocked) page, not total_count"

def test_register_preserves_account_name_region_environment_when_omitted():
    # IN-01: regression test for WR-06 (account_name/region) and WR-01
    # (environment) — re-registering an existing (tenantId, provider,
    # account_id) without resending account_name/region/environment (the
    # shipped UI form only sends fields the user actually touched) must
    # preserve the previously-stored values rather than silently resetting
    # them to defaults ("", "us-east-1", "dev").
    db = _mkdb(); c = _build(db, _mkuser())
    r1 = c.post("/api/cloud-accounts", json={
        "provider": "aws", "account_id": "123456789012",
        "account_name": "Custom Name", "region": "eu-west-1", "environment": "prod",
    })
    assert r1.status_code == 200, f"Got {r1.status_code}"
    first_doc = db._db.cloud_accounts.update_one.call_args_list[0].args[1]["$set"]
    assert first_doc["account_name"] == "Custom Name"
    assert first_doc["region"] == "eu-west-1"
    assert first_doc["environment"] == "prod"

    # Second call simulates the stored doc now being found via find_one,
    # and omits account_name/region/environment entirely — exactly what
    # the shipped UI does when a user never touches those fields.
    db._db.cloud_accounts.find_one = AsyncMock(return_value=first_doc)
    r2 = c.post("/api/cloud-accounts", json={
        "provider": "aws", "account_id": "123456789012",
    })
    assert r2.status_code == 200, f"Got {r2.status_code}"
    second_doc = db._db.cloud_accounts.update_one.call_args_list[1].args[1]["$set"]
    assert second_doc["account_name"] == "Custom Name", (
        "account_name must be preserved when omitted on re-registration"
    )
    assert second_doc["region"] == "eu-west-1", (
        "region must be preserved when omitted on re-registration"
    )
    assert second_doc["environment"] == "prod", (
        "environment must be preserved when omitted on re-registration"
    )

def test_summary_total_accounts_reflects_count_accounts_not_capped_list():
    # IN-01: regression test for WR-05 — GET /api/cloud-accounts/summary's
    # total_accounts must reflect count_accounts()'s unbounded count, not
    # the length of the (possibly capped) account list used to build the
    # by_provider/by_environment breakdown.
    db = _mkdb()
    db._db.cloud_accounts.count_documents = AsyncMock(return_value=150)
    db._db.cloud_accounts.find = MagicMock(return_value=_chain([
        {"provider": "aws", "environment": "prod", "account_name": f"acct-{i}"} for i in range(5)
    ]))
    c = _build(db, _mkuser())
    r = c.get("/api/cloud-accounts/summary")
    assert r.status_code == 200, f"Got {r.status_code}"
    body = r.json()
    assert body["total_accounts"] == 150, f"Got {body}"

def test_tenant_isolation():
    db = _mkdb()
    docs = [
        {"id": "acct-a", "tenantId": "tenant-a", "provider": "aws", "account_id": "111", "credentials_ref": "enc-x"},
        {"id": "acct-b", "tenantId": "tenant-b", "provider": "aws", "account_id": "222", "credentials_ref": "enc-y"},
    ]
    captured_query = {}

    def _find(query, *_a, **_kw):
        captured_query.update(query)
        filtered = [d for d in docs if d.get("tenantId") == query.get("tenantId")]
        return _chain(filtered)

    db._db.cloud_accounts.find = MagicMock(side_effect=_find)
    u = _mkuser("tenant-a", "user"); c = _build(db, u)
    r = c.get("/api/cloud-accounts")
    assert r.status_code == 200
    assert captured_query.get("tenantId") == "tenant-a"
    items = r.json()["items"]
    assert len(items) == 1 and items[0]["id"] == "acct-a"
    assert "credentials_ref" not in items[0]
