import pytest
from datetime import datetime, timezone
from unittest.mock import MagicMock, AsyncMock, patch

from database import TenantIsolatedDatabase
from itam_models import AssetRequest, AssetRequestCreate, AssetRequestStatus
from itam_asset_request_service import ItamAssetRequestService

MOCK_TENANT_ID = "test-tenant-123"
MOCK_REQUESTER_ID = "requester@example.com"
MOCK_APPROVER_ID = "approver@example.com"
MOCK_REQUEST_ID = "ar-12345678"
MOCK_ITEM_DESCRIPTION = "New Monitor"
MOCK_QUANTITY = 1
MOCK_REASON = "Replacement for broken unit"


def _mock_doc(**overrides):
    doc = {
        "_id": MOCK_REQUEST_ID,
        "id": MOCK_REQUEST_ID,
        "tenant_id": MOCK_TENANT_ID,
        "requester_id": MOCK_REQUESTER_ID,
        "item_description": MOCK_ITEM_DESCRIPTION,
        "quantity": MOCK_QUANTITY,
        "reason": MOCK_REASON,
        "status": AssetRequestStatus.PENDING,
        "request_date": datetime.now(timezone.utc),
        "approval_date": None,
        "approver_id": None,
    }
    doc.update(overrides)
    return doc


@pytest.fixture
def mock_db() -> TenantIsolatedDatabase:
    db_instance = AsyncMock(spec=TenantIsolatedDatabase)
    mock_collection = MagicMock()
    mock_collection.insert_one = AsyncMock()
    mock_collection.find_one = AsyncMock()
    mock_collection.find_one_and_update = AsyncMock()
    mock_collection.find = MagicMock()
    db_instance.asset_requests = mock_collection
    return db_instance


@pytest.fixture
def asset_request_service(mock_db: TenantIsolatedDatabase) -> ItamAssetRequestService:
    with patch("itam_asset_request_service.ApprovalService") as MockApproval, \
         patch("itam_asset_request_service.ItamNotificationService") as MockNotify:
        MockApproval.return_value = AsyncMock()
        MockNotify.return_value = AsyncMock()
        yield ItamAssetRequestService(mock_db)


@pytest.mark.asyncio
async def test_create_asset_request(asset_request_service: ItamAssetRequestService, mock_db: TenantIsolatedDatabase):
    request_data = AssetRequestCreate(
        item_description=MOCK_ITEM_DESCRIPTION, quantity=MOCK_QUANTITY, reason=MOCK_REASON
    )

    mock_db.asset_requests.insert_one.return_value = AsyncMock(inserted_id=MOCK_REQUEST_ID)
    mock_db.asset_requests.find_one.return_value = _mock_doc()

    created = await asset_request_service.create_asset_request(MOCK_TENANT_ID, MOCK_REQUESTER_ID, request_data)

    mock_db.asset_requests.insert_one.assert_called_once()
    inserted_doc = mock_db.asset_requests.insert_one.call_args[0][0]
    assert inserted_doc["id"]  # explicit id must be set before insert, not left to Mongo's _id
    assert inserted_doc["tenant_id"] == MOCK_TENANT_ID
    assert inserted_doc["requester_id"] == MOCK_REQUESTER_ID
    assert inserted_doc["status"] == AssetRequestStatus.PENDING

    assert isinstance(created, AssetRequest)
    assert created.status == AssetRequestStatus.PENDING
    asset_request_service.approval_service.create_approval_request.assert_called_once()
    asset_request_service.notification_service.send_asset_request_notification.assert_called_once()


@pytest.mark.asyncio
async def test_get_asset_request_found(asset_request_service: ItamAssetRequestService, mock_db: TenantIsolatedDatabase):
    mock_db.asset_requests.find_one.return_value = _mock_doc()

    found = await asset_request_service.get_asset_request(MOCK_TENANT_ID, MOCK_REQUEST_ID)

    mock_db.asset_requests.find_one.assert_called_once_with({"id": MOCK_REQUEST_ID, "tenant_id": MOCK_TENANT_ID})
    assert isinstance(found, AssetRequest)
    assert found.id == MOCK_REQUEST_ID


