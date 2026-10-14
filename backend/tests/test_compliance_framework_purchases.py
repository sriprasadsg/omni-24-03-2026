"""Per-tenant compliance framework purchases: $5+ per-framework prices, Super Admin
selection, tenant visibility, invoices.

Each test states its card: protects=<observable>; fails_when=<wrong result it rejects>;
no_claim=<what green does not prove>. Real MongoDB (a throwaway omni_test_* database per
test, dropped afterwards; skips without a server) unless a test says otherwise.
"""
import importlib
import os
import sys
from unittest.mock import AsyncMock, patch

import httpx
import jwt
import pytest
from fastapi import FastAPI, HTTPException

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import compliance_purchases as cp
from auth_types import TokenData
import authentication_service
from database import TenantIsolatedDatabase
from finops_service import FinOpsService
from tenant_context import reset_tenant_id, set_tenant_id
from tests._mongo_test_db import mongo_db  # noqa: F401  (fixture)

CATALOGUE = [{"id": "soc2", "name": "SOC 2 Type II"}, {"id": "iso27001", "name": "ISO/IEC 27001:2022"},
             {"id": "hipaa", "name": "HIPAA Security Rule"}]


async def _seed(db, purchased=None):
    await db.compliance_frameworks.insert_many([dict(f, controls=[]) for f in CATALOGUE]
                                               + [{"id": "acme-custom", "name": "Acme internal", "tenantId": "tenant-a"},
                                                  {"id": "other-custom", "name": "Other internal", "tenantId": "tenant-b"}])
    tenant = {"id": "tenant-a", "name": "Acme", "subscriptionTier": "Free"}
    if purchased is not None:
        tenant["purchasedFrameworks"] = purchased
    await db.tenants.insert_many([tenant, {"id": "tenant-b", "name": "Other"}])


class _Context:
    def __init__(self, tenant_id):
        self.tenant_id = tenant_id

    def __enter__(self):
        self.token = set_tenant_id(self.tenant_id)

    def __exit__(self, *exc):
        reset_tenant_id(self.token)


# ── Prices ────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("entry,ok", [
    ({"category": "Compliance", "price": 5}, True), ({"category": "Compliance", "price": 4.99}, False),
    ({"frameworkId": "soc2", "category": "Security", "price": 4}, False), ({"category": "Security", "price": 0}, True),
    ({"category": "Security", "price": -1}, False), ({"category": "Security", "price": float("nan")}, False),
    ({"category": "Security", "price": "x"}, False),
])
def test_price_rule(entry, ok):
    """protects=a compliance price is never below $5.00 and no price is negative or not a number;
    fails_when=$4.99 compliance or a NaN price is accepted; no_claim=MongoDB (pure function)."""
    if ok:
        cp.check_price(entry)
    else:
        with pytest.raises(ValueError):
            cp.check_price(entry)


async def test_price_list_has_one_5_dollar_entry_per_catalogue_framework(mongo_db):
    """protects=Service Pricing lists every catalogue framework at $5.00 per tenant per month, no
    tenant-owned framework, none of the replaced generic entries, and the built-in services once;
    fails_when=a framework is missing, a custom framework is priced, or $200 Compliance Automation
    is still listed; no_claim=the pricing page rendering."""
    await _seed(mongo_db)
    await mongo_db.service_pricing.insert_one({"id": "price-soc2", "name": "SOC 2 Automation",
                                               "category": "Compliance", "unit": "per_month", "price": 500})
    service = FinOpsService()
    first = await service.get_service_pricing(mongo_db)
    second = await service.get_service_pricing(mongo_db)
    frameworks = {e["frameworkId"]: e for e in first if e.get("frameworkId")}
    assert set(frameworks) == {"soc2", "iso27001", "hipaa"}
    assert all(e["price"] == 5.0 and e["unit"] == cp.UNIT and e["category"] == "Compliance" for e in frameworks.values())
    assert not {e["id"] for e in first} & cp.LEGACY_PRICE_IDS
    assert len(first) == len(second) and len({e["id"] for e in first}) == len(first)


