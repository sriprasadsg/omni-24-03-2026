"""
Agent Capability Test Suite
Tests all 34 agent capabilities via API endpoints.
"""
import sys
import io
import requests

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

BASE = 'http://127.0.0.1:5000'

# Login as srihari (tenant_bd85d4ad0c30 - has the registered agent)
r = requests.post(f'{BASE}/api/auth/login',
                  json={'email': 'srihari@exafluence.com', 'password': 'password123'})
TOKEN = r.json()['access_token']
H = {'Authorization': f'Bearer {TOKEN}'}
AGENT_ID = 'agent-27035468'

RESULTS = {}


def test(cat, name, method, path, **kwargs):
    try:
        resp = getattr(requests, method)(f'{BASE}{path}', headers=H, timeout=12, **kwargs)
        ok = resp.status_code < 400
        try:
            d = resp.json()
        except Exception:
            d = resp.text[:80]
        preview = str(d)[:150]
        RESULTS.setdefault(cat, []).append((name, resp.status_code, ok, preview))
        return ok, resp
    except Exception as e:
        RESULTS.setdefault(cat, []).append((name, 0, False, str(e)[:100]))
        return False, None


# ─── AGENT BASE INFO ─────────────────────────────────────────────────────────
test('Agent Base', 'List Agents', 'get', '/api/agents')
test('Agent Base', 'Agent Detail', 'get', f'/api/agents/{AGENT_ID}')
test('Agent Base', 'Capability Definitions', 'get', '/api/agents/capabilities/definitions')
test('Agent Base', 'Agent Capability List', 'get', f'/api/agents/{AGENT_ID}/capabilities')
test('Agent Base', 'Agent Capability Config', 'get', f'/api/agents/{AGENT_ID}/capabilities/configuration')
test('Agent Base', 'Agent Goals', 'get', f'/api/agents/{AGENT_ID}/goals')
test('Agent Base', 'Agent Diagnostics', 'get', f'/api/agents/{AGENT_ID}/diagnostics')
test('Agent Base', 'Agentic Decisions', 'get', f'/api/agents/{AGENT_ID}/agentic-decisions')

# ─── CAPABILITY: metrics_collection ──────────────────────────────────────────
test('metrics_collection', 'POST cap data', 'post',
     f'/api/agents/{AGENT_ID}/capabilities/metrics_collection/data',
     json={'window': '1h'})
test('metrics_collection', 'Agent Metrics Current', 'get',
     f'/api/agents/{AGENT_ID}/metrics/current')
test('metrics_collection', 'Agent Metrics History', 'get',
     f'/api/agents/{AGENT_ID}/metrics/history')

# ─── CAPABILITY: log_collection ──────────────────────────────────────────────
test('log_collection', 'POST cap data', 'post',
     f'/api/agents/{AGENT_ID}/capabilities/log_collection/data',
     json={'limit': 50})
test('log_collection', 'Agent Raw Logs', 'get',
     f'/api/agents/{AGENT_ID}/logs/raw')

# ─── CAPABILITY: process_monitor ─────────────────────────────────────────────
test('process_monitor', 'POST cap data', 'post',
     f'/api/agents/{AGENT_ID}/capabilities/process_monitor/data',
     json={})

# ─── CAPABILITY: log_shipper ─────────────────────────────────────────────────
test('log_shipper', 'POST cap data', 'post',
     f'/api/agents/{AGENT_ID}/capabilities/log_shipper/data',
     json={})

# ─── CAPABILITY: vulnerability_scanning ──────────────────────────────────────
test('vulnerability_scanning', 'POST cap data', 'post',
     f'/api/agents/{AGENT_ID}/capabilities/vulnerability_scanning/data',
     json={})
test('vulnerability_scanning', 'Trigger Vuln Scan', 'post',
     f'/api/agents/{AGENT_ID}/vulnerability-scan',
     json={'scan_type': 'full'})
test('vulnerability_scanning', 'Vuln Scan Results', 'get',
     f'/api/agents/{AGENT_ID}/vulnerability-scans')

# ─── CAPABILITY: fim ─────────────────────────────────────────────────────────
test('fim', 'POST cap data', 'post',
     f'/api/agents/{AGENT_ID}/capabilities/fim/data',
     json={})
test('fim', 'FIM Events', 'get',
     f'/api/agents/{AGENT_ID}/fim-events')

# ─── CAPABILITY: real_time_fim ───────────────────────────────────────────────
test('real_time_fim', 'POST cap data', 'post',
     f'/api/agents/{AGENT_ID}/capabilities/real_time_fim/data',
     json={})

# ─── CAPABILITY: compliance_enforcement ──────────────────────────────────────
test('compliance_enforcement', 'POST cap data', 'post',
     f'/api/agents/{AGENT_ID}/capabilities/compliance_enforcement/data',
     json={})
