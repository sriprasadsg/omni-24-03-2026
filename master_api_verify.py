"""
Master API Verification Script (v2) - Tests all platform features via HTTP API
Using CORRECT endpoint paths from live OpenAPI spec
"""
import requests
import sys

BASE = "http://localhost:5000"
RESULTS = []

def test(name, method, path, expected_ok=True, **kwargs):
    try:
        resp = getattr(requests, method)(f"{BASE}{path}", timeout=8, **kwargs)
        ok = resp.status_code in [200, 201, 202]
        if not expected_ok:
            ok = True  # we just want connectivity, not correctness
        status = "PASS" if ok else f"FAIL({resp.status_code})"
        RESULTS.append((name, status, resp.status_code))
        print(f"  {'OK ' if ok else 'ERR'} [{resp.status_code}] {name}")
        return resp if ok else None
    except Exception as e:
        RESULTS.append((name, f"ERROR", 0))
        print(f"  ERR [---] {name}: {type(e).__name__}")
        return None

print("=" * 65)
print("  MASTER PLATFORM VERIFICATION - v2 (Correct Paths)")
print("=" * 65)

# --- AUTH ---
print("\n[1/14] Authentication & Session Management")
r = test("POST /api/auth/login", "post", "/api/auth/login",
         json={"email": "super@omni.ai", "password": "password123"})
token = ""
if r:
    data = r.json()
    token = data.get("token") or data.get("access_token", "")
    print(f"         Token obtained: {'YES' if token else 'NO'}")
H = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
test("GET /health", "get", "/health")

# --- AGENTS ---
print("\n[2/14] Agent Fleet Management")
test("GET /api/agents", "get", "/api/agents", headers=H)
test("GET /api/agents/approvals/pending", "get", "/api/agents/approvals/pending", headers=H)

# --- ASSETS ---
print("\n[3/14] Assets & Infrastructure")
test("GET /api/assets", "get", "/api/assets", headers=H)
test("GET /api/cloud-accounts", "get", "/api/cloud-accounts", headers=H)
test("GET /api/vulnerabilities", "get", "/api/vulnerabilities", headers=H)
test("GET /api/patches", "get", "/api/patches", headers=H)

# --- SECURITY/SIEM ---
print("\n[4/14] Security (SIEM & SOC)")
test("GET /api/security-events", "get", "/api/security-events", headers=H)
test("GET /api/alerts", "get", "/api/alerts", headers=H)
test("GET /api/soar/playbooks", "get", "/api/soar/playbooks", headers=H)
test("GET /api/siem/rules", "get", "/api/siem/rules", headers=H)
test("GET /api/ueba/stats", "get", "/api/ueba/stats", headers=H)
test("GET /api/ueba/risk-scores", "get", "/api/ueba/risk-scores", headers=H)

# --- COMPLIANCE & GOVERNANCE ---
print("\n[5/14] Governance & Compliance")
test("GET /api/compliance-frameworks", "get", "/api/compliance-frameworks", headers=H)
test("GET /api/compliance", "get", "/api/compliance", headers=H)
test("GET /api/audit-logs", "get", "/api/audit-logs", headers=H)

# --- 2030 GOVERNANCE FEATURES ---
test("GET /api/risks", "get", "/api/risks", headers=H)
test("GET /api/vendors", "get", "/api/vendors", headers=H)
test("GET /api/trust-center/profile", "get", "/api/trust-center/profile", headers=H)
test("GET /api/trust-center/requests", "get", "/api/trust-center/requests", headers=H)

# --- DEVSECOPS ---
print("\n[6/14] DevSecOps & Engineering")
test("GET /api/devsecops/sast/findings", "get", "/api/devsecops/sast/findings", headers=H)
test("GET /api/devsecops/sbom", "get", "/api/devsecops/sbom", headers=H)
test("GET /api/scan/targets", "get", "/api/scan/targets", headers=H)
test("GET /api/supply-chain/findings", "get", "/api/supply-chain/findings", headers=H)

# --- MLOps/AI ---
print("\n[7/14] MLOps & AI")
test("GET /api/mlops/models", "get", "/api/mlops/models", headers=H)
test("GET /api/llmops/models", "get", "/api/llmops/models", headers=H)
test("GET /api/ai-governance/models", "get", "/api/ai-governance/models", headers=H)
test("POST /api/ai/chat", "post", "/api/ai/chat", headers=H,
     json={"message": "ping", "context": {}})

# --- BILLING ---
print("\n[8/14] Billing & FinOps")
test("GET /api/finops/summary", "get", "/api/finops/summary", headers=H)
test("GET /api/billing/invoices", "get", "/api/billing/invoices", headers=H)
test("GET /api/billing/subscriptions", "get", "/api/billing/subscriptions", headers=H)

# --- TICKETING ---
print("\n[9/14] Ticketing Integration")
test("GET /api/ticketing/config", "get", "/api/ticketing/config", headers=H)
test("GET /api/ticketing/tickets", "get", "/api/ticketing/tickets", headers=H)
test("GET /api/webhooks", "get", "/api/webhooks", headers=H)

# --- USERS/TENANTS ---
print("\n[10/14] Users, Tenants & RBAC")
test("GET /api/users", "get", "/api/users", headers=H)
test("GET /api/tenants", "get", "/api/tenants", headers=H)

# --- VOICE ---
print("\n[11/14] Voice Bot")
test("GET /api/voice/status", "get", "/api/voice/status", headers=H)

# --- SWARM/ZERO-TRUST ---
print("\n[12/14] Advanced Security Features")
test("GET /api/zero-trust/device-trust-scores", "get", "/api/zero-trust/device-trust-scores", headers=H)
test("GET /api/xdr/automated-hunts", "get", "/api/xdr/automated-hunts", headers=H)
test("GET /api/threat-intel/stats", "get", "/api/threat-intel/stats", headers=H)

# --- NOTIFICATIONS ---
print("\n[13/14] Notifications & Settings")
test("GET /api/notifications", "get", "/api/notifications", headers=H)
test("GET /api/settings/llm", "get", "/api/settings/llm", headers=H)
test("GET /api/sso/status", "get", "/api/sso/status", headers=H)

# --- STREAMING/WS ---
print("\n[14/14] Data Warehouse & Analytics")
test("POST /api/warehouse/query", "post", "/api/warehouse/query", headers=H, json={"query": "SELECT 1"})
test("GET /api/warehouse/stats", "get", "/api/warehouse/stats", headers=H)
test("GET /api/sustainability/metrics", "get", "/api/sustainability/metrics", headers=H)

# --- SUMMARY ---
print("\n" + "=" * 65)
print("  RESULTS SUMMARY")
print("=" * 65)
passed = [(n, s, c) for n, s, c in RESULTS if s == "PASS"]
failed = [(n, s, c) for n, s, c in RESULTS if s != "PASS"]
print(f"  Total Tests : {len(RESULTS)}")
print(f"  PASSED      : {len(passed)}")
print(f"  FAILED      : {len(failed)}")
print(f"  Pass Rate   : {len(passed)/len(RESULTS)*100:.1f}%")
if failed:
    print("\n  Failed Tests:")
    for name, status, code in failed:
        print(f"    [{code}] {name}")
print("=" * 65)
sys.exit(0 if len(failed) == 0 else 1)
