from fastapi import APIRouter, Depends, Query
from auth_utils import require_auth
from database import get_db
from insider_threat_service import InsiderThreatService

router = APIRouter(prefix="/api/insider-threat", tags=["insider-threat"])


def get_svc(db=Depends(get_db)):
    return InsiderThreatService(db)


@router.get("/profiles")
async def get_profiles(risk_level: str = Query(None), limit: int = Query(50),
                       user=Depends(require_auth), svc: InsiderThreatService = Depends(get_svc)):
    tenant_id = getattr(user, "tenant_id", None)
    profiles = await svc.get_profiles(tenant_id, risk_level, limit)
    for p in profiles:
        p["id"] = p.pop("_id", p.get("id"))
    return {"profiles": profiles}


@router.get("/alerts")
async def get_alerts(limit: int = Query(50), user=Depends(require_auth),
                     svc: InsiderThreatService = Depends(get_svc)):
    tenant_id = getattr(user, "tenant_id", None)
    alerts = await svc.get_alerts(tenant_id, limit)
    for a in alerts:
        a["id"] = a.pop("_id", a.get("id"))
    return {"alerts": alerts}


@router.get("/summary")
async def get_summary(user=Depends(require_auth), svc: InsiderThreatService = Depends(get_svc)):
    tenant_id = getattr(user, "tenant_id", None)
    return await svc.get_summary(tenant_id)


@router.put("/alerts/{alert_id}")
async def update_alert(alert_id: str, body: dict, user=Depends(require_auth),
                       svc: InsiderThreatService = Depends(get_svc)):
    await svc.update_alert_status(alert_id, body.get("status", "open"), body.get("note", ""))
    return {"updated": True}


@router.post("/seed")
async def seed(user=Depends(require_auth), svc: InsiderThreatService = Depends(get_svc)):
    tenant_id = getattr(user, "tenant_id", None)
    await svc.seed_demo_data(tenant_id)
    return {"message": "Insider threat demo data seeded"}
