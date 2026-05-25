import sys, io, requests
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

BASE = 'http://127.0.0.1:5000'
r = requests.post(f'{BASE}/api/auth/login', json={'email': 'super@omni.ai', 'password': 'password123'})
TOKEN = r.json().get('access_token', '')
H = {'Authorization': f'Bearer {TOKEN}'}
RESULTS = {}


def test(cat, name, method, path, **kwargs):
    try:
        resp = getattr(requests, method)(f'{BASE}{path}', headers=H, timeout=10, **kwargs)
        ok = resp.status_code < 400
        try:
            d = resp.json()
        except Exception:
            d = resp.text[:80]
        preview = str(d)[:120] if ok else str(d)[:80]
        RESULTS.setdefault(cat, []).append((name, resp.status_code, ok, preview))
    except Exception as e:
        RESULTS.setdefault(cat, []).append((name, 0, False, str(e)[:80]))


# AUTH
test('Authentication', 'Login', 'post', '/api/auth/login', json={'email': 'super@omni.ai', 'password': 'password123'})
test('Authentication', 'Get My Profile', 'get', '/api/auth/me')
test('Authentication', 'Refresh Token', 'post', '/api/auth/refresh')
test('Authentication', 'Logout', 'post', '/api/auth/logout')

# TENANTS
test('Tenants', 'List Tenants', 'get', '/api/tenants')
test('Tenants', 'Lookup Registration Key', 'post', '/api/tenants/lookup-key', json={'registrationKey': 'dummy'})

# USERS & ROLES
test('Users & RBAC', 'List Users', 'get', '/api/users')
test('Users & RBAC', 'List Roles', 'get', '/api/roles')
test('Users & RBAC', 'Audit Logs', 'get', '/api/audit-logs')

# AGENTS
test('Agents', 'List Agents', 'get', '/api/agents')
test('Agents', 'Capabilities Definitions', 'get', '/api/agents/capabilities/definitions')
test('Agents', 'Pending Approvals', 'get', '/api/agents/approvals/pending')
test('Agents', 'Upgrade Jobs', 'get', '/api/agents/upgrade-jobs')
test('Agents', 'Network Utilization', 'get', '/api/agents/network-utilization')
test('Agents', 'Agentic Decisions', 'get', '/api/agents/agentic-decisions/all')
test('Agents', 'Remote Sessions', 'get', '/api/remote/sessions')

# ASSETS
test('Assets', 'List Assets', 'get', '/api/assets')
test('Assets', 'Search Assets', 'get', '/api/assets/search')

# ALERTS
test('Alerts', 'List Alerts', 'get', '/api/alerts')
test('Alerts', 'Alert Rules', 'get', '/api/alert-rules')
test('Alerts', 'Security Events', 'get', '/api/security-events')
test('Alerts', 'Security Cases', 'get', '/api/security-cases')

# VULNERABILITIES
test('Vulnerabilities', 'List Vulns', 'get', '/api/vulnerabilities')
test('Vulnerabilities', 'Vuln Stats', 'get', '/api/vulnerabilities/stats')
test('Vulnerabilities', 'Patches OS', 'get', '/api/patches/os')
test('Vulnerabilities', 'Patches Prioritized', 'get', '/api/patches/prioritized')
test('Vulnerabilities', 'Patch Compliance', 'get', '/api/patches/compliance-status')
test('Vulnerabilities', 'CVE Lookup', 'get', '/api/patches/cve/CVE-2024-0001')

# EDR
test('EDR / XDR', 'EDR Alerts', 'get', '/api/edr/alerts')
test('EDR / XDR', 'EDR Telemetry', 'get', '/api/edr/telemetry')

# SIEM
test('SIEM', 'SIEM Events', 'get', '/api/siem/events')
test('SIEM', 'SIEM Rules', 'get', '/api/siem/rules')
test('SIEM', 'SIEM Summary', 'get', '/api/siem/summary')
test('SIEM', 'SIEM Logs', 'get', '/api/siem/logs')
test('SIEM', 'SIEM Aggregations', 'get', '/api/siem/aggregations')

# CORRELATION
test('Correlation Engine', 'Correlation Rules', 'get', '/api/correlation/rules')
test('Correlation Engine', 'Correlated Events', 'get', '/api/correlation/events')

# UEBA
test('UEBA', 'Risk Scores', 'get', '/api/ueba/risk-scores')
test('UEBA', 'Anomalies', 'get', '/api/ueba/anomalies')
test('UEBA', 'UEBA Alerts', 'get', '/api/ueba/alerts')
test('UEBA', 'UEBA Stats', 'get', '/api/ueba/stats')
test('UEBA', 'Shadow AI Events', 'get', '/api/ueba/shadow-ai/events')

# THREAT INTEL
test('Threat Intel', 'Threat Feed', 'get', '/api/threat-intel/feed')
test('Threat Intel', 'Threat Stats', 'get', '/api/threat-intel/stats')
test('Threat Intel', 'IP Reputation', 'get', '/api/ai/reputation/ip/8.8.8.8')
test('Threat Intel', 'Domain Reputation', 'get', '/api/ai/reputation/domain/google.com')

