"""Phase 35 tests — GraphQL API layer (strawberry).

Verifies the schema builds and mounts, the hello query works, resolvers
enforce tenant isolation + RBAC from the context user, and unauthenticated
requests leak nothing.
"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from unittest.mock import AsyncMock, MagicMock, patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

import graphql_endpoints as gql_mod
from auth_types import TokenData


def _make_client():
    app = FastAPI()
    app.include_router(gql_mod.router)
    return TestClient(app)


def _user(tenant_id="tenant-a", role="Admin"):
    return TokenData(username="user@tenant.com", role=role, tenant_id=tenant_id, mfa_verified=True)


def _db_with(collection, docs):
    db = MagicMock()
    cursor = MagicMock()
    cursor.to_list = AsyncMock(return_value=docs)
    getattr(db, collection).find = MagicMock(return_value=cursor)
    return db


def _controls_db(docs):
    return _db_with("compliance_controls", docs)


def test_graphql_hello():
    client = _make_client()
    response = client.post("/api/graphql", json={"query": "{ hello }"})
    assert response.status_code == 200
    assert response.json()["data"]["hello"] == "Hello World"


def test_graphql_compliance_controls_tenant_scoped():
    docs = [{
        "id": "cc-1", "tenantId": "tenant-a", "framework": "SOC2",
        "controlId": "AC-1", "title": "Access Control", "status": "Compliant",
    }]
    db = _controls_db(docs)
    client = _make_client()
    query = "{ complianceControls { id framework controlId status } }"

    with patch("graphql_endpoints.get_current_user", AsyncMock(return_value=_user())), \
         patch("graphql_api.resolvers.mongodb") as mock_mongo, \
         patch("graphql_api.resolvers.verify_permission", AsyncMock(return_value=True)):
        mock_mongo.db = db
        response = client.post(
            "/api/graphql",
            json={"query": query},
            headers={"Authorization": "Bearer test-token"},
        )

    assert response.status_code == 200
    data = response.json()["data"]["complianceControls"]
    assert len(data) == 1
    assert data[0]["id"] == "cc-1"
    assert data[0]["controlId"] == "AC-1"
    # query was scoped to the caller's tenant
    assert db.compliance_controls.find.call_args.args[0] == {"tenantId": "tenant-a"}


def test_graphql_unauthenticated_gets_empty_not_data():
    """No bearer token → resolvers return empty lists, never other tenants' data."""
    db = _controls_db([{"id": "cc-1", "tenantId": "tenant-a", "framework": "SOC2",
                        "controlId": "AC-1", "title": "T", "status": "Compliant"}])
    client = _make_client()

    with patch("graphql_api.resolvers.mongodb") as mock_mongo:
        mock_mongo.db = db
        response = client.post(
            "/api/graphql",
            json={"query": "{ complianceControls { id } }"},
        )

    assert response.status_code == 200
    assert response.json()["data"]["complianceControls"] == []
    db.compliance_controls.find.assert_not_called()


def test_graphql_rbac_denied_gets_empty():
    """Authenticated but lacking view:compliance → empty result."""
    db = _controls_db([{"id": "cc-1"}])
    client = _make_client()

    with patch("graphql_endpoints.get_current_user", AsyncMock(return_value=_user(role="Viewer"))), \
         patch("graphql_api.resolvers.mongodb") as mock_mongo, \
         patch("graphql_api.resolvers.verify_permission", AsyncMock(return_value=False)):
        mock_mongo.db = db
        response = client.post(
            "/api/graphql",
            json={"query": "{ complianceControls { id } }"},
            headers={"Authorization": "Bearer test-token"},
        )

    assert response.status_code == 200
    assert response.json()["data"]["complianceControls"] == []
    db.compliance_controls.find.assert_not_called()


def _authed_post(client, db, query, user=None, permitted=True):
    """POST a query as an authenticated user with mocked db/permissions."""
    verify = AsyncMock(return_value=permitted)
    with patch("graphql_endpoints.get_current_user", AsyncMock(return_value=user or _user())), \
         patch("graphql_api.resolvers.mongodb") as mock_mongo, \
         patch("graphql_api.resolvers.verify_permission", verify):
        mock_mongo.db = db
        response = client.post(
            "/api/graphql",
            json={"query": query},
            headers={"Authorization": "Bearer test-token"},
        )
    return response, verify


def test_graphql_evidence_items_tenant_scoped():
    docs = [{
        "id": "ev-1", "tenantId": "tenant-a", "title": "SOC2 Report",
        "file_type": "pdf", "status": "valid", "uploaded_at": "2026-07-01",
    }]
    db = _db_with("evidence", docs)
    client = _make_client()

    response, verify = _authed_post(
        client, db, "{ evidenceItems { id title fileType status } }"
    )

    assert response.status_code == 200
    data = response.json()["data"]["evidenceItems"]
    assert len(data) == 1
    assert data[0] == {"id": "ev-1", "title": "SOC2 Report", "fileType": "pdf", "status": "valid"}
    assert db.evidence.find.call_args.args[0] == {"tenantId": "tenant-a"}
    assert verify.call_args.args[1] == "view:compliance"


