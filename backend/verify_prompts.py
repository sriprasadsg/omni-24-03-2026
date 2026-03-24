import requests
import json

BASE_URL = "http://localhost:5000/api"

def run_test():
    print("🚀 Verifying Prompt Registry...")
    
    # 1. Create a Prompt
    prompt_data = {
        "name": "system-diagnosis",
        "version": "1.0.0",
        "template": "Analyze the following logs for errors:\n{logs}",
        "input_variables": ["logs"],
        "description": "Standard diagnostic prompt"
    }
    
    print(f"📥 Creating Prompt: {prompt_data['name']}")
    try:
        resp = requests.post(f"{BASE_URL}/prompts", json=prompt_data)
        print(f"Create Response: {resp.json()}")
        resp.raise_for_status()
    except Exception as e:
        print(f"❌ Create Failed: {e}")
        return

    # 2. List Prompts
    print("\n📋 Listing Prompts...")
    try:
        resp = requests.get(f"{BASE_URL}/prompts")
        data = resp.json()
        prompts = data.get("prompts", [])
        print(f"Found {len(prompts)} prompts.")
        
        found = any(p['name'] == "system-diagnosis" for p in prompts)
        if found:
            print("✅ Prompt Registry Verification SUCCEEDED!")
        else:
            print("⚠️ Prompt not found in list.")
            
    except Exception as e:
        print(f"❌ List Failed: {e}")

if __name__ == "__main__":
    run_test()
