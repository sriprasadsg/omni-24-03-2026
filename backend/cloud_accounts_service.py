"""Multi-account cloud scanning service — registration, org discovery, scan orchestration.

IN-03 (20-REVIEW.md): this module always goes through the raw ``db._db.<collection>``
accessor and manually adds ``"tenantId"`` to every filter — that is deliberate and
correct here. `cloud_checks_service.run_checks()` (called by `scan_account()` below)
instead uses the tenant-isolation-wrapped ``db.cloud_accounts``/``db.cloud_check_results``
accessors, which inject the tenant id from request context automatically. Both are
safe today, but they are NOT interchangeable: moving this file off ``db._db`` under
the (correct-for-the-*other*-file) assumption that ``db.cloud_accounts`` already
tenant-scopes everything would silently reintroduce a cross-tenant IDOR if done
without also removing the manual "tenantId" filters and confirming context
injection is active on every call path.
"""
import uuid, os, logging
from datetime import datetime, timezone
from typing import Optional
from cryptography.fernet import Fernet
import json

logger = logging.getLogger(__name__)

_FERNET_KEY = os.environ.get("CLOUD_CREDENTIALS_KEY", "")
if not _FERNET_KEY:
    if os.environ.get("APP_ENV", "development").lower() == "production":
        raise RuntimeError(
            "CLOUD_CREDENTIALS_KEY is not set. Refusing to start in production "
            "without a stable encryption key for cloud account credentials. "
            "Generate one with: python -c \"from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())\""
        )
    logger.warning(
        "CLOUD_CREDENTIALS_KEY not set — using ephemeral key (dev only). "
        "Cloud account credentials will not survive restart."
    )
    _FERNET_KEY = Fernet.generate_key().decode()
_FERNET = Fernet(_FERNET_KEY.encode())


def _now() -> str: return datetime.now(timezone.utc).isoformat()
def _id() -> str: return f"acct-{uuid.uuid4().hex[:12]}"


async def register_account(db, tenant_id: str, data: dict) -> dict:
    provider = data.get("provider", "")
    account_id = data.get("account_id", "")
    key = {"tenantId": tenant_id, "provider": provider, "account_id": account_id}
    existing = await db._db.cloud_accounts.find_one(key)

    creds_raw = data.get("credentials_ref", "")
    if creds_raw:
        creds_enc = _encrypt(creds_raw)
    else:
        # CR-01: preserve the previously-stored encrypted credential when the
        # caller doesn't resend it (the shipped UI never sends this field at
        # all), instead of silently overwriting it with an empty string.
        #
        # IN-06: this means every falsy credentials_ref ("", null, or the key
        # being entirely absent) is treated identically to "not provided" —
        # there is currently no way for a client to intentionally *clear* a
        # stored credential (e.g. to de-authorize an account without deleting
        # the whole registration). If rotation/removal is needed later, use an
        # explicit sentinel to distinguish "clear" from "don't touch" instead
        # of overloading falsy-ness for both.
        creds_enc = existing.get("credentials_ref", "") if existing else ""

    doc = {
        "id": existing["id"] if existing else _id(), "tenantId": tenant_id,
        "provider": provider, "account_id": account_id,
        # WR-06: same preserve-on-omission pattern as credentials_ref above —
        # a re-register call that omits account_name/region must not silently
        # blank a previously-set display name or reset a custom region.
        # WR-01: environment is a third sibling field with the identical
        # defect — a re-register call that omits environment must not
        # silently reset a "prod" account down to the "dev" default.
        "account_name": data.get("account_name") or (existing.get("account_name", "") if existing else ""),
        "environment": data.get("environment") or (existing.get("environment", "dev") if existing else "dev"),
        "credentials_ref": creds_enc,
        "region": data.get("region") or (existing.get("region", "us-east-1") if existing else "us-east-1"),
        "last_scan": existing.get("last_scan") if existing else None,
        "scan_status": existing.get("scan_status", "idle") if existing else "idle",
        "created_at": existing["created_at"] if existing else _now(),
    }
    await db._db.cloud_accounts.update_one(key, {"$set": doc}, upsert=True)
    return {k: v for k, v in doc.items() if k != "credentials_ref"}


async def list_accounts(db, tenant_id: str, skip: int = 0, limit: int = 100) -> list:
    docs = await db._db.cloud_accounts.find({"tenantId": tenant_id}, {"_id": 0}).sort(
        "created_at", -1
    ).skip(skip).limit(limit).to_list(length=limit)
    return [{k: v for k, v in d.items() if k != "credentials_ref"} for d in docs]


async def count_accounts(db, tenant_id: str) -> int:
    """WR-03: exposes the true tenant account count so callers can detect
    truncation instead of silently losing accounts beyond the page size."""
    return await db._db.cloud_accounts.count_documents({"tenantId": tenant_id})


