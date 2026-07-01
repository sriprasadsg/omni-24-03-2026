"""Cloud Security Checks Engine — Prowler-style checks for AWS, Azure, GCP.
Combines per-provider check definitions into a single CLOUD_CHECKS list.
"""
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
import uuid
from auth_roles import SUPER_AND_ADMIN_ROLES as _CC_SUPER_ROLES

from cloud_checks_aws import AWS_CHECKS
from cloud_checks_azure import AZURE_CHECKS
from cloud_checks_gcp import GCP_CHECKS
from cloud_checks_k8s import K8S_CHECKS

# DigitalOcean checks
DO_CHECKS: List[Dict[str, Any]] = [
    {"id": "do-fw-001", "name": "DO Firewall Rules Restrict SSH", "description": "Droplet firewall should restrict SSH to trusted IPs", "provider": "digitalocean", "service": "firewall", "severity": "critical", "frameworks": ["NIST-SC-7", "PCI-1.2.1"], "remediation": "Restrict SSH inbound rules to trusted IPs in DO Cloud Firewall."},
    {"id": "do-fw-002", "name": "DO Firewall Rules Restrict RDP", "description": "Droplet firewall should restrict RDP to trusted IPs", "provider": "digitalocean", "service": "firewall", "severity": "critical", "frameworks": ["NIST-SC-7", "PCI-1.2.1"], "remediation": "Restrict RDP inbound rules to trusted IPs in DO Cloud Firewall."},
    {"id": "do-db-001", "name": "DO Managed Database Encryption at Rest", "description": "DO managed databases should have encryption at rest enabled", "provider": "digitalocean", "service": "database", "severity": "high", "frameworks": ["NIST-SC-28", "PCI-3.4"], "remediation": "Enable encryption at rest on DO managed database clusters."},
    {"id": "do-db-002", "name": "DO Managed Database Backups Enabled", "description": "DO managed databases should have automated backups enabled", "provider": "digitalocean", "service": "database", "severity": "medium", "frameworks": ["NIST-CP-9"], "remediation": "Enable automated daily backups on DO managed database clusters."},
    {"id": "do-spaces-001", "name": "DO Spaces Bucket Public Access Disabled", "description": "DO Spaces buckets must not allow public read access", "provider": "digitalocean", "service": "spaces", "severity": "critical", "frameworks": ["NIST-SC-7", "SOC2-CC6.6"], "remediation": "Disable public read access on DO Spaces buckets."},
    {"id": "do-lb-001", "name": "DO Load Balancer SSL Enabled", "description": "DO load balancers should terminate SSL with a valid certificate", "provider": "digitalocean", "service": "loadbalancer", "severity": "high", "frameworks": ["NIST-SC-8", "PCI-4.1"], "remediation": "Configure SSL termination with valid certificate on DO load balancers."},
    {"id": "do-droplet-001", "name": "DO Droplet Monitoring Enabled", "description": "DO Droplets should have monitoring enabled", "provider": "digitalocean", "service": "droplet", "severity": "medium", "frameworks": ["NIST-CA-7"], "remediation": "Enable monitoring agent on all DO droplets."},
    {"id": "do-vpc-001", "name": "DO VPC Network Isolation", "description": "DO resources should be deployed within a VPC for network isolation", "provider": "digitalocean", "service": "vpc", "severity": "high", "frameworks": ["NIST-SC-7", "SOC2-CC6.6"], "remediation": "Deploy DO resources within a VPC network."},
    {"id": "do-k8s-001", "name": "DO Kubernetes Auto-Upgrade Enabled", "description": "DO Kubernetes clusters should have auto-upgrade enabled", "provider": "digitalocean", "service": "kubernetes", "severity": "medium", "frameworks": ["NIST-SI-2"], "remediation": "Enable auto-upgrade on DO Kubernetes node pools."},
    {"id": "do-app-001", "name": "DO App Platform Enforces HTTPS", "description": "DO App Platform apps should enforce HTTPS redirect", "provider": "digitalocean", "service": "appplatform", "severity": "high", "frameworks": ["NIST-SC-8", "PCI-4.1"], "remediation": "Enable HTTPS redirect on DO App Platform apps."},
]

# Combined check list: AWS (~145) + Azure (~80) + GCP (~75) + K8s (~20) + DO (~10) = ~330 checks
CLOUD_CHECKS: List[Dict[str, Any]] = AWS_CHECKS + AZURE_CHECKS + GCP_CHECKS + K8S_CHECKS + DO_CHECKS

_CHECKS_BY_ID: Dict[str, Dict] = {c["id"]: c for c in CLOUD_CHECKS}