test('compliance_enforcement', 'Compliance Scan', 'post',
     f'/api/agents/{AGENT_ID}/compliance/scan',
     json={'framework': 'nist_csf'})

# ─── CAPABILITY: runtime_security ────────────────────────────────────────────
test('runtime_security', 'POST cap data', 'post',
     f'/api/agents/{AGENT_ID}/capabilities/runtime_security/data',
     json={})

# ─── CAPABILITY: edr_realtime ────────────────────────────────────────────────
test('edr_realtime', 'POST cap data', 'post',
     f'/api/agents/{AGENT_ID}/capabilities/edr_realtime/data',
     json={})
test('edr_realtime', 'EDR Alerts', 'get', '/api/edr/alerts')
test('edr_realtime', 'EDR Telemetry Summary', 'get', '/api/edr/telemetry/summary')

# ─── CAPABILITY: persistence_detection ───────────────────────────────────────
test('persistence_detection', 'POST cap data', 'post',
     f'/api/agents/{AGENT_ID}/capabilities/persistence_detection/data',
     json={})
test('persistence_detection', 'Persistence Findings', 'get',
     f'/api/agents/{AGENT_ID}/persistence-findings')
test('persistence_detection', 'Persistence Scan', 'post',
     '/api/persistence/scan',
     json={'agent_id': AGENT_ID})

# ─── CAPABILITY: deception_monitor ───────────────────────────────────────────
test('deception_monitor', 'POST cap data', 'post',
     f'/api/agents/{AGENT_ID}/capabilities/deception_monitor/data',
     json={})
test('deception_monitor', 'Deception Summary', 'get', '/api/deception/summary')
test('deception_monitor', 'Deception Alerts', 'get', '/api/deception/alerts')
test('deception_monitor', 'Honeytokens List', 'get', '/api/deception/honeytokens')

# ─── CAPABILITY: network_discovery ───────────────────────────────────────────
test('network_discovery', 'POST cap data', 'post',
     f'/api/agents/{AGENT_ID}/capabilities/network_discovery/data',
     json={})
test('network_discovery', 'Discovery Scan', 'post',
     f'/api/agents/{AGENT_ID}/discovery/scan',
     json={'subnet': '192.168.1.0/24'})
test('network_discovery', 'Discovery Results', 'get',
     f'/api/agents/{AGENT_ID}/discovery/results')
test('network_discovery', 'Network Devices', 'get', '/api/network-devices')
test('network_discovery', 'Network Topology', 'get', '/api/network-devices/topology')

# ─── CAPABILITY: cloud_metadata ──────────────────────────────────────────────
test('cloud_metadata', 'POST cap data', 'post',
     f'/api/agents/{AGENT_ID}/capabilities/cloud_metadata/data',
     json={})
test('cloud_metadata', 'Cloud Accounts', 'get', '/api/cloud-accounts')

# ─── CAPABILITY: web_monitor ─────────────────────────────────────────────────
test('web_monitor', 'POST cap data', 'post',
     f'/api/agents/{AGENT_ID}/capabilities/web_monitor/data',
     json={})

# ─── CAPABILITY: remote_access ───────────────────────────────────────────────
test('remote_access', 'POST cap data', 'post',
     f'/api/agents/{AGENT_ID}/capabilities/remote_access/data',
     json={})
test('remote_access', 'Remote Sessions', 'get', '/api/remote/sessions')
test('remote_access', 'Remote Agent Status', 'get',
     f'/api/agents/remote/{AGENT_ID}/status')

# ─── CAPABILITY: pii_scanner ─────────────────────────────────────────────────
test('pii_scanner', 'POST cap data', 'post',
     f'/api/agents/{AGENT_ID}/capabilities/pii_scanner/data',
     json={})
test('pii_scanner', 'Governance Catalog', 'get', '/api/governance/catalog')
test('pii_scanner', 'PII Patterns', 'get', '/api/governance/pii-patterns')

# ─── CAPABILITY: sbom_analysis ───────────────────────────────────────────────
test('sbom_analysis', 'POST cap data', 'post',
     f'/api/agents/{AGENT_ID}/capabilities/sbom_analysis/data',
     json={})
test('sbom_analysis', 'SBOMs List', 'get', '/api/sboms')
test('sbom_analysis', 'SBOM Components', 'get', '/api/sboms/components')
test('sbom_analysis', 'Software Inventory', 'get',
     f'/api/agents/{AGENT_ID}/software-inventory')

# ─── CAPABILITY: compliance_evidence_collector ───────────────────────────────
test('compliance_evidence_collector', 'POST cap data', 'post',
     f'/api/agents/{AGENT_ID}/capabilities/compliance_evidence_collector/data',
     json={})
