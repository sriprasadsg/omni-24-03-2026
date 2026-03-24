import asyncio
import json
import httpx
from datetime import datetime

async def verify_jira_automation():
    print("🧪 [Test] Verifying Jira Ticket-to-Agent Automation")
    
    url = "http://127.0.0.1:5000/api/webhooks/jira/inbound"
    
    # Mock Jira payload
    payload = {
        "issue": {
            "key": "PATCH-101",
            "fields": {
                "summary": "Install Slack on EILT0197",
                "description": "Please install the latest version of Slack for the user on host EILT0197."
            }
        }
    }
    
    print(f"📤 Sending mock Jira payload to {url}...")
    
    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(url, json=payload, timeout=20.0)
            
        print(f"📥 Response Status: {response.status_code}")
        print(f"📥 Response Body: {json.dumps(response.json(), indent=2)}")
        
        if response.status_code == 200 and response.json().get("success"):
            print("✅ Verification Successful: Intent detected and task dispatched.")
        else:
            print("❌ Verification Failed.")
            
    except Exception as e:
        print(f"❌ Error during verification: {e}")

if __name__ == "__main__":
    asyncio.run(verify_jira_automation())
