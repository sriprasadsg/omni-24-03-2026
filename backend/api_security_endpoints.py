from fastapi import APIRouter, Depends, Query
from auth_utils import require_auth
from database import get_db
from api_security_service import APISecurityService

router = APIRouter(prefix="/api/api-security", tags=["api-security"])


def get_svc(db=Depends(get_db)):
    return APISecurityService(db)


@router.get("/endpoints")
async def list_endpoints(limit: int = Query(100), user=Depends(require_auth), svc: APISecurityService = Depends(get_svc)):
    tenant_id = getattr(user, "tenant_id", None)
    endpoints = await svc.get_endpoints(tenant_id, limit)
    for e in endpoints:
        e["id"] = e.pop("_id", e.get("id"))
    return {"endpoints": endpoints, "total": len(endpoints)}


@router.post("/discover")
async def discover(user=Depends(require_auth), svc: APISecurityService = Depends(get_svc)):
    tenant_id = getattr(user, "tenant_id", None)
    discovered = await svc.discover_endpoints(tenant_id)
    return {"discovered": len(discovered), "message": f"Scanned and catalogued {len(discovered)} endpoints"}


@router.get("/alerts")
async def get_alerts(severity: str = Query(None), limit: int = Query(50),
                     user=Depends(require_auth), svc: APISecurityService = Depends(get_svc)):
    tenant_id = getattr(user, "tenant_id", None)
    alerts = await svc.get_alerts(tenant_id, severity, limit)
    for a in alerts:
        a["id"] = a.pop("_id", a.get("id"))
    return {"alerts": alerts}


@router.post("/endpoints/{endpoint_id}/analyze")
async def analyze(endpoint_id: str, user=Depends(require_auth), svc: APISecurityService = Depends(get_svc)):
    tenant_id = getattr(user, "tenant_id", None)
    result = await svc.analyze_endpoint(endpoint_id, tenant_id)
    if not result:
        return {"error": "Endpoint not found"}, 404
    return result


@router.get("/summary")
async def summary(user=Depends(require_auth), svc: APISecurityService = Depends(get_svc)):
    tenant_id = getattr(user, "tenant_id", None)
    return await svc.get_summary(tenant_id)
