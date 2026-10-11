"""Regression tests for the 2026-10-11 sidebar audit fixes: pages must show
measured data or an honest empty state, never invented defaults."""
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from authentication_service import get_current_user
from auth_types import TokenData


def _user(role="Super Admin", tenant_id="t1", username="admin@t1.test"):
    return TokenData(username=username, role=role, tenant_id=tenant_id, mfa_verified=True)


def _app(router, user=None):
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_current_user] = lambda: user or _user()
    return app


class _Cursor:
    def __init__(self, docs):
        self._docs = docs

    def sort(self, *a, **k):
        return self

    def limit(self, *a, **k):
        return self

    def skip(self, *a, **k):
        return self

    async def to_list(self, length=None):
        return [dict(d) for d in self._docs]


class _Col:
    """Minimal async collection: equality and $lt filters, $set/$inc updates."""
    def __init__(self, docs=()):
        self.docs = [dict(d) for d in docs]

    def _ok(self, d, flt):
        for k, v in (flt or {}).items():
            if isinstance(v, dict) and "$lt" in v:
                if not d.get(k, 0) < v["$lt"]:
                    return False
            elif isinstance(v, dict):
                continue
            elif d.get(k) != v:
                return False
        return True

    def find(self, flt=None, projection=None):
        return _Cursor([d for d in self.docs if self._ok(d, flt)])

    async def find_one(self, flt=None, projection=None):
        for d in self.docs:
            if self._ok(d, flt):
                return dict(d)
        return None

    async def insert_one(self, doc):
        self.docs.append(dict(doc))

    async def update_one(self, flt, update):
        for d in self.docs:
            if self._ok(d, flt):
                d.update(update.get("$set", {}))
                for k, n in update.get("$inc", {}).items():
                    d[k] = d.get(k, 0) + n
                return MagicMock(modified_count=1)
        return MagicMock(modified_count=0)

    async def count_documents(self, flt=None):
        return len([d for d in self.docs if self._ok(d, flt)])

    def aggregate(self, pipeline):
        return _Cursor([])

    async def create_index(self, *a, **k):
        return None


# ── Service Mesh: no invented services, metrics or topology ─────────────────

def test_service_mesh_is_empty_without_reported_data():
    import service_mesh_service as sm
    db = MagicMock()
    db.mesh_services = _Col()
    db.mesh_metrics = _Col()
    db.mesh_graph_nodes = _Col()
    db.mesh_graph_edges = _Col()
    db.agents = _Col([{"id": "a1", "name": "host", "status": "online"}])
    with patch.object(sm, "get_database", return_value=db):
        client = TestClient(_app(sm.router))
        assert client.get("/api/mesh/services").json() == []
        assert client.get("/api/mesh/metrics").json() == []
        assert client.get("/api/mesh/graph").json() == {"nodes": [], "edges": []}


# ── Data Governance: no default catalog or lineage ───────────────────────────

def test_data_catalog_and_lineage_are_empty_without_entries():
    from data_governance_service import DataGovernanceService
    db = MagicMock()
    db.data_catalog = _Col()
    assert asyncio.run(DataGovernanceService(db).get_data_catalog()) == []


# ── Advanced BI: missing data is None, not a stand-in number ────────────────

def test_bi_metrics_use_none_when_nothing_is_measured():
    from bi_analytics_service import BiAnalyticsService
    db = MagicMock()
    for name in ("agents", "compliance_frameworks", "patch_deployment_jobs", "cost_recommendations",
                 "alerts", "security_cases", "automation_policies", "assets"):
        setattr(db, name, _Col())
    out = asyncio.run(BiAnalyticsService(db).get_bi_metrics("t1"))
    assert out["efficiency"] == {"mttr": None, "automation_rate": None,
                                 "patch_success_rate": None, "remediation_velocity": None}
    assert out["risk_profile"] == [] and out["trends"] == [] and out["asset_distribution"] == []
    assert out["insights"]["risk_level"] is None


def test_bi_forecast_is_a_fit_of_the_actuals():
    from bi_analytics_service import _linear_fit
    slope, intercept = _linear_fit([(0, 10.0), (1, 12.0), (2, 14.0)])
    assert slope == pytest.approx(2.0) and intercept == pytest.approx(10.0)


# ── Cookie consent: percentages present even with no records ─────────────────

def test_cookie_stats_include_percentages_when_empty():
    from cookie_consent_service import CookieConsentService
    db = MagicMock()
    db.cookie_consent_records = _Col()
    svc = CookieConsentService()
    with patch.object(svc, "_db", return_value=db):
        stats = asyncio.run(svc.get_stats("t1"))
    assert stats["fullConsentPct"] == 0 and stats["byCategoryPct"] == {}


