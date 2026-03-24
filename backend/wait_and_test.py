import asyncio
import time
from httpx import AsyncClient
import jwt
from datetime import datetime, timedelta, timezone

SECRET_KEY = "enterprise-omni-agent-secret-key-change-me"
ALGORITHM = "HS256"

def create_test_token(role: str, tenant_id: str):
    expire = datetime.now(timezone.utc) + timedelta(minutes=60)
    to_encode = {"sub": "test@omni.ai", "role": role, "tenant_id": tenant_id, "exp": expire}
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)

async def test_sbom():
    print("Waiting for backend to boot...")
    for _ in range(20):
        try:
            # Test Tenant Admin token
            token = create_test_token("Tenant Admin", "tenant_1234")
            headers = {"Authorization": f"Bearer {token}"}
            
            async with AsyncClient() as client:
                resp = await client.get("http://127.0.0.1:5000/api/sboms", headers=headers)
                print("Tenant Admin Response:", resp.status_code, resp.text)
                return
        except Exception as e:
            time.sleep(2)
    print("Backend never started.")

asyncio.run(test_sbom())
