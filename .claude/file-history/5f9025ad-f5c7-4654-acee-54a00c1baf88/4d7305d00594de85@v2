from motor.motor_asyncio import AsyncIOMotorClient
from typing import Optional, Any, Dict, List
import os
from dotenv import load_dotenv
from tenant_context import get_tenant_id

# Try to import mongomock for fallback
try:
    from mongomock_motor import AsyncMongoMockClient
except ImportError:
    AsyncMongoMockClient = None

class TenantIsolatedCollection:
    """
    Wrapper for Motor collection to automatically inject tenantId filter.
    Fail-Closed: If no tenant_id is found and not in platform-admin context, 
    it enforces a non-matching tenantId to prevent accidental data leakage.
    """
    def __init__(self, collection):
        self._collection = collection

    def _inject_tenant_id(self, filter_query: Dict[str, Any]) -> Dict[str, Any]:
        tenant_id = get_tenant_id()
        
        # If Super Admin, bypass isolation
        if tenant_id == "platform-admin":
            return filter_query if filter_query is not None else {}
        
        # Fail-Closed: If no tenant_id, use a dummy one that never matches
        effective_tenant_id = tenant_id if tenant_id else "NON_EXISTENT_TENANT_ISOLATION_EMERGENCY"
        
        new_filter = filter_query.copy() if filter_query else {}
        new_filter["tenantId"] = effective_tenant_id
        
        import logging
        if not tenant_id:
            logging.error(f"[SECURITY ALERT] DB Access without tenant context on collection: {self._collection.name}")
            
        return new_filter

    def find(self, filter=None, *args, **kwargs):
        return self._collection.find(self._inject_tenant_id(filter), *args, **kwargs)

    async def find_one(self, filter=None, *args, **kwargs):
        return await self._collection.find_one(self._inject_tenant_id(filter), *args, **kwargs)

    async def insert_one(self, document, *args, **kwargs):
        tenant_id = get_tenant_id()
        if tenant_id and tenant_id != "platform-admin":
            document["tenantId"] = tenant_id
        elif not tenant_id:
            # Prevent insertion without tenant context
            document["tenantId"] = "ORPHANED_DATA_NO_TENANT_CONTEXT"
        return await self._collection.insert_one(document, *args, **kwargs)

    async def insert_many(self, documents, *args, **kwargs):
        tenant_id = get_tenant_id()
        for doc in documents:
            if tenant_id and tenant_id != "platform-admin":
                doc["tenantId"] = tenant_id
            elif not tenant_id:
                doc["tenantId"] = "ORPHANED_DATA_NO_TENANT_CONTEXT"
        return await self._collection.insert_many(documents, *args, **kwargs)

    async def update_one(self, filter, update, *args, **kwargs):
        return await self._collection.update_one(self._inject_tenant_id(filter), update, *args, **kwargs)

    async def update_many(self, filter, update, *args, **kwargs):
        return await self._collection.update_many(self._inject_tenant_id(filter), update, *args, **kwargs)

    async def replace_one(self, filter, replacement, *args, **kwargs):
        tenant_id = get_tenant_id()
        if tenant_id and tenant_id != "platform-admin":
            replacement["tenantId"] = tenant_id
        return await self._collection.replace_one(self._inject_tenant_id(filter), replacement, *args, **kwargs)

    async def delete_one(self, filter, *args, **kwargs):
        return await self._collection.delete_one(self._inject_tenant_id(filter), *args, **kwargs)

    async def delete_many(self, filter, *args, **kwargs):
        return await self._collection.delete_many(self._inject_tenant_id(filter), *args, **kwargs)

    async def count_documents(self, filter, *args, **kwargs):
        return await self._collection.count_documents(self._inject_tenant_id(filter), *args, **kwargs)

    async def distinct(self, key, filter=None, *args, **kwargs):
        return await self._collection.distinct(key, self._inject_tenant_id(filter), *args, **kwargs)

    async def find_one_and_update(self, filter, update, *args, **kwargs):
        return await self._collection.find_one_and_update(self._inject_tenant_id(filter), update, *args, **kwargs)

    def aggregate(self, pipeline: List[Dict[str, Any]], *args, **kwargs):
        """
        Injects a $match stage at the beginning of the aggregation pipeline for tenant isolation.
        """
        tenant_id = get_tenant_id()
        
        if tenant_id != "platform-admin":
            effective_tenant_id = tenant_id if tenant_id else "NON_EXISTENT_TENANT_ISOLATION_EMERGENCY"
            match_stage = {"$match": {"tenantId": effective_tenant_id}}
            # Prepend the match stage
            pipeline = [match_stage] + pipeline
            
        return self._collection.aggregate(pipeline, *args, **kwargs)

    def __getattr__(self, name):
        # Fallback for other methods/attributes
        return getattr(self._collection, name)

