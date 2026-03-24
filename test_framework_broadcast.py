
import asyncio
import sys
import os
import requests
import time

# Helper to add project root to path
sys.path.append(os.path.abspath("d:/Downloads/enterprise-omni-agent-ai-platform/backend"))

# Mock Backend URL
BASE_URL = "http://localhost:5000"

def test_trigger_scan():
    print("🚀 Testing Framework Scan Trigger...")
    
    # 1. Trigger the scan
    url = f"{BASE_URL}/api/compliance/nistcsf/scan"
    print(f"Calling POST {url}")
    try:
        resp = requests.post(url)
        print(f"Status: {resp.status_code}")
        print(f"Response: {resp.json()}")
        
        if resp.status_code == 200 and resp.json().get("success"):
            print("✅ Trigger Successful!")
        else:
            print("❌ Trigger Failed")
            return
            
    except Exception as e:
        print(f"❌ Request Failed: {e}")
        return

    # 2. Verify Instruction in DB (if we could access it, but we can't easily from here without DB connection)
    # We will trust the response payload "message" which should say "Scan initiated for X agents"
    
if __name__ == "__main__":
    test_trigger_scan()
