from fastapi import APIRouter, Depends, Query
from auth_utils import require_auth
from database import get_db
from dam_service import DAMService

router = APIRouter(prefix="/api/dam", tags=["database-activity-monitoring"])


def get_svc(db=Depends(get_db)):
    return DAMService(db)


@router.get("/queries")
async def get_queries(database: str = Query(None), limit: int = Query(100),
                      user=Depends(require_auth), svc: DAMService = Depends(get_svc)):
    tenant_id = getattr(user, "tenant_id", "platform")
    queries = await svc.get_query_log(tenant_id, database, limit)
    for q in queries:
        q["id"] = q.pop("_id", q.get("id"))
    return {"queries": queries}


@router.get("/alerts")
async def get_alerts(severity: str = Query(None), limit: int = Query(50),
                     user=Depends(require_auth), svc: DAMService = Depends(get_svc)):
    tenant_id = getattr(user, "tenant_id", "platform")
    alerts = await svc.get_alerts(tenant_id, severity, limit)
    for a in alerts:
        a["id"] = a.pop("_id", a.get("id"))
    return {"alerts": alerts}


@router.post("/queries")
async def log_query(body: dict, user=Depends(require_auth), svc: DAMService = Depends(get_svc)):
    tenant_id = getattr(user, "tenant_id", "platform")
    doc = await svc.log_query(tenant_id, body)
    doc["id"] = doc.pop("_id", doc.get("id"))
    return doc


@router.get("/summary")
async def get_summary(user=Depends(require_auth), svc: DAMService = Depends(get_svc)):
    tenant_id = getattr(user, "tenant_id", "platform")
    return await svc.get_summary(tenant_id)


@router.post("/seed")
async def seed_demo(user=Depends(require_auth), svc: DAMService = Depends(get_svc)):
    tenant_id = getattr(user, "tenant_id", "platform")
    await svc.seed_demo_data(tenant_id)
    return {"message": "Demo DAM data seeded"}


@router.put("/alerts/{alert_id}")
async def update_alert(alert_id: str, body: dict, user=Depends(require_auth), svc: DAMService = Depends(get_svc)):
    await svc.col_alerts.update_one({"_id": alert_id}, {"$set": body})
    return {"updated": True}
