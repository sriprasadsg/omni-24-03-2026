
import asyncio
import os
import re
import sys
import httpx
from datetime import datetime

# Direct DB connection for token if needed, or just read from file
TOKEN_FILE = "token.txt"
BASE_URL = "http://localhost:5000"
AGENT_LOG = r"d:\Downloads\enterprise-omni-agent-ai-platform\agent\agent.log"

EXPECTED_FEATURES = [
    "metrics_collection", 
    "log_collection", 
    "fim", 
    "vulnerability_scanning", 
    "compliance_enforcement", 
    "runtime_security", 
    "predictive_health", 
    "ueba", 
    "sbom_analysis", 
    "system_patching", 
    "software_management", 
    "network_discovery", 
    "persistence_detection",
    "process_injection_simulation"
]

def get_token():
    try:
        with open(TOKEN_FILE, "r") as f:
            return f.read().strip()
    except:
        return None

def check_logs_for_initialization():
    print("\n[LOG CHECK] Scanning agent.log for feature initialization...")
    if not os.path.exists(AGENT_LOG):
        print("ERROR: agent.log not found.")
        return {}

    found_features = set()
    
    # We look for "Collecting data from: X" or "Using default configuration: 14 capabilities"
    try:
        with open(AGENT_LOG, "r", encoding='utf-8', errors='ignore') as f:
            # Read last 2000 lines to be safe
            lines = f.readlines()[-2000:] 
            
            for line in lines:
                for feature in EXPECTED_FEATURES:
                    if f"Collecting data from: {feature}" in line:
                        found_features.add(feature)
                    # Also check for init messages if any
                    
    except Exception as e:
        print(f"Error reading log: {e}")
        
    return found_features

async def check_backend_api(token):
    print("\n[API CHECK] Querying Backend for Agent Capabilities...")
    if not token:
        print("Skipping API check (No token found).")
        return
        
    headers = {"Authorization": f"Bearer {token}"}
    async with httpx.AsyncClient() as client:
        try:
            resp = await client.get(f"{BASE_URL}/api/agents", headers=headers)
            if resp.status_code != 200:
                print(f"Failed to list agents: {resp.status_code}")
                return
            
            agents = resp.json()
            if not agents:
                print("No agents found in API.")
                return
            
            # Find our agent (most likely the one just registered)
            # We can check 'lastSeen' or just take the first one
            target_agent = agents[0] 
            print(f"Checking Agent: {target_agent.get('hostname')} ({target_agent.get('id')})")
            
            caps = target_agent.get("capabilities", [])
            print(f"Backend Reported Capabilities ({len(caps)}):")
            for c in caps:
                print(f" - {c}")
                
            return set(caps)
            
        except Exception as e:
            print(f"API Request Failed: {e}")
            return None

async def main():
    print("="*60)
    print("DEEP FEATURE VERIFICATION")
    print("="*60)
    
    # 1. Log Verification
    log_features = check_logs_for_initialization()
    print(f"\nLog Verification Results: Found {len(log_features)}/{len(EXPECTED_FEATURES)} active features.")
    
    missing_in_logs = set(EXPECTED_FEATURES) - log_features
    if missing_in_logs:
        print(f"WARN: Features NOT seen in logs yet: {missing_in_logs}")
    else:
        print("SUCCESS: All features confirmed active in logs.")
        
    # 2. Backend Verification
    token = get_token()
    api_features = await check_backend_api(token)
    
    if api_features:
        missing_in_api = set(EXPECTED_FEATURES) - set(api_features)
        if missing_in_api:
             print(f"\nWARN: Features NOT reported by Backend: {missing_in_api}")
        else:
             print("\nSUCCESS: All features confirmed registered in Backend.")

    print("\n" + "="*60)
    
if __name__ == "__main__":
    asyncio.run(main())
