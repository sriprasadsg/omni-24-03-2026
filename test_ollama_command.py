
import requests
import json

def test_command():
    try:
        # First login to get token
        login_url = "http://localhost:5000/api/auth/login"
        login_data = {"email": "admin@exafluence.com", "password": "password123"}
        resp = requests.post(login_url, json=login_data)
        token = resp.json().get("access_token")
        
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json"
        }
        
        # Call AI Proxy
        proxy_url = "http://localhost:5000/api/ai-proxy/chat/completions"
        payload = {
            "provider": "ollama",
            "model": "llama3.2:3b",
            "messages": [
                {"role": "system", "content": "You are an AI command parser. Respond with [NAVIGATE:view_name]."},
                {"role": "user", "content": "Go to the security dashboard"}
            ],
            "temperature": 0.1
        }
        
        print("Sending request to AI Proxy (Ollama)...")
        resp = requests.post(proxy_url, json=payload, headers=headers, timeout=60)
        print(f"Status Code: {resp.status_code}")
        
        if resp.status_code == 200:
            data = resp.json()
            content = data.get("choices", [{}])[0].get("message", {}).get("content", "")
            print(f"AI Response:\n{content}")
            
            if "[NAVIGATE:security]" in content or "security" in content.lower():
                print("\nSUCCESS: Ollama correctly parsed the navigation command!")
            else:
                print("\nWARNING: Ollama responded but the parsing might be different.")
        else:
            print(f"Error Response: {resp.text}")

    except Exception as e:
        print(f"Error during test: {e}")

if __name__ == "__main__":
    test_command()
