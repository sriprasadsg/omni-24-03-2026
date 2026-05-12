"""Insider Threat Detection Service — behavioral scoring, risk ranking."""
from datetime import datetime, timezone, timedelta
import uuid


RISK_INDICATORS = [
    {"id": "bulk_download", "name": "Bulk data download", "weight": 25, "category": "data_exfiltration"},
    {"id": "off_hours_access", "name": "Repeated off-hours system access", "weight": 15, "category": "behavioral"},
    {"id": "privilege_escalation_attempt", "name": "Failed privilege escalation", "weight": 30, "category": "access"},
    {"id": "sensitive_data_access", "name": "Access to sensitive data outside role", "weight": 20, "category": "access"},
    {"id": "usb_usage", "name": "USB/removable media usage", "weight": 20, "category": "data_exfiltration"},
    {"id": "email_forwarding", "name": "Auto-forwarding rules to external email", "weight": 35, "category": "data_exfiltration"},
    {"id": "vpn_geo_anomaly", "name": "VPN login from new geolocation", "weight": 15, "category": "access"},
    {"id": "dormant_account", "name": "Dormant account suddenly active", "weight": 20, "category": "behavioral"},
    {"id": "policy_violation", "name": "Repeated policy violations", "weight": 10, "category": "behavioral"},
    {"id": "resignation_activity", "name": "File access spike before resignation", "weight": 40, "category": "data_exfiltration"},
]


class InsiderThreatService:
    def __init__(self, db):
        self.db = db
        self.col_profiles = db["insider_threat_profiles"]
        self.col_events = db["insider_threat_events"]
        self.col_alerts = db["insider_threat_alerts"]

    async def get_profiles(self, tenant_id: str, risk_level: str = None, limit: int = 50):
        q = {"tenant_id": tenant_id}
        if risk_level:
            q["risk_level"] = risk_level
        cursor = self.col_profiles.find(q).sort("risk_score", -1).limit(limit)
        return await cursor.to_list(length=limit)

    async def get_alerts(self, tenant_id: str, limit: int = 50):
        cursor = self.col_alerts.find({"tenant_id": tenant_id}).sort("detected_at", -1).limit(limit)
        return await cursor.to_list(length=limit)

    async def get_summary(self, tenant_id: str):
        high_risk = await self.col_profiles.count_documents({"tenant_id": tenant_id, "risk_level": {"$in": ["high", "critical"]}})
        total = await self.col_profiles.count_documents({"tenant_id": tenant_id})
        open_alerts = await self.col_alerts.count_documents({"tenant_id": tenant_id, "status": "open"})
        critical_alerts = await self.col_alerts.count_documents({"tenant_id": tenant_id, "status": "open", "severity": "critical"})
        return {"total_users_monitored": total, "high_risk_users": high_risk,
                "open_alerts": open_alerts, "critical_alerts": critical_alerts}

    async def update_alert_status(self, alert_id: str, status: str, note: str = ""):
        await self.col_alerts.update_one(
            {"_id": alert_id},
            {"$set": {"status": status, "resolution_note": note, "resolved_at": datetime.now(timezone.utc).isoformat()}}
        )

    async def seed_demo_data(self, tenant_id: str):
        await self.col_profiles.delete_many({"tenant_id": tenant_id})
        await self.col_alerts.delete_many({"tenant_id": tenant_id})
        # Deterministic user profiles — fixed indicator sets by name
        user_defs = [
            ("Alice Johnson",  "Finance",     "Analyst", ["resignation_activity", "bulk_download", "email_forwarding"], 120,  30),
            ("Bob Martinez",   "Engineering", "Engineer",["off_hours_access", "vpn_geo_anomaly"],                         48, 180),
            ("Carol White",    "HR",          "Manager", ["sensitive_data_access", "policy_violation"],                   12,  90),
            ("David Kim",      "IT",          "Admin",   ["privilege_escalation_attempt", "dormant_account"],             36, 270),
            ("Eve Thompson",   "Sales",       "Analyst", [],                                                              72, 120),
            ("Frank Liu",      "Engineering", "Engineer",["usb_usage"],                                                    6, 200),
            ("Grace Patel",    "Legal",       "Analyst", ["bulk_download", "off_hours_access"],                           24, 150),
            ("Hank Brown",     "Finance",     "Manager", ["email_forwarding", "sensitive_data_access", "bulk_download"],  18,  60),
            ("Iris Chen",      "Marketing",   "Engineer",[],                                                              60, 300),
            ("Jack Wilson",    "IT",          "Admin",   ["privilege_escalation_attempt", "bulk_download", "usb_usage"],   3,  45),
        ]
        indicator_map = {ind["id"]: ind for ind in RISK_INDICATORS}
        for name, dept, role, indicator_ids, last_active_h, monitored_days in user_defs:
            indicators = [indicator_map[iid] for iid in indicator_ids if iid in indicator_map]
            score = min(sum(ind["weight"] for ind in indicators), 100)
            level = "critical" if score >= 80 else "high" if score >= 60 else "medium" if score >= 30 else "low"
            profile = {
                "_id": str(uuid.uuid4()),
                "tenant_id": tenant_id,
                "user_name": name,
                "user_email": name.lower().replace(" ", ".") + "@company.com",
                "department": dept,
                "role": role,
                "risk_score": score,
                "risk_level": level,
                "active_indicators": [{"id": i["id"], "name": i["name"], "category": i["category"]} for i in indicators],
                "last_activity": (datetime.now(timezone.utc) - timedelta(hours=last_active_h)).isoformat(),
                "monitored_since": (datetime.now(timezone.utc) - timedelta(days=monitored_days)).isoformat(),
                "alert_count": len([i for i in indicators if i["weight"] >= 20]),
            }
            await self.col_profiles.insert_one(profile)
            if level in ("critical", "high") and indicators:
                ind = indicators[0]
                alert = {
                    "_id": str(uuid.uuid4()),
                    "tenant_id": tenant_id,
                    "user_name": name,
                    "user_email": profile["user_email"],
                    "indicator": ind["id"],
                    "indicator_name": ind["name"],
                    "category": ind["category"],
                    "severity": "critical" if score >= 80 else "high",
                    "risk_score": score,
                    "description": f"{ind['name']} detected for {name}",
                    "detected_at": (datetime.now(timezone.utc) - timedelta(hours=last_active_h // 2 + 1)).isoformat(),
                    "status": "open",
                    "profile_id": profile["_id"],
                }
                await self.col_alerts.insert_one(alert)

