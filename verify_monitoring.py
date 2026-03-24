import asyncio
import os
import sys
import json
import socket
from datetime import datetime

# Add agent directory to path
sys.path.append(os.path.join(os.getcwd(), "agent"))

from agent.capabilities.web_monitor import WebMonitorCapability
from agent.capabilities.logs import LogsCapability

async def verify_monitoring():
    print("="*60)
    print("VERIFYING OMNI-AGENT WEB MONITORING")
    print("="*60)
    
    # 1. Test WebMonitorCapability
    print("\n--- Testing WebMonitorCapability ---")
    web_cap = WebMonitorCapability()
    
    # Trigger some network traffic if possible (local loopback or simple request)
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(1)
        # Try to connect to a local port that might be open, or just scan
        # We'll just rely on existing established connections for the test
    except:
        pass
        
    result = web_cap.collect()
    print(f"Status: {result.get('status')}")
    print(f"Connections found: {result.get('count', 0)}")
    for conn in result.get('web_connections', [])[:3]:
        print(f"  - [{conn['process']}] -> {conn['remote_host']}:{conn['port']}")
    
    # 2. Test LogsCapability
    print("\n--- Testing LogsCapability (Web Service Detection) ---")
    logs_cap = LogsCapability()
    
    # Mock a log file on Linux if we are on Linux
    if sys.platform == "linux":
        mock_path = "/var/log/nginx/access.log"
        try:
            os.makedirs(os.path.dirname(mock_path), exist_ok=True)
            with open(mock_path, "a") as f:
                f.write('127.0.0.1 - - [24/Feb/2026:05:15:00 +0000] "GET / HTTP/1.1" 200 612 "-" "Mozilla/5.0"\n')
            print(f"Created mock Nginx log at {mock_path}")
        except:
            print("Could not create mock Nginx log (permission denied?)")
            
    result_logs = logs_cap.collect()
    print(f"Logs collected: {result_logs.get('count', 0)}")
    
    web_logs = [l for l in result_logs.get('logs', []) if "web_log" in l.get('source', '') or "IIS" in l.get('source', '')]
    print(f"Web/IIS logs found: {len(web_logs)}")
    for log in web_logs[:3]:
        print(f"  - [{log['source']}] {log['message'][:100]}")

    print("\n" + "="*60)
    print("VERIFICATION COMPLETE")
    print("="*60)

if __name__ == "__main__":
    asyncio.run(verify_monitoring())
