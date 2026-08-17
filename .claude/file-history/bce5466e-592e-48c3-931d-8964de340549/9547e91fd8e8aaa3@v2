"""Audit Program Lifecycle service — create, execute, and close audit programs."""
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
import uuid

_AP_SUPER_ROLES = {"Super Admin", "super_admin", "admin", "platform-admin"}
_AP_STATUSES = ["Planning", "Fieldwork", "Review", "Remediation", "Closed"]
_AP_TRANSITIONS = {
    "Planning": {"Fieldwork"},
    "Fieldwork": {"Review", "Planning"},
    "Review": {"Remediation", "Fieldwork", "Closed"},
    "Remediation": {"Review", "Closed"},
    "Closed": set(),
}
_FINDING_SEVERITIES = {"Critical", "High", "Medium", "Low", "Informational"}
_FINDING_STATUSES = {"Open", "In Progress", "Resolved", "Accepted"}


class AuditProgramService:
    def _db(self):
        from database import get_database
        return get_database()

    async def list_programs(self, tenant_id: Optional[str], role: str) -> List[Dict]:
        db = self._db()
        query: Dict[str, Any] = {} if role in _AP_SUPER_ROLES else {"tenantId": tenant_id}
        return await db.audit_programs.find(query, {"_id": 0}).sort("created_at", -1).to_list(length=500)

    async def create_program(self, data: Dict[str, Any], tenant_id: str, created_by: str) -> Dict:
        db = self._db()
        now = datetime.now(timezone.utc).isoformat()
        doc = {
            "id": f"ap-{uuid.uuid4().hex}",
            "tenantId": tenant_id,
            "name": data["name"],
            "description": data.get("description", ""),
            "framework": data.get("framework", ""),
            "type": data.get("type", "Internal"),
            "status": "Planning",
            "auditor": data.get("auditor", created_by),
            "auditee": data.get("auditee", ""),
            "startDate": data.get("startDate", ""),
            "endDate": data.get("endDate", ""),
            "scope": data.get("scope", []),
            "controls": data.get("controls", []),
            "findings": [],
            "createdBy": created_by,
            "created_at": now,
            "updated_at": now,
        }
        await db.audit_programs.insert_one(doc)
        doc.pop("_id", None)
        return doc

    async def get_program(self, program_id: str, tenant_id: Optional[str], role: str) -> Optional[Dict]:
        db = self._db()
        query: Dict[str, Any] = {"id": program_id}
        if role not in _AP_SUPER_ROLES:
            query["tenantId"] = tenant_id
        return await db.audit_programs.find_one(query, {"_id": 0})

    async def update_program(self, program_id: str, data: Dict[str, Any], tenant_id: Optional[str], role: str) -> Optional[Dict]:
        db = self._db()
        query: Dict[str, Any] = {"id": program_id}
        if role not in _AP_SUPER_ROLES:
            query["tenantId"] = tenant_id
        allowed = {"name", "description", "framework", "type", "auditor", "auditee", "startDate", "endDate", "scope", "controls"}
        patch = {k: v for k, v in data.items() if k in allowed}
        if patch:
            patch["updated_at"] = datetime.now(timezone.utc).isoformat()
            await db.audit_programs.update_one(query, {"$set": patch})
        return await db.audit_programs.find_one(query, {"_id": 0})

    async def transition_status(self, program_id: str, new_status: str, tenant_id: Optional[str], role: str) -> Optional[Dict]:
        db = self._db()
        query: Dict[str, Any] = {"id": program_id}
        if role not in _AP_SUPER_ROLES:
            query["tenantId"] = tenant_id
        program = await db.audit_programs.find_one(query, {"_id": 0})
        if not program:
            return None
        current = program.get("status", "Planning")
        allowed_next = _AP_TRANSITIONS.get(current, set())
        if new_status not in allowed_next:
            raise ValueError(f"Cannot transition from {current} to {new_status}")
        now = datetime.now(timezone.utc).isoformat()
        patch: Dict[str, Any] = {"status": new_status, "updated_at": now}
        if new_status == "Closed":
            patch["closedAt"] = now
        await db.audit_programs.update_one(query, {"$set": patch})
        return await db.audit_programs.find_one(query, {"_id": 0})

    async def add_finding(self, program_id: str, finding: Dict[str, Any], tenant_id: Optional[str], role: str) -> Optional[Dict]:
        db = self._db()
        query: Dict[str, Any] = {"id": program_id}
        if role not in _AP_SUPER_ROLES:
            query["tenantId"] = tenant_id
        now = datetime.now(timezone.utc).isoformat()
        f = {
            "id": f"af-{uuid.uuid4().hex}",
            "title": finding.get("title", ""),
            "description": finding.get("description", ""),
            "severity": finding.get("severity", "Medium"),
            "controlId": finding.get("controlId", ""),
            "status": "Open",
            "recommendation": finding.get("recommendation", ""),
            "managementResponse": "",
            "created_at": now,
        }
        await db.audit_programs.update_one(query, {"$push": {"findings": f}, "$set": {"updated_at": now}})
        return await db.audit_programs.find_one(query, {"_id": 0})

    async def update_finding(self, program_id: str, finding_id: str, data: Dict[str, Any], tenant_id: Optional[str], role: str) -> Optional[Dict]:
        db = self._db()
        query: Dict[str, Any] = {"id": program_id, "findings.id": finding_id}
        if role not in _AP_SUPER_ROLES:
            query["tenantId"] = tenant_id
        allowed = {"status", "managementResponse", "recommendation", "severity"}
        patch = {"findings.$." + k: v for k, v in data.items() if k in allowed}
        if patch:
            patch["updated_at"] = datetime.now(timezone.utc).isoformat()
            await db.audit_programs.update_one(query, {"$set": patch})
        return await db.audit_programs.find_one({"id": program_id}, {"_id": 0})

    async def get_report(self, program_id: str, tenant_id: Optional[str], role: str) -> Dict:
        program = await self.get_program(program_id, tenant_id, role)
        if not program:
            return {}
        findings = program.get("findings", [])
        by_severity: Dict[str, int] = {}
        by_status: Dict[str, int] = {}
        for f in findings:
            s = f.get("severity", "Unknown")
            st = f.get("status", "Open")
            by_severity[s] = by_severity.get(s, 0) + 1
            by_status[st] = by_status.get(st, 0) + 1
        return {
            "programId": program_id,
            "name": program.get("name"),
            "status": program.get("status"),
            "framework": program.get("framework"),
            "auditor": program.get("auditor"),
            "startDate": program.get("startDate"),
            "endDate": program.get("endDate"),
            "totalFindings": len(findings),
            "findingsBySeverity": by_severity,
            "findingsByStatus": by_status,
            "openFindings": by_status.get("Open", 0),
            "resolvedFindings": by_status.get("Resolved", 0),
            "findings": findings,
        }

    async def delete_program(self, program_id: str, tenant_id: Optional[str], role: str) -> bool:
        db = self._db()
        query: Dict[str, Any] = {"id": program_id}
        if role not in _AP_SUPER_ROLES:
            query["tenantId"] = tenant_id
        res = await db.audit_programs.delete_one(query)
        return res.deleted_count > 0


audit_program_service = AuditProgramService()
