
import requests
import os

BASE_URL = "http://localhost:5000/api/software"
TEST_FILE = "test_package.exe"
TEST_CONTENT = b"MOCK_EXE_CONTENT"

def verify_repo():
    print("Testing Software Repository API...")
    
    # 1. Upload
    with open(TEST_FILE, "wb") as f:
        f.write(TEST_CONTENT)
        
    print(f"Uploading {TEST_FILE}...")
    with open(TEST_FILE, "rb") as f:
        files = {"file": f}
        try:
            resp = requests.post(f"{BASE_URL}/upload", files=files)
            print(f"Upload Status: {resp.status_code}")
            print(f"Upload Response: {resp.json()}")
            if resp.status_code != 200 or not resp.json().get("success"):
                print("❌ Upload failed")
                return
        except Exception as e:
            print(f"❌ Upload Error: {e}")
            return

    # 2. List
    print("Listing Repository...")
    try:
        resp = requests.get(f"{BASE_URL}/repository")
        print(f"List Status: {resp.status_code}")
        data = resp.json()
        print(f"Files: {data}")
        
        found = any(f['filename'] == TEST_FILE for f in data)
        if found:
            print("✅ File found in repository list")
        else:
            print("❌ File NOT found in repository list")
    except Exception as e:
        print(f"❌ List Error: {e}")

    # 3. Clean up
    if os.path.exists(TEST_FILE):
        os.remove(TEST_FILE)

if __name__ == "__main__":
    verify_repo()
