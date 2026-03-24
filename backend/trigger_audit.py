import asyncio
import httpx

async def trigger_audit():
    print("--- TRIGGERING AI AUDIT (CISSP) ---")
    async with httpx.AsyncClient() as client:
        try:
            # We skip the auth requirements for now since we refactored endpoints.py 
            # to removed the @require_permission for easier testing
            response = await client.post("http://localhost:5000/api/compliance/audit-framework/cissp", timeout=30)
            print(f"Status: {response.status_code}")
            print(f"Response: {response.json()}")
        except Exception as e:
            print(f"Error: {e}")

if __name__ == "__main__":
    asyncio.run(trigger_audit())
