from fastapi import APIRouter, Depends, Query
from auth_utils import require_auth
from database import get_db
from supply_chain_security_service import SupplyChainSecurityService

router = APIRouter(prefix="/api/supply-chain-security", tags=["supply-chain-security"])


def get_svc(db=Depends(get_db)):
    return SupplyChainSecurityService(db)


@router.get("/artifacts")
async def get_artifacts(limit: int = Query(100), user=Depends(require_auth),
                        svc: SupplyChainSecurityService = Depends(get_svc)):
    tenant_id = getattr(user, "tenant_id", None)
    items = await svc.get_artifacts(tenant_id, limit)
    for i in items:
        i["id"] = i.pop("_id", i.get("id"))
    return {"artifacts": items}


@router.get("/vulnerabilities")
async def get_vulnerabilities(severity: str = Query(None), limit: int = Query(100),
                              user=Depends(require_auth), svc: SupplyChainSecurityService = Depends(get_svc)):
    tenant_id = getattr(user, "tenant_id", None)
    vulns = await svc.get_vulnerabilities(tenant_id, severity, limit)
    for v in vulns:
        v["id"] = v.pop("_id", v.get("id"))
    return {"vulnerabilities": vulns}


@router.get("/summary")
async def get_summary(user=Depends(require_auth), svc: SupplyChainSecurityService = Depends(get_svc)):
    tenant_id = getattr(user, "tenant_id", None)
    return await svc.get_summary(tenant_id)


@router.post("/seed")
async def seed(user=Depends(require_auth), svc: SupplyChainSecurityService = Depends(get_svc)):
    tenant_id = getattr(user, "tenant_id", None)
    await svc.seed_demo(tenant_id)
    return {"message": "Supply chain demo data seeded"}
