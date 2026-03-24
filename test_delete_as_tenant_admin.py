
import jwt
import requests
import datetime
import uuid

# Configuration
API_BASE = "http://localhost:5000/api"
SECRET_KEY = "enterprise-omni-agent-secret-key-change-me"
ALGORITHM = "HS256"

# Target Data (from previous script output)
# User: admin@exafluence.com
# Tenant ID: tenant_82dda0f33bc4 (matching Agent)
USER_EMAIL = "admin@exafluence.com"
TENANT_ID = "tenant_82dda0f33bc4"
ROLE = "Tenant Admin"
AGENT_ID = "agent-EILT0197"

def create_token():
    payload = {
        "sub": USER_EMAIL,
        "role": ROLE,
        "tenant_id": TENANT_ID,
        "exp": datetime.datetime.utcnow() + datetime.timedelta(hours=1)
    }
    encoded_jwt = jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt

def test_delete():
    token = create_token()
    print(f"Forged Token for {USER_EMAIL} ({ROLE}, {TENANT_ID})")
    
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }
    
    print(f"Attempting to delete {AGENT_ID}...")
    try:
        response = requests.delete(f"{API_BASE}/agents/{AGENT_ID}", headers=headers)
        print(f"Status Code: {response.status_code}")
        print(f"Response: {response.text}")
        
        if response.status_code == 200:
            print("SUCCESS: Agent deleted.")
        elif response.status_code == 403:
            print("FAILURE: 403 Forbidden. Permission denied.")
        else:
            print(f"FAILURE: Unexpected status code {response.status_code}")
            
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    test_delete()
