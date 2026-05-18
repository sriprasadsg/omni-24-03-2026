#!/usr/bin/env python3
"""
Feature status test script.
Usage: python run_feature_test.py <token>
"""
import sys
import urllib.request

TOKEN = sys.argv[1] if len(sys.argv) > 1 else ""
BASE = "http://localhost:5000"

TESTS = [
    # (section, label, path)
    ("AUTHENTICATION", "Profile (me)", "/api/auth/me"),
    ("AUTHENTICATION", "Users list", "/api/users"),
    ("AUTHENTICATION", "Roles", "/api/roles"),
    ("AUTHENTICATION", "Tenants", "/api/tenants"),
    ("AUTHENTICATION", "SSO Providers", "/api/sso/providers"),

    ("AGENTS & FLEET", "Agent list", "/api/agents"),
    ("AGENTS & FLEET", "Capabilities definitions", "/api/agents/capabilities/definitions"),
    ("AGENTS & FLEET", "Agentic decisions", "/api/agents/agentic-decisions/all"),
    ("AGENTS & FLEET", "Pending approvals", "/api/agents/approvals/pending"),
    ("AGENTS & FLEET", "Network utilization", "/api/agents/network-utilization"),
    ("AGENTS & FLEET", "Swarm list", "/api/swarm/list"),
    ("AGENTS & FLEET", "Swarm topology", "/api/swarm/topology"),

    ("ALERTS & EVENTS", "Alerts", "/api/alerts"),
    ("ALERTS & EVENTS", "Alert rules", "/api/alert-rules"),
    ("ALERTS & EVENTS", "Security events", "/api/security-events"),
    ("ALERTS & EVENTS", "Security cases", "/api/security-cases"),
    ("ALERTS & EVENTS", "Attack paths", "/api/security/attack-paths"),
    ("ALERTS & EVENTS", "Security audit log", "/api/security/audit-log"),

    ("VULNERABILITIES", "Vulnerabilities", "/api/vulnerabilities"),
    ("VULNERABILITIES", "Vuln stats", "/api/vulnerabilities/stats"),
    ("VULNERABILITIES", "Vuln scans", "/api/vulnerability-scans"),
    ("VULNERABILITIES", "Patch compliance", "/api/patches/compliance-status"),

    ("EDR", "EDR telemetry summary", "/api/edr/telemetry/summary"),
    ("EDR", "EDR alerts", "/api/edr/alerts"),
    ("EDR", "EDR IOC", "/api/edr/ioc"),

    ("UEBA", "UEBA stats", "/api/ueba/stats"),
    ("UEBA", "UEBA anomalies", "/api/ueba/anomalies"),
    ("UEBA", "UEBA alerts", "/api/ueba/alerts"),
    ("UEBA", "UEBA risk scores", "/api/ueba/risk-scores"),
    ("UEBA", "UEBA rules", "/api/ueba/rules"),
    ("UEBA", "Shadow AI events", "/api/ueba/shadow-ai/events"),

    ("SIEM", "SIEM summary", "/api/siem/summary"),
    ("SIEM", "SIEM events", "/api/siem/events"),
    ("SIEM", "SIEM logs", "/api/siem/logs"),
    ("SIEM", "SIEM rules", "/api/siem/rules"),
    ("SIEM", "SIEM configs", "/api/siem/configs"),
    ("SIEM", "SIEM aggregations", "/api/siem/aggregations"),

    ("THREAT INTEL", "Threat intel feed", "/api/threat-intel/feed"),
    ("THREAT INTEL", "Threat intel stats", "/api/threat-intel/stats"),

    ("CORRELATION ENGINE", "Correlations", "/api/correlations/"),
    ("CORRELATION ENGINE", "Correlation stats", "/api/correlations/stats"),
    ("CORRELATION ENGINE", "Correlation patterns", "/api/correlations/patterns/list"),

    ("COMPLIANCE", "Compliance overview", "/api/compliance"),
    ("COMPLIANCE", "Compliance evidence", "/api/compliance/evidence"),
    ("COMPLIANCE", "Compliance reports", "/api/compliance/reports"),
    ("COMPLIANCE", "Compliance automation rules", "/api/compliance/automation/rules"),

    ("PLAYBOOKS / SOAR", "Playbooks", "/api/playbooks"),
    ("PLAYBOOKS / SOAR", "SOAR playbooks", "/api/soar/playbooks"),
    ("PLAYBOOKS / SOAR", "SOAR runs", "/api/soar/runs"),
    ("PLAYBOOKS / SOAR", "Response policies", "/api/response/policies"),
    ("PLAYBOOKS / SOAR", "Response history", "/api/response/history"),
    ("PLAYBOOKS / SOAR", "Response quarantine", "/api/response/quarantine"),

    ("AI / GOVERNANCE", "AI service", "/api/ai/"),
    ("AI / GOVERNANCE", "AI systems", "/api/ai-systems"),
    ("AI / GOVERNANCE", "AI governance dashboard", "/api/ai-governance/dashboard"),
    ("AI / GOVERNANCE", "AI governance models", "/api/ai-governance/models"),
    ("AI / GOVERNANCE", "AI governance policies", "/api/ai-governance/policies"),
    ("AI / GOVERNANCE", "AI proxy audit logs", "/api/ai-proxy/audit-logs"),

    ("ASSETS & INVENTORY", "Assets", "/api/assets"),
    ("ASSETS & INVENTORY", "SBOMs", "/api/sboms"),
    ("ASSETS & INVENTORY", "SBOM components", "/api/sboms/components"),
    ("ASSETS & INVENTORY", "Software repository", "/api/software/repository"),
    ("ASSETS & INVENTORY", "Binary analysis history", "/api/analysis/history"),

    ("DEVSECOPS", "SAST projects", "/api/sast/projects"),
    ("DEVSECOPS", "SAST vulnerabilities", "/api/sast/vulnerabilities"),
    ("DEVSECOPS", "SAST statistics", "/api/sast/statistics"),
    ("DEVSECOPS", "Supply chain findings", "/api/supply-chain/findings"),
    ("DEVSECOPS", "Supply chain security", "/api/supply-chain-security/summary"),
    ("DEVSECOPS", "API security summary", "/api/api-security/summary"),
    ("DEVSECOPS", "API security endpoints", "/api/api-security/endpoints"),
    ("DEVSECOPS", "IaC security scans", "/api/iac-security/scans"),
    ("DEVSECOPS", "IaC security violations", "/api/iac-security/violations"),
    ("DEVSECOPS", "Container images", "/api/container-scan/images"),
    ("DEVSECOPS", "Container scan stats", "/api/container-scan/stats"),
    ("DEVSECOPS", "Container vulnerabilities", "/api/container-scan/vulnerabilities"),

    ("CLOUD SECURITY", "Cloud integrations", "/api/cloud-integrations"),
    ("CLOUD SECURITY", "Cloud integ summary", "/api/cloud-integrations/summary"),
    ("CLOUD SECURITY", "Cloud providers", "/api/cloud-integrations/providers"),
    ("CLOUD SECURITY", "Discovered assets", "/api/cloud-integrations/discovered-assets"),
    ("CLOUD SECURITY", "Cloud accounts", "/api/cloud-accounts"),
    ("CLOUD SECURITY", "Cloud remediation capabilities", "/api/cloud/remediation/capabilities"),
    ("CLOUD SECURITY", "Multicloud cost optimization", "/api/multicloud/cost-optimization"),

    ("PRIVACY (GDPR/CCPA)", "Privacy summary", "/api/privacy/summary"),
    ("PRIVACY (GDPR/CCPA)", "Privacy dashboard", "/api/privacy/dashboard"),
    ("PRIVACY (GDPR/CCPA)", "DSR list", "/api/privacy/dsr"),
    ("PRIVACY (GDPR/CCPA)", "Breach notifications", "/api/privacy/breaches"),
    ("PRIVACY (GDPR/CCPA)", "ROPA activities", "/api/privacy/processing-activities"),

    ("ZERO TRUST / PAM", "Device trust scores", "/api/zero-trust/device-trust-scores"),
    ("ZERO TRUST / PAM", "Session risks", "/api/zero-trust/session-risks"),
    ("ZERO TRUST / PAM", "PAM accounts", "/api/pam/accounts"),
    ("ZERO TRUST / PAM", "PAM sessions", "/api/pam/sessions"),
    ("ZERO TRUST / PAM", "PAM stats", "/api/pam/stats"),
    ("ZERO TRUST / PAM", "PAM vault", "/api/pam/vault"),
    ("ZERO TRUST / PAM", "PAM audit", "/api/pam/audit"),
    ("ZERO TRUST / PAM", "BAA agreements", "/api/baa"),
    ("ZERO TRUST / PAM", "BAA stats", "/api/baa/stats"),

    ("FINOPS / ANALYTICS", "AIOps capacity", "/api/aiops/capacity-predictions"),
    ("FINOPS / ANALYTICS", "Analytics BI", "/api/analytics/bi"),
    ("FINOPS / ANALYTICS", "Sustainability metrics", "/api/sustainability/metrics"),
    ("FINOPS / ANALYTICS", "Carbon footprint", "/api/sustainability/carbon-footprint"),
    ("FINOPS / ANALYTICS", "APM health", "/api/apm/health"),
    ("FINOPS / ANALYTICS", "APM endpoints", "/api/apm/endpoints"),
    ("FINOPS / ANALYTICS", "Tracing service map", "/api/tracing/service-map"),
    ("FINOPS / ANALYTICS", "DORA metrics", "/api/dora/metrics"),
    ("FINOPS / ANALYTICS", "Chaos experiments", "/api/chaos/experiments"),
    ("FINOPS / ANALYTICS", "AutoML studies", "/api/automl/studies"),

    ("REPORTS", "Executive summary", "/api/reports/executive-summary"),
    ("REPORTS", "Vulnerability exposure", "/api/reports/vulnerability-exposure"),
    ("REPORTS", "SLA compliance", "/api/reports/sla-compliance"),
    ("REPORTS", "Change management", "/api/reports/change-management"),
    ("REPORTS", "Scheduled reports", "/api/reports/scheduled"),
    ("REPORTS", "Report types", "/api/reports/scheduled/types"),

    ("SETTINGS & ADMIN", "LLM settings", "/api/settings/llm"),
    ("SETTINGS & ADMIN", "DB settings", "/api/settings/database"),
    ("SETTINGS & ADMIN", "Webhooks", "/api/webhooks"),
    ("SETTINGS & ADMIN", "Secrets list", "/api/secrets/list"),
    ("SETTINGS & ADMIN", "Retention policies", "/api/retention/policies"),
    ("SETTINGS & ADMIN", "Risks register", "/api/risks"),
    ("SETTINGS & ADMIN", "Vendors", "/api/vendors"),
    ("SETTINGS & ADMIN", "Trust center", "/api/trust-center/profile"),
    ("SETTINGS & ADMIN", "Training modules", "/api/training/modules"),
    ("SETTINGS & ADMIN", "XDR automated hunts", "/api/xdr/automated-hunts"),
    ("SETTINGS & ADMIN", "System health", "/api/system/health"),
    ("SETTINGS & ADMIN", "DR status", "/dr/status"),
    ("SETTINGS & ADMIN", "DR regions", "/dr/regions"),
]


def check(path):
    req = urllib.request.Request(BASE + path, headers={"Authorization": f"Bearer {TOKEN}"})
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            return r.status
    except urllib.error.HTTPError as e:
        return e.code
    except Exception:
        return 0


results = {}
last_section = None
ok_count = 0
fail_count = 0

print()
print("=" * 58)
print("  Enterprise Omni-Agent — Feature Status Report")
print(f"  Backend: {BASE}")
print("=" * 58)

for section, label, path in TESTS:
    if section != last_section:
        print(f"\n--- {section} ---")
        last_section = section
    status = check(path)
    ok = status == 200
    if ok:
        ok_count += 1
    else:
        fail_count += 1
    icon = "OK  " if ok else "FAIL"
    print(f"  [{icon}] {label:<40}  HTTP {status}")

total = ok_count + fail_count
print()
print("=" * 58)
print(f"  TOTAL: {total} endpoints   OK: {ok_count}   FAIL: {fail_count}")
print(f"  Pass rate: {ok_count/total*100:.1f}%")
print("=" * 58)
print()
