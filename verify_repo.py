import requests
import json
import time

base_url = "http://localhost:5000"

def login():
    # Attempt to login using a common default or from what we know about the platform
    # The user instruction was log in using `admin` for both username and password.
    resp = requests.post(f"{base_url}/api/auth/login", json={
        "username": "admin",
        "password": "password" # Or "admin"? the prompt said "admin" for both
    })
    
    if resp.status_code == 401:
        resp = requests.post(f"{base_url}/api/auth/login", json={
            "username": "admin",
            "password": "admin"
        })
        
    resp.raise_for_status()
    print("Login successful.")
    return resp.json()["token"]

def upload_package(token):
    headers = {"Authorization": f"Bearer {token}"}
    file_path = "d:/Downloads/test_packages/certifi-2026.2.25-py3-none-any.whl"
    
    with open(file_path, "rb") as f:
        files = {"file": f}
        # The endpoint uses a query param `pkg_type=pip`
        resp = requests.post(
            f"{base_url}/api/repo/upload?pkg_type=pip",
            headers=headers,
            files=files
        )
    
    print("Upload Response:", resp.status_code, resp.text)
    resp.raise_for_status()

if __name__ == "__main__":
    try:
        # Wait a sec for the backend to be online just in case
        time.sleep(2)
        token = login()
        upload_package(token)
    except Exception as e:
        print(f"Error during verification: {e}")
