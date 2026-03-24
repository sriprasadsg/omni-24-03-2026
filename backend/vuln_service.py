from typing import List, Dict, Any, Optional
from database import get_database
from datetime import datetime, timezone
import uuid

class VulnerabilityService:
    def __init__(self):
        self.collection_name = "vulnerabilities"

    async def get_vulnerabilities(self, tenant_id: str = "platform-admin") -> List[Dict[str, Any]]:
        """
        List all vulnerabilities for a tenant.
        """
        db = get_database()
        cursor = db[self.collection_name].find({"tenantId": tenant_id})
        vulns = await cursor.to_list(length=1000)
        for v in vulns:
            if "_id" in v:
                v["id"] = str(v["_id"])
                del v["_id"]
        return vulns

    async def get_vulnerability_stats(self, tenant_id: str = "platform-admin") -> Dict[str, Any]:
        """
        Get summary stats for vulnerabilities.
        """
        db = get_database()
        pipeline = [
            {"$match": {"tenantId": tenant_id}},
            {"$group": {
                "_id": "$severity",
                "count": {"$sum": 1}
            }}
        ]
        cursor = db[self.collection_name].aggregate(pipeline)
        results = await cursor.to_list(length=10)
        
        stats = {
            "Critical": 0,
            "High": 0,
            "Medium": 0,
            "Low": 0,
            "total": 0
        }
        
        for r in results:
            severity = r["_id"]
            if severity in stats:
                stats[severity] = r["count"]
                stats["total"] += r["count"]
                
        return stats

vuln_service = VulnerabilityService()
