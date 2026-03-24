from datetime import datetime, timezone, timedelta
from typing import List, Dict, Any, Optional
import uuid

class MaintenanceService:
    def __init__(self, db):
        self.db = db

    async def create_window(self, window_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Create a new maintenance window
        window_data: {
            "tenant_id": str,
            "name": str,
            "start_time": str (ISO),
            "end_time": str (ISO),
            "recurrence": "none" | "daily" | "weekly" | "monthly",
            "days_of_week": List[int] (0-6),
            "is_active": bool
        }
        """
        window_id = str(uuid.uuid4())
        new_window = {
            "id": window_id,
            **window_data,
            "tenantId": window_data.get("tenantId"),
            "created_at": datetime.now(timezone.utc).isoformat()
        }
        await self.db.maintenance_windows.insert_one(new_window)
        return new_window

    async def list_windows(self, tenant_id: str) -> List[Dict[str, Any]]:
        return await self.db.maintenance_windows.find(
            {"tenantId": tenant_id},
            {"_id": 0}
        ).to_list(length=100)

    async def delete_window(self, window_id: str):
        await self.db.maintenance_windows.delete_one({"id": window_id})

    async def is_in_maintenance_window(self, tenant_id: str) -> bool:
        """Check if current time is within any active maintenance window for the tenant"""
        now = datetime.now(timezone.utc)
        windows = await self.db.maintenance_windows.find(
            {"tenantId": tenant_id, "is_active": True},
            {"_id": 0}
        ).to_list(length=100)

        for window in windows:
            start = datetime.fromisoformat(window["start_time"].replace('Z', '+00:00'))
            end = datetime.fromisoformat(window["end_time"].replace('Z', '+00:00'))
            
            recurrence = window.get("recurrence", "none")
            
            if recurrence == "none":
                if start <= now <= end:
                    return True
            elif recurrence == "daily":
                # Check if time of day is within range
                now_time = now.time()
                start_time = start.time()
                end_time = end.time()
                if start_time <= now_time <= end_time:
                    return True
            elif recurrence == "weekly":
                # Check day of week and time of day
                if now.weekday() in window.get("days_of_week", []):
                    now_time = now.time()
                    start_time = start.time()
                    end_time = end.time()
                    if start_time <= now_time <= end_time:
                        return True
            # Monthly can be more complex, skipping for MVP
            
        return False

def get_maintenance_service(db):
    return MaintenanceService(db)
