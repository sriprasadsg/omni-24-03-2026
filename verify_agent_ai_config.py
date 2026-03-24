import sys
import os

# Update path to include agent directory
sys.path.append(os.path.abspath("d:/Downloads/enterprise-omni-agent-ai-platform/agent"))

from agentic_core.llm_engine import AgenticLLM

def verify_agent_backend_config():
    print("Test 1: Initialize AgenticLLM with 'backend' provider")
    
    config = {
        "provider": "backend",
        "api_base_url": "http://localhost:5000",
        "api_key": "test_token"
    }
    
    try:
        llm = AgenticLLM(config)
        print("✅ Initialization successful.")
    except Exception as e:
        print(f"❌ Initialization failed: {e}")
        return

    print("\nTest 2: Check Availability (Backend endpoint /health)")
    if llm.is_available():
        print("✅ Backend is reachable.")
    else:
        print("❌ Backend is unreachable. Ensure backend is running on http://localhost:5000")
        return

    print("\nTest 3: Simulate Analysis (Mock context)")
    context = {
        "system_info": {"os": "Windows"},
        "alerts": ["High CPU"],
        "history": []
    }
    
    # We expect this to call /api/ai/chat
    # The actual call might fail if the token is invalid, but we want to see it try the backend path
    # resulting in a response (even if error) rather than "LLM_UNAVAILABLE" locally.
    
    result = llm.analyze_situation(context)
    
    if result.get("error") == "LLM_UNAVAILABLE":
        print("❌ Failed: Returned LLM_UNAVAILABLE (Local check failed?)")
    else:
        # If we get a response (or backend error like 401/404/500), it means it tried the backend
        print(f"✅ Analysis attempted via backend. Result/Error: {result}")
        
if __name__ == "__main__":
    verify_agent_backend_config()
