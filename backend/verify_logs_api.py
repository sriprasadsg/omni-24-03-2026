import requests
import json

API_BASE_URL = "http://localhost:5000"
EMAIL = "super@omni.ai"
PASSWORD = "password123"

def verify_logs():
    # 1. Login
    print(f"Logging in as {EMAIL}...")
    login_response = requests.post(
        f"{API_BASE_URL}/api/auth/login",
        json={"email": EMAIL, "password": PASSWORD}
    )
    
    if login_response.status_code != 200:
        print(f"Login failed: {login_response.status_code}")
        print(login_response.text)
        return
    
    token = login_response.json().get("access_token")
    print("Login successful.")
    
    # 2. Fetch Logs
    print("Fetching logs...")
    headers = {"Authorization": f"Bearer {token}"}
    logs_response = requests.get(
        f"{API_BASE_URL}/api/logs",
        headers=headers
    )
    
    if logs_response.status_code != 200:
        print(f"Failed to fetch logs: {logs_response.status_code}")
        print(logs_response.text)
        return
    
    logs = logs_response.json()
    print(f"Retrieved {len(logs)} logs.")
    
    # 3. Check for our test logs
    test_logs = [log for log in logs if "verify_log_ingestion.py" in log.get("message", "")]
    
    if test_logs:
        print(f"SUCCESS: Found {len(test_logs)} test logs in the system!")
        for log in test_logs:
            print(f" - [{log.get('severity')}] {log.get('service')}: {log.get('message')}")
    else:
        print("FAILURE: Test logs not found in the system.")
        # Print last 5 logs for context
        print("Last 5 logs in system:")
        for log in logs[:5]:
            print(f" - [{log.get('severity')}] {log.get('service')}: {log.get('message')}")

if __name__ == "__main__":
    verify_logs()
