"""Legacy event writer, now an adapter onto audit_ledger (spec C5: one schema)."""
from typing import Any, Dict, Optional
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
        """Record a security or operational event (e.g. "agent_dispatch", "rag_ingest")
        by ``actor`` on ``resource``; ``status`` SUCCESS/FAILURE maps to the outcome."""
        import audit_ledger
        entry = await audit_ledger.event(
            action, tenant_id, actor={"email": actor},
            outcome="success" if str(status).upper() == "SUCCESS" else "error",
            resourceId=resource, details=details or {}, status=status)
        self.logger.info(f"Audit: [{action}] by [{actor}] -> {status}")
        return "hash" in entry


audit_service = AuditService()
