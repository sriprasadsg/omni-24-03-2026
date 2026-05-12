"""
Knowledge Base Endpoints
Ingest content and answer queries using MongoDB full-text search + AI summarization.
Replaces the broken prompt_service import with a self-contained implementation.
"""

from fastapi import APIRouter, HTTPException, Depends, Body
from typing import List, Dict, Any
from datetime import datetime, timezone
import uuid

from database import get_database
from authentication_service import get_current_user
from auth_types import TokenData
from rbac_service import rbac_service

router = APIRouter(prefix="/api/knowledge", tags=["Knowledge Base"])

_SEED_DOCS = [
    {
        "title": "MITRE ATT&CK Framework Overview",
        "content": (
            "The MITRE ATT&CK framework is a globally-accessible knowledge base of adversary tactics and techniques "
            "based on real-world observations. It is organized into 14 tactics: Reconnaissance, Resource Development, "
            "Initial Access, Execution, Persistence, Privilege Escalation, Defense Evasion, Credential Access, "
            "Discovery, Lateral Movement, Collection, Command and Control, Exfiltration, and Impact. "
            "Each tactic contains multiple techniques and sub-techniques with detection and mitigation guidance."
        ),
        "tags": ["mitre", "attack", "framework", "tactics", "techniques"],
        "source": "platform_seed",
    },
    {
        "title": "Incident Response Playbook: Ransomware",
        "content": (
            "1. Isolate: Immediately quarantine affected hosts by disabling network interfaces or using endpoint isolation. "
            "2. Identify: Determine the ransomware family, affected systems, and encryption scope using file extension analysis. "
            "3. Contain: Block lateral movement by disabling SMB, RDP and shared drives. Remove attacker persistence mechanisms. "
            "4. Eradicate: Deploy AV/EDR tools to remove the ransomware payload. Patch exploited vulnerabilities. "
            "5. Recover: Restore from clean backups after confirming no re-infection. Test restored systems before production. "
            "6. Post-Incident: Conduct root cause analysis, update detection rules, and brief stakeholders."
        ),
        "tags": ["ransomware", "incident-response", "playbook", "containment"],
        "source": "platform_seed",
    },
    {
        "title": "OWASP Top 10 Web Application Vulnerabilities",
        "content": (
            "A01 Broken Access Control — Users can act outside their intended permissions. "
            "A02 Cryptographic Failures — Sensitive data exposed due to weak encryption or missing TLS. "
            "A03 Injection — SQL, NoSQL, OS, LDAP injection via untrusted data sent to an interpreter. "
            "A04 Insecure Design — Missing security controls by design rather than implementation flaws. "
            "A05 Security Misconfiguration — Default configs, open cloud storage, verbose errors. "
            "A06 Vulnerable Components — Libraries and frameworks with known CVEs. "
            "A07 Authentication Failures — Brute force, weak passwords, missing MFA. "
            "A08 Software & Data Integrity Failures — Unsigned updates, insecure CI/CD pipelines. "
            "A09 Security Logging Failures — Insufficient logging prevents detection. "
            "A10 SSRF — Server-side request forgery allows fetching internal resources."
        ),
        "tags": ["owasp", "web-security", "vulnerabilities", "top10"],
        "source": "platform_seed",
    },
    {
        "title": "Zero Trust Architecture Principles",
        "content": (
            "Zero Trust is a security model based on 'never trust, always verify'. Core principles: "
            "1. Verify explicitly — always authenticate and authorize based on all available data points. "
            "2. Least privilege access — limit user access with just-in-time and just-enough-access. "
            "3. Assume breach — minimize blast radius, segment access, verify end-to-end encryption. "
            "Key pillars: Identity, Devices, Applications, Data, Infrastructure, Networks. "
            "Microsegmentation divides the network into secure zones to limit lateral movement. "
            "Continuous validation replaces the traditional perimeter-based security model."
        ),
        "tags": ["zero-trust", "architecture", "identity", "microsegmentation"],
        "source": "platform_seed",
    },
    {
        "title": "GDPR & CCPA Compliance Quick Reference",
        "content": (
            "GDPR (EU): Lawful basis for processing required. Data subject rights: access, erasure, portability, rectification. "
            "72-hour breach notification to supervisory authority. DPO required for large-scale processing. "
            "CCPA (California): Right to know, delete, opt-out of sale, non-discrimination. "
            "Applies to businesses with >$25M revenue or >50K consumer records annually. "
            "Both require data minimisation, purpose limitation, and privacy-by-design. "
            "DSAR (Data Subject Access Requests) must be completed within 30 days (GDPR) or 45 days (CCPA)."
        ),
        "tags": ["gdpr", "ccpa", "privacy", "compliance", "data-protection"],
        "source": "platform_seed",
    },
    {
        "title": "Cloud Security Best Practices (AWS/Azure/GCP)",
        "content": (
            "IAM: Enforce least privilege, rotate credentials, use roles not long-term keys. Enable MFA for all accounts. "
            "Network: Use VPCs, private subnets, security groups, restrict 0.0.0.0/0 ingress. Enable VPC Flow Logs. "
            "Storage: Disable public S3/Blob bucket access. Encrypt at rest with managed keys. Enable versioning. "
            "Logging: Enable CloudTrail, Azure Monitor, GCP Audit Logs. Forward to SIEM. "
            "Vulnerabilities: Use cloud-native security scanners (Security Hub, Defender for Cloud, Security Command Center). "
            "Containers: Scan images for CVEs, avoid running as root, use admission controllers."
        ),
        "tags": ["cloud", "aws", "azure", "gcp", "iam", "cspm"],
        "source": "platform_seed",
    },
    {
        "title": "Vulnerability Severity Scoring (CVSS)",
        "content": (
            "CVSS (Common Vulnerability Scoring System) v3.1 produces a 0-10 score. "
            "Critical: 9.0-10.0 — Requires immediate patching. Remote exploitable, no auth, high impact. "
            "High: 7.0-8.9 — Patch within 30 days. Significant confidentiality, integrity or availability impact. "
            "Medium: 4.0-6.9 — Patch within 90 days. Requires user interaction or local access. "
            "Low: 0.1-3.9 — Patch during next maintenance window. Minimal impact. "
            "Base score factors: Attack Vector (Network/Adjacent/Local/Physical), Attack Complexity, "
            "Privileges Required, User Interaction, Scope, Confidentiality/Integrity/Availability Impact."
        ),
        "tags": ["cvss", "vulnerability", "scoring", "patch-management"],
        "source": "platform_seed",
    },
    {
        "title": "SOC Analyst Investigation Workflow",
        "content": (
            "Tier 1 — Alert Triage: Classify alert as true/false positive. Gather initial context. "
            "Tier 2 — Investigation: Pivot on IOCs (IP, hash, domain). Review endpoint telemetry, logs, network flows. "
            "Tier 3 — Threat Hunting: Proactively search for hidden threats using hypothesis-driven techniques. "
            "Key tools: SIEM correlation, EDR timeline, sandbox detonation, threat intel enrichment. "
            "Escalation criteria: Data exfiltration evidence, privilege escalation, lateral movement, destructive activity. "
            "Documentation: Every action must be logged in the case management system with timestamps."
        ),
        "tags": ["soc", "analyst", "investigation", "triage", "workflow"],
        "source": "platform_seed",
    },
]


