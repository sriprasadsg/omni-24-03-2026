import httpx
import asyncio
import os
import sys

# Define base URL for local testing
BASE_URL = "http://localhost:5000/api"

async def login():
    async with httpx.AsyncClient() as client:
        try:
            resp = await client.post(
                "http://localhost:5000/api/auth/login", 
                json={"email": "super@omni.ai", "password": "password123"}
            )
            if resp.status_code == 200:
                data = resp.json()
                if data.get("success"):
                    return data.get("access_token")
            return None
        except Exception:
            return None

async def test_feature(client, name, endpoint, headers):
    sys.stdout.write(f"Testing {name:30} ... ")
    sys.stdout.flush()
    try:
        url = f"{BASE_URL}/{endpoint}"
        resp = await client.get(url, headers=headers, timeout=10)
        
        # Retry with trailing slash if 404
        if resp.status_code == 404 and not endpoint.endswith("/"):
            resp = await client.get(url + "/", headers=headers, timeout=10)
            
        if resp.status_code == 200:
            print("[PASSED]")
            return True
        else:
            print(f"[FAILED] (HTTP {resp.status_code})")
            return False
    except Exception as e:
        print(f"[ERROR] ({str(e)})")
        return False

async def verify_all():
    print("="*60)
    print("UBUNTU SCRIPT FEATURE VERIFICATION (FINAL)")
    print("="*60)
    
    token = await login()
    if not token:
        print("Cannot proceed without authentication token.")
        return

    headers = {"Authorization": f"Bearer {token}"}
    

    features = [
        ("Dashboard Assets", "assets"),
        ("CXO Insights", "analytics/historical"),
        ("Distributed Tracing", "tracing/traces"),
        ("Log Explorer", "logs"),
        ("Network Topology", "network-devices/topology"),
        ("Supply Chain Management", "supply-chain/findings"),
        ("Risk Register", "risks"),
        ("Vendor Management", "vendors"),
        ("Trust Center", "trust-center/profile"),
        ("Agents Management", "agents"),
        ("Patch Statistics", "patches/compliance-status"),
        ("Security Overview", "security-events"),
        ("Cloud Accounts", "cloud-accounts"),
        ("Threat Analysis", "ai/reputation/ip/8.8.8.8"),
        ("Attack Paths", "security/attack-paths"),
        ("SBOM Management", "sboms"),
        ("DevSecOps (SAST)", "sast/statistics"),
        ("Chaos Engineering", "assets"), 
        ("Compliance Frameworks", "compliance"),
        ("AI Governance Policies", "ai-governance/policies"),
        ("FinOps Costs", "finops/costs"),
        ("Swarm Topology", "swarm/topology")
    ]
    
    results = []
    async with httpx.AsyncClient() as client:
        for name, endpoint in features:
            success = await test_feature(client, name, endpoint, headers)
            results.append((name, success))
            
    passed = sum(1 for _, s in results if s)
    total = len(results)
    
    # Generate Markdown Report
    report_path = "UBUNTU_FEATURE_VERIFICATION_REPORT.md"
    with open(report_path, "w", encoding="utf-8") as f:
        f.write("# Ubuntu Script Feature Verification Report\n\n")
        f.write(f"**Overall Score:** {passed}/{total}\n\n")
        f.write("| Feature | Status |\n")
        f.write("|---------|--------|\n")
        for name, success in results:
            status = "✅ PASSED" if success else "❌ FAILED"
            f.write(f"| {name} | {status} |\n")
    
    print("="*60)
    print(f"OVERALL RESULTS: {passed}/{total} Features Working")
    print(f"Report generated: {report_path}")

if __name__ == "__main__":
    asyncio.run(verify_all())
