import requests
import time
import json

BASE_URL = "http://localhost:5000/api"

def run_verification():
    print("🚀 Verifying Celery Task Queue...")
    
    # 1. Dispatch Task
    payload = {
        "description": "Run system diagnostics and verify patch status",
        "agentId": "agent-verification"
    }
    
    print(f"POST /api/agent/dispatch with {payload}")
    try:
        resp = requests.post(f"{BASE_URL}/agent/dispatch", json=payload)
        resp.raise_for_status()
        data = resp.json()
        
        task_id = data.get("taskId")
        print(f"✅ Task Queued! Task ID: {task_id}")
        
    except Exception as e:
        print(f"❌ Failed to dispatch task: {e}")
        return

    # 2. Poll Status
    print("⏳ Polling for result...")
    status = "PENDING"
    result = None
    
    for _ in range(20): # Wait up to 20 seconds
        try:
            resp = requests.get(f"{BASE_URL}/agent/tasks/{task_id}")
            resp.raise_for_status()
            task_data = resp.json()
            status = task_data.get("status")
            print(f"   Status: {status}")
            
            if status == "SUCCESS" or status == "completed": # Celery uses SUCCESS, our logic might return 'completed' in result dict
                result = task_data.get("result")
                break
            
            if status == "FAILURE":
                print(f"❌ Task Failed.")
                break
                
            time.sleep(1)
            
        except Exception as e:
            print(f"⚠️ Error polling: {e}")
            time.sleep(1)
            
    # 3. Verify Result
    if result:
        print("\n🎉 Task Completed Successfully!")
        print(f"Result: {json.dumps(result, indent=2)}")
        
        # Check if it was processed by the Real Agent Logic
        if "plan" in result:
             print("✅ Confirmed: Real Agent Logic executed.")
        else:
             print("⚠️ Warning: Mock logic might be running (no plan field).")
    else:
        print("❌ Task timed out or failed.")

if __name__ == "__main__":
    run_verification()