async def test_a_framework_price_change_survives_a_restart_and_keeps_its_floor(mongo_db):
    """protects=the Super Admin can raise a framework's price, it is stored (a fresh service instance
    reads it back), it cannot go below $5, and its category/unit cannot be changed; fails_when=prices
    live only in memory or $3 is saved; no_claim=none beyond protects."""
    await _seed(mongo_db)
    service = FinOpsService()
    with pytest.raises(HTTPException) as low:
        await service.update_service_pricing(mongo_db, "compliance-soc2", {"price": 3})
    assert low.value.status_code == 400
    await service.update_service_pricing(mongo_db, "compliance-soc2", {"price": 12.5, "unit": "per_agent", "category": "X"})
    reread = {e["id"]: e for e in await FinOpsService().get_service_pricing(mongo_db)}
    assert reread["compliance-soc2"]["price"] == 12.5
    assert (reread["compliance-soc2"]["unit"], reread["compliance-soc2"]["category"]) == (cp.UNIT, "Compliance")


async def test_pricing_writes_validate_and_framework_prices_cannot_be_removed(mongo_db):
    """protects=a framework price cannot be deleted, a $4 Compliance service cannot be created, an id
    cannot be reused, ordinary services can still be created and deleted, and a bad bulk save writes
    nothing; fails_when=any of those slips through; no_claim=none beyond protects."""
    await _seed(mongo_db)
    service = FinOpsService()
    for call, args in ((service.delete_service_pricing, ("compliance-soc2",)),
                       (service.create_service_pricing, ({"id": "c", "name": "c", "unit": "u", "category": "Compliance", "price": 4},)),
                       (service.create_service_pricing, ({"id": "compliance-hipaa", "name": "h", "unit": "u", "category": "Other", "price": 9},))):
        with pytest.raises(HTTPException):
            await call(mongo_db, *args)
    await service.create_service_pricing(mongo_db, {"id": "svc", "name": "Svc", "unit": "u", "category": "Other", "price": 1})
    assert (await service.delete_service_pricing(mongo_db, "svc"))["id"] == "svc"
    with pytest.raises(HTTPException):
        await service.save_service_pricing(mongo_db, [
            {"id": "new-ok", "name": "n", "unit": "u", "category": "Other", "price": 1},
            {"id": "compliance-iso27001", "name": "ISO", "unit": cp.UNIT, "category": "Compliance", "price": 1}])
    assert await mongo_db.service_pricing.find_one({"id": "new-ok"}) is None


async def test_migration_replaces_generic_entries_and_dedupes(mongo_db):
    """protects=migration 015 removes the generic compliance entries, collapses duplicate ids, seeds the
    built-in list and makes ids unique; fails_when=the $200 entry survives or the index build fails on
    old duplicates; no_claim=the migration runner bookkeeping."""
    await mongo_db.service_pricing.insert_many([
        {"id": "price-compliance", "price": 200}, {"id": "price-edr", "price": 8}, {"id": "price-edr", "price": 9}])
    migration = importlib.import_module("migrations.015_compliance_framework_pricing")
    await migration.up(mongo_db)
    assert await mongo_db.service_pricing.count_documents({"id": "price-compliance"}) == 0
    assert await mongo_db.service_pricing.count_documents({"id": "price-edr"}) == 1
    assert await mongo_db.service_pricing.count_documents({}) == len(FinOpsService()._defaults)
    assert any(i.get("unique") for i in (await mongo_db.service_pricing.index_information()).values())


# ── Visibility ────────────────────────────────────────────────────────────────

async def test_a_tenant_sees_only_purchased_and_own_frameworks(mongo_db):
    """protects=through the database wrapper every read style (find + to_list, async for, chained
    sort/limit, find_one, count, distinct, aggregate) gives tenant-a only its purchases and its own
    framework; fails_when=an unpurchased catalogue framework or tenant-b's framework shows;
    no_claim=reads through raw handles (db._db), which bypass the wrapper by design."""
    await _seed(mongo_db, purchased=["soc2"])
    db = TenantIsolatedDatabase(mongo_db)
    with _Context("tenant-a"):
        listed = {f["id"] for f in await db.compliance_frameworks.find({}, {"_id": 0}).to_list(length=100)}
        iterated = {f["id"] async for f in db.compliance_frameworks.find({})}
        chained = [f["id"] for f in await db.compliance_frameworks.find({}).sort("id", 1).limit(1).to_list(None)]
        assert listed == iterated == {"soc2", "acme-custom"} and chained == ["acme-custom"]
        assert await db.compliance_frameworks.find_one({"id": "iso27001"}) is None
        assert await db.compliance_frameworks.count_documents({}) == 2
        assert set(await db.compliance_frameworks.distinct("id")) == {"soc2", "acme-custom"}
        assert {d["_id"] async for d in db.compliance_frameworks.aggregate([{"$group": {"_id": "$id"}}])} == {"soc2", "acme-custom"}
    for context in ("platform-admin", None):
        with _Context(context):
            assert await db.compliance_frameworks.count_documents({}) == 5


