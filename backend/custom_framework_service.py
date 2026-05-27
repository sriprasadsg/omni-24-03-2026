"""
Custom Compliance Framework Service
Allows organizations to build, version, and manage their own compliance frameworks
with custom controls mapped to evidence sources and agent capabilities.
"""

import uuid
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from database import get_database

logger = logging.getLogger(__name__)

# ── Built-in template scaffolds ────────────────────────────────────────────────

BUILTIN_TEMPLATES = {
    "blank": {
        "name": "Blank Framework",
        "description": "Start from scratch with no pre-defined controls",
        "domains": [],
    },
    "internal_security_policy": {
        "name": "Internal Security Policy",
        "description": "Template for organizational internal security policies",
        "domains": [
            {
                "id": "access_control",
                "name": "Access Control",
                "controls": [
                    {"id": "AC-1", "name": "Password Policy", "description": "All accounts must use strong passwords", "evidence_sources": ["log_shipper", "compliance_evidence_collector"]},
                    {"id": "AC-2", "name": "MFA Enforcement", "description": "Multi-factor authentication required for privileged accounts", "evidence_sources": ["compliance_evidence_collector"]},
                    {"id": "AC-3", "name": "Least Privilege", "description": "Users granted minimum necessary permissions", "evidence_sources": ["compliance_evidence_collector"]},
                ],
            },
            {
                "id": "incident_response",
                "name": "Incident Response",
                "controls": [
                    {"id": "IR-1", "name": "Incident Detection", "description": "Security incidents detected within 24 hours", "evidence_sources": ["log_shipper", "runtime_security"]},
                    {"id": "IR-2", "name": "Incident Response Plan", "description": "Documented IR plan reviewed annually", "evidence_sources": []},
                ],
            },
            {
                "id": "asset_management",
                "name": "Asset Management",
                "controls": [
                    {"id": "AM-1", "name": "Asset Inventory", "description": "All assets inventoried and classified", "evidence_sources": ["network_discovery", "process_monitor"]},
                    {"id": "AM-2", "name": "Software Inventory", "description": "All installed software catalogued", "evidence_sources": ["software_management"]},
                ],
            },
        ],
    },
    "cyber_insurance": {
        "name": "Cyber Insurance Readiness",
        "description": "Controls commonly required by cyber insurance providers",
        "domains": [
            {
                "id": "mfa",
                "name": "Multi-Factor Authentication",
                "controls": [
                    {"id": "CI-MFA-1", "name": "MFA on Remote Access", "description": "MFA required for all remote access (VPN, RDP)", "evidence_sources": ["compliance_evidence_collector"]},
                    {"id": "CI-MFA-2", "name": "MFA on Email", "description": "MFA required for all email accounts", "evidence_sources": []},
                    {"id": "CI-MFA-3", "name": "MFA on Admin Accounts", "description": "MFA required for all privileged accounts", "evidence_sources": ["compliance_evidence_collector"]},
                ],
            },
            {
                "id": "backups",
                "name": "Backup and Recovery",
                "controls": [
                    {"id": "CI-BK-1", "name": "Regular Backups", "description": "Data backed up daily with offsite copy", "evidence_sources": ["backup_verifier"]},
                    {"id": "CI-BK-2", "name": "Immutable Backups", "description": "Backups protected from ransomware modification", "evidence_sources": ["backup_verifier"]},
                    {"id": "CI-BK-3", "name": "Recovery Testing", "description": "Backup restoration tested quarterly", "evidence_sources": ["backup_verifier"]},
                ],
            },
            {
                "id": "patching",
                "name": "Patch Management",
                "controls": [
                    {"id": "CI-PM-1", "name": "Critical Patch SLA", "description": "Critical patches applied within 30 days", "evidence_sources": ["software_management"]},
                    {"id": "CI-PM-2", "name": "EOL Software", "description": "No end-of-life software in production", "evidence_sources": ["software_management"]},
                ],
            },
        ],
    },
}


async def create_framework(tenant_id: str, created_by: str, data: Dict[str, Any]) -> Dict[str, Any]:
    db = get_database()

    template_id = data.get("template_id", "blank")
    template = BUILTIN_TEMPLATES.get(template_id, BUILTIN_TEMPLATES["blank"])

    framework = {
        "id": str(uuid.uuid4()),
        "tenant_id": tenant_id,
        "name": data.get("name", template["name"]),
        "description": data.get("description", template.get("description", "")),
        "version": "1.0",
        "status": "draft",
        "domains": data.get("domains", template.get("domains", [])),
        "tags": data.get("tags", []),
        "created_by": created_by,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "published_at": None,
        "control_count": 0,
        "passing_controls": 0,
        "compliance_score": 0.0,
    }

    # Count total controls across domains
    total = sum(len(d.get("controls", [])) for d in framework["domains"])
    framework["control_count"] = total

    await db.custom_frameworks.insert_one(framework)
    logger.info("[CustomFramework] Created framework '%s' for tenant %s", framework["name"], tenant_id)
    return framework


async def get_framework(framework_id: str, tenant_id: str, role: str) -> Optional[Dict[str, Any]]:
    db = get_database()
    query = {"id": framework_id}
    if role != "super_admin":
        query["tenant_id"] = tenant_id
    fw = await db.custom_frameworks.find_one(query)
    if fw:
        fw["_id"] = str(fw["_id"])
    return fw


async def list_frameworks(tenant_id: str, role: str) -> List[Dict[str, Any]]:
    db = get_database()
    query = {} if role == "super_admin" else {"tenant_id": tenant_id}
    frameworks = await db.custom_frameworks.find(query).sort("created_at", -1).to_list(length=200)
    for fw in frameworks:
        fw["_id"] = str(fw["_id"])
    return frameworks


