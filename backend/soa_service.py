"""Statement of Applicability (SoA) service — ISO 27001 Annex A / framework control scoping."""
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
import uuid

_SOA_SUPER_ROLES = {"Super Admin", "super_admin", "admin", "platform-admin"}

# Default control domains seeded when a new SoA is generated
_FRAMEWORK_DOMAINS = {
    "iso27001": [
        ("A.5", "Organizational Controls"), ("A.6", "People Controls"),
        ("A.7", "Physical Controls"), ("A.8", "Technological Controls"),
    ],
    "soc2": [
        ("CC1", "Control Environment"), ("CC2", "Communication & Information"),
        ("CC3", "Risk Assessment"), ("CC4", "Monitoring Activities"),
        ("CC5", "Control Activities"), ("CC6", "Logical & Physical Access"),
        ("CC7", "System Operations"), ("CC8", "Change Management"),
        ("CC9", "Risk Mitigation"),
    ],
    "nist_800_53": [
        ("AC", "Access Control"), ("AT", "Awareness & Training"),
        ("AU", "Audit & Accountability"), ("CA", "Assessment & Authorization"),
        ("CM", "Configuration Management"), ("CP", "Contingency Planning"),
        ("IA", "Identification & Authentication"), ("IR", "Incident Response"),
        ("MA", "Maintenance"), ("MP", "Media Protection"),
        ("PE", "Physical & Environmental Protection"), ("PL", "Planning"),
        ("PM", "Program Management"), ("PS", "Personnel Security"),
        ("PT", "PII Processing & Transparency"), ("RA", "Risk Assessment"),
        ("SA", "System & Services Acquisition"), ("SC", "System & Communications Protection"),
        ("SI", "System & Information Integrity"), ("SR", "Supply Chain Risk Management"),
    ],
}

_IMPL_STATUSES = {"Implemented", "Planned", "Not Applicable", "Compensating Control"}


