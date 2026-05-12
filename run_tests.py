import httpx, time, json, sys

BASE = "http://localhost:5000"
results = []

def record(name, passed, detail=""):
    mark = "PASS" if passed else "FAIL"
    results.append((mark, name, detail))
    print(f"{mark} | {name} | {detail}", flush=True)

client = httpx.Client(timeout=10)

# 1. Health check
r = client.get(f"{BASE}/health")
record("Backend health", r.status_code == 200, r.status_code)

# 2. Login valid ->> access_token AND refresh_token
r = client.post(f"{BASE}/api/auth/login", json={"email":"super@omni.ai","password":"password123"})
record("Login valid ->> 200", r.status_code == 200, r.status_code)
data = r.json()
token = data.get("access_token","")
refresh_token = data.get("refresh_token","")
record("Login returns access_token", bool(token), str(token)[:30])
record("Login returns refresh_token", bool(refresh_token), str(refresh_token)[:30])

headers = {"Authorization": f"Bearer {token}"}

# 3. Login wrong password ->> generic error (no DEBUG)
r = client.post(f"{BASE}/api/auth/login", json={"email":"super@omni.ai","password":"wrongpass"})
record("Login wrong ->> 401", r.status_code == 401, r.status_code)
detail_str = r.json().get("detail","")
record("No DEBUG info in 401 detail", "DEBUG" not in detail_str and "super@omni.ai" not in detail_str, detail_str)

# 4. Rate limit headers present after login
r = client.post(f"{BASE}/api/auth/login", json={"email":"super@omni.ai","password":"password123"})
rl_headers = [h for h in r.headers if "ratelimit" in h.lower() or "x-ratelimit" in h.lower() or "retry-after" in h.lower()]
record("Rate limit headers present", len(rl_headers) > 0, str(dict(r.headers)))

# 5. GET /api/auth/me
r = client.get(f"{BASE}/api/auth/me", headers=headers)
record("GET /api/auth/me ->> 200", r.status_code == 200, r.status_code)

# 6. POST /api/auth/refresh
r = client.post(f"{BASE}/api/auth/refresh", json={"refresh_token": refresh_token})
record("POST /api/auth/refresh ->> 200", r.status_code == 200, r.json())
new_token = r.json().get("access_token","") if r.status_code == 200 else ""
record("Refresh returns new access_token", bool(new_token), str(new_token)[:30])

# 7. POST /api/auth/logout
r = client.post(f"{BASE}/api/auth/logout", headers=headers)
record("POST /api/auth/logout ->> 200", r.status_code == 200, r.json())

# 8. Password reset
r = client.post(f"{BASE}/api/auth/reset-password/request", json={"email":"super@omni.ai"})
record("Reset password request ->> 200", r.status_code == 200, r.status_code)
reset_token = r.json().get("reset_token","") if r.status_code == 200 else ""
if reset_token:
    r2 = client.post(f"{BASE}/api/auth/reset-password/confirm", json={"token": reset_token, "new_password": "password123"})
    record("Reset password confirm ->> 200", r2.status_code == 200, r2.json())

# 9. EDR pipeline: ingest an alert and check auto-response fires
edr_agent = "test-edr-agent-001"
edr_batch = {
    "agent_id": edr_agent,
    "hostname": "test-host-001",
    "timestamp": "2025-01-01T00:00:00Z",
    "process_tree": [],
    "network_connections": [],
    "alerts": [{
        "alert_id": "test-alert-001",
        "type": "KNOWN_MALICIOUS_PROCESS",
        "severity": "critical",
        "description": "mimikatz.exe detected",
        "process": {"name": "mimikatz.exe", "pid": 1234, "path": "C:\temp\mimikatz.exe"}
    }],
    "alert_count": 1,
    "process_count": 1,
    "etw_events_captured": 0
}
r = client.post(f"{BASE}/api/edr/events", json=edr_batch)
record("POST /api/edr/events ->> 200", r.status_code == 200, r.json())
record("EDR ingest stores alert", r.json().get("alerts_stored",0) >= 1, r.json())