test('compliance_evidence_collector', 'Compliance Evidence', 'get',
     '/api/compliance/evidence')
test('compliance_evidence_collector', 'Compliance Artifacts', 'get',
     '/api/compliance/artifacts')

# ─── CAPABILITY: vendor_risk ─────────────────────────────────────────────────
test('vendor_risk', 'POST cap data', 'post',
     f'/api/agents/{AGENT_ID}/capabilities/vendor_risk/data',
     json={})
test('vendor_risk', 'Vendors List', 'get', '/api/vendors')
test('vendor_risk', 'Vendors Dashboard', 'get', '/api/vendors/dashboard/summary')

# ─── CAPABILITY: predictive_health ───────────────────────────────────────────
test('predictive_health', 'POST cap data', 'post',
     f'/api/agents/{AGENT_ID}/capabilities/predictive_health/data',
     json={})
test('predictive_health', 'Predictive Hosts', 'get', '/api/predictive/hosts')
test('predictive_health', 'Forecast', 'get', '/api/predictive/forecast')
test('predictive_health', 'Model Accuracy', 'get', '/api/predictive/model/accuracy')

# ─── CAPABILITY: ueba ────────────────────────────────────────────────────────
test('ueba', 'POST cap data', 'post',
     f'/api/agents/{AGENT_ID}/capabilities/ueba/data',
     json={})
test('ueba', 'UEBA Risk Scores', 'get', '/api/ueba/risk-scores')
test('ueba', 'UEBA Anomalies', 'get', '/api/ueba/anomalies')
test('ueba', 'UEBA Shadow AI', 'get', '/api/ueba/shadow-ai/events')

# ─── CAPABILITY: ebpf_tracing ────────────────────────────────────────────────
test('ebpf_tracing', 'POST cap data', 'post',
     f'/api/agents/{AGENT_ID}/capabilities/ebpf_tracing/data',
     json={})

# ─── CAPABILITY: shadow_ai ───────────────────────────────────────────────────
test('shadow_ai', 'POST cap data', 'post',
     f'/api/agents/{AGENT_ID}/capabilities/shadow_ai/data',
     json={})
test('shadow_ai', 'Shadow AI Scan', 'post',
     f'/api/agents/{AGENT_ID}/shadow-ai-scan',
     json={})
test('shadow_ai', 'Shadow AI Scans', 'get',
     f'/api/agents/{AGENT_ID}/shadow-ai-scans')
test('shadow_ai', 'UEBA Shadow AI', 'get', '/api/ueba/shadow-ai')

# ─── CAPABILITY: system_patching ─────────────────────────────────────────────
test('system_patching', 'POST cap data', 'post',
     f'/api/agents/{AGENT_ID}/capabilities/system_patching/data',
     json={})
test('system_patching', 'Patches Prioritized', 'get', '/api/patches/prioritized')
test('system_patching', 'Patches OS', 'get', '/api/patches/os')

# ─── CAPABILITY: patch_installer ─────────────────────────────────────────────
test('patch_installer', 'POST cap data', 'post',
     f'/api/agents/{AGENT_ID}/capabilities/patch_installer/data',
     json={})
test('patch_installer', 'Patch Deploy', 'post',
     '/api/patches/deploy',
     json={'agent_id': AGENT_ID, 'patch_ids': []})

# ─── CAPABILITY: software_management ─────────────────────────────────────────
test('software_management', 'POST cap data', 'post',
     f'/api/agents/{AGENT_ID}/capabilities/software_management/data',
     json={})
test('software_management', 'Software Repository', 'get', '/api/software/repository')
test('software_management', 'Deployment Jobs', 'get', '/api/software/deployment-jobs')
test('software_management', 'Software Deploy', 'post',
     '/api/software/deploy',
     json={'agent_id': AGENT_ID, 'package': 'test'})

# ─── CAPABILITY: remediation_executor ────────────────────────────────────────
test('remediation_executor', 'POST cap data', 'post',
     f'/api/agents/{AGENT_ID}/capabilities/remediation_executor/data',
     json={})
test('remediation_executor', 'Remediation List', 'get', '/api/remediation/')
test('remediation_executor', 'Response History', 'get', '/api/response/history')

# ─── CAPABILITY: autonomous_response ─────────────────────────────────────────
test('autonomous_response', 'POST cap data', 'post',
     f'/api/agents/{AGENT_ID}/capabilities/autonomous_response/data',
     json={})
test('autonomous_response', 'Response Policies', 'get', '/api/response/policies')
test('autonomous_response', 'Pending Approvals', 'get', '/api/agents/approvals/pending')
test('autonomous_response', 'Approvals History', 'get', '/api/approvals/history')

# ─── CAPABILITY: agent_update ─────────────────────────────────────────────────
test('agent_update', 'POST cap data', 'post',
     f'/api/agents/{AGENT_ID}/capabilities/agent_update/data',
     json={})
