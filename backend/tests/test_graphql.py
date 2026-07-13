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


def _controls_db(docs):
    db = MagicMock()
    cursor = MagicMock()
    cursor.to_list = AsyncMock(return_value=docs)
    db.compliance_controls.find = MagicMock(return_value=cursor)
    return db


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
