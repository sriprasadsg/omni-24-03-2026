import requests
import json

BASE_URL = "http://localhost:5000/api"

def run_test():
    print("🚀 Verifying RAG System...")
    
    # 1. Ingest Data
    snippet = "The secret code for the server room is 998877."
    print(f"📥 Ingesting: '{snippet}'")
    
    try:
        resp = requests.post(f"{BASE_URL}/knowledge/ingest", json={"content": snippet, "source": "test_script"})
        print(f"Ingest Response: {resp.json()}")
        resp.raise_for_status()
    except Exception as e:
        print(f"❌ Ingest Failed: {e}")
        return

    # 2. Query Data
    query = "What is the code for the server room?"
    print(f"\n🔍 Querying: '{query}'")
    
    try:
        resp = requests.post(f"{BASE_URL}/knowledge/query", json={"query": query})
        data = resp.json()
        print(f"Query Response: {json.dumps(data, indent=2)}")
        
        results = data.get("results", [])
        if results and "998877" in results[0].get("content", ""):
            print("✅ RAG Verification SUCCEEDED! Retrieved correct info.")
        else:
            print("⚠️ RAG Verification FAILED. Did not match expected content.")
            
    except Exception as e:
        print(f"❌ Query Failed: {e}")

if __name__ == "__main__":
    run_test()
