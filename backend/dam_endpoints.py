from fastapi import APIRouter, Depends, Query
from typing import Optional
from pydantic import BaseModel, Field
from auth_utils import require_auth
from database import get_db
from dam_service import DAMService

router = APIRouter(prefix="/api/dam", tags=["database-activity-monitoring"])


class DAMQueryLog(BaseModel):
    query: str = Field(..., min_length=1, max_length=10000)
    database: Optional[str] = None
    user: Optional[str] = None
    duration_ms: Optional[float] = None
    rows_affected: Optional[int] = None
    query_type: Optional[str] = None


class DAMAlertUpdate(BaseModel):
    status: Optional[str] = None
    note: Optional[str] = None
    acknowledged: Optional[bool] = None


def get_svc(db=Depends(get_db)):
    return DAMService(db)


@router.get("/queries")
async def get_queries(database: str = Query(None), limit: int = Query(100),
                      user=Depends(require_auth), svc: DAMService = Depends(get_svc)):
    tenant_id = getattr(user, "tenant_id", None)
    queries = await svc.get_query_log(tenant_id, database, limit)
    for q in queries:
        q["id"] = q.pop("_id", q.get("id"))
    return {"queries": queries}


@router.get("/alerts")
async def get_alerts(severity: str = Query(None), limit: int = Query(50),
                     user=Depends(require_auth), svc: DAMService = Depends(get_svc)):
    tenant_id = getattr(user, "tenant_id", None)
    alerts = await svc.get_alerts(tenant_id, severity, limit)
    for a in alerts:
        a["id"] = a.pop("_id", a.get("id"))
    return {"alerts": alerts}


@router.post("/queries")
async def log_query(body: DAMQueryLog, user=Depends(require_auth), svc: DAMService = Depends(get_svc)):
    tenant_id = getattr(user, "tenant_id", None)
    doc = await svc.log_query(tenant_id, body.model_dump(exclude_none=True))
    doc["id"] = doc.pop("_id", doc.get("id"))
    return doc


@router.get("/summary")
async def get_summary(user=Depends(require_auth), svc: DAMService = Depends(get_svc)):
    tenant_id = getattr(user, "tenant_id", None)
    return await svc.get_summary(tenant_id)


@router.post("/seed")
async def seed_demo(user=Depends(require_auth), svc: DAMService = Depends(get_svc)):
    tenant_id = getattr(user, "tenant_id", None)
    await svc.seed_demo_data(tenant_id)
    return {"message": "Demo DAM data seeded"}


@router.put("/alerts/{alert_id}")
async def update_alert(alert_id: str, body: DAMAlertUpdate, user=Depends(require_auth), svc: DAMService = Depends(get_svc)):
    tenant_id = getattr(user, "tenant_id", None)
    result = await svc.col_alerts.update_one(
        {"_id": alert_id, "tenantId": tenant_id}, {"$set": body.model_dump(exclude_none=True)}
    )
    if result.matched_count == 0:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="Alert not found")
    return {"updated": True}
