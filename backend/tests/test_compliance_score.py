"""Phase 9 compliance score tests — SCORE-01, SCORE-02, SCORE-03.

Wave-0 (unit):
  - test_score_endpoint_happy_path: GET /api/compliance/score → 200 with valid payload
  - test_score_tenant_isolation: Two tenants get independent scores
  - test_score_cache_hit: Second call returns cached payload; DB hit only once
  - test_score_empty_tenant: No asset_compliance records → overall_score 0.0
  - test_severity_weight_formula: Critical failure lowers score more than Low failure
  - test_score_extremes: All-Compliant = 100.0, all-Non-Compliant = 0.0
  - test_per_framework_breakdown: Per-framework breakdown has correct shape
  - test_cache_invalidated_on_upload: Cache invalidated after bulk evidence upload

asyncio.run() used for async cases (pytest-asyncio not installed — decision 02-01).
"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import io
import json
import zipfile
from unittest.mock import AsyncMock, MagicMock, patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from authentication_service import get_current_user
import compliance_score_endpoints as score_mod
import compliance_bulk_evidence_endpoints as bulk_mod


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

def _fake_user(role="admin", tenant_id="tenant-a", username="admin@test.com"):
    u = MagicMock(); u.role = role; u.tenant_id = tenant_id; u.username = username; return u


def _make_zip_bytes(files: dict) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_STORED) as zf:
        [zf.writestr(n, c) for n, c in files.items()]
    return buf.getvalue()


def _make_full_db(frameworks_data, ac_docs):
    """Combined mock db with compliance_frameworks (raw) and asset_compliance."""
    raw = MagicMock()

    async def _fw_cursor(*a, **kw):
        for fw in frameworks_data:
            yield fw

    fw_col = MagicMock()
    fw_col.find = MagicMock(return_value=_fw_cursor())
    raw.compliance_frameworks = fw_col

    db = MagicMock()
    db._db = raw

    async def _ac_cursor(*a, **kw):
        for doc in ac_docs:
            yield doc

    db.asset_compliance = MagicMock()
    db.asset_compliance.find = MagicMock(return_value=_ac_cursor())
    return db


def _make_score_app(user, db_mock):
    app = FastAPI()
    app.include_router(score_mod.router)
    app.dependency_overrides[get_current_user] = lambda: user
    return app


def _make_bulk_app(user):
    app = FastAPI()
    app.include_router(bulk_mod.router)
    app.dependency_overrides[get_current_user] = lambda: user
    return app


def _score_get(user, db_mock):
    """Helper: make app, GET /api/compliance/score with cache miss."""
    app = _make_score_app(user, db_mock)
    with patch.object(score_mod, "get_database", return_value=db_mock), \
         patch.object(score_mod.cache, "get", return_value=None), \
         patch.object(score_mod.cache, "set", return_value=True):
        return TestClient(app).get("/api/compliance/score")


_SAMPLE_FWS = [
    {"id": "soc2", "name": "SOC 2 Type II", "shortName": "SOC 2",
     "controls": [{"id": "CC6.1", "category": "Access Control"},
                  {"id": "CC6.2", "category": "Cryptography"}]},
    {"id": "iso27001", "name": "ISO 27001", "shortName": "ISO 27001",
     "controls": [{"id": "A.9.1", "category": "Audit"},
                  {"id": "A.9.2", "category": "Configuration"}]},
]

_SAMPLE_AC = [
    {"controlId": "CC6.1", "status": "Compliant",     "tenantId": "tenant-a"},
    {"controlId": "CC6.2", "status": "Non-Compliant", "tenantId": "tenant-a"},
    {"controlId": "A.9.1", "status": "Compliant",     "tenantId": "tenant-a"},
    {"controlId": "A.9.2", "status": "Warning",       "tenantId": "tenant-a"},
]


# ---------------------------------------------------------------------------
# SCORE-01: happy path
# ---------------------------------------------------------------------------

def test_score_endpoint_happy_path():
    """GET /api/compliance/score returns 200 with overall_score, frameworks, computed_at, tenant_id."""
    resp = _score_get(_fake_user(tenant_id="tenant-a"), _make_full_db(_SAMPLE_FWS, _SAMPLE_AC))
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert "overall_score" in body and 0.0 <= body["overall_score"] <= 100.0
    assert "frameworks" in body and len(body["frameworks"]) > 0
    assert "computed_at" in body and "tenant_id" in body
    assert body["tenant_id"] == "tenant-a"


# ---------------------------------------------------------------------------
# SCORE-01: tenant isolation
# ---------------------------------------------------------------------------

def test_score_tenant_isolation():
    """Tenant-a (Compliant) and tenant-b (Non-Compliant) get different scores."""
    fw = [{"id": "fw1", "name": "FW1", "shortName": "FW1",
           "controls": [{"id": "C1", "category": "Audit"}]}]

    resp_a = _score_get(_fake_user(tenant_id="ta"),
                        _make_full_db(fw, [{"controlId": "C1", "status": "Compliant", "tenantId": "ta"}]))
    resp_b = _score_get(_fake_user(tenant_id="tb"),
                        _make_full_db(fw, [{"controlId": "C1", "status": "Non-Compliant", "tenantId": "tb"}]))

    assert resp_a.status_code == 200 and resp_b.status_code == 200
    sa = resp_a.json()["overall_score"]
    sb = resp_b.json()["overall_score"]
    assert sa > sb, f"Compliant tenant should score higher than Non-Compliant: {sa} vs {sb}"


# ---------------------------------------------------------------------------
# SCORE-01: cache hit path
# ---------------------------------------------------------------------------

def test_score_cache_hit():
    """Cache hit on second call; DB find called only once total."""
    fw = [{"id": "fw1", "name": "FW1", "shortName": "FW1",
           "controls": [{"id": "C1", "category": "Audit"}]}]
    ac = [{"controlId": "C1", "status": "Compliant", "tenantId": "tenant-a"}]
    db_mock = _make_full_db(fw, ac)
    user = _fake_user(tenant_id="tenant-a")
    app = _make_score_app(user, db_mock)

    hit_count = {"n": 0}
    orig_find = db_mock._db.compliance_frameworks.find

    def counting_find(*a, **kw):
        hit_count["n"] += 1
        return orig_find(*a, **kw)

    db_mock._db.compliance_frameworks.find = MagicMock(side_effect=counting_find)

    cached_payload = {"overall_score": 100.0, "frameworks": [], "computed_at": "t", "tenant_id": "tenant-a"}

    # Call 1: cache miss → DB hit
    with patch.object(score_mod, "get_database", return_value=db_mock), \
         patch.object(score_mod.cache, "get", return_value=None), \
         patch.object(score_mod.cache, "set", return_value=True):
        r1 = TestClient(app).get("/api/compliance/score")

    assert r1.status_code == 200 and hit_count["n"] == 1

    # Call 2: cache hit → no DB call
    with patch.object(score_mod, "get_database", return_value=db_mock), \
         patch.object(score_mod.cache, "get", return_value=cached_payload), \
         patch.object(score_mod.cache, "set", return_value=True):
        r2 = TestClient(app).get("/api/compliance/score")

    assert r2.status_code == 200 and hit_count["n"] == 1, f"DB called on cache hit: {hit_count['n']}"
    assert r2.json()["overall_score"] == 100.0


# ---------------------------------------------------------------------------
# SCORE-01: empty tenant
# ---------------------------------------------------------------------------

def test_score_empty_tenant():
    """No asset_compliance records → overall_score 0.0 and total_controls 0 per framework."""
    fw = [{"id": "fw1", "name": "FW1", "shortName": "FW1",
           "controls": [{"id": "C1", "category": "Audit"}]}]
    resp = _score_get(_fake_user(tenant_id="empty"), _make_full_db(fw, []))
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["overall_score"] == 0.0, f"Expected 0.0, got {body['overall_score']}"
    for fw_entry in body["frameworks"]:
        assert fw_entry["total_controls"] == 0, f"Expected total_controls=0: {fw_entry}"


# ---------------------------------------------------------------------------
# SCORE-02: severity weight formula
# ---------------------------------------------------------------------------

def test_severity_weight_formula():
    """Critical Non-Compliant lowers score more than Low/Medium Non-Compliant."""
    # Scenario A: Critical control (Access Control) is Non-Compliant; Medium (Operations) is Compliant
    fw = [{"id": "fw1", "name": "FW", "shortName": "FW",
           "controls": [{"id": "C1", "category": "Access Control"},
                        {"id": "C2", "category": "Operations"}]}]

    ac_a = [{"controlId": "C1", "status": "Non-Compliant", "tenantId": "t1"},
            {"controlId": "C2", "status": "Compliant",     "tenantId": "t1"}]
    resp_a = _score_get(_fake_user(tenant_id="t1"), _make_full_db(fw, ac_a))

    # Scenario B: Medium (Operations) Non-Compliant; Critical (Access Control) is Compliant
    ac_b = [{"controlId": "C1", "status": "Compliant",     "tenantId": "t2"},
            {"controlId": "C2", "status": "Non-Compliant", "tenantId": "t2"}]
    resp_b = _score_get(_fake_user(tenant_id="t2"), _make_full_db(fw, ac_b))

    assert resp_a.status_code == 200 and resp_b.status_code == 200
    s_crit = resp_a.json()["overall_score"]
    s_low = resp_b.json()["overall_score"]
    assert s_crit < s_low, (
        f"Critical failure ({s_crit}) should lower score more than Medium failure ({s_low})"
    )


# ---------------------------------------------------------------------------
# SCORE-02: extremes
# ---------------------------------------------------------------------------

def test_score_extremes():
    """All-Compliant → 100.0; all-Non-Compliant → 0.0."""
    fw = [{"id": "fw1", "name": "FW", "shortName": "FW",
           "controls": [{"id": "C1", "category": "Audit"},
                        {"id": "C2", "category": "Configuration"}]}]

    all_c = [{"controlId": "C1", "status": "Compliant", "tenantId": "tx"},
             {"controlId": "C2", "status": "Compliant", "tenantId": "tx"}]
    resp_c = _score_get(_fake_user(tenant_id="tx"), _make_full_db(fw, all_c))
    assert resp_c.json()["overall_score"] == 100.0, resp_c.json()

    all_f = [{"controlId": "C1", "status": "Non-Compliant", "tenantId": "ty"},
             {"controlId": "C2", "status": "Non-Compliant", "tenantId": "ty"}]
    resp_f = _score_get(_fake_user(tenant_id="ty"), _make_full_db(fw, all_f))
    assert resp_f.json()["overall_score"] == 0.0, resp_f.json()


# ---------------------------------------------------------------------------
# SCORE-03: per-framework breakdown
# ---------------------------------------------------------------------------

def test_per_framework_breakdown():
    """frameworks list entries have required keys with correct types."""
    resp = _score_get(_fake_user(tenant_id="tenant-a"), _make_full_db(_SAMPLE_FWS, _SAMPLE_AC))
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert len(body["frameworks"]) > 0

    required = {"framework_id", "framework_name", "short_name", "score",
                "passing", "failing", "partial", "total_controls"}
    for fw in body["frameworks"]:
        missing = required - set(fw.keys())
        assert not missing, f"Missing keys {missing} in framework: {fw}"
        assert 0 <= fw["score"] <= 100
        assert all(isinstance(fw[k], int) for k in ("passing", "failing", "partial", "total_controls"))


# ---------------------------------------------------------------------------
# SCORE-01: cache invalidated on bulk upload
# ---------------------------------------------------------------------------

def test_cache_invalidated_on_upload():
    """After successful bulk upload, invalidate_cache called with compliance:score:{tenant_id}."""
    pdf_bytes = b"%PDF-1.4 test data"
    zip_bytes = _make_zip_bytes({"policy.pdf": pdf_bytes})
    manifest = json.dumps([{"filename": "policy.pdf", "control_id": "CC6.1"}])
    user = _fake_user(role="admin", tenant_id="tenant-a")

    raw = MagicMock()
    raw.evidence_audit_log = MagicMock()
    raw.evidence_audit_log.insert_one = AsyncMock(return_value=MagicMock(inserted_id="coc"))
    db_mock = MagicMock()
    db_mock._db = raw
    db_mock.control_evidence = MagicMock()
    db_mock.control_evidence.insert_one = AsyncMock(return_value=MagicMock(inserted_id="cev"))

    app = _make_bulk_app(user)

    with patch.object(bulk_mod, "get_database", return_value=db_mock), \
         patch("asyncio.to_thread", new=AsyncMock(return_value=None)), \
         patch("compliance_bulk_evidence_endpoints.invalidate_cache") as mock_inv:
        resp = TestClient(app).post(
            "/api/compliance/evidence/bulk",
            files={"zip_file": ("batch.zip", zip_bytes, "application/zip")},
            data={"manifest": manifest},
        )

    assert resp.status_code == 200, resp.text
    invalidated_keys = [c.args[0] for c in mock_inv.call_args_list]
    assert f"compliance:score:tenant-a" in invalidated_keys
    assert "compliance:score:__super__" in invalidated_keys
    assert f"compliance:threat-score:tenant-a" in invalidated_keys
    assert "compliance:threat-score:__super__" in invalidated_keys
