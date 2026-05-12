"""Supply Chain Security Service — SLSA levels, dependency vulnerabilities, provenance."""
from datetime import datetime
import uuid


SLSA_LEVELS = {
    0: {"name": "SLSA 0", "description": "No guarantees", "color": "red"},
    1: {"name": "SLSA 1", "description": "Documented build process", "color": "orange"},
    2: {"name": "SLSA 2", "description": "Tamper-resistant build service", "color": "yellow"},
    3: {"name": "SLSA 3", "description": "Hardened build, auditable", "color": "blue"},
    4: {"name": "SLSA 4", "description": "Two-party review, hermetic builds", "color": "green"},
}

ECOSYSTEMS = ["npm", "pypi", "maven", "go", "nuget", "cargo", "rubygems"]
VULN_SEVERITIES = ["critical", "high", "medium", "low"]


class SupplyChainSecurityService:
    def __init__(self, db):
        self.db = db
        self.col_artifacts = db["sc_artifacts"]
        self.col_vulns = db["sc_dependency_vulns"]
        self.col_provenance = db["sc_provenance"]

    async def get_artifacts(self, tenant_id: str, limit: int = 100):
        cursor = self.col_artifacts.find({"tenant_id": tenant_id}).sort("created_at", -1).limit(limit)
        return await cursor.to_list(length=limit)

    async def get_vulnerabilities(self, tenant_id: str, severity: str = None, limit: int = 100):
        q = {"tenant_id": tenant_id}
        if severity:
            q["severity"] = severity
        cursor = self.col_vulns.find(q).sort("cvss_score", -1).limit(limit)
        return await cursor.to_list(length=limit)

    async def get_summary(self, tenant_id: str):
        artifacts = await self.col_artifacts.count_documents({"tenant_id": tenant_id})
        critical_vulns = await self.col_vulns.count_documents({"tenant_id": tenant_id, "severity": "critical", "status": "open"})
        high_vulns = await self.col_vulns.count_documents({"tenant_id": tenant_id, "severity": "high", "status": "open"})
        slsa_4 = await self.col_artifacts.count_documents({"tenant_id": tenant_id, "slsa_level": 4})
        return {"artifacts": artifacts, "critical_vulns": critical_vulns,
                "high_vulns": high_vulns, "slsa_4_compliant": slsa_4}

    async def seed_demo(self, tenant_id: str):
        await self.col_artifacts.delete_many({"tenant_id": tenant_id})
        await self.col_vulns.delete_many({"tenant_id": tenant_id})
        # Deterministic seed data — varied by index, not random
        artifact_defs = [
            ("backend-api",   "pypi",    3, "2.4.1",  [("requests", "2.28.0",  "CVE-2023-32681", "high",     7.5, True,  "2.31.0", "open"),
                                                        ("urllib3",  "1.26.14", "CVE-2023-43804", "medium",   5.9, True,  "1.26.18","open")]),
            ("frontend-app",  "npm",     2, "3.1.0",  [("lodash",   "4.17.20", "CVE-2021-23337", "high",     7.2, True,  "4.17.21","open"),
                                                        ("axios",    "0.21.1",  "CVE-2021-3749",  "medium",   6.1, True,  "0.21.4", "in_progress")]),
            ("agent-daemon",  "go",      4, "1.8.3",  []),
            ("ml-service",    "pypi",    1, "1.2.0",  [("numpy",    "1.23.0",  "CVE-2021-41495", "medium",   5.3, True,  "1.24.0", "open"),
                                                        ("pillow",   "9.0.0",   "CVE-2022-22815", "medium",   5.0, True,  "9.0.1",  "open"),
                                                        ("torch",    "1.13.0",  "CVE-2022-45907", "critical", 9.8, False, "",       "open")]),
            ("auth-service",  "npm",     3, "4.0.2",  [("jsonwebtoken","8.5.1","CVE-2022-23529", "high",     7.6, True,  "9.0.0",  "open")]),
            ("data-pipeline", "pypi",    0, "0.9.7",  [("cryptography","38.0.0","CVE-2023-0286", "high",     7.4, True,  "39.0.1", "open"),
                                                        ("paramiko",  "2.11.0", "CVE-2023-48795", "medium",   5.9, True,  "3.4.0",  "in_progress"),
                                                        ("PyYAML",   "5.4.1",   "CVE-2020-14343", "critical", 9.8, True,  "6.0",    "open")]),
        ]
        for name, ecosystem, slsa, version, vulns in artifact_defs:
            artifact = {
                "_id": str(uuid.uuid4()), "tenant_id": tenant_id,
                "name": name, "version": version,
                "ecosystem": ecosystem,
                "slsa_level": slsa,
                "slsa_name": SLSA_LEVELS[slsa]["name"],
                "signed": slsa >= 2,
                "provenance_available": slsa >= 1,
                "dependency_count": len(vulns) * 15 + 20,
                "vuln_count": len(vulns),
                "last_scanned": datetime.now(timezone.utc).isoformat(),
                "created_at": datetime.now(timezone.utc).isoformat(),
            }
            await self.col_artifacts.insert_one(artifact)
            for pkg, pkg_ver, cve, sev, cvss, fix_avail, fix_ver, status in vulns:
                await self.col_vulns.insert_one({
                    "_id": str(uuid.uuid4()), "tenant_id": tenant_id,
                    "artifact_id": artifact["_id"], "artifact_name": name,
                    "package": pkg,
                    "package_version": pkg_ver,
                    "cve_id": cve,
                    "severity": sev,
                    "cvss_score": cvss,
                    "fix_available": fix_avail,
                    "fix_version": fix_ver,
                    "status": status,
                    "detected_at": datetime.now(timezone.utc).isoformat(),
                })
