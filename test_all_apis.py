#!/usr/bin/env python3
"""
Comprehensive Backend API Test Suite
Tests all major platform endpoints to verify functionality
"""
import requests
import yaml
from typing import Dict, Any

class PlatformTester:
    def __init__(self, base_url="http://localhost:5000", config_path="agent/config.yaml"):
        self.base_url = base_url
        self.headers = self._load_auth(config_path)
        self.results = []
        
    def _load_auth(self, config_path):
        with open(config_path, "r") as f:
            config = yaml.safe_load(f)
        token = config["agent_token"]
        return {"Authorization": f"Bearer {token}"}
    
    def test_endpoint(self, name: str, endpoint: str) -> Dict[str, Any]:
        """Test an API endpoint and return results"""
        try:
            response = requests.get(f"{self.base_url}{endpoint}", headers=self.headers, timeout=5)
            success = response.status_code == 200
            
            result = {
                "name": name,
                "endpoint": endpoint,
                "status_code": response.status_code,
                "success": success,
                "error": None if success else response.text[:200]
            }
            
            if success:
                try:
                    data = response.json()
                    result["data_count"] = len(data) if isinstance(data, list) else ("object" if isinstance(data, dict) else "unknown")
                except:
                    result["data_count"] = "non-json"
            
            return result
        except Exception as e:
            return {
                "name": name,
                "endpoint": endpoint,
                "status_code": 0,
                "success": False,
                "error": str(e)
            }
    
    def run_all_tests(self):
        """Test all major platform endpoints"""
        tests = [
            # Authentication
            ("Current User", "/api/auth/me"),
            
            # Core Features
            ("Agents", "/api/agents"),
            ("Assets", "/api/assets"),
            ("Metrics", "/api/metrics"),
            ("Alerts", "/api/alerts"),
            
            # Security
            ("Security Cases", "/api/security-cases"),
            ("Security Events", "/api/security-events"),
            ("Playbooks", "/api/playbooks"),
            ("Vulnerabilities", "/api/vulnerabilities"),
            
            # SBOM
            ("SBOMs", "/api/sboms"),
            ("SBOM Components", "/api/sboms/components"),
            
            # Compliance
            ("Compliance Frameworks", "/api/compliance"),
            ("Audit Logs", "/api/audit-logs"),
            
            # Patch Management
            ("Patches", "/api/patches"),
            ("Patch Deployment Jobs", "/api/patches/deployment-jobs"),
            
            # Cloud Security
            ("Cloud Accounts", "/api/cloud-accounts"),
            ("CSPM Findings", "/api/cspm-findings"),
            
            # FinOps
            ("FinOps Pricing", "/api/finops/pricing"),
            
            # AI Governance
            ("AI Systems", "/api/ai-systems"),
            
            # Admin
            ("Users", "/api/users"),
            ("Roles", "/api/roles"),
            ("Tenants", "/api/tenants"),
            
            # Infrastructure
            ("Network Devices", "/api/network-devices"),
            ("Integrations", "/api/integrations/configs"),
            
            # Observability
            ("Logs", "/api/logs"),
            ("Notifications", "/api/notifications"),
        ]
        
        print("="*70)
        print("PLATFORM API TEST SUITE")
        print("="*70)
        print()
        
        passed = 0
        failed = 0
        
        for name, endpoint in tests:
            result = self.test_endpoint(name, endpoint)
            self.results.append(result)
            
            status_icon = "✅" if result["success"] else "❌"
            status_text = f"OK ({result.get('data_count', 'N/A')} items)" if result["success"] else f"FAIL ({result['status_code']})"
            
            print(f"{status_icon} {name:30} {status_text}")
            
            if result["success"]:
                passed += 1
            else:
                failed += 1
                if result.get("error"):
                    print(f"   Error: {result['error']}")
        
        print()
        print("="*70)
        print(f"SUMMARY: {passed} passed, {failed} failed out of {len(tests)} tests")
        print("="*70)
        
        return self.results

if __name__ == "__main__":
    tester = PlatformTester()
    tester.run_all_tests()
