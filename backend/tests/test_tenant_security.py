"""
Additional tenant isolation security tests — cross-tenant bypass scenarios,
insert stamping, aggregate pipeline injection, and update filter guarding.

These complement test_tenant_isolation.py with adversarial / edge-case
scenarios that exercise the fail-closed behaviour from multiple angles.
"""
import sys
import os
import asyncio

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from unittest.mock import AsyncMock, MagicMock


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_col():
    col = MagicMock()
    col.find_one = AsyncMock(return_value=None)
    col.find = MagicMock(return_value=MagicMock())
    col.insert_one = AsyncMock(return_value=MagicMock(inserted_id="mock-id"))
    col.insert_many = AsyncMock()
    col.update_one = AsyncMock(return_value=MagicMock(modified_count=1))
    col.delete_one = AsyncMock(return_value=MagicMock(deleted_count=1))
    col.count_documents = AsyncMock(return_value=0)
    col.aggregate = MagicMock(return_value=MagicMock())
    col.name = "mock_collection"
    return col


# ===========================================================================
# Cross-tenant bypass — attacker tries to override tenantId in the query
# ===========================================================================

class TestCrossTenantBypassPrevention:

    def test_attacker_supplied_tenant_id_is_overwritten_on_find(self):
        """Attacker-controlled tenantId in query must be replaced by the context var."""
        from database import TenantIsolatedCollection
        from tenant_context import set_tenant_id

        set_tenant_id("tenant-a")
        inner = _make_col()
        col = TenantIsolatedCollection(inner)

        # Attacker tries to inject a different tenant
        result_filter = col._inject_tenant_id({"tenantId": "tenant-b", "id": "secret-doc"})

        assert result_filter["tenantId"] == "tenant-a", (
            "Context-var tenant must win over attacker-supplied tenantId"
        )

    def test_attacker_supplied_tenant_id_overwrite_on_async_find_one(self):
        """The overwrite must also happen through the async find_one code path."""
        from database import TenantIsolatedCollection
        from tenant_context import set_tenant_id

        set_tenant_id("tenant-a")
        inner = _make_col()
        col = TenantIsolatedCollection(inner)

        asyncio.run(col.find_one({"tenantId": "tenant-b"}))

        sent_filter = inner.find_one.call_args[0][0]
        assert sent_filter["tenantId"] == "tenant-a", (
            f"Cross-tenant bypass via find_one: sent tenantId={sent_filter.get('tenantId')}"
        )

    def test_attacker_supplied_tenant_id_overwrite_on_update_one(self):
        """update_one filter must also enforce the context tenant."""
        from database import TenantIsolatedCollection
        from tenant_context import set_tenant_id

        set_tenant_id("tenant-a")
        inner = _make_col()
        col = TenantIsolatedCollection(inner)

        asyncio.run(col.update_one({"tenantId": "tenant-b", "id": "x"}, {"$set": {"foo": "bar"}}))

        sent_filter = inner.update_one.call_args[0][0]
        assert sent_filter["tenantId"] == "tenant-a"

    def test_attacker_supplied_tenant_id_overwrite_on_delete_one(self):
        """delete_one filter must also enforce the context tenant."""
        from database import TenantIsolatedCollection
        from tenant_context import set_tenant_id

        set_tenant_id("tenant-a")
        inner = _make_col()
        col = TenantIsolatedCollection(inner)

        asyncio.run(col.delete_one({"tenantId": "tenant-b", "id": "x"}))

        sent_filter = inner.delete_one.call_args[0][0]
        assert sent_filter["tenantId"] == "tenant-a"


# ===========================================================================
# insert_one / insert_many — tenant stamping
# ===========================================================================

class TestInsertTenantStamping:

    def test_insert_one_stamps_tenant_id(self):
        """insert_one must stamp tenantId onto the document."""
        from database import TenantIsolatedCollection
        from tenant_context import set_tenant_id

        set_tenant_id("tenant-b")
        inner = _make_col()
        col = TenantIsolatedCollection(inner)

        asyncio.run(col.insert_one({"name": "test-asset"}))

        doc_inserted = inner.insert_one.call_args[0][0]
        assert doc_inserted.get("tenantId") == "tenant-b", (
            f"tenantId not stamped on insert_one: got {doc_inserted}"
        )

    def test_insert_one_without_tenant_uses_orphan_sentinel(self):
        """insert_one with no tenant context must stamp ORPHANED sentinel, not empty."""
        from database import TenantIsolatedCollection
        from tenant_context import set_tenant_id

        set_tenant_id(None)
        inner = _make_col()
        col = TenantIsolatedCollection(inner)

        asyncio.run(col.insert_one({"name": "orphan-doc"}))

        doc_inserted = inner.insert_one.call_args[0][0]
        tenant_used = doc_inserted.get("tenantId", "")
        assert tenant_used != "", "Fail-closed: empty tenant must not produce empty tenantId on insert"
        assert tenant_used != "tenant-a", "Must not use another tenant's ID"

    def test_insert_many_stamps_all_documents(self):
        """insert_many must stamp tenantId onto every document in the batch."""
        from database import TenantIsolatedCollection
        from tenant_context import set_tenant_id

        set_tenant_id("tenant-c")
        inner = _make_col()
        col = TenantIsolatedCollection(inner)

        docs = [{"name": f"doc-{i}"} for i in range(3)]
        asyncio.run(col.insert_many(docs))

        docs_inserted = inner.insert_many.call_args[0][0]
        for doc in docs_inserted:
            assert doc.get("tenantId") == "tenant-c", (
                f"insert_many did not stamp all docs: {doc}"
            )

    def test_platform_admin_insert_does_not_stamp_tenant(self):
        """Super-admin (platform-admin) inserts must not be stamped with a tenant ID."""
        from database import TenantIsolatedCollection
        from tenant_context import set_tenant_id

        set_tenant_id("platform-admin")
        inner = _make_col()
        col = TenantIsolatedCollection(inner)

        asyncio.run(col.insert_one({"name": "platform-global-doc"}))

        doc_inserted = inner.insert_one.call_args[0][0]
        # platform-admin bypass: tenantId should not be forced to platform-admin
        # (the original doc is passed as-is, or without forced override)
        assert doc_inserted.get("tenantId") != "NON_EXISTENT_TENANT_ISOLATION_EMERGENCY"
        assert doc_inserted.get("tenantId") != "ORPHANED_DATA_NO_TENANT_CONTEXT"


