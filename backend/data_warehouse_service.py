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

def get_data_warehouse_service(db: AsyncIOMotorDatabase) -> DataWarehouseService:
    return DataWarehouseService(db)
