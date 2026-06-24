from fastapi import APIRouter, Depends, Query
from authentication_service import get_current_user
from database import get_database
from datetime import datetime, timezone
import uuid
import random
from auth_roles import SUPER_ROLES as _SUPER_ROLES

router = APIRouter(prefix="/api/tracing", tags=["Distributed Tracing"])
_SERVICES = [
    "api-gateway", "auth-service", "user-service",
    "order-service", "payment-service", "notification-service",
]
_OPS = [
    "HTTP GET /users", "HTTP POST /orders", "gRPC Authenticate",
    "DB Query users", "Cache GET", "Publish event",
]


def _make_span(service: str, name: str, start_ms: int, duration: int, parent_id: str | None = None) -> dict:
    return {
        "id": uuid.uuid4().hex[:16],
        "name": name,
        "service": service,
        "startTime": start_ms,
        "duration": duration,
        "status": "ERROR" if random.random() < 0.1 else "OK",
        "parentId": parent_id,
        "children": [],
    }


def _seed_traces(tenant_id: str) -> list[dict]:
    now_ms = int(datetime.now(timezone.utc).timestamp() * 1000)
    traces = []
    for _ in range(12):
        ts = now_ms - random.randint(0, 3_600_000)
        root_dur = random.randint(80, 1200)
        root = _make_span(_SERVICES[0], random.choice(_OPS), ts, root_dur)
        c1 = _make_span(_SERVICES[1], random.choice(_OPS), ts + 10, root_dur - 30, root["id"])
        c2 = _make_span(_SERVICES[2], random.choice(_OPS), ts + 20, root_dur - 60, root["id"])
        root["children"] = [c1, c2]
        errors = sum(1 for s in (root, c1, c2) if s["status"] == "ERROR")
        traces.append({
            "id": f"trace-{uuid.uuid4().hex[:12]}",
            "tenantId": tenant_id,
            "rootSpan": root,
            "totalDuration": root_dur,
            "serviceCount": 3,
            "errorCount": errors,
            "timestamp": datetime.fromtimestamp(ts / 1000, tz=timezone.utc).isoformat(),
        })
    return traces


def _seed_service_map(tenant_id: str) -> dict:
    nodes = [
        {
            "id": svc,
            "requestCount": random.randint(200, 5000),
            "errorCount": random.randint(0, 50),
            "avgLatency": random.randint(5, 250),
        }
        for svc in _SERVICES
    ]
    edges = [
        {"from": _SERVICES[0], "to": _SERVICES[1], "requestCount": random.randint(100, 2000)},
        {"from": _SERVICES[0], "to": _SERVICES[2], "requestCount": random.randint(100, 2000)},
        {"from": _SERVICES[1], "to": _SERVICES[3], "requestCount": random.randint(50, 1000)},
        {"from": _SERVICES[3], "to": _SERVICES[4], "requestCount": random.randint(50, 800)},
        {"from": _SERVICES[4], "to": _SERVICES[5], "requestCount": random.randint(20, 400)},
    ]
    return {"tenantId": tenant_id, "nodes": nodes, "edges": edges}


def _effective_tenant(current_user) -> str | None:
    if isinstance(current_user, dict):
        return current_user.get("tenant_id") or current_user.get("tenantId")
    return getattr(current_user, "tenant_id", None)


def _caller_role(current_user) -> str:
    if isinstance(current_user, dict):
        return current_user.get("role", "")
    return getattr(current_user, "role", "") or ""


@router.get("/traces")
async def get_traces(
    limit: int = 50,
    tenant_id: str | None = Query(None),
    current_user=Depends(get_current_user),
):
    db = get_database()
    role = _caller_role(current_user)
    effective = tenant_id or _effective_tenant(current_user)

    query: dict = {}
    if role not in _SUPER_ROLES and effective:
        query["tenantId"] = effective

    count = await db.traces.count_documents(query if query else {"tenantId": effective})
    if count == 0 and effective:
        await db.traces.insert_many(_seed_traces(effective))

    return await db.traces.find(query, {"_id": 0}).sort("timestamp", -1).limit(limit).to_list(length=limit)


@router.get("/spans")
async def get_spans(
    trace_id: str | None = Query(None),
    limit: int = 200,
    current_user=Depends(get_current_user),
):
    db = get_database()
    role = _caller_role(current_user)
    effective = _effective_tenant(current_user)

    query: dict = {}
    if trace_id:
        query["traceId"] = trace_id
    if role not in _SUPER_ROLES and effective:
        query["tenantId"] = effective

    spans = await db.spans.find(query, {"_id": 0}).sort("startTime", -1).limit(limit).to_list(length=limit)
    return {"spans": spans, "count": len(spans)}


@router.get("/service-map")
async def get_service_map(
    tenant_id: str | None = Query(None),
    current_user=Depends(get_current_user),
):
    db = get_database()
    effective = tenant_id or _effective_tenant(current_user)

    smap = await db.service_maps.find_one({"tenantId": effective}, {"_id": 0})
    if not smap:
        smap = _seed_service_map(effective)
        inserted = await db.service_maps.insert_one(smap)
        smap.pop("_id", None)

    return smap