async def test_no_purchases_means_no_catalogue_frameworks(mongo_db):
    """protects=an existing tenant with no purchasedFrameworks field sees no catalogue framework (rollout
    decision: none until ticked); fails_when=a missing list shows everything; no_claim=none beyond protects."""
    await _seed(mongo_db)
    with _Context("tenant-a"):
        assert {f["id"] async for f in TenantIsolatedDatabase(mongo_db).compliance_frameworks.find({})} == {"acme-custom"}


async def test_tenant_writes_stay_inside_its_frameworks(mongo_db):
    """protects=a tenant cannot change an unpurchased catalogue framework, and a framework it creates
    is its own rather than a new catalogue entry for everyone; fails_when=update_one reaches iso27001 or
    the new framework has no tenantId; no_claim=none beyond protects."""
    await _seed(mongo_db, purchased=["soc2"])
    db = TenantIsolatedDatabase(mongo_db)
    with _Context("tenant-a"):
        assert (await db.compliance_frameworks.update_one({"id": "iso27001"}, {"$set": {"progress": 99}})).matched_count == 0
        await db.compliance_frameworks.insert_one({"id": "acme-2", "name": "Acme two"})
    assert (await mongo_db.compliance_frameworks.find_one({"id": "acme-2"}))["tenantId"] == "tenant-a"
    assert "progress" not in await mongo_db.compliance_frameworks.find_one({"id": "iso27001"})


async def test_a_failed_purchase_lookup_fails_the_read(mongo_db):
    """protects=if the tenant's purchases cannot be read the framework read fails instead of returning
    the whole catalogue; fails_when=an error falls back to no filter; no_claim=none beyond protects."""
    await _seed(mongo_db, purchased=["soc2"])
    db = TenantIsolatedDatabase(mongo_db)
    with _Context("tenant-a"), patch.object(cp, "purchased", AsyncMock(side_effect=RuntimeError("down"))):
        with pytest.raises(RuntimeError):
            await db.compliance_frameworks.find({}).to_list(None)


def _token(role, tenant):
    # Read the signing key now, not at import: other tests may rotate it, and TenantMiddleware
    # reads the current one.
    return jwt.encode({"sub": f"{role}@x", "role": role, "tenant_id": tenant},
                      authentication_service.SECRET_KEY, algorithm=authentication_service.ALGORITHM)


async def test_the_framework_list_route_follows_the_purchase(mongo_db):
    """protects=GET /api/frameworks as a tenant user (tenant context from a real JWT through
    TenantMiddleware) lists only the purchased and own frameworks, and a platform user lists all;
    fails_when=the route still returns the 44-style full catalogue to tenants; no_claim=the browser UI."""
    import compliance_frameworks_endpoints as endpoints
    from tenant_middleware import TenantMiddleware
    await _seed(mongo_db, purchased=["iso27001"])
    app = FastAPI()
    app.add_middleware(TenantMiddleware)
    app.include_router(endpoints.router)
    # The endpoint module's own reference: another test may have reloaded authentication_service.
    app.dependency_overrides[endpoints.get_current_user] = lambda: TokenData(username="u", role="Tenant Admin", tenant_id="tenant-a")
    with patch.object(endpoints, "get_database", lambda: TenantIsolatedDatabase(mongo_db)):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t") as client:
            tenant = await client.get("/api/frameworks", headers={"Authorization": f"Bearer {_token('Tenant Admin', 'tenant-a')}"})
            platform = await client.get("/api/frameworks", headers={"Authorization": f"Bearer {_token('Super Admin', 'platform-admin')}"})
    assert {f["id"] for f in tenant.json()["frameworks"]} == {"iso27001", "acme-custom"}
    assert len(platform.json()["frameworks"]) == 5


# ── Super Admin selection ────────────────────────────────────────────────────

