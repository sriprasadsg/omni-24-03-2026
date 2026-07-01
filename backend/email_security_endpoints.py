from fastapi import APIRouter, Depends, Query
from auth_utils import require_auth
from database import get_db
from email_security_service import EmailSecurityService

router = APIRouter(prefix="/api/email-security", tags=["email-security"])


def get_svc(db=Depends(get_db)):
    return EmailSecurityService(db)


@router.get("/threats")
async def get_threats(threat_type: str = Query(None), limit: int = Query(50),
                      user=Depends(require_auth), svc: EmailSecurityService = Depends(get_svc)):
    tenant_id = getattr(user, "tenant_id", None)
    threats = await svc.get_threats(tenant_id, threat_type, limit)
    for t in threats:
        t["id"] = t.pop("_id", t.get("id"))
    return {"threats": threats}


@router.get("/domains")
async def get_domain_health(user=Depends(require_auth), svc: EmailSecurityService = Depends(get_svc)):
    tenant_id = getattr(user, "tenant_id", None)
    domains = await svc.get_domain_health(tenant_id)
    for d in domains:
        d["id"] = d.pop("_id", d.get("id"))
    return {"domains": domains}


@router.get("/quarantine")
async def get_quarantine(limit: int = Query(50), user=Depends(require_auth),
                         svc: EmailSecurityService = Depends(get_svc)):
    tenant_id = getattr(user, "tenant_id", None)
    items = await svc.get_quarantine(tenant_id, limit)
    for i in items:
        i["id"] = i.pop("_id", i.get("id"))
    return {"items": items}


@router.post("/quarantine/{email_id}/release")
async def release(email_id: str, user=Depends(require_auth), svc: EmailSecurityService = Depends(get_svc)):
    tenant_id = getattr(user, "tenant_id", None)
    await svc.release_quarantine(email_id, tenant_id)
    return {"released": True}


@router.get("/summary")
async def get_summary(user=Depends(require_auth), svc: EmailSecurityService = Depends(get_svc)):
    tenant_id = getattr(user, "tenant_id", None)
    return await svc.get_summary(tenant_id)


@router.post("/seed")
async def seed(user=Depends(require_auth), svc: EmailSecurityService = Depends(get_svc)):
    tenant_id = getattr(user, "tenant_id", None)
    await svc.seed_demo(tenant_id)
    return {"message": "Email security demo data seeded"}
