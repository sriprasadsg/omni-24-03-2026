from datetime import datetime, timedelta, timezone
from typing import List
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from database import TenantIsolatedDatabase
from itam_models import AssetRequest, AssetRequestCreate, AssetRequestStatus
from itam_asset_request_service import ItamAssetRequestService

# Mock for the get_database dependency
@pytest.fixture
def mock_db_client():
    with patch('database.get_database', autospec=True) as mock_get_db:
        mock_db = MagicMock(spec=TenantIsolatedDatabase)
        mock_db.asset_requests = AsyncMock()
        mock_get_db.return_value = mock_db
        yield mock_db

@pytest.fixture
def asset_request_service(mock_db_client):
    with patch('approval_service.ApprovalService', autospec=True) as MockApprovalService:
        mock_approval_service = MockApprovalService.return_value
        with patch('itam_notification_service.ItamNotificationService', autospec=True) as MockItamNotificationService:
            mock_notification_service = MockItamNotificationService.return_value
            service = ItamAssetRequestService(mock_db_client)
            service.approval_service = mock_approval_service
            service.notification_service = mock_notification_service
            yield service

@pytest.mark.asyncio
async def test_create_asset_request(asset_request_service, mock_db_client):
    tenant_id = "test_tenant"
    requester_id = "requester@example.com"
    request_data = AssetRequestCreate(
        item_description="New Laptop",
        quantity=1,
        reason="For new hire"
    )

    mock_db_client.asset_requests.insert_one.return_value = MagicMock(inserted_id="ar-test")
    mock_db_client.asset_requests.find_one.return_value = {
        "id": "ar-test",
        "tenant_id": tenant_id,
        "requester_id": requester_id,
        "item_description": request_data.item_description,
        "quantity": request_data.quantity,
        "reason": request_data.reason,
        "status": AssetRequestStatus.PENDING,
        "request_date": datetime.now(timezone.utc).isoformat(),
        "createdAt": datetime.now(timezone.utc).isoformat(),
        "updatedAt": datetime.now(timezone.utc).isoformat(),
    }

    asset_request = await asset_request_service.create_asset_request(tenant_id, requester_id, request_data)

    assert asset_request.item_description == request_data.item_description
    assert asset_request.status == AssetRequestStatus.PENDING
    asset_request_service.approval_service.create_approval_request.assert_called_once()
    asset_request_service.notification_service.send_asset_request_notification.assert_called_once()
    mock_db_client.asset_requests.insert_one.assert_called_once()

@pytest.mark.asyncio
async def test_get_asset_request(asset_request_service, mock_db_client):
    tenant_id = "test_tenant"
    request_id = "ar-test"
    mock_db_client.asset_requests.find_one.return_value = {
        "id": request_id,
        "tenant_id": tenant_id,
        "requester_id": "requester@example.com",
        "item_description": "New Monitor",
        "quantity": 2,
        "reason": "Upgrade",
        "status": AssetRequestStatus.PENDING,
        "request_date": datetime.now(timezone.utc).isoformat(),
        "createdAt": datetime.now(timezone.utc).isoformat(),
        "updatedAt": datetime.now(timezone.utc).isoformat(),
    }

    asset_request = await asset_request_service.get_asset_request(tenant_id, request_id)

    assert asset_request.id == request_id
    assert asset_request.tenant_id == tenant_id
    mock_db_client.asset_requests.find_one.assert_called_once_with({"id": request_id, "tenant_id": tenant_id})

@pytest.mark.asyncio
async def test_list_asset_requests(asset_request_service, mock_db_client):
    tenant_id = "test_tenant"
    mock_db_client.asset_requests.find.return_value.skip.return_value.limit.return_value.to_list.return_value = [
        {"id": "ar-1", "tenant_id": tenant_id, "status": AssetRequestStatus.PENDING, "requester_id": "req1", "item_description": "a", "quantity": 1, "reason": "a", "request_date": datetime.now(timezone.utc).isoformat()},
        {"id": "ar-2", "tenant_id": tenant_id, "status": AssetRequestStatus.APPROVED, "requester_id": "req2", "item_description": "b", "quantity": 1, "reason": "b", "request_date": datetime.now(timezone.utc).isoformat()}
    ]

    requests = await asset_request_service.list_asset_requests(tenant_id)
    assert len(requests) == 2
    assert requests[0].status == AssetRequestStatus.PENDING
    mock_db_client.asset_requests.find.assert_called_once_with({"tenant_id": tenant_id})

