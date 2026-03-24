"""
Backend API Comprehensive Test Script
Tests all major API endpoints and database connectivity
"""

import asyncio
import httpx
from motor.motor_asyncio import AsyncIOMotorClient
from datetime import datetime

BASE_URL = "http://localhost:5000"

async def test_health_endpoint():
    """Test health endpoint"""
    async with httpx.AsyncClient() as client:
        response = await client.get(f"{BASE_URL}/health")
        return {
            "endpoint": "/health",
            "status": response.status_code,
            "response": response.json() if response.status_code == 200 else None
        }

async def test_agents_endpoint():
    """Test agents list endpoint"""
    async with httpx.AsyncClient() as client:
        response = await client.get(f"{BASE_URL}/api/agents")
        data = response.json() if response.status_code == 200 else None
        return {
            "endpoint": "/api/agents",
            "status": response.status_code,
            "agent_count": len(data) if data else 0,
            "sample": data[0] if data and len(data) > 0 else None
        }

async def test_assets_endpoint():
    """Test assets endpoint"""
    async with httpx.AsyncClient() as client:
        response = await client.get(f"{BASE_URL}/api/assets")
        data = response.json() if response.status_code == 200 else None
        return {
            "endpoint": "/api/assets",
            "status": response.status_code,
            "asset_count": len(data) if data else 0
        }

async def test_asset_details():
    """Test specific asset details"""
    async with httpx.AsyncClient() as client:
        response = await client.get(f"{BASE_URL}/api/assets/agent-EILT0197")
        data = response.json() if response.status_code == 200 else None
        return {
            "endpoint": "/api/assets/agent-EILT0197",
            "status": response.status_code,
            "has_hardware_data": bool(
                data and 
                data.get("cpuModel") != "Unknown CPU" and
                data.get("ram") != "Unknown" and
                data.get("macAddress") != "00:00:00:00:00:00"
            ) if data else False,
            "hardware": {
                "cpu": data.get("cpuModel"),
                "ram": data.get("ram"),
                "mac": data.get("macAddress")
            } if data else None
        }

async def test_asset_metrics():
    """Test asset metrics endpoint"""
    async with httpx.AsyncClient() as client:
        response = await client.get(f"{BASE_URL}/api/assets/agent-EILT0197/metrics?range=1h")
        data = response.json() if response.status_code == 200 else None
        return {
            "endpoint": "/api/assets/{id}/metrics",
            "status": response.status_code,
            "has_metrics": bool(data and len(data) > 0) if data else False
        }

async def test_database_connectivity():
    """Test MongoDB connectivity"""
    try:
        client = AsyncIOMotorClient("mongodb://localhost:27017")
        db = client["enterprise_omni_agent"]
        
        # Test collections
        collections = await db.list_collection_names()
        
        # Count documents
        agents_count = await db.agents.count_documents({})
        assets_count = await db.assets.count_documents({})
        
        client.close()
        
        return {
            "database": "MongoDB",
            "status": "Connected",
            "collections": collections,
            "agents_count": agents_count,
            "assets_count": assets_count
        }
    except Exception as e:
        return {
            "database": "MongoDB",
            "status": "Error",
            "error": str(e)
        }

async def main():
    print("=" * 80)
    print("BACKEND API COMPREHENSIVE TEST")
    print("=" * 80)
    print(f"Test Time: {datetime.now()}")
    print()
    
    # Run all tests
    tests = [
        ("Health Check", test_health_endpoint()),
        ("Agents API", test_agents_endpoint()),
        ("Assets API", test_assets_endpoint()),
        ("Asset Details", test_asset_details()),
        ("Asset Metrics", test_asset_metrics()),
        ("Database", test_database_connectivity())
    ]
    
    results = []
    for name, test in tests:
        print(f"Testing {name}...", end=" ")
        try:
            result = await test
            print("✅" if result.get("status") in [200, "Connected"] else "⚠️")
            results.append((name, result))
        except Exception as e:
            print(f"❌ Error: {e}")
            results.append((name, {"error": str(e)}))
    
    # Print detailed results
    print("\n" + "=" * 80)
    print("DETAILED RESULTS")
    print("=" * 80)
    
    for name, result in results:
        print(f"\n{name}:")
        for key, value in result.items():
            if isinstance(value, dict) and len(str(value)) > 200:
                print(f"  {key}: [Large object]")
            else:
                print(f"  {key}: {value}")
    
    print("\n" + "=" * 80)
    print("TEST SUMMARY")
    print("=" * 80)
    
    total = len(results)
    passed = sum(1 for _, r in results if r.get("status") in [200, "Connected"])
    print(f"Total Tests: {total}")
    print(f"Passed: {passed}")
    print(f"Failed: {total - passed}")
    print("=" * 80)

if __name__ == "__main__":
    asyncio.run(main())
