"""Tests for the FAIR risk quantification layer (plan 31-01, FAIR-01).

Covers the pure Monte Carlo engine (risk_fair_service) and the persisted,
tenant-scoped endpoint (risk_fair_endpoints + RiskService.attach_fair_results).
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from unittest.mock import AsyncMock, patch
from fastapi import FastAPI
from fastapi.testclient import TestClient

import risk_service
from risk_fair_service import run_fair_simulation
from risk_fair_endpoints import router
from authentication_service import get_current_user
from auth_types import TokenData


def _user(role="security_analyst", tenant_id="t1"):
    return TokenData(username="test@example.com", role=role, tenant_id=tenant_id, mfa_verified=True)


def _client(user):
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_current_user] = lambda: user
    return TestClient(app)


_VALID_INPUTS = {
    "lef_min": 1, "lef_likely": 2, "lef_max": 3,
    "lm_min": 1000, "lm_likely": 10000, "lm_max": 100000,
    "iterations": 5000,
}


# ─── engine ──────────────────────────────────────────────────────────────────

def test_math_sanity():
    """Point estimates (min==likely==max) collapse to a deterministic loss."""
    results = run_fair_simulation({
        "lef_min": 2, "lef_likely": 2, "lef_max": 2,
        "lm_min": 5000, "lm_likely": 5000, "lm_max": 5000,
        "iterations": 2000,
    })
    # Annual loss = 2 events/yr × $5000 = $10000, no variance.
    assert results["mean"] == 10000
    assert results["p10"] == results["p50"] == results["p90"] == 10000
    assert all(0.0 <= pt["probability"] <= 1.0 for pt in results["exceedance_curve"])


def test_math_distribution_ordering():
    """Non-degenerate inputs produce ordered percentiles and a bounded mean."""
    results = run_fair_simulation(_VALID_INPUTS)
    assert results["p10"] <= results["p50"] <= results["p90"]
    # LEF in [1,3], LM in [1e3,1e5] → annual loss strictly within [1e3, 3e5].
    assert 1000 <= results["mean"] <= 300000
    assert len(results["exceedance_curve"]) >= 1


# ─── endpoint: valid + persistence ──────────────────────────────────────────

@patch("risk_service.RiskService._db")
def test_valid_simulation_persists(mock_db):
    db = AsyncMock()
    db.risks.find_one.return_value = {"id": "r1", "title": "x", "tenantId": "t1", "likelihood": 3, "impact": 4}
    mock_db.return_value = db

    resp = _client(_user()).post("/api/risks/r1/fair-simulation", json=_VALID_INPUTS)
    assert resp.status_code == 200
    body = resp.json()
    assert body["fair_inputs"]["lef_likely"] == 2
    assert set(body["fair_results"]) == {"mean", "p10", "p50", "p90", "exceedance_curve"}
    db.risks.replace_one.assert_awaited_once()


# ─── endpoint: validation ────────────────────────────────────────────────────

def test_invalid_lef_range_rejected():
    bad = {**_VALID_INPUTS, "lef_min": 5, "lef_likely": 2, "lef_max": 3}
    resp = _client(_user()).post("/api/risks/r1/fair-simulation", json=bad)
    assert resp.status_code == 422


def test_invalid_lm_range_rejected():
    bad = {**_VALID_INPUTS, "lm_min": 50000, "lm_likely": 10000, "lm_max": 100000}
    resp = _client(_user()).post("/api/risks/r1/fair-simulation", json=bad)
    assert resp.status_code == 422


def test_iteration_ceiling_rejected():
    bad = {**_VALID_INPUTS, "iterations": 10_000_000}
    resp = _client(_user()).post("/api/risks/r1/fair-simulation", json=bad)
    assert resp.status_code == 422


# ─── endpoint: tenant isolation ──────────────────────────────────────────────

@patch("risk_service.RiskService._db")
def test_cross_tenant_returns_404(mock_db):
    db = AsyncMock()
    db.risks.find_one.return_value = None  # tenant filter excludes the risk
    mock_db.return_value = db

    resp = _client(_user(tenant_id="t2")).post("/api/risks/r1/fair-simulation", json=_VALID_INPUTS)
    assert resp.status_code == 404
    db.risks.replace_one.assert_not_awaited()


# ─── persistence method: no regression to unrelated fields ───────────────────

@patch("risk_service.RiskService._db")
def test_attach_preserves_existing_fields(mock_db):
    import asyncio
    db = AsyncMock()
    existing = {"id": "r1", "title": "keep", "tenantId": "t1", "risk_score": 12, "owner": "alice"}
    db.risks.find_one.return_value = existing
    mock_db.return_value = db

    merged = asyncio.run(risk_service.risk_service.attach_fair_results(
        "r1", _VALID_INPUTS, {"mean": 1.0}, tenant_id="t1", role="security_analyst"
    ))
    assert merged["title"] == "keep"
    assert merged["risk_score"] == 12
    assert merged["owner"] == "alice"
    assert merged["fair_inputs"] == _VALID_INPUTS
    assert merged["fair_results"] == {"mean": 1.0}
