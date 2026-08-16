import pytest
from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch
from fastapi.testclient import TestClient
from app import _fastapi_app
from auth_types import TokenData
from authentication_service import get_current_user
from itam_models import AssetRequest, AssetRequestStatus
from itam_asset_request_service import ItamAssetRequestService

MOCK_TENANT_ID = "test-tenant-123"
MOCK_REQUESTER_EMAIL = "requester@example.com"
MOCK_APPROVER_EMAIL = "approver@example.com"
MOCK_REQUEST_ID = "ar-endpoint-123"
MOCK_ITEM_DESCRIPTION = "New Monitor"
MOCK_REASON = "Replacement for broken unit"

MOCK_REQUEST_DOC = {
    "id": MOCK_REQUEST_ID,
    "tenant_id": MOCK_TENANT_ID,
    "requester_id": MOCK_REQUESTER_EMAIL,
    "item_description": MOCK_ITEM_DESCRIPTION,
    "quantity": 1,
    "reason": MOCK_REASON,
    "status": AssetRequestStatus.PENDING,
    "request_date": datetime.now(timezone.utc).isoformat(),
}


@pytest.fixture(autouse=True)
def patch_dependencies():
    mock_user = TokenData(username=MOCK_REQUESTER_EMAIL, tenant_id=MOCK_TENANT_ID, role="user")
    _fastapi_app.dependency_overrides[get_current_user] = lambda: mock_user

    mock_service = AsyncMock(spec=ItamAssetRequestService)

    with patch("itam_asset_request_endpoints.verify_permission", new_callable=AsyncMock, return_value=True), \
         patch("itam_asset_request_endpoints.get_database", return_value=AsyncMock()), \
         patch("itam_asset_request_endpoints.ItamAssetRequestService", return_value=mock_service):
        yield mock_service

    if get_current_user in _fastapi_app.dependency_overrides:
        del _fastapi_app.dependency_overrides[get_current_user]


def test_create_asset_request_endpoint(patch_dependencies):
    patch_dependencies.create_asset_request.return_value = AssetRequest.model_validate(MOCK_REQUEST_DOC)

    with TestClient(_fastapi_app) as client:
        response = client.post("/api/v1/itam/asset-requests", json={
            "item_description": MOCK_ITEM_DESCRIPTION, "quantity": 1, "reason": MOCK_REASON
        })
        assert response.status_code == 201
        assert response.json()["item_description"] == MOCK_ITEM_DESCRIPTION


def test_get_asset_request_endpoint(patch_dependencies):
    patch_dependencies.get_asset_request.return_value = AssetRequest.model_validate(MOCK_REQUEST_DOC)

    with TestClient(_fastapi_app) as client:
        response = client.get(f"/api/v1/itam/asset-requests/{MOCK_REQUEST_ID}")
        assert response.status_code == 200
        data = response.json()
        assert data.get("id") == MOCK_REQUEST_ID
        assert "_id" not in data  # response_model_by_alias=False must keep the wire key "id"


def test_get_asset_request_endpoint_not_found(patch_dependencies):
    patch_dependencies.get_asset_request.return_value = None

    with TestClient(_fastapi_app) as client:
        response = client.get("/api/v1/itam/asset-requests/non-existent")
        assert response.status_code == 404


def test_list_asset_requests_endpoint(patch_dependencies):
    patch_dependencies.list_asset_requests.return_value = [
        AssetRequest.model_validate(MOCK_REQUEST_DOC),
        AssetRequest.model_validate({**MOCK_REQUEST_DOC, "id": "ar-2"}),
    ]

    with TestClient(_fastapi_app) as client:
        response = client.get("/api/v1/itam/asset-requests")
        assert response.status_code == 200
        assert len(response.json()) == 2


