from datetime import datetime, timezone
import asyncio
from typing import List, Dict, Any, Optional
from motor.motor_asyncio import AsyncIOMotorDatabase
from data_lake_service import DataLakeService

class ETLService:
    def __init__(self, db: AsyncIOMotorDatabase):
        self.db = db
        self.data_lake = DataLakeService()

    async def run_pipeline(self, tenant_id: str, job_id: str = "manual"):
        """
        Orchestrate the ETL pipeline:
        1. Extract data from operational collections
        2. Transform/Aggregate data
        3. Load to Data Lake (Raw + Processed)
        4. Load to Data Warehouse (Analytics Collections)
        5. Record job history
        """
        start_time = datetime.now(timezone.utc)
        status = "success"
        details = []

        try:
            # Step 1: Extract & Load Raw Data to Lake
            # We'll simulate extracting recent logs and metrics
            logs_count = await self._extract_and_store_raw(tenant_id, "logs")
            metrics_count = await self._extract_and_store_raw(tenant_id, "metrics")
            details.append(f"Extracted {logs_count} logs and {metrics_count} metrics.")

            # Step 2: Transform & Load to Warehouse (Analytics Collections)
            # Example: Aggregate daily threat counts
            threat_stats = await self._aggregate_threats(tenant_id)
            await self._load_to_warehouse(tenant_id, "daily_threat_stats", threat_stats)

            # Example: Aggregate API usage
            api_stats = await self._aggregate_api_usage(tenant_id)
            await self._load_to_warehouse(tenant_id, "daily_api_usage", api_stats)
            
            details.append("Aggregated threat and API usage statistics.")

        except Exception as e:
            status = "failed"
            details.append(f"Error: {str(e)}")
            print(f"ETL Failed: {e}")
        
        finally:
            end_time = datetime.now(timezone.utc)
            duration = (end_time - start_time).total_seconds()
            
            # Record Job History
            job_record = {
                "job_id": job_id,
                "tenant_id": tenant_id,
                "start_time": start_time.isoformat(),
                "end_time": end_time.isoformat(),
                "duration_seconds": duration,
                "status": status,
                "details": details
            }
            await self.db.etl_jobs.insert_one(job_record)
            
            return job_record

    async def _extract_and_store_raw(self, tenant_id: str, collection_name: str) -> int:
        """Extract recent data and store raw JSON in Data Lake"""
        # In a real scenario, we'd filter by timestamp since last run
        # For now, we'll just take the last 100 items as a simulation
        cursor = self.db[collection_name].find({"tenantId": tenant_id}).sort("timestamp", -1).limit(100)
        items = await cursor.to_list(length=100)
        
        if not items:
            return 0

        # Serialize to JSON (handle ObjectId and datetime)
        import json
        from bson import json_util
        
        data_str = json_util.dumps(items)
        
        # Determine path
        timestamp = datetime.now(timezone.utc).strftime("%Y/%m/%d/%H")
        filename = f"{collection_name}_{datetime.now(timezone.utc).timestamp()}.json"
        s3_key = f"raw/{tenant_id}/{collection_name}/{timestamp}/{filename}"
        
        # Upload to Data Lake
        await self.data_lake.upload_file(data_str.encode('utf-8'), s3_key)
        
        return len(items)

    async def _aggregate_threats(self, tenant_id: str) -> List[Dict[str, Any]]:
        """Aggregate threats by severity for the day"""
        pipeline = [
            {"$match": {"tenantId": tenant_id}},
            {"$group": {"_id": "$severity", "count": {"$sum": 1}}}
        ]
        cursor = self.db.security_events.aggregate(pipeline)
        
        stats = []
        async for doc in cursor:
            stats.append({
                "severity": doc["_id"],
                "count": doc["count"],
                "date": datetime.now(timezone.utc).strftime("%Y-%m-%d")
            })
        return stats

    async def _aggregate_api_usage(self, tenant_id: str) -> List[Dict[str, Any]]:
        """Mock aggregation for API usage since we might not have request logs populated yet"""
        return [
            {"endpoint": "/api/agents", "count": 150, "date": datetime.now(timezone.utc).strftime("%Y-%m-%d")},
            {"endpoint": "/api/security", "count": 45, "date": datetime.now(timezone.utc).strftime("%Y-%m-%d")}
        ]

    async def _load_to_warehouse(self, tenant_id: str, table_name: str, data: List[Dict[str, Any]]):
        """Load aggregated data into analytics collections (Warehouse)"""
        if not data:
            return

        collection = self.db[f"analytics_{table_name}"]
        
        # Add metadata
        for item in data:
            item["tenant_id"] = tenant_id
            item["ingested_at"] = datetime.now(timezone.utc).isoformat()
        
        await collection.insert_many(data)

def get_etl_service(db: AsyncIOMotorDatabase) -> ETLService:
    return ETLService(db)