async def seed_knowledge_base(db) -> int:
    """Seed the knowledge base with default security content if empty."""
    await _ensure_text_index(db)
    existing = await db.knowledge_docs.count_documents({"source": "platform_seed"})
    if existing >= len(_SEED_DOCS):
        return 0
    now = datetime.now(timezone.utc).isoformat()
    inserted = 0
    for doc_data in _SEED_DOCS:
        doc_id = f"kb-seed-{__import__('hashlib').md5(doc_data['title'].encode()).hexdigest()[:10]}"
        exists = await db.knowledge_docs.find_one({"id": doc_id})
        if not exists:
            await db.knowledge_docs.insert_one({
                "id": doc_id,
                "content": doc_data["content"],
                "title": doc_data["title"],
                "source": doc_data["source"],
                "tags": doc_data["tags"],
                "tenantId": "global",
                "createdBy": "system",
                "createdAt": now,
            })
            inserted += 1
    return inserted


async def _ensure_text_index(db):
    """Ensure full-text search index exists on knowledge_docs."""
    try:
        await db.knowledge_docs.create_index(
            [("content", "text"), ("title", "text"), ("tags", "text")],
            name="knowledge_text_idx",
            default_language="english",
        )
    except Exception:
        pass  # Index already exists


@router.post("/ingest")
async def ingest_knowledge(
    data: Dict[str, Any] = Body(...),
    current_user: TokenData = Depends(rbac_service.has_permission("manage:ai_risks")),
):
    """
    Ingest content into the knowledge base.
    Body: { content, source?, title?, tags? }
    """
    content = data.get("content", "").strip()
    if not content:
        raise HTTPException(status_code=400, detail="Content is required")

    db = get_database()
    await _ensure_text_index(db)

    doc_id = f"kb-{uuid.uuid4().hex[:12]}"
    doc = {
        "id": doc_id,
        "content": content,
        "title": data.get("title", content[:80]),
        "source": data.get("source", "manual"),
        "tags": data.get("tags", []),
        "tenantId": getattr(current_user, "tenant_id", "default"),
        "createdBy": getattr(current_user, "username", "system"),
        "createdAt": datetime.now(timezone.utc).isoformat(),
    }
    await db.knowledge_docs.insert_one(doc)
    return {"success": True, "doc_id": doc_id, "id": doc_id, "title": doc["title"]}