class SoAService:
    def _db(self):
        from database import get_database
        return get_database()

    async def get_soa(self, framework_id: str, tenant_id: Optional[str], role: str) -> List[Dict]:
        db = self._db()
        query: Dict[str, Any] = {"frameworkId": framework_id}
        if role not in _SOA_SUPER_ROLES:
            query["tenantId"] = tenant_id
        return await db.soa_entries.find(query, {"_id": 0}).sort("controlId", 1).to_list(length=5000)

    async def generate_soa(self, framework_id: str, tenant_id: str) -> List[Dict]:
        """Seed SoA entries from the framework's control library. Idempotent — skips existing."""
        db = self._db()
        framework = await db.compliance_frameworks.find_one({"id": framework_id, "tenantId": tenant_id}, {"_id": 0})
        if not framework:
            framework = await db.compliance_frameworks.find_one({"id": framework_id}, {"_id": 0})

        controls: List[Dict] = []
        if framework:
            raw = framework.get("controls") or framework.get("requirements") or []
            controls = raw if isinstance(raw, list) else []

        if not controls:
            slug = framework_id.lower().replace("-", "_").replace(" ", "_")
            domains = _FRAMEWORK_DOMAINS.get(slug, [("GEN", "General Controls")])
            for code, name in domains:
                controls.append({"id": code, "name": name, "description": f"{name} domain"})

        now = datetime.now(timezone.utc).isoformat()
        created = []
        for ctrl in controls:
            ctrl_id = ctrl.get("id") or ctrl.get("controlId") or str(uuid.uuid4())
            existing = await db.soa_entries.find_one(
                {"frameworkId": framework_id, "tenantId": tenant_id, "controlId": ctrl_id}
            )
            if existing:
                continue
            entry = {
                "id": f"soa-{uuid.uuid4().hex}",
                "tenantId": tenant_id,
                "frameworkId": framework_id,
                "frameworkName": framework.get("name", framework_id) if framework else framework_id,
                "controlId": ctrl_id,
                "controlName": ctrl.get("name") or ctrl.get("title") or ctrl_id,
                "description": ctrl.get("description") or ctrl.get("requirement") or "",
                "included": True,
                "justification": "",
                "implementationStatus": "Planned",
                "implementationDescription": "",
                "owner": "",
                "created_at": now,
                "updated_at": now,
            }
            await db.soa_entries.insert_one(entry)
            entry.pop("_id", None)
            created.append(entry)
        return created

    async def get_entry(self, entry_id: str, tenant_id: Optional[str], role: str) -> Optional[Dict]:
        db = self._db()
        query: Dict[str, Any] = {"id": entry_id}
        if role not in _SOA_SUPER_ROLES:
            query["tenantId"] = tenant_id
        return await db.soa_entries.find_one(query, {"_id": 0})

    async def update_entry(self, entry_id: str, data: Dict[str, Any], tenant_id: Optional[str], role: str) -> Optional[Dict]:
        db = self._db()
        query: Dict[str, Any] = {"id": entry_id}
        if role not in _SOA_SUPER_ROLES:
            query["tenantId"] = tenant_id
        allowed = {"included", "justification", "implementationStatus", "implementationDescription", "owner"}
        update = {k: v for k, v in data.items() if k in allowed}
        if not update:
            return await db.soa_entries.find_one(query, {"_id": 0})
        if "implementationStatus" in update and update["implementationStatus"] not in _IMPL_STATUSES:
            update.pop("implementationStatus")
        update["updated_at"] = datetime.now(timezone.utc).isoformat()
        await db.soa_entries.update_one(query, {"$set": update})
        return await db.soa_entries.find_one(query, {"_id": 0})

    async def bulk_update(self, framework_id: str, updates: List[Dict], tenant_id: str, role: str) -> int:
        db = self._db()
        updated = 0
        for u in updates:
            entry_id = u.get("id")
            if not entry_id:
                continue
            query: Dict[str, Any] = {"id": entry_id, "frameworkId": framework_id}
            if role not in _SOA_SUPER_ROLES:
                query["tenantId"] = tenant_id
            patch = {k: v for k, v in u.items() if k in {"included", "justification", "implementationStatus", "implementationDescription", "owner"}}
            if patch:
                patch["updated_at"] = datetime.now(timezone.utc).isoformat()
                res = await db.soa_entries.update_one(query, {"$set": patch})
                updated += res.modified_count
        return updated

    async def get_summary(self, framework_id: str, tenant_id: Optional[str], role: str) -> Dict:
        entries = await self.get_soa(framework_id, tenant_id, role)
        total = len(entries)
        included = sum(1 for e in entries if e.get("included"))
        by_status: Dict[str, int] = {}
        for e in entries:
            s = e.get("implementationStatus", "Planned")
            by_status[s] = by_status.get(s, 0) + 1
        return {
            "frameworkId": framework_id,
            "total": total,
            "included": included,
            "excluded": total - included,
            "byStatus": by_status,
            "completionPct": round(by_status.get("Implemented", 0) / max(included, 1) * 100),
        }

    async def export_csv(self, framework_id: str, tenant_id: Optional[str], role: str) -> str:
        import io, csv
        entries = await self.get_soa(framework_id, tenant_id, role)
        buf = io.StringIO()
        writer = csv.DictWriter(buf, fieldnames=[
            "controlId", "controlName", "description", "included",
            "justification", "implementationStatus", "implementationDescription", "owner",
        ])
        writer.writeheader()
        for e in entries:
            writer.writerow({
                "controlId": e.get("controlId", ""),
                "controlName": e.get("controlName", ""),
                "description": e.get("description", ""),
                "included": e.get("included", True),
                "justification": e.get("justification", ""),
                "implementationStatus": e.get("implementationStatus", ""),
                "implementationDescription": e.get("implementationDescription", ""),
                "owner": e.get("owner", ""),
            })
        return buf.getvalue()


soa_service = SoAService()
