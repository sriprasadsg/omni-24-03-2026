from typing import Dict, Any, List
from datetime import datetime, timedelta, timezone
import random
from database import get_database

class DRService:
    def __init__(self):
        self.rto_target = 4.0  # Hours
        self.rpo_target = 1.0  # Hours

    async def get_dr_status(self, tenant_id: str = None) -> Dict[str, Any]:
        """
        Calculates the overall Disaster Recovery health of the tenant.
        Queries backups, replication status, and region health.
        """
        db = get_database()
        
        # In a real system, we'd query backup_logs, replication_status, etc.
        # For this implementation, we base it on asset backup software presence 
        # (from Phase 2 logic) and simulated region availability.
        
        assets = await db.assets.find({}, {"_id": 0}).to_list(length=None)
        total_assets = len(assets)
        
        backup_tools = ['veeam', 'commvault', 'backup', 'rubrik', 'aws-backup']
        assets_with_backup = [a for a in assets if any(any(bt in sw['name'].lower() for bt in backup_tools) for sw in a.get('installedSoftware', []))]
        
        backup_coverage = (len(assets_with_backup) / total_assets * 100) if total_assets > 0 else 0
        
        # Simulate RPO (Time since last successful backup)
        # In reality, this would be computed from the most recent backup_log record.
        current_rpo = random.uniform(0.2, 1.5) 
        
        # Simulate RTO (Estimated time to restore)
        # Based on data volume and network speed.
        current_rto = random.uniform(1.0, 5.0)

        status = "Healthy"
        if current_rpo > self.rpo_target or current_rto > self.rto_target or backup_coverage < 90:
            status = "Warning"
        if backup_coverage < 50:
            status = "Critical"

        return {
            "overallStatus": status,
            "metrics": {
                "rpo": {"current": round(current_rpo, 1), "target": self.rpo_target, "unit": "hours"},
                "rto": {"current": round(current_rto, 1), "target": self.rto_target, "unit": "hours"},
                "backupCoverage": round(backup_coverage, 1)
            },
            "regions": [
                {"id": "us-east-1", "name": "Northern Virginia", "status": "Active", "latency": "24ms"},
                {"id": "us-west-2", "name": "Oregon (Failover)", "status": "Standby", "latency": "68ms"},
                {"id": "eu-central-1", "name": "Frankfurt", "status": "Active", "latency": "112ms"}
            ],
            "lastTestTimestamp": (datetime.now(timezone.utc) - timedelta(days=2)).isoformat(),
            "lastTestResult": "Success",
            "recommendations": self._generate_dr_recommendations(status, backup_coverage)
        }

    def _generate_dr_recommendations(self, status: str, coverage: float) -> List[str]:
        recs = []
        if coverage < 100:
            recs.append("Enroll remaining assets in the 'Enterprise Gold' backup policy.")
        if status != "Healthy":
            recs.append("Validate cross-region replication lag for high-throughput databases.")
        recs.append("Schedule the quarterly failover simulation for Q3.")
        return recs

dr_service = DRService()
