import asyncio
from unittest.mock import MagicMock, AsyncMock
import sys
import os

# Add backend to path
sys.path.append(os.path.join(os.path.dirname(__file__), "backend"))

# Mock database module BEFORE importing finops_service
# We need to mock 'database' module because finops_service does 'from database import get_database'
mock_database = MagicMock()
sys.modules["database"] = mock_database

from backend.finops_service import FinOpsService

async def test_finops():
    print("Testing FinOps Logic...")
    
    # Mock DB
    mock_db = MagicMock()
    mock_database.get_database.return_value = mock_db
    
    service = FinOpsService()
    service.db = mock_db # Inject mock db explicitly just in case
    
    # Mock Tenant
    mock_db.tenants.find_one = AsyncMock(return_value={"id": "tenant-1", "name": "Test Tenant"})
    
    # Mock Agents
    mock_agents = [
        {"id": "agent-1", "status": "online", "tenantId": "tenant-1"},
        {"id": "agent-2", "status": "online", "tenantId": "tenant-1"},
        {"id": "agent-3", "status": "offline", "tenantId": "tenant-1"}
    ]
    # Mock cursor
    mock_cursor = AsyncMock()
    mock_cursor.to_list.return_value = mock_agents
    mock_db.agents.find.return_value = mock_cursor
    
    # Mock Update
    mock_db.tenants.update_one = AsyncMock()
    
    # Run calculation
    result = await service.calculate_tenant_costs("tenant-1")
    
    print(f"Result: {result}")
    
    # Verify
    assert result is not None
    assert result["currentMonthCost"] > 0
    # Check structure
    assert "costBreakdown" in result
    assert "costTrend" in result
    assert "forecastedCost" in result
    
    print("✅ FinOps Logic Verified")

if __name__ == "__main__":
    asyncio.run(test_finops())
