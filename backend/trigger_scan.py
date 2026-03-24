import asyncio
import httpx

async def trigger_scan():
    print("--- TRIGGERING COMPLIANCE SCAN (CISSP) ---")
    async with httpx.AsyncClient() as client:
        try:
            # Full path in app.py is /api/compliance + /api/compliance/{framework_id}/scan ?? 
            # Wait, let me check app.py again for the router inclusion.
            # app.include_router(compliance_router) -> it doesn't specify a prefix sometimes.
            # But line 1013 says: app.include_router(ai_auditor_router, prefix="/api/compliance", tags=["Compliance AI"])
            # Line 1010 says: app.include_router(compliance_router)
            
            # Let's check common patterns. compliance_router defines /api/compliance/evidence.
            # So the URL is likely http://localhost:5000/api/compliance/cissp/scan
            
            url = "http://localhost:5000/api/compliance/cissp/scan"
            response = await client.post(url, timeout=30)
            print(f"Status: {response.status_code}")
            print(f"Response: {response.json()}")
        except Exception as e:
            print(f"Error: {e}")

if __name__ == "__main__":
    asyncio.run(trigger_scan())