test('agent_update', 'Latest Agent Update', 'get', '/api/agent-updates/latest')
test('agent_update', 'Upgrade Jobs', 'get', '/api/agents/upgrade-jobs')

# ─── CAPABILITY: vss_manager ─────────────────────────────────────────────────
test('vss_manager', 'POST cap data', 'post',
     f'/api/agents/{AGENT_ID}/capabilities/vss_manager/data',
     json={})

# ─── CAPABILITY: backup_verifier ─────────────────────────────────────────────
test('backup_verifier', 'POST cap data', 'post',
     f'/api/agents/{AGENT_ID}/capabilities/backup_verifier/data',
     json={})
test('backup_verifier', 'Rollback Checkpoints', 'get', '/api/rollback/checkpoints')

# ─── CAPABILITY: process_injection_simulation ────────────────────────────────
test('process_injection_simulation', 'POST cap data', 'post',
     f'/api/agents/{AGENT_ID}/capabilities/process_injection_simulation/data',
     json={})
test('process_injection_simulation', 'Simulation History', 'get', '/api/simulation/history')
test('process_injection_simulation', 'Run Simulation', 'post',
     '/api/simulation/process-injection',
     json={'agent_id': AGENT_ID, 'technique': 'dll_injection'})

# ─── CAPABILITY: threat_intel ────────────────────────────────────────────────
test('threat_intel', 'POST cap data', 'post',
     f'/api/agents/{AGENT_ID}/capabilities/threat_intel/data',
     json={})
test('threat_intel', 'Threat Intel Feed', 'get', '/api/threat-intel/feed')
test('threat_intel', 'Threat Intel Stats', 'get', '/api/threat-intel/stats')
test('threat_intel', 'Agent Threat Intel', 'get',
     f'/api/agents/{AGENT_ID}/threat-intel')
test('threat_intel', 'IP Reputation', 'get', '/api/ai/reputation/ip/1.2.3.4')

# ─── AGENT SWARM & ORCHESTRATION ─────────────────────────────────────────────
test('swarm_orchestration', 'Swarm List', 'get', '/api/swarm/list')
test('swarm_orchestration', 'Swarm Topology', 'get', '/api/swarm/topology')
test('swarm_orchestration', 'Swarm Start', 'post',
     '/api/swarm/start',
     json={'mission': 'threat_hunt', 'agent_ids': [AGENT_ID]})
test('swarm_orchestration', 'Swarm Report', 'get', '/api/swarm/report')

# ─── AGENT SAFETY & GUARDRAILS ───────────────────────────────────────────────
test('safety_guardrails', 'Safety Rules', 'get',
     f'/api/agents/{AGENT_ID}/safety-rules')
test('safety_guardrails', 'Agent Integrity Verify', 'get',
     f'/api/agents/{AGENT_ID}/verify-integrity')
test('safety_guardrails', 'Pending Approvals (global)', 'get',
     '/api/agents/approvals/pending')
test('safety_guardrails', 'Rollback Checkpoints', 'get',
     '/api/rollback/checkpoints')

# ─── AGENT AGENTIC INTELLIGENCE ───────────────────────────────────────────────
test('agentic_intelligence', 'Agentic Decisions (all)', 'get',
     '/api/agents/agentic-decisions/all')
test('agentic_intelligence', 'Agent Goals', 'get',
     f'/api/agents/{AGENT_ID}/goals')
test('agentic_intelligence', 'AI Chat', 'post',
     '/api/ai/chat',
     json={'message': 'What is the current threat level?', 'context': {}})
test('agentic_intelligence', 'AI Threat Hunt', 'post',
     '/api/ai/threat-hunt',
     json={'query': 'suspicious process activity'})

# ─── PRINT RESULTS ───────────────────────────────────────────────────────────
print()
print('=' * 76)
total_pass = sum(1 for items in RESULTS.values() for _, _, ok, _ in items if ok)
total_fail = sum(1 for items in RESULTS.values() for _, _, ok, _ in items if not ok)
total = total_pass + total_fail
print(f'CAPABILITY TEST RESULT:  {total_pass}/{total} PASS  |  {total_fail} FAIL')
print('=' * 76)

for cat, items in RESULTS.items():
    cat_pass = sum(1 for _, _, ok, _ in items if ok)
    status = 'OK' if cat_pass == len(items) else ('PARTIAL' if cat_pass > 0 else 'FAIL')
    print(f'\n[{status}] {cat}  ({cat_pass}/{len(items)})')
    for name, code, ok, preview in items:
        s = 'PASS' if ok else 'FAIL'
        print(f'       {s} [{code:3d}] {name}')
        if not ok:
            print(f'              -> {preview[:100]}')
