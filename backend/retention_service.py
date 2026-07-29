from datetime import datetime, timedelta, timezone

class RetentionService:
    """
    Handles data retention policies and cleanup of old records.
    """
    def __init__(self, db):
        self.db = db
        
    async def cleanup_audit_logs(self, retention_days: int = 90) -> int:
        """Delete audit logs older than retention_days"""
        cutoff = datetime.now(timezone.utc) - timedelta(days=retention_days)
        # Audit logs use 'timestamp' string ISO format usually, strictly we should parse.
        # But assuming ISO format, lexicographical comparison works for standard ISO string.
        # Better safe: $lt string comparison works for ISO8601.
        result = await self.db.audit_logs.delete_many({
            "timestamp": {"$lt": cutoff.isoformat()}
        })
        return result.deleted_count

    async def cleanup_system_metrics(self, retention_days: int = 30) -> int:
        """Delete metrics older than retention_days"""
        cutoff = datetime.now(timezone.utc) - timedelta(days=retention_days)
        result = await self.db.metrics.delete_many({
            "timestamp": {"$lt": cutoff.isoformat()}
        })
        return result.deleted_count

    async def cleanup_notifications(self, retention_days: int = 30) -> int:
        """Delete notifications older than retention_days"""
        cutoff = datetime.now(timezone.utc) - timedelta(days=retention_days)
        result = await self.db.notifications.delete_many({
            "sent_at": {"$lt": cutoff.isoformat()}
        })
        return result.deleted_count

    async def cleanup_agent_location_history(self, retention_days: int = 365) -> int:
        """Delete agent_location_history rows older than retention_days.

        agent_location_history.timestamp is a real BSON Date (native
        datetime, never .isoformat()'d on write — see 46-02) so the cutoff
        here is compared as a datetime object directly, unlike the other
        cleanup_* methods above which compare against ISO string fields.
        Platform-wide sweep, no tenantId filter, matching the other 3
        existing cleanup methods.
        """
        cutoff = datetime.now(timezone.utc) - timedelta(days=retention_days)
        result = await self.db.agent_location_history.delete_many({
            "timestamp": {"$lt": cutoff}
        })
        return result.deleted_count

    async def run_cleanup(self, policies: dict = None) -> dict:
        """Run cleanup tasks using DB-configured retention days."""
        p = policies or {}
        audit_deleted   = await self.cleanup_audit_logs(p.get("audit_logs", 90))
        metrics_deleted = await self.cleanup_system_metrics(p.get("metrics", 30))
        notif_deleted   = await self.cleanup_notifications(p.get("notifications", 30))
        location_history_deleted = await self.cleanup_agent_location_history(
            p.get("agent_location_history", 365)
        )
        report = {
            "audit_logs_deleted":   audit_deleted,
            "metrics_deleted":      metrics_deleted,
            "notifications_deleted": notif_deleted,
            "agent_location_history_deleted": location_history_deleted,
            "status": "completed",
        }
        return report

def get_retention_service(db):
    return RetentionService(db)
