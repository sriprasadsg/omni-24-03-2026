from fastapi import APIRouter, Depends
from authentication_service import get_current_user
from tracing_service import get_tracing_service
from database import get_database

_TRACING_SUPER_ROLES = {"Super Admin", "super_admin", "platform-admin"}

router = APIRouter(prefix="/api/tracing", tags=["Distributed Tracing"])

@router.get("/traces")
async def get_traces(
    limit: int = 50,
    current_user: dict = Depends(get_current_user)
):
    """Get recent distributed traces."""
    db = get_database()
    service = get_tracing_service(db)
    return await service.get_traces(limit)

@router.get("/spans")
async def get_spans(
    trace_id: str = None,
    limit: int = 200,
    current_user: dict = Depends(get_current_user),
):
    """
    Get individual spans, optionally filtered by trace_id.
    Tests: O5 — GET /api/tracing/spans → end-to-end trace data
    """
    db = get_database()
    caller_role = getattr(current_user, "role", "") or (current_user.get("role", "") if isinstance(current_user, dict) else "")
    caller_tenant = getattr(current_user, "tenant_id", None) or (current_user.get("tenant_id") or current_user.get("tenantId") if isinstance(current_user, dict) else None)
    query = {}
    if trace_id:
        query["traceId"] = trace_id
    # Always scope non-admins to their own tenant's spans
    if caller_role not in _TRACING_SUPER_ROLES and caller_tenant:
        query["tenantId"] = caller_tenant
    spans = await db.spans.find(query, {"_id": 0}).sort("startTime", -1).limit(limit).to_list(length=limit)
    return {"spans": spans, "count": len(spans)}


@router.get("/service-map")
async def get_service_map(
    current_user: dict = Depends(get_current_user)
):
    """Get the live service dependency map."""
    db = get_database()
    service = get_tracing_service(db)
    return await service.get_service_map()
