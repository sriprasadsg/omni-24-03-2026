import pytest
import sys
import os
from unittest.mock import AsyncMock, MagicMock
from datetime import datetime, timezone

_BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _BACKEND_DIR not in sys.path:
    sys.path.insert(0, _BACKEND_DIR)

from itam_asset_service import ItamAssetService

class MockTenantIsolatedDatabase:
    def __init__(self):
        self.assets = MagicMock()

class MockDB:
    def __init__(self):
        self.assets = MagicMock()

@pytest.fixture
def mock_db():
    return MockDB()

@pytest.fixture
def itam_asset_service(mock_db):
    return ItamAssetService(mock_db)

class TestItamAssetService:
    def test_calculate_depreciation_normal(self, itam_asset_service):
        """Test straight-line depreciation calculation with normal values."""
        # Purchase: $1000, Salvage: $100, Life: 5 years, Elapsed: 2 years
        book_value = itam_asset_service.calculate_depreciation(1000.0, 100.0, 5, 2)
        # Annual depreciation = (1000 - 100) / 5 = 180
        # Book value after 2 years = 1000 - (180 * 2) = 640
        assert book_value == 640.0

    def test_calculate_depreciation_floor_at_salvage(self, itam_asset_service):
        """Test that book value never goes below salvage value."""
        book_value = itam_asset_service.calculate_depreciation(1000.0, 100.0, 5, 10)
        assert book_value == 100.0

    def test_calculate_depreciation_zero_life(self, itam_asset_service):
        """Test depreciation with zero useful life (edge case)."""
        book_value = itam_asset_service.calculate_depreciation(1000.0, 100.0, 0, 2)
        assert book_value == 1000.0

    def test_calculate_depreciation_same_as_purchase(self, itam_asset_service):
        """Test book value at year 0 equals purchase price."""
        book_value = itam_asset_service.calculate_depreciation(1000.0, 100.0, 5, 0)
        assert book_value == 1000.0

    @pytest.mark.asyncio
    async def test_get_asset_depreciation_details_complete(self, itam_asset_service, mock_db):
        """Test getting depreciation details with complete data."""
        asset_data = {
            "id": "asset-123",
            "tenantId": "tenant-a",
            "purchaseCostCents": 100000,  # $1000.00
            "salvage_value": 100.0,
            "useful_life_years": 5,
            "purchaseDate": "2022-01-01T00:00:00Z"
        }
        mock_db.assets.find_one = AsyncMock(return_value=asset_data)

        result = await itam_asset_service.get_asset_depreciation_details("asset-123", "tenant-a")

        assert "book_value" in result
        assert "annual_depreciation" in result
        assert "years_elapsed" in result
        assert result["annual_depreciation"] == 180.0  # (1000 - 100) / 5

    @pytest.mark.asyncio
    async def test_get_asset_depreciation_details_missing_purchase_date(self, itam_asset_service, mock_db):
        """Test getting depreciation details when purchase date is missing."""
        asset_data = {
            "id": "asset-123",
            "tenantId": "tenant-a",
            "purchaseCostCents": 100000,
            "salvage_value": 100.0,
            "useful_life_years": 5,
            "purchaseDate": None
        }
        mock_db.assets.find_one = AsyncMock(return_value=asset_data)

        result = await itam_asset_service.get_asset_depreciation_details("asset-123", "tenant-a")

        assert "message" in result
        assert result["message"] == "Purchase date missing"

    @pytest.mark.asyncio
    async def test_get_asset_depreciation_details_asset_not_found(self, itam_asset_service, mock_db):
        """Test getting depreciation details when asset is not found."""
        mock_db.assets.find_one = AsyncMock(return_value=None)

        result = await itam_asset_service.get_asset_depreciation_details("asset-123", "tenant-a")

        assert result == {}

    @pytest.mark.asyncio
    async def test_get_asset_depreciation_details_zero_life(self, itam_asset_service, mock_db):
        """Test getting depreciation details when useful life is zero."""
        asset_data = {
            "id": "asset-123",
            "tenantId": "tenant-a",
            "purchaseCostCents": 100000,
            "salvage_value": 100.0,
            "useful_life_years": 0,
            "purchaseDate": "2022-01-01T00:00:00Z"
        }
        mock_db.assets.find_one = AsyncMock(return_value=asset_data)

        result = await itam_asset_service.get_asset_depreciation_details("asset-123", "tenant-a")

        assert "message" in result
        assert result["message"] == "Depreciation info incomplete"