# ===========================================================================
# Aggregate pipeline — match stage injection
# ===========================================================================

class TestAggregatePipelineInjection:

    def test_aggregate_prepends_tenant_match_for_regular_tenant(self):
        """aggregate() must inject a $match tenantId stage at position 0."""
        from database import TenantIsolatedCollection
        from tenant_context import set_tenant_id

        set_tenant_id("tenant-x")
        inner = _make_col()
        col = TenantIsolatedCollection(inner)

        col.aggregate([{"$group": {"_id": "$status", "count": {"$sum": 1}}}])

        pipeline_sent = inner.aggregate.call_args[0][0]
        assert len(pipeline_sent) >= 2, "Pipeline must have at least 2 stages after injection"
        first_stage = pipeline_sent[0]
        assert "$match" in first_stage
        assert first_stage["$match"].get("tenantId") == "tenant-x"

    def test_aggregate_bypasses_injection_for_platform_admin(self):
        """platform-admin aggregate calls must NOT have an injected $match."""
        from database import TenantIsolatedCollection
        from tenant_context import set_tenant_id

        set_tenant_id("platform-admin")
        inner = _make_col()
        col = TenantIsolatedCollection(inner)

        original_pipeline = [{"$group": {"_id": "$tenantId", "count": {"$sum": 1}}}]
        col.aggregate(original_pipeline)

        pipeline_sent = inner.aggregate.call_args[0][0]
        # No $match stage injected — pipeline length matches original
        assert len(pipeline_sent) == 1
        assert "$match" not in pipeline_sent[0]

    def test_aggregate_no_tenant_context_uses_emergency_string(self):
        """aggregate() with no tenant context must use the emergency sentinel."""
        from database import TenantIsolatedCollection
        from tenant_context import set_tenant_id

        set_tenant_id(None)
        inner = _make_col()
        col = TenantIsolatedCollection(inner)

        col.aggregate([{"$count": "total"}])

        pipeline_sent = inner.aggregate.call_args[0][0]
        first_stage = pipeline_sent[0]
        assert "$match" in first_stage
        tenant_used = first_stage["$match"].get("tenantId", "")
        assert tenant_used == "NON_EXISTENT_TENANT_ISOLATION_EMERGENCY"


# ===========================================================================
# TenantIsolatedDatabase — routing
# ===========================================================================

class TestTenantIsolatedDatabaseRouting:

    def test_non_exempt_collection_is_wrapped(self):
        """Any collection not in the exempt list must be a TenantIsolatedCollection."""
        from database import TenantIsolatedCollection, TenantIsolatedDatabase

        raw_db = MagicMock()
        db = TenantIsolatedDatabase(raw_db)

        assert isinstance(db["security_events"], TenantIsolatedCollection)
        assert isinstance(db["assets"], TenantIsolatedCollection)
        assert isinstance(db["vulnerabilities"], TenantIsolatedCollection)
        assert isinstance(db["tickets"], TenantIsolatedCollection)

    def test_exempt_collection_bypasses_isolation(self):
        """Global reference collections (compliance_frameworks, etc.) must not be wrapped.

        DB-F10 (2026-08-25 audit): "roles" is deliberately excluded from
        this list now — a live query found it contains real tenant-specific
        role documents, so exempting it leaked one tenant's custom roles to
        every other tenant. See test_tenant_isolation.py's
        test_exempt_collections_bypass_isolation for the full rationale.
        """
        from database import TenantIsolatedCollection, TenantIsolatedDatabase

        raw_db = MagicMock()
        db = TenantIsolatedDatabase(raw_db)

        for exempt in ("compliance_frameworks", "compliance_controls",
                       "ai_governance_frameworks", "system_features",
                       "tenants", "response_policies", "playbooks"):
            col = db[exempt]
            assert not isinstance(col, TenantIsolatedCollection), (
                f"Collection '{exempt}' should bypass tenant isolation but is wrapped"
            )

        assert isinstance(db["roles"], TenantIsolatedCollection), (
            "roles must be tenant-isolated (DB-F10) — it is not purely global reference data"
        )
