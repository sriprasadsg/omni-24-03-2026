from datetime import datetime, timedelta, timezone
import asyncio

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
        
    async def run_cleanup(self) -> dict:
        """Run all cleanup tasks"""
        print(f"[{datetime.now()}] Starting Data Retention Cleanup...")
        
        audit_deleted = await self.cleanup_audit_logs()
        metrics_deleted = await self.cleanup_system_metrics()
        notif_deleted = await self.cleanup_notifications()
        
        report = {
            "audit_logs_deleted": audit_deleted,
            "metrics_deleted": metrics_deleted,
            "notifications_deleted": notif_deleted,
            "status": "completed"
        }
        print(f"[{datetime.now()}] Cleanup Complete: {report}")
        return report

def get_retention_service(db):
    return RetentionService(db)
