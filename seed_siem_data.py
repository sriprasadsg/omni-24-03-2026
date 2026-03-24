import asyncio
import httpx
import jwt
from datetime import datetime, timedelta

# Configuration should match authentication_service.py
SECRET_KEY = "enterprise-omni-agent-secret-key-change-me"
ALGORITHM = "HS256"

async def seed_siem():
    # Corrected URL: no /api prefix based on app.py and siem_endpoints.py
    url = "http://localhost:5010/api/siem/ingest"
    
    tenant_id = "tenant_2af80af8f8bc" 
    
    # Generate a JWT token for the seeding process
    token_data = {
        "sub": "seed-service@omni.ai",
        "role": "platform-admin",
        "tenant_id": "platform-admin",
        "exp": datetime.utcnow() + timedelta(hours=1)
    }
    token = jwt.encode(token_data, SECRET_KEY, algorithm=ALGORITHM)
    
    headers = {
        "Authorization": f"Bearer {token}",
        "X-Tenant-ID": tenant_id # Override for the specific tenant we want to seed
    }

    # The siem_endpoints.ingest_log takes source as a query param and payload as body
    events = [
        {"source": "okta", "event": {"action": "user.login.succeeded", "user": "admin@exafluence.com", "ip": "1.2.3.4"}},
        {"source": "cloudtrail", "event": {"eventName": "StopLogging", "userIdentity": {"type": "IAMUser", "userName": "attacker"}}},
        {"source": "syslog", "event": {"message": "Accepted password for root from 192.168.1.100 port 22 ssh2", "facility": "auth"}},
        {"source": "okta", "event": {"action": "user.mfa.factor.deactivate", "user": "victim@exafluence.com", "target": "TOTP"}}
    ]

    async with httpx.AsyncClient() as client:
        for e in events:
            try:
                # Correcting call: query params for source
                ingest_url = f"{url}?source={e['source']}"
                resp = await client.post(ingest_url, json=e['event'], headers=headers)
                print(f"Ingested {e['source']}: {resp.status_code} - {resp.text}")
            except Exception as ex:
                print(f"Failed to ingest {e['source']}: {ex}")

if __name__ == "__main__":
    asyncio.run(seed_siem())
