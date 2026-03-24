"""
Supply Chain Detection Service
-------------------------------
Detects dependency confusion, typosquatting, and OSV database matches.
"""

import re
import uuid
import json
import hashlib
from datetime import datetime, timezone
from database import get_database

# Known legitimate internal package name patterns (customize per org)
INTERNAL_PACKAGE_PATTERNS = [
    r"^@myorg/",
    r"^internal-",
    r"^company-",
]

# Commonly typosquatted packages
KNOWN_CRITICAL_PACKAGES = {
    "requests", "flask", "django", "numpy", "pandas", "boto3", "sqlalchemy",
    "fastapi", "uvicorn", "pydantic", "react", "lodash", "express", "axios",
    "webpack", "babel", "typescript", "eslint", "pytest", "setuptools",
}


def levenshtein(s1: str, s2: str) -> int:
    """Compute Levenshtein edit distance between two strings."""
    if len(s1) < len(s2):
        return levenshtein(s2, s1)
    if len(s2) == 0:
        return len(s1)
    prev = list(range(len(s2) + 1))
    for i, c1 in enumerate(s1):
        curr = [i + 1]
        for j, c2 in enumerate(s2):
            curr.append(min(prev[j + 1] + 1, curr[j] + 1, prev[j] + (c1 != c2)))
        prev = curr
    return prev[-1]


def check_typosquatting(package_name: str) -> list[dict]:
    """Check if a package name looks suspiciously close to a well-known package."""
    name_clean = package_name.lower().replace("-", "").replace("_", "")
    findings = []
    for known in KNOWN_CRITICAL_PACKAGES:
        known_clean = known.lower().replace("-", "").replace("_", "")
        dist = levenshtein(name_clean, known_clean)
        if 0 < dist <= 2 and name_clean != known_clean:
            findings.append({
                "type": "TYPOSQUATTING",
                "package": package_name,
                "similar_to": known,
                "edit_distance": dist,
                "severity": "high",
                "description": f"Package '{package_name}' is very similar to '{known}' (edit distance: {dist}). Possible typosquatting.",
            })
    return findings


def check_dependency_confusion(package_name: str, is_internal: bool = False) -> list[dict]:
    """
    Detect potential dependency confusion: internal package name exists on public registry.
    If is_internal=True, flag if the name could be claimed on PyPI/npm.
    """
    findings = []
    is_internal_pattern = any(re.match(p, package_name) for p in INTERNAL_PACKAGE_PATTERNS)
    # Simple heuristic: internal-sounding names that aren't scoped
    if is_internal or is_internal_pattern:
        if not package_name.startswith("@"):
            findings.append({
                "type": "DEPENDENCY_CONFUSION",
                "package": package_name,
                "severity": "critical",
                "description": f"Internal package '{package_name}' appears un-scoped — attacker could claim this name on PyPI/npm. Use scoped packages (e.g. @{package_name.split('/')[0]}/...) or ensure the name is reserved on public registries.",
            })
    return findings


async def scan_package_list(packages: list[dict], tenant_id: str) -> dict:
    """
    Scan a list of { name, version, ecosystem } packages for supply chain risks.
    """
    all_findings = []
    osv_matches = []

    for pkg in packages:
        name = pkg.get("name", "")
        version = pkg.get("version", "")
        ecosystem = pkg.get("ecosystem", "PyPI")

        # Typosquatting check
        all_findings.extend(check_typosquatting(name))

        # Dependency confusion check
        all_findings.extend(check_dependency_confusion(name, is_internal=pkg.get("is_internal", False)))

        # OSV lookup (async HTTP)
        try:
            import httpx
            async with httpx.AsyncClient(timeout=5) as client:
                payload = {"package": {"name": name, "ecosystem": ecosystem}}
                if version:
                    payload["version"] = version
                resp = await client.post("https://api.osv.dev/v1/query", json=payload)
                if resp.status_code == 200:
                    vulns = resp.json().get("vulns", [])
                    for v in vulns[:3]:  # Limit to 3 per package
                        osv_matches.append({
                            "type": "OSV_VULNERABILITY",
                            "package": name,
                            "version": version,
                            "vuln_id": v.get("id"),
                            "severity": "high",
                            "summary": v.get("summary", ""),
                            "description": f"OSV vulnerability {v.get('id')} found in {name}@{version}: {v.get('summary', '')}",
                        })
        except Exception:
            pass  # OSV API unavailable

    scan_id = str(uuid.uuid4())
    all_findings.extend(osv_matches)
    doc = {
        "scan_id": scan_id,
        "tenant_id": tenant_id,
        "packages_scanned": len(packages),
        "findings": all_findings,
        "finding_count": len(all_findings),
        "scanned_at": datetime.now(timezone.utc).isoformat(),
    }
    if all_findings:
        db = get_database()
        await db.supply_chain_findings.insert_one(doc)

    doc.pop("_id", None)
    return doc


async def list_findings(tenant_id: str, limit: int = 100) -> list:
    db = get_database()
    docs = await db.supply_chain_findings.find({"tenant_id": tenant_id}).sort("scanned_at", -1).limit(limit).to_list(limit)
    for d in docs:
        d["_id"] = str(d["_id"])
    return docs
