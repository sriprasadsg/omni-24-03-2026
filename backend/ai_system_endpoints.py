import logging
from fastapi import APIRouter, Depends, HTTPException
from database import get_database
from authentication_service import get_current_user
from auth_types import TokenData

router = APIRouter(prefix="/api/ai-systems", tags=["AI Systems"])
logger = logging.getLogger(__name__)


@router.get("")
async def list_ai_systems(current_user: TokenData = Depends(get_current_user)):
    """List all AI systems — merges ai_models and ai_systems collections."""
    try:
        db = get_database()
        tenant_id = current_user.tenant_id or None

        # Query both collections
        models = await db.ai_models.find(
            {"tenantId": tenant_id}, {"_id": 0}
        ).to_list(length=500)

        systems = await db.ai_systems.find(
            {"tenantId": tenant_id}, {"_id": 0}
        ).to_list(length=500)


        # Merge, deduplicate by id
        seen: set = set()
        merged = []
        for doc in models + systems:
            uid = doc.get("id") or str(doc.get("_id", ""))
            if uid and uid not in seen:
                seen.add(uid)
                # Normalise to a consistent shape the dashboard expects
                merged.append({
                    "id":     uid,
                    "name":   doc.get("name") or doc.get("modelName") or uid,
                    "type":   doc.get("type") or doc.get("modelType") or doc.get("status") or "system",
                    "status": doc.get("status") or "active",
                    **{k: v for k, v in doc.items() if k not in ("id", "name", "type", "status")},
                })

        return merged
    except Exception as e:
        logger.exception("Unhandled exception")
        raise HTTPException(status_code=500, detail="Internal server error")


_AI_SUPER_ROLES = {"Super Admin", "super_admin", "platform-admin"}


@router.get("/{system_id}/risks")
async def get_system_risks(system_id: str, current_user: TokenData = Depends(get_current_user)):
    """Get risks for a specific AI system — checks both ai_systems and ai_models."""
    try:
        db = get_database()
        tenant_id = current_user.tenant_id or None
        caller_role = getattr(current_user, "role", None)
        tenant_filter: dict = {} if caller_role in _AI_SUPER_ROLES else {"tenantId": tenant_id}

        risks: list = []
        seen: set = set()

        # 1. Check ai_systems collection
        sys_doc = await db.ai_systems.find_one({"id": system_id, **tenant_filter}, {"_id": 0})
        if sys_doc:
            for r in sys_doc.get("risks", []):
                rid = r.get("id")
                if rid and rid not in seen:
                    risks.append(r)
                    seen.add(rid)

        # 2. Check ai_models collection
        model_doc = await db.ai_models.find_one({"id": system_id, **tenant_filter}, {"_id": 0})
        if model_doc:
            for r in model_doc.get("risks", []):
                rid = r.get("id")
                if rid and rid not in seen:
                    risks.append(r)
                    seen.add(rid)

        # 3. Standalone risk assessment collections
        risk_filter = {
            "$or": [{"system_id": system_id}, {"systemId": system_id}, {"modelId": system_id}],
            **tenant_filter,
        }
        for collection in (db.ai_risk_assessments, db.risks):
            cursor = collection.find(risk_filter, {"_id": 0})
            async for r in cursor:
                rid = r.get("id")
                if not rid or rid not in seen:
                    if not rid:
                        rid = str(r.get("_id", ""))
                        r["id"] = rid
                    risks.append(r)
                    seen.add(rid)

        # Normalise shape
        normalised = []
        for r in risks:
            normalised.append({
                "id":       r.get("id", ""),
                "title":    r.get("title") or r.get("name") or r.get("description", "")[:80] or "Unnamed Risk",
                "severity": r.get("severity") or r.get("riskLevel") or "medium",
                "status":   r.get("status") or "open",
                **{k: v for k, v in r.items() if k not in ("id", "title", "severity", "status")},
            })

        return normalised
    except Exception as e:
        raise HTTPException(status_code=500, detail="Internal server error")