# COMPLIANCE
test('Compliance', 'Frameworks', 'get', '/api/compliance/frameworks')
test('Compliance', 'Compliance Stats', 'get', '/api/compliance/stats')
test('Compliance', 'Compliance Reports', 'get', '/api/compliance/reports')
test('Compliance', 'Frameworks Dashboard', 'get', '/api/compliance-frameworks')
test('Compliance', 'BAA Management', 'get', '/api/baa')
test('Compliance', 'Custom Frameworks', 'get', '/api/custom-frameworks')

# PLAYBOOKS
test('Playbooks', 'List Playbooks', 'get', '/api/playbooks')
test('Playbooks', 'Enhanced Templates', 'get', '/api/playbooks/enhanced/templates')
test('Playbooks', 'Enhanced Executions', 'get', '/api/playbooks/enhanced/executions')
test('Playbooks', 'Enhanced Analytics', 'get', '/api/playbooks/enhanced/analytics')
test('Playbooks', 'SOAR Playbooks', 'get', '/api/soar/playbooks')

# INCIDENTS
test('Incidents', 'List Incidents', 'get', '/api/incidents')
test('Incidents', 'Incident Warroom', 'get', '/api/incident-warroom/rooms')

# RESPONSE & REMEDIATION
test('Response', 'Response History', 'get', '/api/response/history')
test('Response', 'Response Policies', 'get', '/api/response/policies')
test('Response', 'Rollback Checkpoints', 'get', '/api/rollback/checkpoints')
test('Response', 'AI Remediation', 'get', '/api/remediation/')

# SBOM
test('SBOM', 'List SBOMs', 'get', '/api/sboms')
test('SBOM', 'SBOM Components', 'get', '/api/sboms/components')

# SECRETS
test('Secrets Vault', 'List Secrets', 'get', '/api/secrets/list')
test('Secrets Vault', 'Secrets Stats', 'get', '/api/secrets/stats')
test('Secrets Vault', 'Rotation Check', 'get', '/api/secrets/rotation/check')
test('Secrets Vault', 'Secrets Audit Log', 'get', '/api/secrets/audit-log')

# DECEPTION
test('Deception', 'Deception Traps', 'get', '/api/deception/traps')

# JIT ACCESS
test('JIT Access', 'JIT Requests', 'get', '/api/jit-access/requests')

# SOFTWARE
test('Software Management', 'Repository', 'get', '/api/software/repository')
test('Software Management', 'Deployment Jobs', 'get', '/api/software/deployment-jobs')
test('Software Management', 'Packages', 'get', '/api/repo/packages')
test('Software Management', 'Agent Updates', 'get', '/api/agent-updates/latest')

# AI / LLM
test('AI Services', 'AI Status', 'get', '/api/ai/')
test('AI Services', 'AI Config', 'get', '/api/ai/config')
test('AI Services', 'Training Status', 'get', '/api/ai/train/status')
test('AI Services', 'Model Info', 'get', '/api/ai/train/model-info')
test('AI Services', 'AI Governance Models', 'get', '/api/ai-governance/models')
test('AI Services', 'AI Governance Dashboard', 'get', '/api/ai-governance/dashboard')
test('AI Services', 'AI Systems', 'get', '/api/ai-systems')
test('AI Services', 'LLM Proxy Audit', 'get', '/api/ai-proxy/audit-logs')
test('AI Services', 'CISSP Oracle Domains', 'get', '/api/cissp-oracle/domains')
test('AI Services', 'AutoML Studies', 'get', '/api/automl/studies')

# FINOPS
test('FinOps', 'Cost Snapshot', 'get', '/api/finops/costs')
test('FinOps', 'FinOps Budgets', 'get', '/api/finops/budgets')
test('FinOps', 'FinOps Anomalies', 'get', '/api/finops/anomalies')
test('FinOps', 'Sustainability Metrics', 'get', '/api/sustainability/metrics')

# PAYMENT & SUBSCRIPTION
test('Payment', 'Payment Methods', 'get', '/api/payments/methods')
test('Payment', 'Invoices', 'get', '/api/payments/invoices')
test('Payment', 'Gateways', 'get', '/api/payments/configured-gateways')
test('Payment', 'Subscription Info', 'get', '/api/payments/subscription-info')
test('Payment', 'Usage', 'get', '/api/payments/usage')

# REPORTING
test('Reporting', 'Executive Summary', 'get', '/api/reports/executive-summary')
test('Reporting', 'Vulnerability Exposure', 'get', '/api/reports/vulnerability-exposure')
test('Reporting', 'SLA Compliance', 'get', '/api/reports/sla-compliance')
test('Reporting', 'Scheduled Reports', 'get', '/api/reports/scheduled')
test('Reporting', 'Change Management', 'get', '/api/reports/change-management')

# SETTINGS
test('Settings', 'LLM Settings', 'get', '/api/settings/llm')
test('Settings', 'DB Settings', 'get', '/api/settings/database')

