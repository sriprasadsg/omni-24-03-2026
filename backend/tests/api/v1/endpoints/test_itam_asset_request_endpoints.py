from datetime import datetime, timezone
from typing import List
from unittest.mock import AsyncMock, patch, MagicMock

import pytest
from fastapi import status
from fastapi.testclient import TestClient

from app.main import app  # Assuming main.py is where the FastAPI app is initialized and routers are included
from authentication_service import get_current_user
from rbac_utils import verify_permission
from itam_models import AssetRequest, AssetRequestCreate, AssetRequestStatus
from itam_asset_request_service import ItamAssetRequestService

# Mock for get_current_user to return a test user
@pytest.fixture
def test_user():
    return MagicMock(
        tenant_id="test_tenant",
        email="test_user@example.com",
        roles=["Requester"],
        permissions=["create:asset_request", "view:asset_request"]
    )

@pytest.fixture
def test_approver_user():
    return MagicMock(
        tenant_id="test_tenant",
        email="test_approver@example.com",
        roles=["Approver"],
        permissions=["approve:asset_request", "view:asset_request"]
    )

# Mock ItamAssetRequestService
@pytest.fixture
def mock_asset_request_service():
    with patch('itam_asset_request_service.ItamAssetRequestService', autospec=True) as MockService:
        service_instance = MockService.return_value
        yield service_instance

@pytest.fixture(autouse=True)
def mock_dependencies(test_user, test_approver_user, mock_asset_request_service):
    app.dependency_overrides[get_current_user] = lambda: test_user
    app.dependency_overrides[verify_permission] = AsyncMock(return_value=True)
    with patch('database.get_database', autospec=True) as mock_get_db:
        mock_db = MagicMock()
        mock_get_db.return_value = mock_db
        yield
    app.dependency_overrides = {}

client = TestClient(app)

@pytest.mark.asyncio
async def test_create_asset_request_endpoint(test_user, mock_asset_request_service):
    request_data = AssetRequestCreate(
        item_description="New Keyboard",
        quantity=1,
        reason="Mechanical keyboard for coding"
    )
    mock_asset_request_service.create_asset_request.return_value = AssetRequest(
        id="ar-new",
        tenant_id=test_user.tenant_id,
        requester_id=test_user.email,
        item_description=request_data.item_description,
        quantity=request_data.quantity,
        reason=request_data.reason,
        status=AssetRequestStatus.PENDING,
        request_date=datetime.now(timezone.utc),
        createdAt=datetime.now(timezone.utc),
        updatedAt=datetime.now(timezone.utc),
    )

    response = client.post(
        "/api/v1/itam/asset-requests",
        json=request_data.model_dump(),
        headers={"Authorization": "Bearer test_token"}
    )

    assert response.status_code == status.HTTP_201_CREATED
    assert response.json()["item_description"] == "New Keyboard"
    mock_asset_request_service.create_asset_request.assert_called_once_with(
        test_user.tenant_id,
        test_user.email,
        request_data
    )

@pytest.mark.asyncio
async def test_get_asset_request_endpoint(test_user, mock_asset_request_service):
    request_id = "ar-new"
    mock_asset_request_service.get_asset_request.return_value = AssetRequest(
        id=request_id,
        tenant_id=test_user.tenant_id,
        requester_id=test_user.email,
        item_description="New Keyboard",
        quantity=1,
        reason="Mechanical keyboard for coding",
        status=AssetRequestStatus.PENDING,
        request_date=datetime.now(timezone.utc),
        createdAt=datetime.now(timezone.utc),
        updatedAt=datetime.now(timezone.utc),
    )

    response = client.get(
        f"/api/v1/itam/asset-requests/{request_id}",
        headers={"Authorization": "Bearer test_token"}
    )

    assert response.status_code == status.HTTP_200_OK
    assert response.json()["id"] == request_id
    mock_asset_request_service.get_asset_request.assert_called_once_with(
        test_user.tenant_id,
        request_id
    )