@pytest.mark.asyncio
async def test_get_asset_request_not_found(asset_request_service: ItamAssetRequestService, mock_db: TenantIsolatedDatabase):
    mock_db.asset_requests.find_one.return_value = None

    found = await asset_request_service.get_asset_request(MOCK_TENANT_ID, "non-existent")

    assert found is None


@pytest.mark.asyncio
async def test_list_asset_requests(asset_request_service: ItamAssetRequestService, mock_db: TenantIsolatedDatabase):
    mock_cursor = MagicMock()
    mock_cursor.skip.return_value = mock_cursor
    mock_cursor.limit.return_value = mock_cursor
    mock_cursor.to_list = AsyncMock(return_value=[_mock_doc(), _mock_doc(id="ar-99999999")])
    mock_db.asset_requests.find.return_value = mock_cursor

    results = await asset_request_service.list_asset_requests(MOCK_TENANT_ID)

    assert len(results) == 2
    assert all(isinstance(r, AssetRequest) for r in results)


@pytest.mark.asyncio
async def test_approve_asset_request(asset_request_service: ItamAssetRequestService, mock_db: TenantIsolatedDatabase):
    mock_db.asset_requests.find_one.return_value = _mock_doc(status=AssetRequestStatus.PENDING)
    mock_db.asset_requests.find_one_and_update.return_value = _mock_doc(
        status=AssetRequestStatus.APPROVED, approver_id=MOCK_APPROVER_ID
    )

    approved = await asset_request_service.approve_asset_request(MOCK_TENANT_ID, MOCK_REQUEST_ID, MOCK_APPROVER_ID)

    assert approved is not None
    assert approved.status == AssetRequestStatus.APPROVED
    asset_request_service.notification_service.send_asset_request_notification.assert_called_once()


@pytest.mark.asyncio
async def test_approve_asset_request_not_pending(asset_request_service: ItamAssetRequestService, mock_db: TenantIsolatedDatabase):
    mock_db.asset_requests.find_one.return_value = _mock_doc(status=AssetRequestStatus.APPROVED)

    approved = await asset_request_service.approve_asset_request(MOCK_TENANT_ID, MOCK_REQUEST_ID, MOCK_APPROVER_ID)

    assert approved is None
    mock_db.asset_requests.find_one_and_update.assert_not_called()


@pytest.mark.asyncio
async def test_reject_asset_request(asset_request_service: ItamAssetRequestService, mock_db: TenantIsolatedDatabase):
    mock_db.asset_requests.find_one.return_value = _mock_doc(status=AssetRequestStatus.PENDING)
    mock_db.asset_requests.find_one_and_update.return_value = _mock_doc(
        status=AssetRequestStatus.REJECTED, approver_id=MOCK_APPROVER_ID
    )

    rejected = await asset_request_service.reject_asset_request(MOCK_TENANT_ID, MOCK_REQUEST_ID, MOCK_APPROVER_ID)

    assert rejected is not None
    assert rejected.status == AssetRequestStatus.REJECTED
    asset_request_service.notification_service.send_asset_request_notification.assert_called_once()


@pytest.mark.asyncio
async def test_reject_asset_request_not_pending(asset_request_service: ItamAssetRequestService, mock_db: TenantIsolatedDatabase):
    mock_db.asset_requests.find_one.return_value = _mock_doc(status=AssetRequestStatus.REJECTED)

    rejected = await asset_request_service.reject_asset_request(MOCK_TENANT_ID, MOCK_REQUEST_ID, MOCK_APPROVER_ID)

    assert rejected is None
    mock_db.asset_requests.find_one_and_update.assert_not_called()
