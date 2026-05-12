"""Database Activity Monitoring (DAM) service."""
from datetime import datetime, timezone, timedelta
import uuid


RISK_RULES = [
    {"id": "bulk_delete", "name": "Bulk DELETE operation", "severity": "critical",
     "match": lambda q: q.get("operation") == "DELETE" and q.get("rows_affected", 0) > 1000},
    {"id": "schema_change", "name": "Schema modification (DDL)", "severity": "high",
     "match": lambda q: q.get("operation") in ["ALTER", "DROP", "TRUNCATE"]},
    {"id": "off_hours", "name": "Off-hours privileged access", "severity": "high",
     "match": lambda q: q.get("hour", 12) not in range(8, 18) and q.get("user_privilege") == "admin"},
    {"id": "new_user_access", "name": "First-time user accessing sensitive table", "severity": "medium",
     "match": lambda q: q.get("first_access", False)},
    {"id": "high_row_count", "name": "Unusually large SELECT", "severity": "medium",
     "match": lambda q: q.get("operation") == "SELECT" and q.get("rows_returned", 0) > 50000},
]


class DAMService:
    def __init__(self, db):
        self.db = db
        self.col_queries = db["dam_query_log"]
        self.col_alerts = db["dam_alerts"]
        self.col_policies = db["dam_policies"]

    async def log_query(self, tenant_id: str, entry: dict):
        doc = {
            "_id": str(uuid.uuid4()),
            "tenant_id": tenant_id,
            "database": entry.get("database", "unknown"),
            "user": entry.get("user", "unknown"),
            "user_privilege": entry.get("user_privilege", "standard"),
            "operation": entry.get("operation", "SELECT").upper(),
            "table": entry.get("table", ""),
            "query_hash": entry.get("query_hash", ""),
            "rows_affected": entry.get("rows_affected", 0),
            "rows_returned": entry.get("rows_returned", 0),
            "duration_ms": entry.get("duration_ms", 0),
            "source_ip": entry.get("source_ip", ""),
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "hour": datetime.now(timezone.utc).hour,
            "first_access": entry.get("first_access", False),
            "risk_score": 0.0,
            "triggered_rules": [],
        }
        triggered = []
        for rule in RISK_RULES:
            try:
                if rule["match"](doc):
                    triggered.append({"id": rule["id"], "name": rule["name"], "severity": rule["severity"]})
            except Exception:
                pass
        doc["triggered_rules"] = triggered
        doc["risk_score"] = max(
            ({"critical": 1.0, "high": 0.8, "medium": 0.5, "low": 0.2}.get(r["severity"], 0) for r in triggered),
            default=0.0
        )
        await self.col_queries.insert_one(doc)
        if triggered:
            for rule in triggered:
                alert = {
                    "_id": str(uuid.uuid4()),
                    "tenant_id": tenant_id,
                    "rule_id": rule["id"],
                    "rule_name": rule["name"],
                    "severity": rule["severity"],
                    "user": doc["user"],
                    "database": doc["database"],
                    "table": doc["table"],
                    "operation": doc["operation"],
                    "detected_at": doc["timestamp"],
                    "status": "open",
                    "query_id": doc["_id"],
                }
                await self.col_alerts.insert_one(alert)
        return doc

    async def get_query_log(self, tenant_id: str, database: str = None, limit: int = 100):
        q = {"tenant_id": tenant_id}
        if database:
            q["database"] = database
        cursor = self.col_queries.find(q).sort("timestamp", -1).limit(limit)
        return await cursor.to_list(length=limit)

    async def get_alerts(self, tenant_id: str, severity: str = None, limit: int = 50):
        q = {"tenant_id": tenant_id}
        if severity:
            q["severity"] = severity
        cursor = self.col_alerts.find(q).sort("detected_at", -1).limit(limit)
        return await cursor.to_list(length=limit)

    async def get_summary(self, tenant_id: str):
        now = datetime.now(timezone.utc)
        since_24h = (now - timedelta(hours=24)).isoformat()
        total_queries = await self.col_queries.count_documents({"tenant_id": tenant_id, "timestamp": {"$gte": since_24h}})
        risky = await self.col_queries.count_documents({"tenant_id": tenant_id, "risk_score": {"$gte": 0.5}, "timestamp": {"$gte": since_24h}})
        open_alerts = await self.col_alerts.count_documents({"tenant_id": tenant_id, "status": "open"})
        critical_alerts = await self.col_alerts.count_documents({"tenant_id": tenant_id, "status": "open", "severity": "critical"})
        return {
            "queries_24h": total_queries,
            "risky_queries_24h": risky,
            "open_alerts": open_alerts,
            "critical_alerts": critical_alerts,
        }

    async def seed_demo_data(self, tenant_id: str):
        # Deterministic query log — fixed records that exercise all RISK_RULES
        query_records = [
            # (database,   user,         privilege,  operation, table,       rows_aff, rows_ret, dur_ms, source_ip,     first, hour)
            ("prod_db",   "app_user",   "standard", "SELECT",  "users",          0,    1200,    45,   "10.0.1.10",  False, 10),
            ("prod_db",   "app_user",   "standard", "INSERT",  "audit_logs",     1,       0,    12,   "10.0.1.10",  False, 11),
            ("prod_db",   "etl_job",    "standard", "SELECT",  "payments",       0,   75000,   980,   "10.0.2.5",   False, 14),  # high_row_count
            ("analytics", "readonly_svc","standard","SELECT",  "pii_data",       0,      50,    89,   "10.0.3.21",  True,  15),  # first_access
            ("prod_db",   "dba",        "admin",    "ALTER",   "users",          0,       0,   200,   "10.0.0.5",   False, 23),  # schema_change + off_hours
            ("auth_db",   "admin",      "admin",    "SELECT",  "sessions",       0,     320,    55,   "10.0.0.5",   False,  2),  # off_hours
            ("prod_db",   "etl_job",    "standard", "DELETE",  "audit_logs",  2500,       0,   340,   "10.0.2.5",   False, 16),  # bulk_delete
            ("analytics", "app_user",   "standard", "UPDATE",  "api_keys",       3,       0,    20,   "10.0.1.12",  False,  9),
            ("prod_db",   "dba",        "admin",    "DROP",    "temp_tokens",    0,       0,   150,   "10.0.0.5",   False, 22),  # schema_change + off_hours
            ("auth_db",   "readonly_svc","standard","SELECT",  "users",          0,      80,    34,   "10.0.3.21",  True,  13),  # first_access
            ("prod_db",   "app_user",   "standard", "SELECT",  "payments",       0,    4500,   123,   "10.0.1.10",  False, 10),
            ("analytics", "etl_job",    "standard", "INSERT",  "pii_data",      45,       0,    67,   "10.0.2.5",   False, 16),
            ("prod_db",   "admin",      "admin",    "TRUNCATE","temp_imports",   0,       0,   180,   "10.0.0.5",   False,  1),  # schema_change + off_hours
            ("auth_db",   "app_user",   "standard", "SELECT",  "api_keys",       0,      12,    18,   "10.0.1.11",  False, 14),
            ("prod_db",   "etl_job",    "standard", "SELECT",  "audit_logs",     0,   90000,  2200,   "10.0.2.5",   False, 11),  # high_row_count
        ]
        for db, user, priv, op, table, rows_aff, rows_ret, dur, ip, first, hour in query_records:
            await self.log_query(tenant_id, {
                "database": db,
                "user": user,
                "user_privilege": priv,
                "operation": op,
                "table": table,
                "rows_affected": rows_aff,
                "rows_returned": rows_ret,
                "duration_ms": dur,
                "source_ip": ip,
                "first_access": first,
                "hour": hour,
            })

