from fastapi import APIRouter, Depends, Query, HTTPException
from auth_utils import require_auth
from database import get_db
from ndr_service import NDRService

_ANOMALY_ALLOWED_FIELDS = {"status", "note", "acknowledged"}

router = APIRouter(prefix="/api/ndr", tags=["network-detection-response"])


def get_svc(db=Depends(get_db)):
    return NDRService(db)


@router.get("/anomalies")
async def get_anomalies(severity: str = Query(None), limit: int = Query(50),
                        user=Depends(require_auth), svc: NDRService = Depends(get_svc)):
    tenant_id = getattr(user, "tenant_id", None)
    anomalies = await svc.get_anomalies(tenant_id, severity, limit)
    for a in anomalies:
        a["id"] = a.pop("_id", a.get("id"))
    return {"anomalies": anomalies}


@router.post("/detect")
async def run_detection(user=Depends(require_auth), svc: NDRService = Depends(get_svc)):
    tenant_id = getattr(user, "tenant_id", None)
    detected = await svc.run_detection(tenant_id)
    for a in detected:
        a["id"] = a.pop("_id", a.get("id"))
    return {"detected": len(detected), "anomalies": detected}


@router.post("/flows")
async def ingest_flow(body: dict, user=Depends(require_auth), svc: NDRService = Depends(get_svc)):
    tenant_id = getattr(user, "tenant_id", None)
    doc = await svc.ingest_flow(tenant_id, body)
    doc["id"] = doc.pop("_id", doc.get("id"))
    return doc


@router.get("/summary")
async def get_summary(user=Depends(require_auth), svc: NDRService = Depends(get_svc)):
    tenant_id = getattr(user, "tenant_id", None)
    return await svc.get_traffic_summary(tenant_id)


@router.post("/seed")
async def seed(user=Depends(require_auth), svc: NDRService = Depends(get_svc)):
    tenant_id = getattr(user, "tenant_id", None)
    await svc.seed_demo(tenant_id)
    return {"message": "NDR demo data seeded"}


@router.put("/anomalies/{anomaly_id}")
async def update_anomaly(anomaly_id: str, body: dict, user=Depends(require_auth), svc: NDRService = Depends(get_svc)):
    tenant_id = getattr(user, "tenant_id", None)
    filtered = {k: v for k, v in body.items() if k in _ANOMALY_ALLOWED_FIELDS}
    if not filtered:
        raise HTTPException(status_code=400, detail="No valid fields to update")
    result = await svc.col_anomalies.update_one(
        {"_id": anomaly_id, "tenantId": tenant_id},
        {"$set": filtered}
    )
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Anomaly not found")
    return {"updated": True}