def test_list_asset_requests_endpoint_approver_without_request_assets():
    """itam_admin has manage:procurement but not request:assets — must still
    be able to list the queue it needs to approve/reject (regression test for
    the bug where list/get required request:assets specifically, locking
    approvers out of the requests they were supposed to review)."""
    mock_user = TokenData(username=MOCK_APPROVER_EMAIL, tenant_id=MOCK_TENANT_ID, role="itam_admin")
    _fastapi_app.dependency_overrides[get_current_user] = lambda: mock_user

    mock_service = AsyncMock(spec=ItamAssetRequestService)
    mock_service.list_asset_requests.return_value = [AssetRequest.model_validate(MOCK_REQUEST_DOC)]

    async def fake_verify_permission(user, permission):
        return permission == "manage:procurement"

    with patch("itam_asset_request_endpoints.verify_permission", side_effect=fake_verify_permission), \
         patch("itam_asset_request_endpoints.get_database", return_value=AsyncMock()), \
         patch("itam_asset_request_endpoints.ItamAssetRequestService", return_value=mock_service):

        with TestClient(_fastapi_app) as client:
            response = client.get("/api/v1/itam/asset-requests")
            assert response.status_code == 200
            assert len(response.json()) == 1

    if get_current_user in _fastapi_app.dependency_overrides:
        del _fastapi_app.dependency_overrides[get_current_user]


def test_approve_asset_request_endpoint(patch_dependencies):
    patch_dependencies.approve_asset_request.return_value = AssetRequest.model_validate({
        **MOCK_REQUEST_DOC, "status": AssetRequestStatus.APPROVED, "approver_id": MOCK_APPROVER_EMAIL
    })

    with TestClient(_fastapi_app) as client:
        response = client.patch(f"/api/v1/itam/asset-requests/{MOCK_REQUEST_ID}/approve")
        assert response.status_code == 200
        assert response.json()["status"] == "approved"


def test_approve_asset_request_endpoint_bad_state(patch_dependencies):
    patch_dependencies.approve_asset_request.return_value = None

    with TestClient(_fastapi_app) as client:
        response = client.patch(f"/api/v1/itam/asset-requests/{MOCK_REQUEST_ID}/approve")
        assert response.status_code == 400


def test_reject_asset_request_endpoint(patch_dependencies):
    patch_dependencies.reject_asset_request.return_value = AssetRequest.model_validate({
        **MOCK_REQUEST_DOC, "status": AssetRequestStatus.REJECTED, "approver_id": MOCK_APPROVER_EMAIL
    })

    with TestClient(_fastapi_app) as client:
        response = client.patch(f"/api/v1/itam/asset-requests/{MOCK_REQUEST_ID}/reject")
        assert response.status_code == 200
        assert response.json()["status"] == "rejected"


def test_create_asset_request_permission_denied():
    mock_user = TokenData(username=MOCK_REQUESTER_EMAIL, tenant_id=MOCK_TENANT_ID, role="user")
    _fastapi_app.dependency_overrides[get_current_user] = lambda: mock_user

    mock_service = AsyncMock(spec=ItamAssetRequestService)

    with patch("itam_asset_request_endpoints.verify_permission", new_callable=AsyncMock, return_value=False), \
         patch("itam_asset_request_endpoints.get_database", return_value=AsyncMock()), \
         patch("itam_asset_request_endpoints.ItamAssetRequestService", return_value=mock_service):

        with TestClient(_fastapi_app) as client:
            response = client.post("/api/v1/itam/asset-requests", json={
                "item_description": MOCK_ITEM_DESCRIPTION, "quantity": 1, "reason": MOCK_REASON
            })
            assert response.status_code == 403

    if get_current_user in _fastapi_app.dependency_overrides:
        del _fastapi_app.dependency_overrides[get_current_user]


def test_approve_asset_request_permission_denied():
    mock_user = TokenData(username=MOCK_REQUESTER_EMAIL, tenant_id=MOCK_TENANT_ID, role="user")
    _fastapi_app.dependency_overrides[get_current_user] = lambda: mock_user

    mock_service = AsyncMock(spec=ItamAssetRequestService)

    with patch("itam_asset_request_endpoints.verify_permission", new_callable=AsyncMock, return_value=False), \
         patch("itam_asset_request_endpoints.get_database", return_value=AsyncMock()), \
         patch("itam_asset_request_endpoints.ItamAssetRequestService", return_value=mock_service):

        with TestClient(_fastapi_app) as client:
            response = client.patch(f"/api/v1/itam/asset-requests/{MOCK_REQUEST_ID}/approve")
            assert response.status_code == 403

    if get_current_user in _fastapi_app.dependency_overrides:
        del _fastapi_app.dependency_overrides[get_current_user]
