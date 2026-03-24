import requests
import json

base_url = "http://127.0.0.1:5000/api"

def test_governance_expert():
    # 1. Login
    print("Logging in...")
    login_url = f"{base_url}/auth/login"
    login_data = {"username": "admin", "password": "password123"}
    res = requests.post(login_url, json=login_data)
    if res.status_code != 200:
        print("Login failed")
        return
    
    token = res.json().get("access_token")
    headers = {"Authorization": f"Bearer {token}"}

    # 2. Register mockup model
    print("Registering mockup model...")
    model_id = "test-llama-expert"
    model_data = {
        "id": "test-llama-expert",
        "name": "Llama 3.2 Security Expert",
        "description": "Specialized AI for ISO 42001 governance.",
        "framework": "Ollama",
        "type": "LLM",
        "owner": "Security Team",
        "riskLevel": "Medium",
        "createdAt": "2026-02-18T00:00:00Z",
        "updatedAt": "2026-02-18T00:00:00Z",
        "versions": [],
        "currentVersion": "1.0"
    }

    reg_res = requests.post(f"{base_url}/ai-governance/register-model", 
                            headers=headers, json=model_data)
    print(f"Registration status: {reg_res.status_code}")
    if reg_res.status_code != 200:
        print(f"Registration failed: {reg_res.text}")

    # 3. Trigger Expert Evaluation
    url = f"{base_url}/ai-governance/expert-evaluate/{model_id}"
    print(f"Triggering expert evaluation at {url}...")
    eval_res = requests.post(url, headers=headers)
    
    if eval_res.status_code == 200:
        print("Expert evaluation SUCCESS!")
        print(json.dumps(eval_res.json(), indent=2))
    else:
        print(f"Expert evaluation FAILED: {eval_res.status_code}")
        print(eval_res.text)

if __name__ == "__main__":
    test_governance_expert()
