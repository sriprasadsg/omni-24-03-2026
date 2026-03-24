from datetime import datetime
from typing import Optional, Dict, Any
from database import get_database
import logging

class AuditService:
    def __init__(self):
        self.logger = logging.getLogger("AuditService")

    async def log_event(self, 
                        action: str, 
                        actor: str, 
                        resource: str, 
                        details: Optional[Dict[str, Any]] = None, 
                        status: str = "SUCCESS",
                        tenant_id: str = "unknown") -> bool:
        """
        Log a security or operational event to the database.
        
        Args:
            action: The action performed (e.g., "agent_dispatch", "rag_ingest")
            actor: The user or system ID performing the action
            resource: The target resource ID (e.g., task_id, doc_id)
            details: Additional context
            status: SUCCESS or FAILURE
            tenant_id: Tenant context
        """
        try:
            db = get_database()
            event = {
                "timestamp": datetime.utcnow().isoformat(),
                "action": action,
                "actor": actor,
                "resource": resource,
                "details": details or {},
                "status": status,
                "tenantId": tenant_id
            }
            
            await db.audit_logs.insert_one(event)
            self.logger.info(f"Audit: [{action}] by [{actor}] -> {status}")
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to write audit log: {e}")
            return False

audit_service = AuditService()
