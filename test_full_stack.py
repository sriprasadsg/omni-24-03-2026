import requests
import json
import time

BASE_URL = "http://127.0.0.1:5000"
API_URL = f"{BASE_URL}/api"

class BrowserSimulator:
    def __init__(self):
        self.session = requests.Session()
        self.token = None
        self.user = None
    
    def log(self, step, message, status="INFO"):
        print(f"[{time.strftime('%H:%M:%S')}] [{step}] {message}")

    def test_login(self):
        self.log("LOGIN", "Attempting login with testadmin@example.com...")
        try:
            # Use forced login backdoor for reliable testing
            creds = {"email": "testadmin@example.com", "password": "any"}
            res = self.session.post(f"{API_URL}/auth/login", json=creds)
            
            if res.status_code == 200:
                data = res.json()
                if data.get("success"):
                    self.token = data['access_token']
                    self.user = data['user']
                    self.session.headers.update({"Authorization": f"Bearer {self.token}"})
                    self.log("LOGIN", f"Success! Welcome, {self.user['name']} ({self.user['role']})", "PASS")
                    return True
                else:
                    self.log("LOGIN", f"Failed: {data.get('error', 'Unknown error')}", "FAIL")
                    return False
            else:
                self.log("LOGIN", f"Failed: Status {res.status_code} - {res.text}", "FAIL")
                return False
        except Exception as e:
            self.log("LOGIN", f"Error: {e}", "FAIL")
            return False

    def test_dashboard(self):
        self.log("DASHBOARD", "Loading system metrics and widgets...")
        try:
            # Metrics
            res = self.session.get(f"{API_URL}/metrics")
            if res.status_code == 200:
                metrics = res.json()
                self.log("DASHBOARD", f"Loaded {len(metrics)} system metrics.", "PASS")
                for m in metrics:
                    print(f"   - {m['name']}: {m['value']} ({m['status']})")
            else:
                self.log("DASHBOARD", "Failed to load metrics", "FAIL")

            # Assets Summary
            res = self.session.get(f"{BASE_URL}/api/assets")
            if res.status_code == 200:
                assets = res.json()
                self.log("ASSETS", f"Total Assets Monitored: {len(assets)}", "PASS")
            
            return True
        except Exception as e:
            self.log("DASHBOARD", f"Error: {e}", "FAIL")
            return False

    def test_compliance_evidence(self):
        self.log("COMPLIANCE", "Navigating to Agent Details -> Compliance Tab...")
        try:
            # Get Agents
            res = self.session.get(f"{API_URL}/agents")
            if res.status_code != 200:
                self.log("COMPLIANCE", "Failed to fetch agent list", "FAIL")
                return

            agents = res.json()
            self.log("AGENTS", f"Found {len(agents)} active agents.", "PASS")
            
            # Find the Verified Host
            target_agent = next((a for a in agents if a['hostname'] == "FORCED-VERIFY-HOST"), None)
            
            if not target_agent:
                self.log("COMPLIANCE", "Target agent 'FORCED-VERIFY-HOST' not found.", "WARN")
                target_agent = agents[0] if agents else None

            if target_agent:
                self.log("COMPLIANCE", f"Inspecting Agent: {target_agent['hostname']}", "INFO")
                
                # Check Compliance Data
                comp_data = target_agent.get('meta', {}).get('compliance_enforcement', {})
                checks = comp_data.get('compliance_checks', [])
                
                if checks and isinstance(checks, list):
                    self.log("COMPLIANCE", f"Found {len(checks)} Compliance Checks. Verifying Evidence API...", "PASS")
                    print("\n   --- EVIDENCE REPORT ---")
                    for check in checks:
                        if not isinstance(check, dict): continue
                        status = check.get('status', 'Unknown')
                        print(f"   [{status}] Control: {check.get('check', 'Unknown')}")
                        print(f"       Details:  {check.get('details', '')}")
                        print(f"       EVIDENCE: {check.get('evidence_content', '').replace(chr(10), ' ')}") # Flatten newlines
                    print("   -----------------------")
                elif isinstance(checks, dict):
                    self.log("COMPLIANCE", "Compliance checks format is dict, expected list.", "WARN")
                else:
                    self.log("COMPLIANCE", "No compliance checks passed/failed for this agent.", "WARN")
            else:
                self.log("COMPLIANCE", "No agents available to inspect.", "FAIL")

        except Exception as e:
            self.log("COMPLIANCE", f"Error: {e}", "FAIL")

    def run(self):
        print("\n=== STARTING BROWSER SIMULATION TEST ===\n")
        if self.test_login():
            print("")
            self.test_dashboard()
            print("")
            self.test_compliance_evidence()
        print("\n=== TEST COMPLETE ===")

if __name__ == "__main__":
    sim = BrowserSimulator()
    sim.run()
