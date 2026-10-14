import logging
from typing import List, Dict, Any, Optional
from database import get_database

class AuditService:
    """
    Manages audit logging and rollback capabilities using MongoDB.
    Implements SHA-256 Hash Chaining for Immutable Ledger.
    """
    
    def log_action(self, *args, **kwargs):
        raise RuntimeError(
            "AuditService.log_action() is a no-op stub. "
            "Use await log_action_async(...) to persist audit entries."
        )

    async def log_action_async(self,
                   user_name: str,
                   action: str,
                   resource_type: str,
                   resource_id: str,
                   details: str,
                   previous_state: Optional[Dict[str, Any]] = None,
                   tenant_id: str = "default-tenant") -> Dict[str, Any]:
        """Adapter onto audit_ledger.record (spec C5): one schema, one atomic chain."""
        import audit_ledger
        entry = audit_ledger.build(
            action, tenant_id, actor={"email": user_name},
            userName=user_name, resourceType=resource_type, resourceId=resource_id,
            details=details, previousState=previous_state)
        try:  # this module's get_database, so callers and tests that scope it are honoured
            db = get_database()
            raw = getattr(db, "_db", None)
            db = raw if raw is not None and hasattr(raw, "audit_logs") else db
        except Exception:
            db = None
        await audit_ledger.record(entry, db=db)
        logging.info(f"[AUDIT] {user_name} performed {action} on {resource_type} {resource_id} [Hash: {entry.get('hash', 'spooled')[:8]}...]")
        return entry

    async def get_logs(
        self,
        tenant_id: str = None,
        is_super_admin: bool = False,
        resource_type: Optional[str] = None,
        resource_id: Optional[str] = None,
        limit: int = 100,
        skip: int = 0,
        filters: Optional[Dict[str, Any]] = None,
    ) -> List[Dict[str, Any]]:
        """
        Retrieve logs filtered by tenant.
        Super-admins with is_super_admin=True may omit tenant_id to see all tenants.
        All other callers must supply a tenant_id; omitting it returns an empty list.

        resource_type / resource_id narrow the query as additional equality terms —
        they never replace the tenantId term, so a resource filter can never leak
        another tenant's entries.
        """
        db = get_database()
        query: Dict[str, Any] = {}
        if tenant_id:
            query["tenantId"] = tenant_id
        elif not is_super_admin:
            # Fail-closed: no tenant context and not a super-admin → return nothing
            logging.warning("[AUDIT] get_logs called without tenant_id by non-super-admin — returning empty list")
            return []

        for key, value in (filters or {}).items():  # extra equality/range terms (spec C5)
            if key != "tenantId":  # never widens the tenant scope
                query[key] = value
        if resource_type:
            query["resourceType"] = resource_type
        if resource_id:
            query["resourceId"] = resource_id

        safe_limit = max(1, min(int(limit or 100), 1000))
        safe_skip = max(0, int(skip or 0))

        # Return most recent first
        logs = await db.audit_logs.find(query, {"_id": 0}) \
            .sort("timestamp", -1) \
            .skip(safe_skip) \
            .limit(safe_limit) \
            .to_list(length=safe_limit)
        return logs

    async def get_log_by_id(self, log_id: str) -> Optional[Dict[str, Any]]:
        db = get_database()
        return await db.audit_logs.find_one({"id": log_id}, {"_id": 0})

    async def rollback(self, log_id: str, current_user: str, tenant_id: str = None) -> Dict[str, Any]:
        """
        Rollback.
        """
        log_entry = await self.get_log_by_id(log_id)
        if not log_entry:
            raise ValueError("Audit log entry not found")
        
        # Verify tenant ownership
        if tenant_id and log_entry.get("tenantId") != tenant_id:
            raise ValueError("Unauthorized: Audit log belongs to another tenant")

        if not log_entry.get("previousState"):
            raise ValueError("No previous state recorded for this action. Cannot rollback.")

        logging.info(f"[AUDIT] Rolling back action {log_entry['action']} on {log_entry['resourceId']}")
        
        # Log the rollback action itself!
        await self.log_action_async(
            user_name=current_user,
            action=f"rollback.{log_entry['action']}",
            resource_type=log_entry['resourceType'],
            resource_id=log_entry['resourceId'],
            details=f"Rolled back change from {log_entry['timestamp']}",
            previous_state=None, 
            tenant_id=log_entry.get('tenantId') or None
        )
        
        return log_entry["previousState"]

    async def verify_integrity(self, tenant_id: str) -> Dict[str, Any]:
        """Walk the tenant's chain by seq (audit_ledger.verify)."""
        import audit_ledger
        return await audit_ledger.verify(tenant_id)

# Global singleton
_audit_service = AuditService()

def get_audit_service():
    return _audit_service

