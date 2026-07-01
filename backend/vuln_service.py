from typing import Dict, Any
from database import get_database

class VulnerabilityService:
    def __init__(self):
        self.collection_name = "vulnerabilities"

    async def get_vulnerabilities(
        self,
        tenant_id: str = "platform-admin",
        page: int = 1,
        page_size: int = 100,
        severity: str = None,
    ) -> Dict[str, Any]:
        """
        List vulnerabilities for a tenant with pagination.
        """
        db = get_database()
        query: dict = {"tenantId": tenant_id}
        if severity:
            query["severity"] = severity
        skip = (page - 1) * page_size
        cursor = db[self.collection_name].find(query, {"_id": 0}).skip(skip).limit(page_size)
        vulns = await cursor.to_list(length=page_size)
        for v in vulns:
            if "_id" in v:
                v["id"] = str(v["_id"])
                del v["_id"]
        total = await db[self.collection_name].count_documents(query)
        return {"items": vulns, "total": total, "page": page, "page_size": page_size}

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
