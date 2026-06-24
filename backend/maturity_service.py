"""Maturity Level Scoring service — CMMI-style 1–5 assessments per security domain."""
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
import uuid
from auth_roles import SUPER_AND_ADMIN_ROLES as _M_SUPER_ROLES

MATURITY_LEVELS = {
    1: "Initial",
    2: "Managed",
    3: "Defined",
    4: "Quantitatively Managed",
    5: "Optimizing",
}

DEFAULT_DOMAINS = [
    "Access Control",
    "Asset Management",
    "Audit & Accountability",
    "Business Continuity",
    "Change Management",
    "Cryptography",
    "Data Classification & Privacy",
    "Endpoint Security",
    "Identity & Authentication",
    "Incident Response",
    "Network Security",
    "Patch & Vulnerability Management",
    "Physical Security",
    "Risk Management",
    "Secure Development",
    "Security Awareness & Training",
    "Security Monitoring & SIEM",
    "Supply Chain Security",
    "Third-Party & Vendor Risk",
    "Threat Intelligence",
]


class MaturityService:
    def _db(self):
        from database import get_database
        return get_database()

    async def list_assessments(self, tenant_id: Optional[str], role: str, framework: Optional[str] = None) -> List[Dict]:
        db = self._db()
        query: Dict[str, Any] = {} if role in _M_SUPER_ROLES else {"tenantId": tenant_id}
        if framework:
            query["framework"] = framework
        return await db.maturity_assessments.find(query, {"_id": 0}).sort("assessed_at", -1).to_list(length=2000)

    async def get_domains(self) -> List[str]:
        return DEFAULT_DOMAINS

    async def upsert_assessment(self, data: Dict[str, Any], tenant_id: str, assessed_by: str) -> Dict:
        """Create or update a maturity assessment for a domain."""
        db = self._db()
        now = datetime.now(timezone.utc).isoformat()
        level = int(data.get("level", 1))
        if level not in MATURITY_LEVELS:
            level = max(1, min(5, level))
        domain = data.get("domain", "")
        framework = data.get("framework", "General")
        existing = await db.maturity_assessments.find_one(
            {"tenantId": tenant_id, "domain": domain, "framework": framework},
            {"_id": 0},
        )
        if existing:
            patch = {
                "level": level,
                "levelName": MATURITY_LEVELS[level],
                "evidence": data.get("evidence", existing.get("evidence", "")),
                "notes": data.get("notes", existing.get("notes", "")),
                "targetLevel": data.get("targetLevel", existing.get("targetLevel")),
                "assessed_by": assessed_by,
                "assessed_at": now,
                "updated_at": now,
            }
            await db.maturity_assessments.update_one(
                {"tenantId": tenant_id, "domain": domain, "framework": framework},
                {"$set": patch},
            )
            return {**existing, **patch}
        doc = {
            "id": f"mat-{uuid.uuid4().hex}",
            "tenantId": tenant_id,
            "framework": framework,
            "domain": domain,
            "level": level,
            "levelName": MATURITY_LEVELS[level],
            "evidence": data.get("evidence", ""),
            "notes": data.get("notes", ""),
            "targetLevel": data.get("targetLevel"),
            "assessed_by": assessed_by,
            "assessed_at": now,
            "created_at": now,
            "updated_at": now,
        }
        await db.maturity_assessments.insert_one(doc)
        doc.pop("_id", None)
        await db.maturity_history.insert_one({**doc, "id": f"mh-{uuid.uuid4().hex}"})
        return doc

    async def get_summary(self, tenant_id: Optional[str], role: str, framework: Optional[str] = None) -> Dict:
        assessments = await self.list_assessments(tenant_id, role, framework)
        if not assessments:
            return {"averageLevel": 0, "levelName": "Not Assessed", "byDomain": {}, "byLevel": {}, "totalDomains": 0, "assessedDomains": 0}
        total = len(assessments)
        avg = sum(a.get("level", 0) for a in assessments) / total
        avg_rounded = round(avg, 1)
        by_level: Dict[int, int] = {}
        by_domain: Dict[str, int] = {}
        for a in assessments:
            lvl = a.get("level", 0)
            by_level[lvl] = by_level.get(lvl, 0) + 1
            by_domain[a.get("domain", "Unknown")] = lvl
        return {
            "averageLevel": avg_rounded,
            "levelName": MATURITY_LEVELS.get(round(avg_rounded), "Mixed"),
            "byDomain": by_domain,
            "byLevel": {MATURITY_LEVELS[k]: v for k, v in by_level.items()},
            "totalDomains": len(DEFAULT_DOMAINS),
            "assessedDomains": total,
            "coveragePct": round(total / len(DEFAULT_DOMAINS) * 100),
        }

    async def get_history(self, domain: str, tenant_id: Optional[str], role: str) -> List[Dict]:
        db = self._db()
        query: Dict[str, Any] = {"domain": domain}
        if role not in _M_SUPER_ROLES:
            query["tenantId"] = tenant_id
        return await db.maturity_history.find(query, {"_id": 0}).sort("assessed_at", 1).to_list(length=500)

    async def get_gaps(self, tenant_id: Optional[str], role: str, framework: Optional[str] = None) -> List[Dict]:
        assessments = await self.list_assessments(tenant_id, role, framework)
        assessed = {a["domain"]: a for a in assessments}
        gaps = []
        for domain in DEFAULT_DOMAINS:
            a = assessed.get(domain)
            if not a:
                gaps.append({"domain": domain, "currentLevel": 0, "targetLevel": 3, "gap": 3, "status": "Not Assessed"})
            else:
                target = a.get("targetLevel") or 4
                current = a.get("level", 0)
                gap = max(0, target - current)
                if gap > 0:
                    gaps.append({"domain": domain, "currentLevel": current, "targetLevel": target, "gap": gap, "status": "Below Target"})
        gaps.sort(key=lambda x: -x["gap"])
        return gaps


maturity_service = MaturityService()