@pytest.mark.asyncio
async def test_approve_asset_request(asset_request_service, mock_db_client):
    tenant_id = "test_tenant"
    request_id = "ar-test"
    approver_id = "approver@example.com"

    pending_request_dict = {
        "id": request_id,
        "tenant_id": tenant_id,
        "requester_id": "requester@example.com",
        "item_description": "New Laptop",
        "quantity": 1,
        "reason": "For new hire",
        "status": AssetRequestStatus.PENDING,
        "request_date": datetime.now(timezone.utc).isoformat(),
        "createdAt": datetime.now(timezone.utc).isoformat(),
        "updatedAt": datetime.now(timezone.utc).isoformat(),
    }
    approved_request_dict = {**pending_request_dict, "status": AssetRequestStatus.APPROVED, "approver_id": approver_id, "approval_date": datetime.now(timezone.utc).isoformat()}

    mock_db_client.asset_requests.find_one.return_value = pending_request_dict
    mock_db_client.asset_requests.find_one_and_update.return_value = approved_request_dict

    approved_request = await asset_request_service.approve_asset_request(tenant_id, request_id, approver_id)

    assert approved_request.status == AssetRequestStatus.APPROVED
    assert approved_request.approver_id == approver_id
    asset_request_service.notification_service.send_asset_request_notification.assert_called_once()
    mock_db_client.asset_requests.find_one_and_update.assert_called_once()

@pytest.mark.asyncio
async def test_reject_asset_request(asset_request_service, mock_db_client):
    tenant_id = "test_tenant"
    request_id = "ar-test"
    approver_id = "approver@example.com"

    pending_request_dict = {
        "id": request_id,
        "tenant_id": tenant_id,
        "requester_id": "requester@example.com",
        "item_description": "New Laptop",
        "quantity": 1,
        "reason": "For new hire",
        "status": AssetRequestStatus.PENDING,
        "request_date": datetime.now(timezone.utc).isoformat(),
        "createdAt": datetime.now(timezone.utc).isoformat(),
        "updatedAt": datetime.now(timezone.utc).isoformat(),
    }
    rejected_request_dict = {**pending_request_dict, "status": AssetRequestStatus.REJECTED, "approver_id": approver_id, "approval_date": datetime.now(timezone.utc).isoformat()}

    mock_db_client.asset_requests.find_one.return_value = pending_request_dict
    mock_db_client.asset_requests.find_one_and_update.return_value = rejected_request_dict

    rejected_request = await asset_request_service.reject_asset_request(tenant_id, request_id, approver_id)

    assert rejected_request.status == AssetRequestStatus.REJECTED
    assert rejected_request.approver_id == approver_id
    asset_request_service.notification_service.send_asset_request_notification.assert_called_once()
    mock_db_client.asset_requests.find_one_and_update.assert_called_once()

@pytest.mark.asyncio
async def test_approve_non_pending_request_fails(asset_request_service, mock_db_client):
    tenant_id = "test_tenant"
    request_id = "ar-test"
    approver_id = "approver@example.com"

    # Mock an already approved request
    approved_request_dict = {
        "id": request_id,
        "tenant_id": tenant_id,
        "requester_id": "requester@example.com",
        "item_description": "New Laptop",
        "quantity": 1,
        "reason": "For new hire",
        "status": AssetRequestStatus.APPROVED, # Already approved
        "request_date": datetime.now(timezone.utc).isoformat(),
        "createdAt": datetime.now(timezone.utc).isoformat(),
        "updatedAt": datetime.now(timezone.utc).isoformat(),
    }
    mock_db_client.asset_requests.find_one.return_value = approved_request_dict

    result = await asset_request_service.approve_asset_request(tenant_id, request_id, approver_id)
    assert result is None
    asset_request_service.notification_service.send_asset_request_notification.assert_not_called()
    mock_db_client.asset_requests.find_one_and_update.assert_not_called()