async def scan_account(db, account_id: str, tenant_id: str) -> dict:
    from cloud_checks_service import cloud_checks_service
    account = await db._db.cloud_accounts.find_one({"id": account_id, "tenantId": tenant_id})
    if not account:
        return {"error": "Cloud account not found", "ran": 0}
    await db._db.cloud_accounts.update_one(
        {"id": account_id, "tenantId": tenant_id}, {"$set": {"scan_status": "scanning"}}
    )
    try:
        provider = account.get("provider", "aws")

        # PROV-02: Ingest real findings for M365/Atlas before run_checks
        if provider == "microsoft365":
            from m365_ingest import poll_m365_secure_scores
            creds = _decrypt(account.get("credentials_ref", ""))
            try: config = json.loads(creds)
            except: config = {}
            await poll_m365_secure_scores(config, account_id, tenant_id)
        elif provider == "mongodb_atlas":
            from mongodb_atlas_ingest import poll_mongodb_atlas_findings
            creds = _decrypt(account.get("credentials_ref", ""))
            try: config = json.loads(creds)
            except: config = {}
            await poll_mongodb_atlas_findings(config, account_id, tenant_id)

        result = await cloud_checks_service.run_checks(account_id, provider, tenant_id)
        await db._db.cloud_accounts.update_one(
            {"id": account_id, "tenantId": tenant_id}, {"$set": {"scan_status": "idle", "last_scan": _now()}}
        )
        return result
    except Exception as e:
        await db._db.cloud_accounts.update_one(
            {"id": account_id, "tenantId": tenant_id}, {"$set": {"scan_status": "failed"}}
        )
        return {"error": str(e), "ran": 0}


async def get_results(db, account_id: str, tenant_id: str) -> list:
    return await db.cloud_check_results.find({"accountId": account_id, "tenantId": tenant_id}, {"_id": 0}).sort("checked_at", -1).to_list(length=1000)


async def get_summary(db, tenant_id: str) -> dict:
    # WR-05: total_accounts must come from count_accounts() (unbounded), and the
    # account list used for the by_provider/by_environment breakdown must not be
    # silently capped at list_accounts()'s default limit=100 — otherwise tenants
    # with >100 accounts get a truncated summary, the same failure WR-03 fixed
    # for the paginated list endpoint.
    total_accounts = await count_accounts(db, tenant_id)
    accounts = await list_accounts(db, tenant_id, skip=0, limit=max(total_accounts, 1))
    # WR-04: use count_documents instead of loading a capped result set into
    # memory, so pass/fail/total stay accurate no matter how many check
    # results a tenant accumulates.
    total = await db.cloud_check_results.count_documents({"tenantId": tenant_id})
    passed = await db.cloud_check_results.count_documents({"tenantId": tenant_id, "result": "PASS"})
    failed = await db.cloud_check_results.count_documents({"tenantId": tenant_id, "result": "FAIL"})
    by_provider: dict = {}
    by_env: dict = {}
    for a in accounts:
        p = a.get("provider", "unknown")
        by_provider[p] = by_provider.get(p, 0) + 1
        e = a.get("environment", "unknown")
        if e not in by_env:
            by_env[e] = []
        by_env[e].append(a.get("account_name", a.get("account_id", "")))
    return {"total_accounts": total_accounts, "total_checks": total, "pass": passed, "fail": failed, "by_provider": by_provider, "by_environment": {k: {"accounts": v, "count": len(v)} for k, v in by_env.items()}}


async def discover_org_accounts(db, tenant_id: str, credentials: dict) -> dict:
    """Simulate org discovery (real impl calls AWS Organizations ListAccounts)."""
    discovered = []
    for i in range(1, 4):
        aid = f"org-acct-{i}"
        key = {"tenantId": tenant_id, "provider": "aws", "account_id": aid}
        existing = await db._db.cloud_accounts.find_one(key)
        doc = {
            "id": existing["id"] if existing else _id(), "tenantId": tenant_id,
            "provider": "aws", "account_id": aid, "account_name": f"Member {i}", "environment": "prod",
            "credentials_ref": _encrypt(f"assume-role-{aid}"), "region": "us-east-1",
            "last_scan": existing.get("last_scan") if existing else None,
            "scan_status": existing.get("scan_status", "idle") if existing else "idle",
            "created_at": existing["created_at"] if existing else _now(),
        }
        await db._db.cloud_accounts.update_one(key, {"$set": doc}, upsert=True)
        discovered.append(aid)
    return {"discovered": len(discovered), "account_ids": discovered}


def _encrypt(plain: str) -> str:
    if not plain:
        return plain
    return _FERNET.encrypt(plain.encode()).decode()

def _decrypt(enc: str) -> str:
    if not enc:
        return enc
    return _FERNET.decrypt(enc.encode()).decode()