class CloudChecksService:
    def _db(self):
        from database import get_database
        return get_database()

    def list_checks(self, provider: Optional[str] = None, service: Optional[str] = None, severity: Optional[str] = None) -> List[Dict]:
        checks = CLOUD_CHECKS
        if provider:
            checks = [c for c in checks if c["provider"] == provider]
        if service:
            checks = [c for c in checks if c["service"] == service]
        if severity:
            checks = [c for c in checks if c["severity"] == severity]
        return checks

    async def get_results(self, tenant_id: Optional[str], role: str, provider: Optional[str] = None, account_id: Optional[str] = None) -> List[Dict]:
        db = self._db()
        query: Dict[str, Any] = {} if role in _CC_SUPER_ROLES else {"tenantId": tenant_id}
        if provider:
            query["provider"] = provider
        if account_id:
            query["accountId"] = account_id
        return await db.cloud_check_results.find(query, {"_id": 0}).sort("checked_at", -1).to_list(length=5000)

    async def run_checks(self, account_id: str, provider: str, tenant_id: str, credentials_hint: Optional[str] = None) -> Dict:
        """Evaluate checks against the account's imported findings from native scanners."""
        db = self._db()
        account = await db.cloud_accounts.find_one({"id": account_id, "tenantId": tenant_id}, {"_id": 0})
        if not account:
            return {"error": "Cloud account not found", "ran": 0}

        findings_raw = await db.cloud_findings.find(
            {"accountId": account_id, "tenantId": tenant_id}, {"_id": 0}
        ).to_list(length=10000)
        finding_titles = {f.get("title", "").lower() for f in findings_raw}
        failing_ids = {f.get("checkId", "").lower() for f in findings_raw if f.get("severity") in ("critical", "high", "medium")}

        now = datetime.now(timezone.utc).isoformat()
        upserted = 0
        provider_checks = [c for c in CLOUD_CHECKS if c["provider"] == provider]
        for check in provider_checks:
            cid = check["id"]
            name_lower = check["name"].lower()
            in_findings = cid.lower() in failing_ids or any(
                kw in title for title in finding_titles for kw in name_lower.split()[:3] if len(kw) > 3
            )
            result = "FAIL" if in_findings else "PASS"
            doc = {
                "id": f"ccr-{uuid.uuid4().hex}",
                "tenantId": tenant_id,
                "accountId": account_id,
                "provider": provider,
                "checkId": cid,
                "checkName": check["name"],
                "service": check["service"],
                "severity": check["severity"],
                "result": result,
                "frameworks": check["frameworks"],
                "remediation": check["remediation"],
                "detail": "Based on imported findings from native cloud scanner." if in_findings else "No matching findings found.",
                "checked_at": now,
            }
            await db.cloud_check_results.update_one(
                {"tenantId": tenant_id, "accountId": account_id, "checkId": cid},
                {"$set": doc},
                upsert=True,
            )
            upserted += 1
        return {"ran": upserted, "accountId": account_id, "provider": provider, "checked_at": now}

    async def get_summary(self, tenant_id: Optional[str], role: str, account_id: Optional[str] = None) -> Dict:
        results = await self.get_results(tenant_id, role, account_id=account_id)
        if not results:
            total_checks = len(CLOUD_CHECKS)
            return {"total": total_checks, "pass": 0, "fail": 0, "bySeverity": {}, "byProvider": {}, "byService": {}, "coverage": 0}
        total = len(results)
        passed = sum(1 for r in results if r.get("result") == "PASS")
        failed = sum(1 for r in results if r.get("result") == "FAIL")
        by_sev: Dict[str, int] = {}
        by_prov: Dict[str, Dict] = {}
        by_svc: Dict[str, int] = {}
        for r in results:
            sev = r.get("severity", "unknown")
            if r.get("result") == "FAIL":
                by_sev[sev] = by_sev.get(sev, 0) + 1
            prov = r.get("provider", "unknown")
            if prov not in by_prov:
                by_prov[prov] = {"pass": 0, "fail": 0}
            by_prov[prov][r.get("result", "FAIL").lower()] = by_prov[prov].get(r.get("result", "FAIL").lower(), 0) + 1
            svc = r.get("service", "unknown")
            if r.get("result") == "FAIL":
                by_svc[svc] = by_svc.get(svc, 0) + 1
        return {
            "total": total,
            "pass": passed,
            "fail": failed,
            "passPct": round(passed / max(total, 1) * 100),
            "bySeverity": by_sev,
            "byProvider": by_prov,
            "byService": by_svc,
            "coverage": round(total / len(CLOUD_CHECKS) * 100),
        }


cloud_checks_service = CloudChecksService()
