import urllib.request
import urllib.parse
import json
import socket
import sys
import os
import platform

# Add parent directory to path to import agent modules
sys.path.insert(0, os.path.abspath('.'))

try:
    from capabilities.compliance import ComplianceEnforcementCapability
    
    # 1. Run full compliance capability
    print("Running compliance checks (this may take a minute)...")
    cap = ComplianceEnforcementCapability()
    compliance_data = cap.collect()
    print(f"Collected {compliance_data.get('total_checks', 0)} checks. Passed: {compliance_data.get('passed', 0)}, Failed: {compliance_data.get('failed', 0)}")
    
    # 2. Package into expected heartbeat format
    hostname = socket.gethostname()
    
    # Try to find existing agent config to get the real Agent ID
    agent_id = f"agent-{hostname}"
    try:
        if os.path.exists('config.yaml'):
            import yaml
            with open('config.yaml', 'r') as f:
                config = yaml.safe_load(f)
                agent_id = config.get('agent_id', agent_id)
    except: pass
    
    payload = {
        "agentId": agent_id,
        "hostname": hostname,
        "tenantId": "default", # Use default or specific tenant if known
        "status": "Online",
        "platform": platform.system(),
        "version": "2.0.1",
        "ipAddress": socket.gethostbyname(socket.gethostname()),
        "meta": {
            "compliance_enforcement": compliance_data
        }
    }
    
    # 3. Post to backend
    url = f"http://localhost:5000/api/agents/{agent_id}/heartbeat"
    data = json.dumps(payload).encode('utf-8')
    req = urllib.request.Request(url, data=data, method='POST')
    req.add_header('Content-Type', 'application/json')
    import yaml
    try:
        if os.path.exists('config.yaml'):
            with open('config.yaml', 'r') as f:
                config = yaml.safe_load(f)
                tenant_key = config.get('tenant_key', 'test_key_123')
                req.add_header('X-Tenant-Key', tenant_key)
    except Exception as e:
        print(f"Warn: {e}")
    
    print("Sending compliance evidence to backend...")
    with urllib.request.urlopen(req) as response:
        resp_data = response.read().decode()
        print(f"Server response: {response.status}")
        print(resp_data)
        
    print("Successfully pushed live admin compliance evidence to the platform!")
    
except Exception as e:
    print(f"Error: {e}")
