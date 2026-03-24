
import requests
import jwt
from datetime import datetime, timedelta, timezone

# Configuration
API_BASE = "http://127.0.0.1:5000"
SECRET_KEY = "enterprise-omni-agent-secret-key-change-me"
ALGORITHM = "HS256"

def create_test_token():
    expire = datetime.now(timezone.utc) + timedelta(minutes=60)
    data = {
        "sub": "admin@example.com",
        "role": "admin",
        "tenant_id": "default",
        "exp": expire
    }
    return jwt.encode(data, SECRET_KEY, algorithm=ALGORITHM)

def test_endpoint():
    token = create_test_token()
    headers = {"Authorization": f"Bearer {token}"}
    
    print(f"Testing with token: {token[:10]}...")
    
    # Test without slash
    url_no_slash = f"{API_BASE}/api/experiments"
    print(f"\nGET {url_no_slash}")
    try:
        res = requests.get(url_no_slash, headers=headers, allow_redirects=False)
        print(f"Status: {res.status_code}")
        if res.status_code == 307:
            print(f"Redirect Location: {res.headers.get('Location')}")
    except Exception as e:
        print(f"Error: {e}")

    # Test with slash
    url_slash = f"{API_BASE}/api/experiments/"
    print(f"\nGET {url_slash}")
    try:
        res = requests.get(url_slash, headers=headers)
        print(f"Status: {res.status_code}")
        print(f"Response: {res.text[:100]}...")
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    test_endpoint()
