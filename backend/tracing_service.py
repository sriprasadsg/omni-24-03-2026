from datetime import datetime, timedelta, timezone
import random
import uuid
from typing import List, Dict, Any

class TracingService:
    def __init__(self, db=None):
        self.db = db
        self.services = ["frontend", "auth-service", "user-service", "payment-service", "inventory-service", "notification-service", "database"]
        self.operations = ["GET /api/v1/users", "POST /api/v1/checkout", "GET /api/v1/products", "POST /api/v1/login"]

    async def ensure_tracing_collections(self):
        """Ensure tracing collections exist (no seed data)"""
        if not self.db:
            return
            
        collections = await self.db.list_collection_names()
        
        # Initialize collections without seed data
        if "traces" not in collections:
            await self.db.create_collection("traces")
        
        if "service_map" not in collections:
            await self.db.create_collection("service_map")

    async def get_service_map(self) -> Dict[str, Any]:
        """Get service map from MongoDB."""
        if not self.db:
            return {"nodes": [], "edges": []}
            
        try:
            await self.ensure_tracing_collections()
            
            service_map = await self.db.service_map.find_one({}, {"_id": 0})
            if not service_map:
                # If still empty after ensure, return empty structure
                return {"nodes": [], "edges": []}
            
            return {"nodes": service_map.get("nodes", []), "edges": service_map.get("edges", [])}
        except Exception as e:
            print(f"Error getting service map: {e}")
            return {"nodes": [], "edges": []}

    async def get_traces(self, limit: int = 20) -> List[Dict[str, Any]]:
        """Get traces from MongoDB."""
        if not self.db:
            return []
            
        try:
            await self.ensure_tracing_collections()
            
            traces = await self.db.traces.find({}, {"_id": 0}).sort("startTime", -1).limit(limit).to_list(length=limit)
            return traces
        except Exception as e:
            print(f"Error getting traces: {e}")
            return []

_tracing_service = None

def get_tracing_service(db=None):
    global _tracing_service
    if _tracing_service is None or db is not None:
        _tracing_service = TracingService(db)
    return _tracing_service
