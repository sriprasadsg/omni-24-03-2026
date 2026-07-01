from datetime import datetime, timezone


def compute_stale(uploaded_at: str, threshold_days: int) -> dict:
    """Return stale flag and age in days for a single evidence record.

    Caller is responsible for only passing automated evidence
    (systemGenerated=True or source='auto'). This function does not
    decide whether evidence is automated — it only computes the staleness.

    Args:
        uploaded_at: ISO 8601 timestamp string (UTC or offset-aware).
        threshold_days: Age in days beyond which evidence is considered stale.

    Returns:
        {"stale": bool, "stale_days": int}
    """
    try:
        dt = datetime.fromisoformat(uploaded_at.replace("Z", "+00:00"))
    except (ValueError, AttributeError, TypeError):
        return {"stale": False, "stale_days": 0}
    now = datetime.now(timezone.utc)
    age_days = (now - dt).days
    return {"stale": age_days >= threshold_days, "stale_days": age_days}


async def get_staleness_threshold(db, tenant_id) -> int:
    """Fetch the staleness threshold (days) for a tenant.

    Lookup order:
    1. Per-tenant doc: {type: "evidence_staleness", tenantId: <tenant_id>}
    2. Global doc:     {type: "evidence_staleness"} (no tenantId field)
    3. Hard-coded default: 7

    Mirrors the _get_raw_llm_settings tenant-first/global-fallback pattern
    in settings_endpoints.py (lines 71-82).

    Args:
        db: TenantIsolatedDatabase (or raw Motor db).
        tenant_id: Tenant identifier string or None/empty.

    Returns:
        int — threshold days (minimum 1, default 7).
    """
    raw = db._db if hasattr(db, "_db") else db
    if tenant_id:
        doc = await raw.system_settings.find_one(
            {"type": "evidence_staleness", "tenantId": tenant_id}
        )
        if doc and isinstance(doc.get("thresholdDays"), int):
            return doc["thresholdDays"]
    doc = await raw.system_settings.find_one(
        {"type": "evidence_staleness", "tenantId": {"$exists": False}}
    )
    if doc and isinstance(doc.get("thresholdDays"), int):
        return doc["thresholdDays"]
    return 7
