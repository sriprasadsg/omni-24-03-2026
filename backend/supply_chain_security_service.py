"""Supply Chain Security Service — SLSA levels, dependency vulnerabilities, provenance."""
from datetime import datetime, timezone
import hashlib
import json
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

# Each criterion maps to the minimum SLSA level it belongs to.
SLSA_CRITERIA = {
    "has_build_script":         (1, "Documented, scripted build process"),
    "build_service_used":       (2, "Build runs on a hosted CI/CD service (e.g. GitHub Actions)"),
    "source_control_integrity": (2, "Source hosted in version-controlled system with integrity checks"),
    "signed_artifact":          (2, "Artifact is cryptographically signed"),
    "reproducible_build":       (3, "Build is reproducible given the same inputs"),
    "ephemeral_environment":    (3, "Build runs in ephemeral, isolated environment"),
    "build_service_admin_free": (3, "Build service cannot be influenced by individual admins"),
    "two_party_review":         (4, "All source changes require two-party code review"),
    "hermetic_build":           (4, "Hermetic build — no network access or external deps during build"),
}


class SupplyChainSecurityService:
    def __init__(self, db):
        self.db = db
        self.col_artifacts = db["sc_artifacts"]
        self.col_vulns = db["sc_dependency_vulns"]
        self.col_provenance = db["sc_provenance"]
        self.col_policy = db["sc_slsa_policy"]

    # ── SLSA Assessment ──────────────────────────────────────────────────────

    @staticmethod
    def assess_slsa_level(build_info: dict) -> dict:
        """Score build_info flags against SLSA criteria; return level 0-4 + gaps."""
        met, gaps = [], []
        for key, (level, desc) in SLSA_CRITERIA.items():
            if build_info.get(key):
                met.append(key)
            else:
                gaps.append({"criterion": key, "required_for_level": level, "description": desc})

        # Highest level where all criteria at that level (and below) are satisfied
        achieved = 0
        for lv in range(1, 5):
            level_keys = [k for k, (l, _) in SLSA_CRITERIA.items() if l == lv]
            if all(k in met for k in level_keys):
                achieved = lv
            else:
                break

        next_level_gaps = [g for g in gaps if g["required_for_level"] == achieved + 1]
        return {
            "slsa_level": achieved,
            "slsa_name": SLSA_LEVELS[achieved]["name"],
            "slsa_color": SLSA_LEVELS[achieved]["color"],
            "met_criteria": met,
            "gaps": gaps,
            "recommendations": [g["description"] for g in next_level_gaps],
        }

    # ── Artifact Management ──────────────────────────────────────────────────

    async def get_artifacts(self, tenant_id: str, limit: int = 100):
        cursor = self.col_artifacts.find({"tenant_id": tenant_id}).sort("created_at", -1).limit(limit)
        return await cursor.to_list(length=limit)

    async def register_artifact(self, tenant_id: str, name: str, version: str,
                                ecosystem: str, build_info: dict) -> dict:
        assessment = self.assess_slsa_level(build_info)
        artifact = {
            "_id": str(uuid.uuid4()),
            "tenant_id": tenant_id,
            "name": name,
            "version": version,
            "ecosystem": ecosystem,
            "slsa_level": assessment["slsa_level"],
            "slsa_name": assessment["slsa_name"],
            "slsa_color": assessment["slsa_color"],
            "slsa_gaps": assessment["gaps"],
            "slsa_recommendations": assessment["recommendations"],
            "signed": build_info.get("signed_artifact", False),
            "provenance_available": assessment["slsa_level"] >= 1,
            "dependency_count": 0,
            "vuln_count": 0,
            "last_scanned": None,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        await self.col_artifacts.insert_one(artifact)
        artifact["id"] = artifact.pop("_id")
        return artifact

    # ── Dependency Vulnerability Scanning ────────────────────────────────────

    async def get_vulnerabilities(self, tenant_id: str, severity: str = None, limit: int = 100):
        q = {"tenant_id": tenant_id}
        if severity:
            q["severity"] = severity
        cursor = self.col_vulns.find(q).sort("cvss_score", -1).limit(limit)
        return await cursor.to_list(length=limit)

    async def scan_artifact_deps(self, artifact_id: str, packages: list, tenant_id: str) -> dict:
        """Run OSV + typosquatting scan for an artifact; store findings in sc_dependency_vulns."""
        from supply_chain_service import scan_package_list
        scan_result = await scan_package_list(packages, tenant_id)

        vuln_count = 0
        for finding in scan_result.get("findings", []):
            if finding["type"] == "OSV_VULNERABILITY":
                await self.col_vulns.insert_one({
                    "_id": str(uuid.uuid4()),
                    "tenant_id": tenant_id,
                    "artifact_id": artifact_id,
                    "artifact_name": artifact_id,
                    "package": finding["package"],
                    "package_version": finding.get("version", ""),
                    "cve_id": finding.get("vuln_id", ""),
                    "severity": finding.get("severity", "medium"),
                    "cvss_score": 7.0,
                    "fix_available": False,
                    "fix_version": "",
                    "status": "open",
                    "detected_at": datetime.now(timezone.utc).isoformat(),
                })
                vuln_count += 1

        await self.col_artifacts.update_one(
            {"_id": artifact_id, "tenant_id": tenant_id},
            {"$set": {
                "dependency_count": len(packages),
                "vuln_count": vuln_count,
                "last_scanned": datetime.now(timezone.utc).isoformat(),
            }}
        )
        return {**scan_result, "artifact_id": artifact_id, "vulnerabilities_stored": vuln_count}

    # ── Artifact Provenance ──────────────────────────────────────────────────

    async def generate_provenance(self, artifact_id: str, tenant_id: str, build_info: dict) -> dict | None:
        """Create a hash-chained SLSA provenance attestation for an artifact."""
        artifact = await self.col_artifacts.find_one({"_id": artifact_id, "tenant_id": tenant_id})
        if not artifact:
            return None

        subject = {"name": artifact["name"], "version": artifact["version"],
                   "ecosystem": artifact["ecosystem"]}
        subject_hash = hashlib.sha256(json.dumps(subject, sort_keys=True).encode()).hexdigest()

        existing = await self.col_provenance.find_one(
            {"artifact_id": artifact_id, "tenant_id": tenant_id},
            sort=[("created_at", -1)]
        )
        previous_hash = existing.get("provenance_hash") if existing else "0" * 64

        now = datetime.now(timezone.utc).isoformat()
        record = {
            "_id": str(uuid.uuid4()),
            "artifact_id": artifact_id,
            "tenant_id": tenant_id,
            "subject": subject,
            "subject_hash": subject_hash,
            "build_type": build_info.get("build_type", "https://github.com/actions/runner"),
            "builder_id": build_info.get("builder_id", ""),
            "build_config_uri": build_info.get("config_uri", ""),
            "invocation_id": build_info.get("invocation_id", str(uuid.uuid4())),
            "previous_hash": previous_hash,
            "slsa_level": artifact.get("slsa_level", 0),
            "created_at": now,
        }
        chain_input = f"{subject_hash}|{previous_hash}|{now}"
        record["provenance_hash"] = hashlib.sha256(chain_input.encode()).hexdigest()

        await self.col_provenance.insert_one(record)
        await self.col_artifacts.update_one(
            {"_id": artifact_id},
            {"$set": {"provenance_available": True,
                      "latest_provenance_hash": record["provenance_hash"]}}
        )
        record["id"] = record.pop("_id")
        return record

    async def get_provenance(self, artifact_id: str, tenant_id: str) -> list:
        cursor = self.col_provenance.find(
            {"artifact_id": artifact_id, "tenant_id": tenant_id}
        ).sort("created_at", -1).limit(20)
        docs = await cursor.to_list(length=20)
        for d in docs:
            d["id"] = d.pop("_id")
        return docs

    # ── SLSA Policy ──────────────────────────────────────────────────────────

    async def get_slsa_policy(self, tenant_id: str) -> dict:
        doc = await self.col_policy.find_one({"tenant_id": tenant_id})
        if not doc:
            return {"tenant_id": tenant_id, "min_slsa_level": 1, "enforce": False, "exceptions": []}
        doc.pop("_id", None)
        return doc

    async def set_slsa_policy(self, tenant_id: str, min_level: int,
                              enforce: bool, exceptions: list) -> dict:
        doc = {
            "tenant_id": tenant_id,
            "min_slsa_level": max(0, min(4, min_level)),
            "enforce": enforce,
            "exceptions": exceptions,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
        await self.col_policy.update_one({"tenant_id": tenant_id}, {"$set": doc}, upsert=True)
        return doc

    # ── Summary ──────────────────────────────────────────────────────────────

    async def get_summary(self, tenant_id: str):
        artifacts = await self.col_artifacts.count_documents({"tenant_id": tenant_id})
        critical_vulns = await self.col_vulns.count_documents(
            {"tenant_id": tenant_id, "severity": "critical", "status": "open"})
        high_vulns = await self.col_vulns.count_documents(
            {"tenant_id": tenant_id, "severity": "high", "status": "open"})
        slsa_4 = await self.col_artifacts.count_documents({"tenant_id": tenant_id, "slsa_level": 4})
        provenance_count = await self.col_provenance.count_documents({"tenant_id": tenant_id})
        policy = await self.get_slsa_policy(tenant_id)
        return {
            "artifacts": artifacts,
            "critical_vulns": critical_vulns,
            "high_vulns": high_vulns,
            "slsa_4_compliant": slsa_4,
            "provenance_records": provenance_count,
            "policy": policy,
        }

    # ── Demo Seed ────────────────────────────────────────────────────────────

    async def seed_demo(self, tenant_id: str):
        await self.col_artifacts.delete_many({"tenant_id": tenant_id})
        await self.col_vulns.delete_many({"tenant_id": tenant_id})
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
                "name": name, "version": version, "ecosystem": ecosystem,
                "slsa_level": slsa, "slsa_name": SLSA_LEVELS[slsa]["name"],
                "slsa_color": SLSA_LEVELS[slsa]["color"],
                "signed": slsa >= 2, "provenance_available": slsa >= 1,
                "dependency_count": len(vulns) * 15 + 20, "vuln_count": len(vulns),
                "last_scanned": datetime.now(timezone.utc).isoformat(),
                "created_at": datetime.now(timezone.utc).isoformat(),
            }
            await self.col_artifacts.insert_one(artifact)
            for pkg, pkg_ver, cve, sev, cvss, fix_avail, fix_ver, status in vulns:
                await self.col_vulns.insert_one({
                    "_id": str(uuid.uuid4()), "tenant_id": tenant_id,
                    "artifact_id": artifact["_id"], "artifact_name": name,
                    "package": pkg, "package_version": pkg_ver, "cve_id": cve,
                    "severity": sev, "cvss_score": cvss, "fix_available": fix_avail,
                    "fix_version": fix_ver, "status": status,
                    "detected_at": datetime.now(timezone.utc).isoformat(),
                })
