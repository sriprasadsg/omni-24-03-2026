import pytest
import sys
import os
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime, timezone, timedelta

_BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _BACKEND_DIR not in sys.path:
    sys.path.insert(0, _BACKEND_DIR)

from itam_scheduled_tasks import run_warranty_alert_pass, _tenant_admin_emails
from itam_finance_service import WARRANTY_STATUS_EXPIRING, WARRANTY_STATUS_EXPIRED

class MockDB:
    def __init__(self):
        self.assets = MagicMock()
        self.users = MagicMock()

@pytest.fixture
def mock_db():
    return MockDB()

class MockCursor:
    def __init__(self, assets):
        self.assets = assets
        self.index = 0

    def __aiter__(self):
        return self

    async def __anext__(self):
        if self.index < len(self.assets):
            asset = self.assets[self.index]
            self.index += 1
            return asset
        else:
            raise StopAsyncIteration

class TestItamScheduledTasks:
    @pytest.mark.asyncio
    async def test_warranty_alert_pass_expiring_asset(self, mock_db):
        """Test warranty alert pass triggers for expiring asset."""
        now = datetime.now(timezone.utc)
        expiry_soon = (now + timedelta(days=15)).isoformat()

        assets = [{
            "id": "asset-1",
            "tenantId": "tenant-a",
            "assetTag": "IT-0001",
            "warranty_expiry_date": expiry_soon,
            "warrantyAlertSentAt": None,
            "purchaseDate": "2024-01-01T00:00:00Z"
        }]

        mock_db.assets.find.return_value = MockCursor(assets)
        mock_db.assets.update_one = AsyncMock()
        mock_db.assets.find_one = AsyncMock(return_value=None) # For _tenant_admin_emails if needed

        with patch("itam_scheduled_tasks._tenant_admin_emails", return_value=["admin@tenant-a.com"]):
            with patch("itam_scheduled_tasks.ItamNotificationService") as MockNotificationService:
                mock_service = MockNotificationService.return_value
                mock_service.send_warranty_expiry_alert = AsyncMock()

                count = await run_warranty_alert_pass(mock_db)

                assert count == 1
                mock_service.send_warranty_expiry_alert.assert_awaited_once()
                call_args = mock_service.send_warranty_expiry_alert.call_args
                assert call_args.kwargs["warranty_status"] == WARRANTY_STATUS_EXPIRING
                mock_db.assets.update_one.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_warranty_alert_pass_expired_asset(self, mock_db):
        """Test warranty alert pass triggers for expired asset."""
        now = datetime.now(timezone.utc)
        expiry_past = (now - timedelta(days=10)).isoformat()

        assets = [{
            "id": "asset-2",
            "tenantId": "tenant-a",
            "assetTag": "IT-0002",
            "warranty_expiry_date": expiry_past,
            "warrantyAlertSentAt": None,
            "purchaseDate": "2023-01-01T00:00:00Z"
        }]

        mock_db.assets.find.return_value = MockCursor(assets)
        mock_db.assets.update_one = AsyncMock()

        with patch("itam_scheduled_tasks._tenant_admin_emails", return_value=["admin@tenant-a.com"]):
            with patch("itam_scheduled_tasks.ItamNotificationService") as MockNotificationService:
                mock_service = MockNotificationService.return_value
                mock_service.send_warranty_expiry_alert = AsyncMock()

                count = await run_warranty_alert_pass(mock_db)

                assert count == 1
                mock_service.send_warranty_expiry_alert.assert_awaited_once()
                call_args = mock_service.send_warranty_expiry_alert.call_args
                assert call_args.kwargs["warranty_status"] == WARRANTY_STATUS_EXPIRED

    @pytest.mark.asyncio
    async def test_warranty_alert_pass_active_asset_no_alert(self, mock_db):
        """Test warranty alert pass does not trigger for active asset outside window."""
        now = datetime.now(timezone.utc)
        expiry_far = (now + timedelta(days=100)).isoformat()

        assets = [{
            "id": "asset-3",
            "tenantId": "tenant-a",
            "assetTag": "IT-0003",
            "warranty_expiry_date": expiry_far,
            "warrantyAlertSentAt": None,
            "purchaseDate": "2024-01-01T00:00:00Z"
        }]

        mock_db.assets.find.return_value = MockCursor(assets)
        mock_db.assets.update_one = AsyncMock()

        with patch("itam_scheduled_tasks._tenant_admin_emails", return_value=["admin@tenant-a.com"]):
            with patch("itam_scheduled_tasks.ItamNotificationService") as MockNotificationService:
                mock_service = MockNotificationService.return_value
                mock_service.send_warranty_expiry_alert = AsyncMock()

                count = await run_warranty_alert_pass(mock_db)

                assert count == 0
                mock_service.send_warranty_expiry_alert.assert_not_awaited()
                mock_db.assets.update_one.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_warranty_alert_pass_already_alerted_skipped(self, mock_db):
        """Test warranty alert pass skips asset already alerted."""
        now = datetime.now(timezone.utc)
        expiry_soon = (now + timedelta(days=15)).isoformat()

        assets = [{
            "id": "asset-4",
            "tenantId": "tenant-a",
            "assetTag": "IT-0004",
            "warranty_expiry_date": expiry_soon,
            "warrantyAlertSentAt": "2024-01-01T00:00:00Z", # Already alerted
            "purchaseDate": "2024-01-01T00:00:00Z"
        }]

        mock_db.assets.find.return_value = MockCursor(assets)
        mock_db.assets.update_one = AsyncMock()

        with patch("itam_scheduled_tasks._tenant_admin_emails", return_value=["admin@tenant-a.com"]):
            with patch("itam_scheduled_tasks.ItamNotificationService") as MockNotificationService:
                mock_service = MockNotificationService.return_value
                mock_service.send_warranty_expiry_alert = AsyncMock()

                count = await run_warranty_alert_pass(mock_db)

                assert count == 0
                mock_service.send_warranty_expiry_alert.assert_not_awaited()
                mock_db.assets.update_one.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_warranty_alert_pass_no_tenant_id_skipped(self, mock_db):
        """Test warranty alert pass skips asset with no tenantId."""
        now = datetime.now(timezone.utc)
        expiry_soon = (now + timedelta(days=15)).isoformat()

        assets = [{
            "id": "asset-5",
            "tenantId": "",
            "assetTag": "IT-0005",
            "warranty_expiry_date": expiry_soon,
            "warrantyAlertSentAt": None,
            "purchaseDate": "2024-01-01T00:00:00Z"
        }]

        mock_db.assets.find.return_value = MockCursor(assets)
        mock_db.assets.update_one = AsyncMock()

        with patch("itam_scheduled_tasks._tenant_admin_emails", return_value=["admin@tenant-a.com"]):
            with patch("itam_scheduled_tasks.ItamNotificationService") as MockNotificationService:
                mock_service = MockNotificationService.return_value
                mock_service.send_warranty_expiry_alert = AsyncMock()

                count = await run_warranty_alert_pass(mock_db)

                assert count == 0
                mock_service.send_warranty_expiry_alert.assert_not_awaited()