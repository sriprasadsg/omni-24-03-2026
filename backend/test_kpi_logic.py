import asyncio
import jwt
from database import get_database, connect_to_mongo
from datetime import datetime, timedelta

# Mock a Super Admin user
SECRET_KEY = "your-secret-key" # Need to find the real one or mock it
ALGORITHM = "HS256"

async def check_kpi():
    await connect_to_mongo()
    db = get_database()
    
    # Check what's in the DB for Acme
    acme_id = "tenant_f15daa22a46a"
    total = await db.agents.count_documents({"tenantId": acme_id})
    online = await db.agents.count_documents({"tenantId": acme_id, "status": "Online"})
    print(f"Acme ({acme_id}) count in DB: {online}/{total}")

    # Now simulate the KPI endpoint logic
    query = {"tenantId": acme_id}
    # This matches kpi_endpoints.py:84
    active_agents = await db.agents.count_documents({**query, "status": "Online"})
    total_agents = await db.agents.count_documents(query)
    
    print(f"KPI Logic Result: {active_agents}/{total_agents}")

if __name__ == "__main__":
    asyncio.run(check_kpi())