# ── Trust Center: framable public page, measured analytics ──────────────────

def test_public_trust_page_allows_same_origin_framing_and_external_script():
    from app import _fastapi_app
    res = TestClient(_fastapi_app).get("/trust/any-slug")
    assert res.status_code == 200
    assert res.headers["x-frame-options"] == "SAMEORIGIN"
    assert "frame-ancestors 'self'" in res.headers["content-security-policy"]
    # the page's script must be a same-origin file: CSP blocks inline scripts
    assert '<script src="/static/trust-page.js"></script>' in res.text
    assert "<script>" not in res.text and "fonts.googleapis.com" not in res.text


def test_trust_analytics_counts_recorded_views():
    import trust_endpoints as te
    import trust_service as ts
    db = MagicMock()
    db.trust_profiles = _Col([{"public_documents": [{"name": "Policy", "url": "/p.pdf"}]}])
    db.trust_page_views = _Col()
    db._db.trust_page_views = db.trust_page_views
    asyncio.run(ts.record_profile_view(db, "t1"))
    asyncio.run(ts.record_profile_view(db, "t1"))
    with patch.object(te, "get_database", return_value=db), \
         patch.object(ts, "count_profile_views", AsyncMock(return_value=len(db.trust_page_views.docs))):
        res = TestClient(_app(te.router)).get("/api/trust-center/analytics").json()
    assert res == {"profile_views_30d": 2, "public_documents": 1}


# ── Agent installer: the public download never starts a build ───────────────

def test_public_installer_download_does_not_trigger_a_build(tmp_path):
    import update_endpoints as ue
    with patch.object(ue, "BINARY_STORAGE_PATH", str(tmp_path)), \
         patch.object(ue, "_executor") as executor:
        res = TestClient(_app(ue.router)).get("/api/agent-updates/download/OmniAgent-Setup.exe")
    assert res.status_code == 404
    executor.submit.assert_not_called()


def test_build_info_explains_why_no_installer_is_available(tmp_path):
    import update_endpoints as ue
    with patch.object(ue, "BINARY_STORAGE_PATH", str(tmp_path)), patch("sys.platform", "linux"):
        info = ue.installer_build_info()
        assert info["available"] is False and "Windows" in info["reason"]
        (tmp_path / "OmniAgent-Setup.exe").write_bytes(b"MZ")
        assert ue.installer_build_info()["available"] is True


# ── System Health: background task status comes from the event loop ─────────

def test_background_tasks_report_live_state():
    import system_health_endpoints as she

    async def scenario():
        async def forever():
            await asyncio.sleep(3600)
        task = asyncio.create_task(forever(), name="nvd_sync_loop")
        try:
            return {t["name"]: t["status"] for t in she._background_tasks()}
        finally:
            task.cancel()

    status = asyncio.run(scenario())
    assert status["NVD CVE Sync"] == "running"
    assert status["XDR Correlation Engine"] == "not running"


# ── Secure Share: real files behind token, password, expiry and limits ──────

def test_secure_share_round_trip(tmp_path):
    import file_share_endpoints as fe
    import file_share_service as fs
    db = MagicMock()
    db.file_shares = _Col()
    db._db = db
    with patch.object(fs, "SHARE_DIR", str(tmp_path)), patch.object(fe, "get_database", return_value=db):
        client = TestClient(_app(fe.router))
        created = client.post(
            "/api/file-share/shares",
            files={"file": ("report.txt", b"quarterly numbers", "text/plain")},
            data={"expires_in_days": "7", "password": "s3cret", "max_accesses": "1"},
        )
        assert created.status_code == 200, created.text
        share = created.json()
        assert "password_hash" not in share and "stored_name" not in share
        token = share["access_token"]

        anon = TestClient(_app(fe.router))
        assert anon.post(f"/api/file-share/access/{token}", json={}).status_code == 403
        assert anon.post(f"/api/file-share/access/{token}", json={"password": "nope"}).status_code == 403
        ok = anon.post(f"/api/file-share/access/{token}", json={"password": "s3cret"})
        assert ok.status_code == 200 and ok.content == b"quarterly numbers"
        assert "attachment" in ok.headers["content-disposition"]
        # max_accesses=1 is enforced
        assert anon.post(f"/api/file-share/access/{token}", json={"password": "s3cret"}).status_code == 410
        assert anon.post("/api/file-share/access/not-a-token", json={}).status_code == 404

        # revoking removes the stored file
        assert client.delete(f"/api/file-share/shares/{share['id']}").status_code == 200
        assert not any(tmp_path.iterdir())
