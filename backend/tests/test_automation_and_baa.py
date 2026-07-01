"""
Tests for automation_endpoints.py and baa_endpoints.py.

Covers:
  - Automation: GET/POST/PUT scoping, RBAC, whitelist validation, tenant isolation
  - BAA: list/create/sign/terminate, bug regression (single-party sign must not activate)
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from fastapi import FastAPI
from fastapi.testclient import TestClient
from authentication_service import get_current_user
from auth_types import TokenData


# ─── helpers ─────────────────────────────────────────────────────────────────

def _col(**overrides):
    col = MagicMock()
    col.find_one   = AsyncMock(return_value=None)
    col.insert_one = AsyncMock()
    col.update_one = AsyncMock(return_value=MagicMock(matched_count=1))
    col.delete_one = AsyncMock()
    col.find       = MagicMock()
    col.find.return_value.to_list = AsyncMock(return_value=[])
    col.find.return_value.sort    = MagicMock(return_value=MagicMock())
    col.find.return_value.sort.return_value.to_list = AsyncMock(return_value=[])
    for k, v in overrides.items():
        setattr(col, k, v)
    return col


def _db(**collections):
    db = MagicMock()
    db.__getitem__ = lambda self, name: getattr(self, name, _col())
    for name, col in collections.items():
        setattr(db, name, col)
    return db


def _user(role="security_analyst", tenant_id="t1"):
    return TokenData(username="test@example.com", role=role, tenant_id=tenant_id, mfa_verified=True)


def _app(router, user):
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_current_user] = lambda: user
    return app


VALID_POLICY = {
    "name": "Auto-remediate offline agents",
    "description": "Kicks off remediation when an agent goes offline.",
    "trigger": "agent.error",
    "action": "remediate.agent",
    "conditions": [{"field": "severity", "operator": "equals", "value": "critical"}],
    "isEnabled": True,
}


# ═══════════════════════════════════════════════════════════════════════════════
# Automation Policies
# ═══════════════════════════════════════════════════════════════════════════════

class TestAutomationPoliciesGet:

    def test_get_returns_list(self):
        from automation_endpoints import router
        policies = [{"id": "p1", "tenantId": "t1", "name": "P1"}]
        col = _col()
        col.find.return_value.to_list = AsyncMock(return_value=policies)
        db = _db(automation_policies=col)
        app = _app(router, _user(role="Viewer"))
        with patch("automation_endpoints.get_database", return_value=db):
            res = TestClient(app).get("/api/automation-policies")
        assert res.status_code == 200
        assert res.json() == policies

    def test_super_admin_passes_empty_filter(self):
        from automation_endpoints import router
        col = _col()
        col.find.return_value.to_list = AsyncMock(return_value=[])
        db = _db(automation_policies=col)
        app = _app(router, _user(role="super_admin", tenant_id=None))
        with patch("automation_endpoints.get_database", return_value=db):
            TestClient(app).get("/api/automation-policies")
        # Super admin should query with {} (no tenantId filter)
        call_filter = col.find.call_args.args[0]
        assert call_filter == {}, f"Expected empty filter for super_admin, got {call_filter}"


class TestAutomationPoliciesCreate:

    def test_create_success(self):
        from automation_endpoints import router
        col = _col()
        db = _db(automation_policies=col)
        app = _app(router, _user(role="security_analyst"))
        with patch("automation_endpoints.get_database", return_value=db):
            res = TestClient(app).post("/api/automation-policies", json=VALID_POLICY)
        assert res.status_code == 200
        data = res.json()
        assert "id" in data
        assert data["name"] == VALID_POLICY["name"]
        assert data["tenantId"] == "t1"

    def test_create_forbidden_for_viewer(self):
        from automation_endpoints import router
        db = _db(automation_policies=_col())
        app = _app(router, _user(role="Viewer"))
        with patch("automation_endpoints.get_database", return_value=db):
            res = TestClient(app).post("/api/automation-policies", json=VALID_POLICY)
        assert res.status_code == 403

    def test_create_rejects_invalid_trigger(self):
        from automation_endpoints import router
        db = _db(automation_policies=_col())
        app = _app(router, _user(role="admin"))
        with patch("automation_endpoints.get_database", return_value=db):
            res = TestClient(app).post("/api/automation-policies",
                                       json={**VALID_POLICY, "trigger": "evil.trigger"})
        assert res.status_code == 400
        assert "trigger" in res.json()["detail"].lower()

    def test_create_rejects_invalid_action(self):
        from automation_endpoints import router
        db = _db(automation_policies=_col())
        app = _app(router, _user(role="admin"))
        with patch("automation_endpoints.get_database", return_value=db):
            res = TestClient(app).post("/api/automation-policies",
                                       json={**VALID_POLICY, "action": "destroy.everything"})
        assert res.status_code == 400

    def test_create_rejects_invalid_condition_operator(self):
        from automation_endpoints import router
        db = _db(automation_policies=_col())
        app = _app(router, _user(role="admin"))
        bad_conditions = [{"field": "x", "operator": "eval", "value": "1"}]
        with patch("automation_endpoints.get_database", return_value=db):
            res = TestClient(app).post("/api/automation-policies",
                                       json={**VALID_POLICY, "conditions": bad_conditions})
        assert res.status_code == 400


class TestAutomationPoliciesUpdate:

    def test_update_success(self):
        from automation_endpoints import router
        existing = {"id": "p1", "tenantId": "t1", **VALID_POLICY}
        updated  = {**existing, "isEnabled": False}
        col = _col()
        col.find_one = AsyncMock(side_effect=[existing, updated])
        db = _db(automation_policies=col)
        app = _app(router, _user(role="admin"))
        with patch("automation_endpoints.get_database", return_value=db):
            res = TestClient(app).put("/api/automation-policies",
                                      json={**VALID_POLICY, "id": "p1", "isEnabled": False})
        assert res.status_code == 200

    def test_update_forbidden_cross_tenant(self):
        from automation_endpoints import router
        # Policy belongs to t2, caller is t1
        existing = {"id": "p1", "tenantId": "t2", **VALID_POLICY}
        col = _col()
        col.find_one = AsyncMock(return_value=existing)
        db = _db(automation_policies=col)
        app = _app(router, _user(role="admin", tenant_id="t1"))
        with patch("automation_endpoints.get_database", return_value=db):
            res = TestClient(app).put("/api/automation-policies",
                                      json={**VALID_POLICY, "id": "p1", "isEnabled": False})
        assert res.status_code == 403

    def test_update_not_found(self):
        from automation_endpoints import router
        col = _col()
        col.find_one = AsyncMock(return_value=None)
        db = _db(automation_policies=col)
        app = _app(router, _user(role="admin"))
        with patch("automation_endpoints.get_database", return_value=db):
            res = TestClient(app).put("/api/automation-policies",
                                      json={**VALID_POLICY, "id": "nonexistent"})
        assert res.status_code == 404

    def test_super_admin_can_update_any_tenant(self):
        from automation_endpoints import router
        existing = {"id": "p1", "tenantId": "other-tenant", **VALID_POLICY}
        updated  = {**existing, "isEnabled": False}
        col = _col()
        col.find_one = AsyncMock(side_effect=[existing, updated])
        col.update_one = AsyncMock(return_value=MagicMock(matched_count=1))
        db = _db(automation_policies=col)
        app = _app(router, _user(role="super_admin", tenant_id=None))
        with patch("automation_endpoints.get_database", return_value=db):
            res = TestClient(app).put("/api/automation-policies",
                                      json={**VALID_POLICY, "id": "p1", "isEnabled": False})
        assert res.status_code == 200


# ═══════════════════════════════════════════════════════════════════════════════
# BAA Endpoints
# ═══════════════════════════════════════════════════════════════════════════════

class TestBAACreate:

    def test_create_returns_draft_with_tenant(self):
        from baa_endpoints import router
        col = _col()
        db = _db(baa_agreements=col)
        app = _app(router, _user(role="Tenant Admin"))
        # baa_endpoints imports get_database lazily inside _db(), so patch at database module level
        with patch("database.get_database", return_value=db):
            res = TestClient(app).post("/api/baa", json={
                "business_associate": "ACME Corp",
                "contact_email": "legal@acme.com",
            })
        assert res.status_code == 200
        data = res.json()
        assert data["status"] == "draft"
        assert data["business_associate"] == "ACME Corp"
        assert data.get("tenantId") == "t1"

    def test_create_starts_unsigned(self):
        from baa_endpoints import router
        col = _col()
        db = _db(baa_agreements=col)
        app = _app(router, _user(role="admin"))
        with patch("database.get_database", return_value=db):
            res = TestClient(app).post("/api/baa", json={"business_associate": "X"})
        assert res.status_code == 200
        data = res.json()
        assert data["signed_by_us"] is False
        assert data["signed_by_vendor"] is False


class TestBAASign:

    def test_single_party_sign_does_not_activate(self):
        """Regression: signing by only one party must NOT set status='active'."""
        from baa_endpoints import router
        baa = {"id": "b1", "tenantId": "t1", "status": "draft",
               "signed_by_us": False, "signed_by_vendor": False}
        col = _col()
        # find_one after first sign: signed_by_us=True but vendor still False
        col.find_one = AsyncMock(return_value={**baa, "signed_by_us": True, "signed_by_vendor": False})
        col.update_one = AsyncMock(return_value=MagicMock(matched_count=1))
        db = _db(baa_agreements=col)
        app = _app(router, _user(role="admin"))

        with patch("database.get_database", return_value=db):
            res = TestClient(app).post("/api/baa/b1/sign", json={"party": "us"})

        assert res.status_code == 200
        for call in col.update_one.call_args_list:
            update_doc = call.args[1] if len(call.args) > 1 else {}
            status_set = update_doc.get("$set", {}).get("status")
            assert status_set != "active", "Bug regression: BAA activated after only one-party sign"

    def test_both_parties_signed_activates(self):
        """BAA activates only when both signed_by_us and signed_by_vendor are True."""
        from baa_endpoints import router
        col = _col()
        col.find_one = AsyncMock(return_value={
            "id": "b1", "tenantId": "t1", "status": "pending_signature",
            "signed_by_us": True, "signed_by_vendor": True,
        })
        col.update_one = AsyncMock(return_value=MagicMock(matched_count=1))
        db = _db(baa_agreements=col)
        app = _app(router, _user(role="admin"))

        with patch("database.get_database", return_value=db):
            TestClient(app).post("/api/baa/b1/sign", json={"party": "vendor"})

        activate_calls = [
            c for c in col.update_one.call_args_list
            if c.args[1].get("$set", {}).get("status") == "active"
        ]
        assert len(activate_calls) >= 1, "BAA should be activated when both parties sign"


class TestBAATerminate:

    def test_terminate_sets_status(self):
        from baa_endpoints import router
        col = _col()
        col.update_one = AsyncMock(return_value=MagicMock(matched_count=1))
        db = _db(baa_agreements=col)
        app = _app(router, _user(role="Tenant Admin"))

        with patch("database.get_database", return_value=db):
            res = TestClient(app).post("/api/baa/b1/terminate",
                                       json={"reason": "Vendor contract ended"})

        assert res.status_code == 200
        update_doc = col.update_one.call_args.args[1]
        assert update_doc["$set"]["status"] == "terminated"
        assert update_doc["$set"]["termination_reason"] == "Vendor contract ended"

    def test_terminate_respects_tenant_filter(self):
        """Terminate filter must include caller's tenantId to prevent cross-tenant attacks."""
        from baa_endpoints import router
        col = _col()
        col.update_one = AsyncMock(return_value=MagicMock(matched_count=0))
        db = _db(baa_agreements=col)
        app = _app(router, _user(role="Tenant Admin", tenant_id="t2"))

        with patch("database.get_database", return_value=db):
            TestClient(app).post("/api/baa/b1/terminate", json={"reason": "x"})

        filter_arg = col.update_one.call_args.args[0]
        assert filter_arg.get("tenantId") == "t2", (
            f"Filter should scope to caller tenant 't2', got {filter_arg}"
        )