async def update_framework(framework_id: str, tenant_id: str, role: str, data: Dict[str, Any]) -> bool:
    db = get_database()
    query = {"id": framework_id}
    if role != "super_admin":
        query["tenant_id"] = tenant_id

    fw = await db.custom_frameworks.find_one(query)
    if not fw:
        return False

    update = {"updated_at": datetime.now(timezone.utc).isoformat()}
    for field in ("name", "description", "domains", "tags", "status"):
        if field in data:
            update[field] = data[field]

    if "domains" in data:
        total = sum(len(d.get("controls", [])) for d in data["domains"])
        update["control_count"] = total

    if data.get("status") == "published" and not fw.get("published_at"):
        update["published_at"] = datetime.now(timezone.utc).isoformat()

    await db.custom_frameworks.update_one(query, {"$set": update})
    return True


async def add_domain(framework_id: str, tenant_id: str, role: str, domain: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    db = get_database()
    query = {"id": framework_id}
    if role != "super_admin":
        query["tenant_id"] = tenant_id

    fw = await db.custom_frameworks.find_one(query)
    if not fw:
        return None

    domain_id = domain.get("id", str(uuid.uuid4())[:8])
    new_domain = {
        "id": domain_id,
        "name": domain.get("name", "New Domain"),
        "description": domain.get("description", ""),
        "controls": domain.get("controls", []),
    }

    domains = fw.get("domains", [])
    domains.append(new_domain)
    total = sum(len(d.get("controls", [])) for d in domains)

    await db.custom_frameworks.update_one(
        {"id": framework_id},
        {"$set": {"domains": domains, "control_count": total, "updated_at": datetime.now(timezone.utc).isoformat()}},
    )
    return new_domain


async def add_control(
    framework_id: str, domain_id: str, tenant_id: str, role: str, control: Dict[str, Any]
) -> Optional[Dict[str, Any]]:
    db = get_database()
    query = {"id": framework_id}
    if role != "super_admin":
        query["tenant_id"] = tenant_id

    fw = await db.custom_frameworks.find_one(query)
    if not fw:
        return None

    domains = fw.get("domains", [])
    target_domain = next((d for d in domains if d["id"] == domain_id), None)
    if not target_domain:
        return None

    new_control = {
        "id": control.get("id", f"CTRL-{str(uuid.uuid4())[:6].upper()}"),
        "name": control.get("name", "New Control"),
        "description": control.get("description", ""),
        "evidence_sources": control.get("evidence_sources", []),
        "guidance": control.get("guidance", ""),
        "severity": control.get("severity", "medium"),
        "automated": control.get("automated", False),
        "status": "not_assessed",
    }

    target_domain["controls"].append(new_control)
    total = sum(len(d.get("controls", [])) for d in domains)

    await db.custom_frameworks.update_one(
        {"id": framework_id},
        {"$set": {"domains": domains, "control_count": total, "updated_at": datetime.now(timezone.utc).isoformat()}},
    )
    return new_control


async def evaluate_framework_compliance(framework_id: str, tenant_id: str, role: str) -> Dict[str, Any]:
    """
    Auto-evaluate controls that have evidence_sources mapped to agent capabilities.
    Returns per-domain and overall compliance scores.
    """
    db = get_database()
    query = {"id": framework_id}
    if role != "super_admin":
        query["tenant_id"] = tenant_id

    fw = await db.custom_frameworks.find_one(query)
    if not fw:
        return {}

    # Get latest compliance evidence from agent
    evidence = await db.compliance_evidence.find_one(
        {"tenant_id": fw["tenant_id"]}, sort=[("collected_at", -1)]
    )

    available_sources = set()
    if evidence:
        for k, v in evidence.get("data", {}).items():
            if v and v.get("status") not in ("error", "unavailable"):
                available_sources.add(k)

    total_controls = 0
    passing = 0
    domain_scores = []

    for domain in fw.get("domains", []):
        d_total = len(domain.get("controls", []))
        d_pass = 0
        for ctrl in domain.get("controls", []):
            sources = ctrl.get("evidence_sources", [])
            if not sources:
                # Manual control — cannot auto-assess
                pass
            else:
                covered = all(s in available_sources for s in sources)
                if covered:
                    d_pass += 1
        total_controls += d_total
        passing += d_pass
        domain_scores.append({
            "domain_id": domain["id"],
            "domain_name": domain["name"],
            "total": d_total,
            "passing": d_pass,
            "score": round((d_pass / d_total * 100) if d_total else 0, 1),
        })

    overall_score = round((passing / total_controls * 100) if total_controls else 0, 1)

    await db.custom_frameworks.update_one(
        {"id": framework_id},
        {"$set": {
            "passing_controls": passing,
            "compliance_score": overall_score,
            "last_evaluated": datetime.now(timezone.utc).isoformat(),
        }},
    )

    return {
        "framework_id": framework_id,
        "overall_score": overall_score,
        "total_controls": total_controls,
        "passing_controls": passing,
        "domain_scores": domain_scores,
        "evaluated_at": datetime.now(timezone.utc).isoformat(),
    }


async def delete_framework(framework_id: str, tenant_id: str, role: str) -> bool:
    db = get_database()
    query = {"id": framework_id}
    if role != "super_admin":
        query["tenant_id"] = tenant_id
    result = await db.custom_frameworks.delete_one(query)
    return result.deleted_count > 0
