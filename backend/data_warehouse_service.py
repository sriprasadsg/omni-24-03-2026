from motor.motor_asyncio import AsyncIOMotorDatabase
from typing import List, Dict, Any, Optional

class DataWarehouseService:
    def __init__(self, db: AsyncIOMotorDatabase):
        self.db = db

    async def query_analytics(self, tenant_id: str, table_name: str, query: Dict[str, Any] = None) -> List[Dict[str, Any]]:
        """Generic query for analytics tables"""
        if query is None:
            query = {}
        
        query["tenant_id"] = tenant_id
        collection_name = f"analytics_{table_name}"
        
        cursor = self.db[collection_name].find(query).limit(1000)
        results = []
        async for doc in cursor:
            doc["id"] = str(doc.pop("_id"))
            results.append(doc)
            
        return results

    async def get_aggregated_stats(self, tenant_id: str) -> Dict[str, Any]:
        """Get high-level statistics for the dashboard"""
        
        # Example: Total threats today
        threat_count = 0
        cursor = self.db.analytics_daily_threat_stats.find({"tenant_id": tenant_id})
        async for doc in cursor:
            threat_count += doc.get("count", 0)
            
        # Example: API usage total
        api_count = 0
        cursor = self.db.analytics_daily_api_usage.find({"tenant_id": tenant_id})
        async for doc in cursor:
            api_count += doc.get("count", 0)
            
        return {
            "total_threats_processed": threat_count,
            "total_api_calls_analyzed": api_count,
            "warehouse_status": "healthy"
        }

    async def run_etl(self, tenant_id: str) -> Dict[str, Any]:
        """
        Aggregate live data from operational collections into analytics_* collections.
        Called hourly by the scheduler so warehouse queries return current data.
        """
        from datetime import datetime, timezone
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")

        # ── Daily threat stats ────────────────────────────────────────────────
        threat_count = await self.db.security_events.count_documents({"tenantId": tenant_id})
        await self.db.analytics_daily_threat_stats.update_one(
            {"tenant_id": tenant_id, "date": today},
            {"$set": {"count": threat_count, "updated_at": datetime.now(timezone.utc).isoformat()}},
            upsert=True,
        )

        # ── Daily API usage (apm_metrics) ─────────────────────────────────────
        api_count = await self.db.apm_metrics.count_documents({"type": "http_request"})
        await self.db.analytics_daily_api_usage.update_one(
            {"tenant_id": tenant_id, "date": today},
            {"$set": {"count": api_count, "updated_at": datetime.now(timezone.utc).isoformat()}},
            upsert=True,
        )

        # ── Asset snapshot ────────────────────────────────────────────────────
        asset_count = await self.db.assets.count_documents({"tenantId": tenant_id})
        online_agents = await self.db.agents.count_documents({"tenantId": tenant_id, "status": "Online"})
        await self.db.analytics_asset_snapshots.update_one(
            {"tenant_id": tenant_id, "date": today},
            {"$set": {
                "asset_count": asset_count,
                "online_agents": online_agents,
                "updated_at": datetime.now(timezone.utc).isoformat(),
            }},
            upsert=True,
        )

        # ── Compliance scores ─────────────────────────────────────────────────
        frameworks = await self.db.compliance_frameworks.find(
            {"tenant_id": tenant_id}, {"name": 1, "compliance_score": 1}
        ).to_list(length=20)
        await self.db.analytics_compliance_scores.update_one(
            {"tenant_id": tenant_id, "date": today},
            {"$set": {
                "frameworks": [{"name": f.get("name"), "score": f.get("compliance_score", 0)} for f in frameworks],
                "updated_at": datetime.now(timezone.utc).isoformat(),
            }},
            upsert=True,
        )

        return {
            "tenant_id": tenant_id,
            "date": today,
            "threat_count": threat_count,
            "api_count": api_count,
            "asset_count": asset_count,
            "online_agents": online_agents,
        }


def get_data_warehouse_service(db: AsyncIOMotorDatabase) -> DataWarehouseService:
    return DataWarehouseService(db)
