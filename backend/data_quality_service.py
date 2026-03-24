from typing import Dict, Any, List, Optional
from datetime import datetime, timezone

class DataQualityService:
    def __init__(self):
        self.quarantine = [] # In-memory quarantine for demo

    def validate_schema(self, data: Dict[str, Any], required_fields: List[str]) -> bool:
        """Check if data contains all required fields"""
        for field in required_fields:
            if field not in data:
                return False
        return True

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
        avg_completeness = total_completeness / len(dataset)
        
        # Simple scoring logic: Quality is mostly based on completeness for now
        return min(100.0, max(0.0, avg_completeness))

    def quarantine_data(self, data: Dict[str, Any], reason: str):
        """Move invalid records to quarantine"""
        record = {
            "data": data,
            "reason": reason,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
        self.quarantine.append(record)

    def get_quarantined_items(self) -> List[Dict[str, Any]]:
        return self.quarantine

# Global instance
quality_service = DataQualityService()