@router.post("/query")
async def query_knowledge(
    data: Dict[str, Any] = Body(...),
    current_user: TokenData = Depends(rbac_service.has_permission("view:ai_governance")),
):
    """
    Query the knowledge base using full-text search.
    Body: { query, limit? }
    Returns ranked results with relevance snippets.
    """
    query = data.get("query", "").strip()
    if not query:
        raise HTTPException(status_code=400, detail="Query is required")

    limit = min(int(data.get("limit", 10)), 50)
    db = get_database()
    await _ensure_text_index(db)

    tenant_id = getattr(current_user, "tenant_id", "default")

    try:
        cursor = db.knowledge_docs.find(
            {
                "$text": {"$search": query},
                "$or": [{"tenantId": tenant_id}, {"tenantId": "global"}],
            },
            {"score": {"$meta": "textScore"}, "_id": 0},
        ).sort([("score", {"$meta": "textScore"})]).limit(limit)
        results = await cursor.to_list(length=limit)
    except Exception:
        # Text index may not exist yet — fall back to regex
        results = await db.knowledge_docs.find(
            {
                "$or": [{"tenantId": tenant_id}, {"tenantId": "global"}],
                "content": {"$regex": query, "$options": "i"},
            },
            {"_id": 0},
        ).limit(limit).to_list(length=limit)

    # Produce a short snippet around the matching text
    def _snippet(content: str, q: str, window: int = 200) -> str:
        lower = content.lower()
        idx = lower.find(q.split()[0].lower()) if q else -1
        if idx == -1:
            return content[:window]
        start = max(0, idx - 40)
        return ("…" if start else "") + content[start: start + window] + "…"

    return {
        "success": True,
        "results": [
            {
                "id": r.get("id"),
                "title": r.get("title", ""),
                "source": r.get("source", ""),
                "snippet": _snippet(r.get("content", ""), query),
                "tags": r.get("tags", []),
                "createdAt": r.get("createdAt", ""),
                "relevance": round(float(r.get("score", 0)), 3),
            }
            for r in results
        ],
        "count": len(results),
        "query": query,
    }


@router.get("/docs")
async def list_docs(
    limit: int = 50,
    current_user: TokenData = Depends(get_current_user),
):
    """List all knowledge base documents for the current tenant."""
    db = get_database()
    tenant_id = getattr(current_user, "tenant_id", "default")
    docs = await db.knowledge_docs.find(
        {"$or": [{"tenantId": tenant_id}, {"tenantId": "global"}]},
        {"_id": 0, "content": 0},
    ).sort("createdAt", -1).limit(limit).to_list(length=limit)
    return {"docs": docs, "count": len(docs)}


@router.delete("/docs/{doc_id}")
async def delete_doc(
    doc_id: str,
    current_user: TokenData = Depends(rbac_service.has_permission("manage:ai_risks")),
):
    """Delete a knowledge base document."""
    db = get_database()
    tenant_id = getattr(current_user, "tenant_id", "default")
    result = await db.knowledge_docs.delete_one({"id": doc_id, "tenantId": tenant_id})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Document not found")
    return {"success": True}
