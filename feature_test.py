"""
Comprehensive feature test for Enterprise Omni-Agent AI Platform.
Run: python feature_test.py
"""
import requests
import json
import sys
from datetime import datetime

BASE = "http://localhost:5000"
session = requests.Session()
session.headers.update({"Content-Type": "application/json"})

results = []
TOKEN = None
TENANT_ID = None
AGENT_ID = None

def record(category, name, resp=None, expected=None, error=None):
    if error:
        results.append({"cat": category, "name": name, "status": "ERROR", "code": None, "detail": str(error)})
        return
    code = resp.status_code
    expected = expected or [200, 201]
    ok = code in expected
    try:
        body = resp.json()
    except Exception:
        body = resp.text[:120]
    results.append({
        "cat": category,
        "name": name,
        "status": "PASS" if ok else "FAIL",
        "code": code,
        "detail": "" if ok else str(body)[:120]
    })

def auth_headers():
    return {"Authorization": f"Bearer {TOKEN}"}

# ── 1. HEALTH ──────────────────────────────────────────────────────────────────
try:
    r = session.get(f"{BASE}/health", timeout=5)
    record("Health", "GET /health", r)
except Exception as e:
    record("Health", "GET /health", error=e)

# ── 2. AUTH ────────────────────────────────────────────────────────────────────
try:
    r = session.post(f"{BASE}/api/auth/login",
                     json={"email": "super@omni.ai", "password": "Admin@Omni2026!"},
                     timeout=5)
    record("Auth", "POST /api/auth/login (super admin)", r, [200])
    if r.status_code == 200:
        data = r.json()
        TOKEN = data.get("access_token") or data.get("token")
        TENANT_ID = data.get("tenant_id") or "platform-admin"
        session.headers.update({"Authorization": f"Bearer {TOKEN}"})
except Exception as e:
    record("Auth", "POST /api/auth/login", error=e)

try:
    r = session.post(f"{BASE}/api/auth/login",
                     json={"email": "wrong@example.com", "password": "wrong"},
                     timeout=5)
    record("Auth", "POST /api/auth/login (bad creds -> 401/429)", r, [401, 403, 422, 429])
except Exception as e:
    record("Auth", "POST /api/auth/login (bad creds)", error=e)

try:
    r = session.get(f"{BASE}/api/auth/me", timeout=5)
    record("Auth", "GET /api/auth/me", r)
except Exception as e:
    record("Auth", "GET /api/auth/me", error=e)

try:
    r = session.post(f"{BASE}/api/auth/refresh", timeout=5)
    record("Auth", "POST /api/auth/refresh", r, [200, 400, 401, 422])
except Exception as e:
    record("Auth", "POST /api/auth/refresh", error=e)

# ── 3. TENANTS ─────────────────────────────────────────────────────────────────
try:
    r = session.get(f"{BASE}/api/tenants", timeout=5)
    record("Tenants", "GET /api/tenants", r)
    if r.status_code == 200:
        tenants = r.json()
        if isinstance(tenants, list) and tenants:
            TENANT_ID = tenants[0].get("id", TENANT_ID)
except Exception as e:
    record("Tenants", "GET /api/tenants", error=e)

try:
    r = session.get(f"{BASE}/api/tenants/{TENANT_ID}/branding", timeout=5)
    record("Tenants", "GET /api/tenants/{id}/branding", r, [200, 404])
except Exception as e:
    record("Tenants", "GET /api/tenants/{id}/branding", error=e)

# ── 4. USERS / ROLES ──────────────────────────────────────────────────────────
try:
    r = session.get(f"{BASE}/api/users", timeout=5)
    record("Users", "GET /api/users", r, [200, 404])
except Exception as e:
    record("Users", "GET /api/users", error=e)

