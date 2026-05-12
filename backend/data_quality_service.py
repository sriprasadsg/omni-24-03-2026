from typing import Dict, Any, List
from datetime import datetime, timezone
from database import get_database


class DataQualityService:
    def validate_schema(self, data: Dict[str, Any], required_fields: List[str]) -> bool:
        """Check if data contains all required fields"""
        return all(field in data for field in required_fields)

    def check_completeness(self, data: Dict[str, Any]) -> float:
        """Calculate percentage of non-null fields"""
        if not data:
            return 0.0
        total = len(data)
        filled = sum(1 for v in data.values() if v is not None and v != "")
        return (filled / total) * 100

    def calculate_quality_score(self, dataset: List[Dict[str, Any]]) -> float:
        """Calculate overall quality score (0-100) for a dataset"""
        if not dataset:
            return 100.0
        total_completeness = sum(self.check_completeness(d) for d in dataset)
        return min(100.0, max(0.0, total_completeness / len(dataset)))

    async def quarantine_data(self, data: Dict[str, Any], reason: str):
        """Persist invalid record to MongoDB quarantine collection"""
        db = get_database()
        record = {
            "data": data,
            "reason": reason,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        await db.data_quarantine.insert_one(record)

    async def get_quarantined_items(self) -> List[Dict[str, Any]]:
        """Return quarantined records from MongoDB"""
        db = get_database()
        return await db.data_quarantine.find({}, {"_id": 0}).sort("timestamp", -1).to_list(length=500)


quality_service = DataQualityService()