async def test_only_the_super_admin_sets_purchases_and_ids_are_checked(mongo_db):
    """protects=PATCH /api/tenants/{id} stores de-duplicated catalogue ids for a Super Admin, refuses a
    tenant admin (403) and refuses unknown or tenant-owned ids (400); fails_when=a tenant admin buys
    its own frameworks or a typo is stored; no_claim=the Manage Tenant screen."""
    import tenant_endpoints
    await _seed(mongo_db)
    app = FastAPI()
    app.include_router(tenant_endpoints.router)
    user = {"value": TokenData(username="o", role="Super Admin", tenant_id="platform-admin")}
    app.dependency_overrides[tenant_endpoints.get_current_user] = lambda: user["value"]
    with patch.object(tenant_endpoints.mongodb, "db", mongo_db), patch.object(tenant_endpoints, "get_database", lambda: mongo_db):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t") as client:
            ok = await client.patch("/api/tenants/tenant-a", json={"purchasedFrameworks": ["soc2", "hipaa", "soc2"]})
            bad = await client.patch("/api/tenants/tenant-a", json={"purchasedFrameworks": ["soc2", "acme-custom"]})
            user["value"] = TokenData(username="a", role="Tenant Admin", tenant_id="tenant-a")
            refused = await client.patch("/api/tenants/tenant-a", json={"purchasedFrameworks": ["iso27001"]})
    assert ok.status_code == 200 and ok.json()["purchasedFrameworks"] == ["soc2", "hipaa"]
    assert bad.status_code == 400 and refused.status_code == 403
    assert (await mongo_db.tenants.find_one({"id": "tenant-a"}))["purchasedFrameworks"] == ["soc2", "hipaa"]


# ── Billing ──────────────────────────────────────────────────────────────────

async def test_the_invoice_bills_each_purchased_framework_monthly(mongo_db):
    """protects=the generated invoice has one line per purchased framework at its configured price
    (raised SOC 2, default $5 HIPAA) and the subtotal includes them; unpurchased frameworks are not
    billed; fails_when=a purchase is missing from the invoice or ISO is billed; no_claim=payment collection."""
    import billing_service
    await _seed(mongo_db, purchased=["soc2", "hipaa"])
    await FinOpsService().update_service_pricing(mongo_db, "compliance-soc2", {"price": 20})
    zero = {"charges": [], "total_amount": 0.0, "currency": "USD"}
    with _Context("tenant-a"), patch.object(billing_service, "get_database", lambda: TenantIsolatedDatabase(mongo_db)), \
            patch.object(billing_service.BillingService, "calculate_usage_charges", AsyncMock(return_value=zero)):
        invoice = await billing_service.BillingService.generate_invoice("tenant-a", "2026-10")
    lines = {l["frameworkId"]: l["amount"] for l in invoice["lineItems"] if l.get("frameworkId")}
    assert lines == {"soc2": 20.0, "hipaa": 5.0}
    assert invoice["subtotal"] == 25.0


# Reading the catalogue through a raw handle (db._db, mongodb.db) skips the purchase filter.
# Only these work outside a tenant's request; a tenant-facing module must use db.compliance_frameworks.
_RAW_FRAMEWORK_READERS = {"ai_services/dataset_builder.py", "app_background_tasks.py",
                          "compliance_purchases.py", "database_migrations.py"}


def test_tenant_facing_code_reads_frameworks_through_the_scoped_collection():
    """protects=no endpoint or service reaches the framework catalogue around the purchase filter;
    fails_when=new code reads db._db.compliance_frameworks for a tenant (as compliance scores, narratives
    and the MCP tools did before this change); no_claim=dynamic access patterns the regex cannot see."""
    import re
    root = os.path.join(os.path.dirname(__file__), "..")
    pattern = re.compile(r"(_db|\braw|raw_db|mongodb\.db)(\.compliance_frameworks\b|\[['\"]compliance_frameworks['\"]\])")
    skip_dirs = {"tests", "migrations", "scripts", "__pycache__", "node_modules"}
    found = set()
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in skip_dirs and not d.startswith(("venv", "."))]
        for name in filenames:
            if name.endswith(".py"):
                path = os.path.join(dirpath, name)
                rel = os.path.relpath(path, root).replace(os.sep, "/")
                if rel.count("/") <= 1 and not rel.startswith(("seed", "expand_", "fix_", "dump_", "ingest_")):
                    with open(path, encoding="utf-8", errors="ignore") as handle:
                        if pattern.search(handle.read()):
                            found.add(rel)
    assert found <= _RAW_FRAMEWORK_READERS, sorted(found - _RAW_FRAMEWORK_READERS)