def test_graphql_risks_tenant_scoped_and_uses_risk_permission():
    docs = [{
        "id": "r-1", "tenantId": "tenant-a", "title": "Data breach",
        "description": "d", "category": "security", "status": "Open",
        "likelihood": 4, "impact": 5, "risk_score": 20,
    }]
    db = _db_with("risks", docs)
    client = _make_client()

    response, verify = _authed_post(client, db, "{ risks { id title riskScore status } }")

    assert response.status_code == 200
    data = response.json()["data"]["risks"]
    assert data == [{"id": "r-1", "title": "Data breach", "riskScore": 20, "status": "Open"}]
    assert db.risks.find.call_args.args[0] == {"tenantId": "tenant-a"}
    assert verify.call_args.args[1] == "view:risk"


def test_graphql_users_tenant_scoped_and_password_excluded():
    docs = [{
        "id": "u-1", "tenantId": "tenant-a", "username": "a@t.com",
        "email": "a@t.com", "role": "Admin",
    }]
    db = _db_with("users", docs)
    client = _make_client()

    response, verify = _authed_post(client, db, "{ users { id username role tenantId } }")

    assert response.status_code == 200
    data = response.json()["data"]["users"]
    assert data == [{"id": "u-1", "username": "a@t.com", "role": "Admin", "tenantId": "tenant-a"}]
    assert db.users.find.call_args.args[0] == {"tenantId": "tenant-a"}
    projection = db.users.find.call_args.args[1]
    assert projection.get("password") == 0
    assert projection.get("hashed_password") == 0
    assert verify.call_args.args[1] == "manage:users"


def test_graphql_tenants_super_admin_only():
    docs = [
        {"id": "tenant-a", "name": "Acme", "subscription_tier": "enterprise", "enabled_features": ["gql"]},
        {"id": "tenant-b", "name": "Beta", "subscription_tier": "standard", "enabled_features": []},
    ]
    query = "{ tenants { id name subscriptionTier } }"
    client = _make_client()

    # Regular tenant Admin is NOT a super-admin: empty list, no db read.
    db = _db_with("tenants", docs)
    response, _ = _authed_post(client, db, query, user=_user(role="Admin"))
    assert response.status_code == 200
    assert response.json()["data"]["tenants"] == []
    db.tenants.find.assert_not_called()

    # Super-admin sees all tenants.
    db = _db_with("tenants", docs)
    response, _ = _authed_post(client, db, query, user=_user(role="super_admin"))
    assert response.status_code == 200
    data = response.json()["data"]["tenants"]
    assert [t["id"] for t in data] == ["tenant-a", "tenant-b"]
    assert data[0]["subscriptionTier"] == "enterprise"


def test_graphql_cross_tenant_isolation():
    """Tenant-b caller: query filter is tenant-b, tenant-a docs never surface."""
    client = _make_client()
    tenant_b_docs = [{
        "id": "cc-b1", "tenantId": "tenant-b", "framework": "ISO27001",
        "controlId": "A.5.1", "title": "Policies", "status": "Compliant",
    }]
    db = _controls_db(tenant_b_docs)

    response, _ = _authed_post(
        client, db, "{ complianceControls { id controlId } }",
        user=_user(tenant_id="tenant-b"),
    )

    assert response.status_code == 200
    data = response.json()["data"]["complianceControls"]
    assert db.compliance_controls.find.call_args.args[0] == {"tenantId": "tenant-b"}
    assert [c["id"] for c in data] == ["cc-b1"]


def test_graphql_multi_query_partial_permissions():
    """One request, two roots: permitted root returns data, denied root is empty."""
    client = _make_client()
    db = MagicMock()
    controls_cursor = MagicMock()
    controls_cursor.to_list = AsyncMock(return_value=[{
        "id": "cc-1", "tenantId": "tenant-a", "framework": "SOC2",
        "controlId": "AC-1", "title": "T", "status": "Compliant",
    }])
    db.compliance_controls.find = MagicMock(return_value=controls_cursor)
    risks_cursor = MagicMock()
    risks_cursor.to_list = AsyncMock(return_value=[{"id": "r-1", "tenantId": "tenant-a", "title": "R"}])
    db.risks.find = MagicMock(return_value=risks_cursor)

    async def perm(user, permission):
        return permission == "view:compliance"

    with patch("graphql_endpoints.get_current_user", AsyncMock(return_value=_user())), \
         patch("graphql_api.resolvers.mongodb") as mock_mongo, \
         patch("graphql_api.resolvers.verify_permission", side_effect=perm):
        mock_mongo.db = db
        response = client.post(
            "/api/graphql",
            json={"query": "{ complianceControls { id } risks { id } }"},
            headers={"Authorization": "Bearer test-token"},
        )

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["complianceControls"] == [{"id": "cc-1"}]
    assert data["risks"] == []
    db.risks.find.assert_not_called()