class TenantIsolatedDatabase:
    """
    Wrapper for Motor database to return isolated collections.
    """
    def __init__(self, db):
        self._db = db

    def __getattr__(self, name):
        collection = getattr(self._db, name)
        # We only wrap actual collections, not internal methods
        if name.startswith("_") or name in ["client", "name", "codec_options", "read_preference", "write_concern", "read_concern", "list_collection_names", "create_collection", "drop_collection", "validate_collection", "command", "dereference"]:
            return collection
        # EXEMPTION: global reference data (shared across all tenants)
        if name in [
            "compliance_frameworks",
            "compliance_controls",
            "ai_governance_frameworks",
            "system_features",
            "tenants",
            "roles",
            "response_policies",  # platform-level security policies, seeded globally
            "playbooks",          # platform-seeded playbooks shared across tenants
            "ip_bans",            # platform-wide IP block list, checked before tenant context is set
            "crypto_inventory",   # platform-wide PQC inventory seeded at startup
        ]:
            return collection
        return TenantIsolatedCollection(collection)

    def __getitem__(self, name):
        # EXEMPTION: global reference data (shared across all tenants)
        if name in [
            "compliance_frameworks",
            "compliance_controls",
            "ai_governance_frameworks",
            "system_features",
            "tenants",
            "roles",
            "response_policies",  # platform-level security policies, seeded globally
            "playbooks",          # platform-seeded playbooks shared across tenants
            "ip_bans",            # platform-wide IP block list, checked before tenant context is set
            "crypto_inventory",   # platform-wide PQC inventory seeded at startup
        ]:
            return self._db[name]
        return TenantIsolatedCollection(self._db[name])

load_dotenv()

class MongoDB:
    client: Optional[AsyncIOMotorClient] = None
    db = None

mongodb = MongoDB()
db = None  # Global compatibility reference
_demo_mode: bool = False  # Set to True when running against in-memory mock


def is_demo_mode() -> bool:
    """Return True if the app is running against the in-memory mock database."""
    return _demo_mode