# Wait for background orchestrator task
time.sleep(3)

# Check that auto-response task was queued
r = client.get(f"{BASE}/api/response/tasks/{edr_agent}")
record("EDR auto-response: GET /api/response/tasks ->> 200", r.status_code == 200, r.status_code)
tasks = r.json() if r.status_code == 200 else []
kill_tasks = [t for t in tasks if t.get("action") == "kill_process"]
record("EDR auto-response: kill_process task queued", len(kill_tasks) > 0, f"{len(tasks)} tasks, kill={len(kill_tasks)}")

# 10. EDR endpoints
r = client.get(f"{BASE}/api/edr/alerts", headers=headers)
record("GET /api/edr/alerts ->> 200", r.status_code == 200, r.status_code)
r = client.get(f"{BASE}/api/edr/telemetry/summary", headers=headers)
record("GET /api/edr/telemetry/summary ->> 200", r.status_code == 200, r.status_code)

# 11. Response policies (3 built-ins)
r = client.get(f"{BASE}/api/response/policies", headers=headers)
record("GET /api/response/policies ->> 200", r.status_code == 200, r.status_code)
policies = r.json() if r.status_code == 200 else []
policy_ids = [p.get("policy_id","") for p in policies]
record("Built-in policy: auto-kill-mimikatz present", "auto-kill-mimikatz" in policy_ids, policy_ids)
record("Built-in policy: alert-encoded-powershell present", "alert-encoded-powershell" in policy_ids, policy_ids)
record("Built-in policy: quarantine-suspicious-temp present", "quarantine-suspicious-temp" in policy_ids, policy_ids)

# 12. Manual response action
r = client.post(f"{BASE}/api/response/execute", headers=headers,
    json={"agent_id": edr_agent, "action": "isolate_host", "params": {}, "reason": "test"})
record("POST /api/response/execute ->> 200", r.status_code == 200, r.json())

# 13. XDR playbooks seeded
r = client.get(f"{BASE}/api/playbooks", headers=headers)
record("GET /api/playbooks ->> 200", r.status_code == 200, r.status_code)
pbs = r.json() if r.status_code == 200 else []
xdr_pbs = [p for p in pbs if p.get("trigger_type") == "correlation"]
record("XDR playbooks seeded (4 expected)", len(xdr_pbs) >= 4, f"{len(xdr_pbs)} found")

# 14. Search endpoints
for path, label in [
    (f"/api/agents/search?q=test", "agents"),
    (f"/api/assets/search?q=test", "assets"),
    (f"/api/alerts/search?q=test", "alerts"),
]:
    r = client.get(f"{BASE}{path}", headers=headers)
    record(f"GET {path} ->> 200", r.status_code == 200, f"{r.status_code}: {r.text[:100]}")

# 15. Bulk delete (nonexistent IDs ->> deleted=0, not 404)
for path, label, body in [
    ("/api/agents/bulk", "agents", ["nonexistent-agent-999"]),
    ("/api/assets/bulk", "assets", ["nonexistent-asset-999"]),
    ("/api/alerts/bulk", "alerts", ["nonexistent-alert-999"]),
]:
    r = client.request("DELETE", f"{BASE}{path}", headers=headers, json=body)
    record(f"DELETE {path} ->> 200", r.status_code == 200, f"{r.status_code}: {r.text[:100]}")

print("\n=== SUMMARY ===")
passed = sum(1 for r in results if r[0]=="PASS")
failed = sum(1 for r in results if r[0]=="FAIL")
print(f"PASSED: {passed}/{len(results)}")
print(f"FAILED: {failed}/{len(results)}")
if failed:
    print("\nFailed tests:")
    for r in results:
        if r[0] == "FAIL":
            print(f"  FAIL | {r[1]} | {r[2]}")
