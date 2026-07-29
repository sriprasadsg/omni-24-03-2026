"""
Tests for geo_security_endpoints.py — Phase 47 Plan 04 (GSEC-02/GSEC-03, D-06).

Covers the admin-gated GET/PATCH /api/settings/geo-security config surface:
tenant-resolved reads (via geo_security_service.get_geo_security_settings),
admin-gated tenant-scoped writes (system_settings type "geo_security_detectors"),
and ISO 3166 alpha-2 country-code validation at the Pydantic boundary (D-03).

Mirrors test_agent_location_history_endpoints.py's mock-db factory, TestClient
+ dependency-override on get_current_user, and admin-gate test conventions.

This file MUST fail at collection/import (module does not exist yet) until
Task 2 lands backend/geo_security_endpoints.py — RED first.
"""
import os
import sys
from unittest.mock import AsyncMock, MagicMock, patch

_BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _BACKEND_DIR not in sys.path:
    sys.path.insert(0, _BACKEND_DIR)

# geo_security_endpoints.py is created in Task 2 — guard so collection
# succeeds even before that task lands (Task 1 runs first, RED).
try:
    import geo_security_endpoints as endpoints_mod
except ImportError:
    endpoints_mod = None

from fastapi import FastAPI
from fastapi.testclient import TestClient
from authentication_service import get_current_user
from auth_types import TokenData


# ---------------------------------------------------------------------------
# Shared mock-DB factory (mirrors test_agent_location_history_endpoints.py's
# _mock_db())
# ---------------------------------------------------------------------------
def _mock_db():
    db = MagicMock()

    settings_col = MagicMock()
    settings_col.find_one = AsyncMock(return_value=None)
    settings_col.update_one = AsyncMock()
    db.system_settings = settings_col

    # get_database()/get_geo_security_settings's `db._db if hasattr(db, "_db")
    # else db` unwrap guard must resolve back to this same configured mock.
    db._db = db

    return db


_TENANT_A_USER = TokenData(
    username="a@test.com", role="user", tenant_id="tenant-a", mfa_verified=True,
)
_TENANT_A_ADMIN = TokenData(
    username="admin@test.com", role="admin", tenant_id="tenant-a", mfa_verified=True,
)


def _app_for(user):
    app = FastAPI()
    app.include_router(endpoints_mod.router)
    app.dependency_overrides[get_current_user] = lambda: user
    return app


# ===========================================================================
# admin_gate
# ===========================================================================
class TestAdminGate:
    def test_admin_gate_non_admin_patch_forbidden(self):
        assert endpoints_mod is not None, "geo_security_endpoints not yet created (47-04)"
        db = _mock_db()

        with patch.object(endpoints_mod, "get_database", return_value=db):
            with TestClient(_app_for(_TENANT_A_USER)) as client:
                r = client.patch(
                    "/api/settings/geo-security",
                    json={"impossible_travel_enabled": False},
                )

        assert r.status_code == 403
        db.system_settings.update_one.assert_not_awaited()


# ===========================================================================
# get_returns_defaults
# ===========================================================================
class TestGetReturnsDefaults:
    def test_get_returns_hardcoded_defaults_when_no_doc_stored(self):
        assert endpoints_mod is not None, "geo_security_endpoints not yet created (47-04)"
        db = _mock_db()

        with patch.object(endpoints_mod, "get_database", return_value=db):
            with TestClient(_app_for(_TENANT_A_USER)) as client:
                r = client.get("/api/settings/geo-security")

        assert r.status_code == 200
        body = r.json()
        assert body["impossible_travel_enabled"] is True
        assert body["geo_fence_enabled"] is False
        assert body["allowed_country_codes"] == []


# ===========================================================================
# patch_persists
# ===========================================================================
class TestPatchPersists:
    def test_patch_persists_tenant_scoped_system_settings_doc(self):
        assert endpoints_mod is not None, "geo_security_endpoints not yet created (47-04)"
        db = _mock_db()
        state: dict = {}

        async def _update_one(filter_, update, upsert=False):
            state.update(update["$set"])
            return MagicMock()

        async def _find_one(filter_):
            return dict(state) if state else None

        db.system_settings.update_one = AsyncMock(side_effect=_update_one)
        db.system_settings.find_one = AsyncMock(side_effect=_find_one)

        with patch.object(endpoints_mod, "get_database", return_value=db):
            with TestClient(_app_for(_TENANT_A_ADMIN)) as client:
                patch_r = client.patch(
                    "/api/settings/geo-security",
                    json={
                        "impossible_travel_enabled": False,
                        "geo_fence_enabled": True,
                        "allowed_country_codes": ["US", "GB"],
                    },
                )
                assert patch_r.status_code == 200

                get_r = client.get("/api/settings/geo-security")

        db.system_settings.update_one.assert_awaited_once()
        call_args = db.system_settings.update_one.call_args
        filter_arg = call_args[0][0]
        assert filter_arg.get("type") == "geo_security_detectors"
        assert filter_arg.get("tenantId") == "tenant-a"

        body = get_r.json()
        assert body["impossible_travel_enabled"] is False
        assert body["geo_fence_enabled"] is True
        assert body["allowed_country_codes"] == ["US", "GB"]


# ===========================================================================
# validation_rejects_bad_country
# ===========================================================================
class TestValidationRejectsBadCountry:
    def test_patch_rejects_three_letter_country_code(self):
        assert endpoints_mod is not None, "geo_security_endpoints not yet created (47-04)"
        db = _mock_db()

        with patch.object(endpoints_mod, "get_database", return_value=db):
            with TestClient(_app_for(_TENANT_A_ADMIN)) as client:
                r = client.patch(
                    "/api/settings/geo-security",
                    json={"allowed_country_codes": ["USA", "x"]},
                )

        assert r.status_code in (400, 422)
        db.system_settings.update_one.assert_not_awaited()


# ===========================================================================
# validation_normalizes_case
# ===========================================================================
class TestValidationNormalizesCase:
    def test_patch_normalizes_lowercase_codes_to_uppercase(self):
        assert endpoints_mod is not None, "geo_security_endpoints not yet created (47-04)"
        db = _mock_db()
        state: dict = {}

        async def _update_one(filter_, update, upsert=False):
            state.update(update["$set"])
            return MagicMock()

        db.system_settings.update_one = AsyncMock(side_effect=_update_one)

        with patch.object(endpoints_mod, "get_database", return_value=db):
            with TestClient(_app_for(_TENANT_A_ADMIN)) as client:
                r = client.patch(
                    "/api/settings/geo-security",
                    json={"allowed_country_codes": ["us", "gb"]},
                )

        assert r.status_code == 200
        assert r.json()["allowed_country_codes"] == ["US", "GB"]
        assert state.get("allowed_country_codes") == ["US", "GB"]
