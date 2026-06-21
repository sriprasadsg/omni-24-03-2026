from datetime import datetime, timezone
import logging


async def _append_coc_entry(
    db,
    evidence_id: str,
    tenant_id: str,
    actor: str,
    action_type: str,
    snapshot_before: dict | None,
    snapshot_after: dict | None,
) -> None:
    """Append an immutable chain-of-custody entry to evidence_audit_log.

    Fire-and-forget: swallows exceptions and returns None so that a failed
    CoC write never propagates to the caller and never breaks a user operation.
    Must be called AFTER the primary DB mutation succeeds (per research Pitfall 2).

    Uses raw Motor (db._db) to bypass TenantIsolatedCollection.insert_one,
    which would auto-inject tenantId from request context and conflict with
    the explicit tenantId we set here (per research Critical Implementation Note).

    Args:
        db:              TenantIsolatedDatabase or raw Motor db.
        evidence_id:     ID of the affected evidence record.
        tenant_id:       Tenant that owns the record.
        actor:           Username or system actor performing the mutation.
        action_type:     One of "create" | "update" | "delete".
        snapshot_before: Evidence document before mutation, or None for creates.
        snapshot_after:  Evidence document after mutation, or None for deletes.
    """
    try:
        raw = db._db if hasattr(db, "_db") else db
        await raw.evidence_audit_log.insert_one({
            "evidenceId":      evidence_id,
            "tenantId":        tenant_id,
            "actor":           actor,
            "action_type":     action_type,
            "timestamp":       datetime.now(timezone.utc).isoformat(),
            "snapshot_before": snapshot_before,
            "snapshot_after":  snapshot_after,
        })
    except Exception as e:
        logging.getLogger(__name__).error("CoC append failed: %s", e)
