import uuid
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional
from database import get_database

class IngestService:
    """
    Handles normalization, validation, and storage of security logs from diverse sources.
    Targets the OCSF (Open Cybersecurity Schema Framework) for standardization.
    """

    async def ingest_raw_log(self, tenant_id: str, source: str, raw_data: Dict[str, Any]):
        """
        Main entry point for log ingestion.
        """
        normalized_event = self.normalize_to_ocsf(source, raw_data)
        normalized_event["tenantId"] = tenant_id
        normalized_event["ingestedAt"] = datetime.now(timezone.utc).isoformat()
        normalized_event["id"] = str(uuid.uuid4())

        db = get_database()
        if db:
            await db.security_events.insert_one(normalized_event)
        
        return normalized_event["id"]

    def normalize_to_ocsf(self, source: str, raw: Dict[str, Any]) -> Dict[str, Any]:
        """
        Maps source-specific fields to OCSF-like standardized fields.
        """
        event = {
            "metadata": {
                "version": "1.1.0",
                "product": source,
            },
            "time": raw.get("timestamp") or raw.get("time") or datetime.now(timezone.utc).isoformat(),
            "status": "Success",
            "severity": self._map_severity(raw.get("severity", "Informational")),
        }

        if source == "okta":
            event.update({
                "category_name": "Identity & Access Management",
                "class_name": "Authentication",
                "actor": {
                    "user": {"name": raw.get("actor", {}).get("alternateId")},
                    "id": raw.get("actor", {}).get("id")
                },
                "activity_name": raw.get("eventType"),
                "message": raw.get("displayMessage")
            })
        elif source == "syslog":
            event.update({
                "category_name": "System Activity",
                "class_name": "Process Usage",
                "message": raw.get("message"),
                "device": {"hostname": raw.get("hostname")},
                "process": {"name": raw.get("app_name"), "pid": raw.get("procid")}
            })
        elif source == "cloudtrail":
            event.update({
                "category_name": "Cloud Activity",
                "class_name": "API Activity",
                "activity_name": raw.get("eventName"),
                "actor": {"user": {"name": raw.get("userIdentity", {}).get("arn")}},
                "resources": raw.get("resources", []),
                "message": f"AWS API Call: {raw.get('eventName')}"
            })
        else:
            event.update({
                "category_name": "Generic",
                "class_name": "Raw Event",
                "message": str(raw)
            })

        return event

    def _map_severity(self, raw_severity: str) -> str:
        s = str(raw_severity).lower()
        if any(keyword in s for keyword in ["crit", "fatal", "emerg"]): return "Critical"
        if any(keyword in s for keyword in ["err", "fail", "alert"]): return "High"
        if any(keyword in s for keyword in ["warn", "notice"]): return "Medium"
        return "Low"

    async def get_security_events(self, tenant_id: str, limit: int = 100, skip: int = 0):
        db = get_database()
        if not db:
            return []
            
        query = {"tenantId": tenant_id} if tenant_id != "platform-admin" else {}
        cursor = db.security_events.find(query)\
            .sort("time", -1)\
            .skip(skip)\
            .limit(limit)
        events = await cursor.to_list(length=limit)
        # Convert ObjectId to string for JSON serialization
        for e in events:
            e["_id"] = str(e["_id"])
        return events

ingest_service = IngestService()