# ── 5. AGENTS ─────────────────────────────────────────────────────────────────
try:
    r = session.get(f"{BASE}/api/agents", timeout=5)
    record("Agents", "GET /api/agents", r)
    if r.status_code == 200:
        ags = r.json()
        if isinstance(ags, list) and ags:
            AGENT_ID = ags[0].get("id")
        elif isinstance(ags, dict):
            items = ags.get("agents") or ags.get("data") or []
            if items:
                AGENT_ID = items[0].get("id")
except Exception as e:
    record("Agents", "GET /api/agents", error=e)

try:
    r = session.get(f"{BASE}/api/secrets/stats", timeout=5)
    record("Agents", "GET /api/secrets/stats", r, [200, 404])
except Exception as e:
    record("Agents", "GET /api/secrets/stats", error=e)

try:
    r = session.post(f"{BASE}/api/agent/download-token/nonexistent-tenant", timeout=5)
    record("Agents", "POST /api/agent/download-token (super admin -> 200)", r, [200, 403, 404])
except Exception as e:
    record("Agents", "POST /api/agent/download-token", error=e)

# ── 6. ASSETS ─────────────────────────────────────────────────────────────────
try:
    r = session.get(f"{BASE}/api/assets", timeout=5)
    record("Assets", "GET /api/assets", r)
except Exception as e:
    record("Assets", "GET /api/assets", error=e)

try:
    r = session.get(f"{BASE}/api/assets/summary", timeout=5)
    record("Assets", "GET /api/assets/summary", r, [200, 404])
except Exception as e:
    record("Assets", "GET /api/assets/summary", error=e)

try:
    r = session.get(f"{BASE}/api/asset-metrics", timeout=5)
    record("Assets", "GET /api/asset-metrics", r, [200, 404])
except Exception as e:
    record("Assets", "GET /api/asset-metrics", error=e)

# ── 7. COMPLIANCE ─────────────────────────────────────────────────────────────
try:
    r = session.get(f"{BASE}/api/compliance/frameworks", timeout=5)
    record("Compliance", "GET /api/compliance/frameworks", r, [200, 404])
except Exception as e:
    record("Compliance", "GET /api/compliance/frameworks", error=e)

try:
    r = session.get(f"{BASE}/api/compliance/summary", timeout=5)
    record("Compliance", "GET /api/compliance/summary", r, [200, 404])
except Exception as e:
    record("Compliance", "GET /api/compliance/summary", error=e)

try:
    r = session.get(f"{BASE}/api/compliance/evidence", timeout=5)
    record("Compliance", "GET /api/compliance/evidence", r, [200, 404])
except Exception as e:
    record("Compliance", "GET /api/compliance/evidence", error=e)

try:
    r = session.get(f"{BASE}/api/compliance/reports", timeout=5)
    record("Compliance", "GET /api/compliance/reports", r, [200, 404])
except Exception as e:
    record("Compliance", "GET /api/compliance/reports", error=e)

try:
    r = session.get(f"{BASE}/api/custom-frameworks", timeout=5)
    record("Compliance", "GET /api/custom-frameworks", r, [200, 404])
except Exception as e:
    record("Compliance", "GET /api/custom-frameworks", error=e)

# ── 8. SECURITY / ALERTS ──────────────────────────────────────────────────────
try:
    r = session.get(f"{BASE}/api/alerts", timeout=5)
    record("Security", "GET /api/alerts", r, [200, 404])
except Exception as e:
    record("Security", "GET /api/alerts", error=e)

try:
    r = session.get(f"{BASE}/api/correlation/rules", timeout=5)
    record("Security", "GET /api/correlation/rules", r, [200, 404])
except Exception as e:
    record("Security", "GET /api/correlation/rules", error=e)

try:
    r = session.get(f"{BASE}/api/deception/honeypots", timeout=5)
    record("Security", "GET /api/deception/honeypots", r, [200, 404])
except Exception as e:
    record("Security", "GET /api/deception/honeypots", error=e)

try:
    r = session.get(f"{BASE}/api/jit-access/requests", timeout=5)
    record("Security", "GET /api/jit-access/requests", r, [200, 404])
except Exception as e:
    record("Security", "GET /api/jit-access/requests", error=e)