# NETWORK
test('Network / Zero Trust', 'Network Overview', 'get', '/api/network/overview')
test('Network / Zero Trust', 'Zero Trust Devices', 'get', '/api/zero-trust/device-trust-scores')
test('Network / Zero Trust', 'Zero Trust Sessions', 'get', '/api/zero-trust/session-risks')

# SWARM
test('Agent Swarm', 'Swarm List', 'get', '/api/swarm/list')
test('Agent Swarm', 'Swarm Topology', 'get', '/api/swarm/topology')
test('Agent Swarm', 'Swarm Peers', 'get', '/api/swarm/peers')

# SYSTEM HEALTH
test('System Health', 'System Health', 'get', '/api/system/health')
test('System Health', 'System Resources', 'get', '/api/system/resources')
test('System Health', 'Predictive Hosts', 'get', '/api/predictive/hosts')
test('System Health', 'APM Health', 'get', '/api/apm/health')
test('System Health', 'APM Endpoints', 'get', '/api/apm/endpoints')

# DEVSECOPS
test('DevSecOps', 'SAST Projects', 'get', '/api/sast/projects')
test('DevSecOps', 'SAST History', 'get', '/api/sast/history')
test('DevSecOps', 'SAST Vulns', 'get', '/api/sast/vulnerabilities')
test('DevSecOps', 'Pipeline Scans', 'get', '/api/pipeline-security/scans')
test('DevSecOps', 'Pipeline Stats', 'get', '/api/pipeline-security/stats')
test('DevSecOps', 'IaC Scans', 'get', '/api/iac-security/scans')
test('DevSecOps', 'Supply Chain Summary', 'get', '/api/supply-chain-security/summary')
test('DevSecOps', 'Supply Chain Vulns', 'get', '/api/supply-chain-security/vulnerabilities')

# VENDOR RISK
test('Vendor Risk', 'Vendors List', 'get', '/api/vendors')
test('Vendor Risk', 'Vendors Dashboard', 'get', '/api/vendors/dashboard/summary')

# DATA GOVERNANCE
test('Data Governance', 'Governance Policies', 'get', '/api/data-governance/policies')
test('Data Governance', 'Privacy Dashboard', 'get', '/api/privacy/dashboard')
test('Data Governance', 'Consent Tracking', 'get', '/api/privacy/consent-tracking')
test('Data Governance', 'DSR Requests', 'get', '/api/privacy/dsr')
test('Data Governance', 'Retention Policies', 'get', '/api/retention/policies')

# PENTEST
test('Pentesting', 'Pentest Jobs', 'get', '/api/pentest/jobs')
test('Pentesting', 'Pentest Stats', 'get', '/api/pentest/stats')
test('Pentesting', 'Pentest Tools', 'get', '/api/pentest/tools')

# INTEGRATIONS
test('Integrations', 'Integrations List', 'get', '/api/integrations')
test('Integrations', 'Webhooks', 'get', '/api/webhooks')
test('Integrations', 'Ticketing Config', 'get', '/api/ticketing/config')
test('Integrations', 'SSO Status', 'get', '/api/sso/status')

# ANALYTICS & INSIGHTS
test('Analytics & Insights', 'Historical Analytics', 'get', '/api/analytics/historical')
test('Analytics & Insights', 'BI Analytics', 'get', '/api/analytics/bi')
test('Analytics & Insights', 'DORA Metrics', 'get', '/api/dora/metrics')
test('Analytics & Insights', 'Insights Summary', 'get', '/api/insights/summary')
test('Analytics & Insights', 'KPIs', 'get', '/api/kpis')

# TRACING & APM
test('Tracing & APM', 'Traces', 'get', '/api/tracing/traces')
test('Tracing & APM', 'Service Map', 'get', '/api/tracing/service-map')
test('Tracing & APM', 'APM Alerts', 'get', '/api/apm/alerts')

# CLOUD
test('Cloud Security', 'Cloud Accounts', 'get', '/api/cloud-accounts')
test('Cloud Security', 'AI Remediation CSPM', 'get', '/api/ai/remediation/cspm')

# TRAINING MODULES
test('Security Training', 'Training Modules', 'get', '/api/training/modules')
test('Security Training', 'My Training', 'get', '/api/training/my-training')

# Print results
print()
print('=' * 72)
total_pass = sum(1 for items in RESULTS.values() for _, _, ok, _ in items if ok)
total_fail = sum(1 for items in RESULTS.values() for _, _, ok, _ in items if not ok)
total = total_pass + total_fail
print(f'OVERALL RESULT:  {total_pass}/{total} PASS  |  {total_fail} FAIL')
print('=' * 72)

for cat, items in RESULTS.items():
    cat_pass = sum(1 for _, _, ok, _ in items if ok)
    status = 'OK' if cat_pass == len(items) else ('PARTIAL' if cat_pass > 0 else 'FAIL')
    print(f'\n[{status}] {cat} ({cat_pass}/{len(items)})')
    for name, code, ok, preview in items:
        s = 'PASS' if ok else 'FAIL'
        print(f'       {s} [{code:3d}] {name}')
        if not ok:
            print(f'              -> {preview[:90]}')