@pytest.mark.asyncio
async def test_list_asset_requests_endpoint(test_user, mock_asset_request_service):
    mock_asset_request_service.list_asset_requests.return_value = [
        AssetRequest(
            id="ar-1",
            tenant_id=test_user.tenant_id,
            requester_id=test_user.email,
            item_description="Item 1",
            quantity=1,
            reason="Reason 1",
            status=AssetRequestStatus.PENDING,
            request_date=datetime.now(timezone.utc),
            createdAt=datetime.now(timezone.utc),
            updatedAt=datetime.now(timezone.utc),
        ),
        AssetRequest(
            id="ar-2",
            tenant_id=test_user.tenant_id,
            requester_id="other_user@example.com",
            item_description="Item 2",
            quantity=2,
            reason="Reason 2",
            status=AssetRequestStatus.APPROVED,
            request_date=datetime.now(timezone.utc),
            createdAt=datetime.now(timezone.utc),
            updatedAt=datetime.now(timezone.utc),
        )
    ]

    response = client.get(
        "/api/v1/itam/asset-requests",
        headers={"Authorization": "Bearer test_token"}
    )

    assert response.status_code == status.HTTP_200_OK
    assert len(response.json()) == 1 # Only own requests for non-approver
    assert response.json()[0]["id"] == "ar-1"
    mock_asset_request_service.list_asset_requests.assert_called_once_with(
        test_user.tenant_id,
        None, # status_filter
        0, # skip
        100 # limit
    )

@pytest.mark.asyncio
async def test_approve_asset_request_endpoint(test_approver_user, mock_asset_request_service):
    app.dependency_overrides[get_current_user] = lambda: test_approver_user
    request_id = "ar-approve"
    mock_asset_request_service.approve_asset_request.return_value = AssetRequest(
        id=request_id,
        tenant_id=test_approver_user.tenant_id,
        requester_id="requester@example.com",
        item_description="Item to approve",
        quantity=1,
        reason="Reason",
        status=AssetRequestStatus.APPROVED,
        request_date=datetime.now(timezone.utc),
        approval_date=datetime.now(timezone.utc),
        approver_id=test_approver_user.email,
        createdAt=datetime.now(timezone.utc),
        updatedAt=datetime.now(timezone.utc),
    )

    response = client.patch(
        f"/api/v1/itam/asset-requests/{request_id}/approve",
        headers={"Authorization": "Bearer test_token"}
    )

    assert response.status_code == status.HTTP_200_OK
    assert response.json()["status"] == AssetRequestStatus.APPROVED
    mock_asset_request_service.approve_asset_request.assert_called_once_with(
        test_approver_user.tenant_id,
        request_id,
        test_approver_user.email
    )

@pytest.mark.asyncio
async def test_reject_asset_request_endpoint(test_approver_user, mock_asset_request_service):
    app.dependency_overrides[get_current_user] = lambda: test_approver_user
    request_id = "ar-reject"
    mock_asset_request_service.reject_asset_request.return_value = AssetRequest(
        id=request_id,
        tenant_id=test_approver_user.tenant_id,
        requester_id="requester@example.com",
        item_description="Item to reject",
        quantity=1,
        reason="Reason",
        status=AssetRequestStatus.REJECTED,
        request_date=datetime.now(timezone.utc),
        approval_date=datetime.now(timezone.utc),
        approver_id=test_approver_user.email,
        createdAt=datetime.now(timezone.utc),
        updatedAt=datetime.now(timezone.utc),
    )

    response = client.patch(
        f"/api/v1/itam/asset-requests/{request_id}/reject",
        headers={"Authorization": "Bearer test_token"}
    )

    assert response.status_code == status.HTTP_200_OK
    assert response.json()["status"] == AssetRequestStatus.REJECTED
    mock_asset_request_service.reject_asset_request.assert_called_once_with(
        test_approver_user.tenant_id,
        request_id,
        test_approver_user.email
    )

@pytest.mark.asyncio
async def test_create_asset_request_unauthorized(mock_asset_request_service):
    app.dependency_overrides[get_current_user] = lambda: MagicMock(
        tenant_id="test_tenant",
        email="unauthorized@example.com",
        roles=["User"],
        permissions=["view:dashboard"] # Missing create:asset_request
    )
    app.dependency_overrides[verify_permission] = AsyncMock(return_value=False)

    request_data = AssetRequestCreate(
        item_description="Unauthorized Item",
        quantity=1,
        reason="Need it"
    )

    response = client.post(
        "/api/v1/itam/asset-requests",
        json=request_data.model_dump(),
        headers={"Authorization": "Bearer test_token"}
    )

    assert response.status_code == status.HTTP_403_FORBIDDEN
    mock_asset_request_service.create_asset_request.assert_not_called()

@pytest.mark.asyncio
async def test_approve_asset_request_unauthorized(test_user, mock_asset_request_service):
    app.dependency_overrides[get_current_user] = lambda: test_user # A requester, not an approver
    app.dependency_overrides[verify_permission] = AsyncMock(side_effect=[True, False]) # view ok, approve not ok

    response = client.patch(
        "/api/v1/itam/asset-requests/ar-some-id/approve",
        headers={"Authorization": "Bearer test_token"}
    )

    assert response.status_code == status.HTTP_403_FORBIDDEN
    mock_asset_request_service.approve_asset_request.assert_not_called()