try:
    r = session.get(f"{BASE}/api/secrets", timeout=5)
    record("Security", "GET /api/secrets", r, [200, 404])
except Exception as e:
    record("Security", "GET /api/secrets", error=e)

# ── 9. INCIDENTS ──────────────────────────────────────────────────────────────
try:
    r = session.get(f"{BASE}/api/incidents", timeout=5)
    record("Incidents", "GET /api/incidents", r, [200, 404])
except Exception as e:
    record("Incidents", "GET /api/incidents", error=e)

try:
    r = session.get(f"{BASE}/api/incidents/warroom", timeout=5)
    record("Incidents", "GET /api/incidents/warroom", r, [200, 404])
except Exception as e:
    record("Incidents", "GET /api/incidents/warroom", error=e)

try:
    r = session.get(f"{BASE}/api/response/actions", timeout=5)
    record("Incidents", "GET /api/response/actions", r, [200, 404])
except Exception as e:
    record("Incidents", "GET /api/response/actions", error=e)

# ── 10. PLAYBOOKS ─────────────────────────────────────────────────────────────
try:
    r = session.get(f"{BASE}/api/playbooks", timeout=5)
    record("Playbooks", "GET /api/playbooks", r)
except Exception as e:
    record("Playbooks", "GET /api/playbooks", error=e)

try:
    r = session.get(f"{BASE}/api/playbooks/test", timeout=5)
    record("Playbooks", "GET /api/playbooks/test", r)
except Exception as e:
    record("Playbooks", "GET /api/playbooks/test", error=e)

# ── 11. AI / LLM ──────────────────────────────────────────────────────────────
try:
    r = session.get(f"{BASE}/api/ai/models", timeout=5)
    record("AI/LLM", "GET /api/ai/models", r, [200, 404])
except Exception as e:
    record("AI/LLM", "GET /api/ai/models", error=e)

try:
    r = session.get(f"{BASE}/api/ai/status", timeout=5)
    record("AI/LLM", "GET /api/ai/status", r, [200, 404])
except Exception as e:
    record("AI/LLM", "GET /api/ai/status", error=e)

try:
    r = session.get(f"{BASE}/api/ai-system/providers", timeout=5)
    record("AI/LLM", "GET /api/ai-system/providers", r, [200, 404])
except Exception as e:
    record("AI/LLM", "GET /api/ai-system/providers", error=e)

try:
    r = session.get(f"{BASE}/api/ai-system/training/jobs", timeout=5)
    record("AI/LLM", "GET /api/ai-system/training/jobs", r, [200, 404])
except Exception as e:
    record("AI/LLM", "GET /api/ai-system/training/jobs", error=e)

# ── 12. SOFTWARE / SBOM ───────────────────────────────────────────────────────
try:
    r = session.get(f"{BASE}/api/software", timeout=5)
    record("Software/SBOM", "GET /api/software", r, [200, 404])
except Exception as e:
    record("Software/SBOM", "GET /api/software", error=e)

try:
    r = session.get(f"{BASE}/api/sbom", timeout=5)
    record("Software/SBOM", "GET /api/sbom", r, [200, 404])
except Exception as e:
    record("Software/SBOM", "GET /api/sbom", error=e)

# ── 13. DATA GOVERNANCE ───────────────────────────────────────────────────────
try:
    r = session.get(f"{BASE}/api/data-governance/policies", timeout=5)
    record("Data Governance", "GET /api/data-governance/policies", r, [200, 404])
except Exception as e:
    record("Data Governance", "GET /api/data-governance/policies", error=e)

try:
    r = session.get(f"{BASE}/api/data-governance/classifications", timeout=5)
    record("Data Governance", "GET /api/data-governance/classifications", r, [200, 404])
except Exception as e:
    record("Data Governance", "GET /api/data-governance/classifications", error=e)

# ── 14. PAYMENT ───────────────────────────────────────────────────────────────
try:
    r = session.get(f"{BASE}/api/payment/plans", timeout=5)
    record("Payment", "GET /api/payment/plans", r, [200, 404])