async def connect_to_mongo():
    """Connect to MongoDB with exponential-backoff retry (3 attempts)."""
    import logging as _logging
    import asyncio as _asyncio

    mongodb_url = os.getenv("MONGODB_URL", "mongodb://localhost:27017").strip()
    mongodb_db_name = os.getenv("MONGODB_DB_NAME", "omni_platform")
    max_attempts = 3
    base_delay = 0.5  # seconds

    last_exc: Exception | None = None
    for attempt in range(1, max_attempts + 1):
        try:
            client = AsyncIOMotorClient(mongodb_url, serverSelectionTimeoutMS=3000)
            await client.server_info()
            mongodb.client = client
            _logging.getLogger(__name__).info(
                "[DATABASE] Connected to MongoDB at %s (attempt %d/%d)", mongodb_url, attempt, max_attempts
            )
            last_exc = None
            break
        except Exception as exc:
            last_exc = exc
            _logging.getLogger(__name__).warning(
                "[DATABASE] MongoDB connection attempt %d/%d failed: %s", attempt, max_attempts, exc
            )
            if attempt < max_attempts:
                await _asyncio.sleep(base_delay * (2 ** (attempt - 1)))

    if last_exc is not None:
        _logging.getLogger(__name__).critical(
            "[DATABASE] MongoDB unreachable after %d attempts (%s). "
            "All data written this session will be LOST on restart.",
            max_attempts, mongodb_url,
        )
        if os.getenv("ALLOW_MOCK_DB", "false").lower() in ("1", "true", "yes"):
            if AsyncMongoMockClient:
                _logging.getLogger(__name__).warning(
                    "⚠️  Running in DEMO MODE — data is not persisted. Set MONGODB_URL to use a real database."
                )
                mongodb.client = AsyncMongoMockClient()
                global _demo_mode
                _demo_mode = True
            else:
                raise last_exc
        else:
            raise last_exc

    mongodb.db = mongodb.client[mongodb_db_name]
    global db
    db = mongodb.db
    
    # Create indexes
    try:
        await mongodb.db.agents.create_index("hostname")
        await mongodb.db.agents.create_index("tenantId")
    
        await mongodb.db.assets.create_index("hostname")
        await mongodb.db.assets.create_index("tenantId")
        await mongodb.db.assets.create_index("id", unique=True)
        await mongodb.db.vulnerabilities.create_index("assetId")
        await mongodb.db.patches.create_index("tenantId")
        await mongodb.db.security_events.create_index("tenantId")
        await mongodb.db.security_cases.create_index("tenantId")
        await mongodb.db.audit_logs.create_index("tenantId")
        await mongodb.db.tenants.create_index("id", unique=True)
        await mongodb.db.tenants.create_index("name", unique=True)
        await mongodb.db.users.create_index("email", unique=True)
        await mongodb.db.users.create_index("tenantId")
        await mongodb.db.playbooks.create_index("tenantId")
        await mongodb.db.notifications.create_index("tenantId")
        await mongodb.db.cloud_accounts.create_index("tenantId")
        await mongodb.db.system_features.create_index("id", unique=True)
        await mongodb.db.system_features.create_index("category")
        await mongodb.db.usage_records.create_index("tenantId")
        await mongodb.db.usage_records.create_index("timestamp")
        await mongodb.db.compliance_evidence.create_index("tenantId")
        await mongodb.db.compliance_evidence.create_index("controlId")
        # Metrics time-series collections
        await mongodb.db.asset_metrics.create_index([("asset_id", 1), ("timestamp", -1)])
        await mongodb.db.agent_metrics_history.create_index([("agent_id", 1), ("timestamp", -1)])

        # Compound indexes for high-traffic event/alert collections
        await mongodb.db.security_events.create_index([("tenantId", 1), ("timestamp", -1)])
        await mongodb.db.audit_logs.create_index([("tenantId", 1), ("timestamp", -1)])
        await mongodb.db.fim_events.create_index([("tenantId", 1), ("timestamp", -1)])
        await mongodb.db.edr_telemetry.create_index([("tenantId", 1), ("timestamp", -1)])
        await mongodb.db.threat_alerts.create_index([("tenantId", 1), ("timestamp", -1)])
        await mongodb.db.threat_alerts.create_index([("tenantId", 1), ("severity", 1)])
        await mongodb.db.correlation_rules.create_index([("tenantId", 1), ("enabled", 1)])
        await mongodb.db.pentest_jobs.create_index([("tenant_id", 1), ("status", 1)])
        await mongodb.db.pentest_jobs.create_index([("tenant_id", 1), ("created_at", -1)])
        await mongodb.db.patches.create_index([("tenantId", 1), ("status", 1)])
        await mongodb.db.vulnerabilities.create_index([("tenantId", 1), ("severity", 1)])
        await mongodb.db.compliance_evidence.create_index([("tenantId", 1), ("controlId", 1)])
        # evidence_audit_log: CoC collection — no expiry index; compliance audit trails
        # must be retained long-term and must not be auto-purged.
        await mongodb.db.evidence_audit_log.create_index([("evidenceId", 1), ("tenantId", 1)])
        await mongodb.db.evidence_audit_log.create_index([("tenantId", 1), ("timestamp", -1)])
        await mongodb.db.tickets.create_index([("tenantId", 1), ("status", 1)])
        await mongodb.db.tickets.create_index([("tenantId", 1), ("created_at", -1)])
        await mongodb.db.tickets.create_index([("tenantId", 1), ("priority", 1)])
        await mongodb.db.tickets.create_index("id", unique=True)
        # Indexes for ticket report queries (sla, resolution time, assignee workload, ageing)
        await mongodb.db.tickets.create_index([("tenantId", 1), ("sla_status", 1)])
        await mongodb.db.tickets.create_index([("tenantId", 1), ("resolved_at", -1)])
        await mongodb.db.tickets.create_index([("tenantId", 1), ("assignee", 1)])
        await mongodb.db.tickets.create_index([("tenantId", 1), ("due_date", 1), ("status", 1)])
        await mongodb.db.tickets.create_index([("tenantId", 1), ("escalated", 1)])

        # software_inventory: compound unique index so per-heartbeat upserts are O(1) not O(n)
        await mongodb.db.software_inventory.create_index(
            [("agent_id", 1), ("name", 1)], unique=True, background=True
        )

        # TTL indexes — auto-expire high-volume event data to prevent unbounded growth
        await mongodb.db.security_events.create_index("timestamp", expireAfterSeconds=7776000)   # 90 days
        await mongodb.db.audit_logs.create_index("timestamp", expireAfterSeconds=15552000)       # 180 days
        await mongodb.db.edr_telemetry.create_index("timestamp", expireAfterSeconds=2592000)     # 30 days
        await mongodb.db.fim_events.create_index("timestamp", expireAfterSeconds=7776000)        # 90 days

        # TTL indexes for auth/security collections that previously grew unboundedly.
        # login_attempts: brute-force records expire after 24 h (longer than any lockout window)
        await mongodb.db.login_attempts.create_index("last_attempt", expireAfterSeconds=86400)
        # password_reset_tokens: tokens are short-lived; purge after 1 h regardless
        await mongodb.db.password_reset_tokens.create_index("created_at", expireAfterSeconds=3600)
        # revoked_tokens: only needs to outlive the longest possible access-token TTL (24 h)
        await mongodb.db.revoked_tokens.create_index("revoked_at", expireAfterSeconds=86400)
        # report_delivery_logs: compound index for per-schedule history queries (SCHED-02)
        await mongodb.db.report_delivery_logs.create_index(
            [("schedule_id", 1), ("run_at", -1)],
            name="schedule_history_idx",
        )
        # agent_ai_decisions: indexes for agentic AI audit log queries (AI-03)
        # NO TTL index — SOC 2 CC6.1 requires audit records are not auto-purged
        await mongodb.db.agent_ai_decisions.create_index(
            [("agent_id", 1), ("started_at", -1)],
            name="agent_ai_decisions_agent_time_idx",
        )
        await mongodb.db.agent_ai_decisions.create_index(
            [("tool_name", 1)],
            name="agent_ai_decisions_tool_idx",
        )
        await mongodb.db.agent_ai_decisions.create_index(
            [("tenantId", 1), ("started_at", -1)],
            name="agent_ai_decisions_tenant_time_idx",
        )
        await mongodb.db.agent_ai_decisions.create_index(
            [("source", 1), ("started_at", -1)],
            name="agent_ai_decisions_source_idx",
        )
    except Exception as index_error:
        import logging as _logging
        _logging.getLogger(__name__).warning(
            "[DATABASE] Index creation failed (expected with mock DB): %s", index_error
        )

    import logging as _logging
    _logging.getLogger(__name__).info("[DATABASE] Ready — using database: %s", mongodb_db_name)

async def close_mongo_connection():
    """Close MongoDB connection"""
    if mongodb.client:
        mongodb.client.close()
        import logging as _logging
        _logging.getLogger(__name__).info("[DATABASE] MongoDB connection closed")

def get_database():
    """Get database instance with tenant isolation"""
    if mongodb.db is None:
        raise RuntimeError(
            "Database not connected. The server is still starting up or MongoDB is unreachable."
        )
    return TenantIsolatedDatabase(mongodb.db)

# Alias used by newer endpoint files as a FastAPI Depends target
def get_db():
    """FastAPI dependency that returns the tenant-isolated database."""
    return get_database()
