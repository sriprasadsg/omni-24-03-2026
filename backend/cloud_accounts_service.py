"""Multi-account cloud scanning service — registration, org discovery, scan orchestration."""
import uuid, os, logging
from datetime import datetime, timezone
from typing import Optional
from cryptography.fernet import Fernet

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
    creds_raw = data.get("credentials_ref", "")
    creds_enc = _encrypt(creds_raw) if creds_raw else creds_raw
    provider = data.get("provider", "")
    account_id = data.get("account_id", "")
    key = {"tenantId": tenant_id, "provider": provider, "account_id": account_id}
    existing = await db._db.cloud_accounts.find_one(key)
    doc = {
        "id": existing["id"] if existing else _id(), "tenantId": tenant_id,
        "provider": provider, "account_id": account_id,
        "account_name": data.get("account_name", ""), "environment": data.get("environment", "dev"),
        "credentials_ref": creds_enc, "region": data.get("region", "us-east-1"),
        "last_scan": existing.get("last_scan") if existing else None,
        "scan_status": existing.get("scan_status", "idle") if existing else "idle",
        "created_at": existing["created_at"] if existing else _now(),
    }
    await db._db.cloud_accounts.update_one(key, {"$set": doc}, upsert=True)
    return {k: v for k, v in doc.items() if k != "credentials_ref"}


async def list_accounts(db, tenant_id: str) -> list:
    docs = await db._db.cloud_accounts.find({"tenantId": tenant_id}, {"_id": 0}).sort("created_at", -1).to_list(length=100)
    return [{k: v for k, v in d.items() if k != "credentials_ref"} for d in docs]


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
    accounts = await list_accounts(db, tenant_id)
    results = await db.cloud_check_results.find({"tenantId": tenant_id}, {"_id": 0}).to_list(length=5000)
    total = len(results)
    passed = sum(1 for r in results if r.get("result") == "PASS")
    failed = sum(1 for r in results if r.get("result") == "FAIL")
    by_provider: dict = {}
    by_env: dict = {}
    for a in accounts:
        p = a.get("provider", "unknown")
        by_provider[p] = by_provider.get(p, 0) + 1
        e = a.get("environment", "unknown")
        if e not in by_env:
            by_env[e] = []
        by_env[e].append(a.get("account_name", a.get("account_id", "")))
    return {"total_accounts": len(accounts), "total_checks": total, "pass": passed, "fail": failed, "by_provider": by_provider, "by_environment": {k: {"accounts": v, "count": len(v)} for k, v in by_env.items()}}


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