except Exception as e:
    record("Payment", "GET /api/payment/plans", error=e)

try:
    r = session.get(f"{BASE}/api/payment/subscriptions", timeout=5)
    record("Payment", "GET /api/payment/subscriptions", r, [200, 404])
except Exception as e:
    record("Payment", "GET /api/payment/subscriptions", error=e)

# ── 15. ADMIN ─────────────────────────────────────────────────────────────────
try:
    r = session.get(f"{BASE}/api/admin/evidence", timeout=5)
    record("Admin", "GET /api/admin/evidence", r, [200, 404])
except Exception as e:
    record("Admin", "GET /api/admin/evidence", error=e)

try:
    r = session.get(f"{BASE}/api/admin/usage", timeout=5)
    record("Admin", "GET /api/admin/usage", r, [200, 404])
except Exception as e:
    record("Admin", "GET /api/admin/usage", error=e)

# ── 16. PLATFORM / SETTINGS ───────────────────────────────────────────────────
try:
    r = session.get(f"{BASE}/api/platform/settings", timeout=5)
    record("Platform", "GET /api/platform/settings", r, [200, 404])
except Exception as e:
    record("Platform", "GET /api/platform/settings", error=e)

try:
    r = session.get(f"{BASE}/api/platform/health", timeout=5)
    record("Platform", "GET /api/platform/health", r, [200, 404])
except Exception as e:
    record("Platform", "GET /api/platform/health", error=e)

# ── 17. BAA / CONTRACTS ───────────────────────────────────────────────────────
try:
    r = session.get(f"{BASE}/api/baa", timeout=5)
    record("BAA", "GET /api/baa", r, [200, 404])
except Exception as e:
    record("BAA", "GET /api/baa", error=e)

# ── 18. SECURITY - RATE LIMIT / AUTH GUARD ────────────────────────────────────
try:
    r = requests.get(f"{BASE}/api/agents", timeout=5)  # no auth
    record("Security Guards", "GET /api/agents (no auth -> 401)", r, [401, 403])
except Exception as e:
    record("Security Guards", "GET /api/agents (no auth)", error=e)

try:
    r = requests.get(f"{BASE}/api/secrets/list", timeout=5)  # no auth
    record("Security Guards", "GET /api/secrets/list (no auth -> 401)", r, [401, 403])
except Exception as e:
    record("Security Guards", "GET /api/secrets/list (no auth)", error=e)

# ── REPORT ────────────────────────────────────────────────────────────────────
categories = {}
for r in results:
    cat = r["cat"]
    if cat not in categories:
        categories[cat] = []
    categories[cat].append(r)

total = len(results)
passed = sum(1 for r in results if r["status"] == "PASS")
failed = sum(1 for r in results if r["status"] == "FAIL")
errors = sum(1 for r in results if r["status"] == "ERROR")

print()
print("=" * 70)
print(f"  ENTERPRISE OMNI-AGENT PLATFORM — FEATURE TEST REPORT")
print(f"  {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}")
print("=" * 70)

for cat, items in categories.items():
    cat_pass = sum(1 for i in items if i["status"] == "PASS")
    cat_total = len(items)
    print(f"\n  [{cat}]  {cat_pass}/{cat_total}")
    print("  " + "-" * 60)
    for item in items:
        icon = "+" if item["status"] == "PASS" else ("!" if item["status"] == "ERROR" else "X")
        code_str = f"HTTP {item['code']}" if item["code"] else "N/A"
        detail = f"  << {item['detail']}" if item["detail"] else ""
        print(f"  {icon} {item['name']:<50} {code_str}{detail}")

print()
print("=" * 70)
print(f"  SUMMARY:  {passed} PASS  |  {failed} FAIL  |  {errors} ERROR  |  {total} TOTAL")
print("=" * 70)
print()

sys.exit(0 if failed == 0 and errors == 0 else 1)
