"""MITRE ATT&CK Endpoints — /api/mitre/*"""
from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from authentication_service import get_current_user
import mitre_service

router = APIRouter(prefix="/api/mitre", tags=["MITRE ATT&CK"])

@router.get("/matrix")
async def get_matrix(current_user=Depends(get_current_user)):
    return mitre_service.get_full_matrix()

@router.get("/coverage")
async def get_coverage(current_user=Depends(get_current_user)):
    heatmap = await mitre_service.get_coverage_heatmap(current_user.tenant_id or "default")
    return heatmap

@router.get("/technique/{technique_id}")
async def get_technique(technique_id: str, current_user=Depends(get_current_user)):
    return mitre_service.get_technique_detail(technique_id)

@router.get("/navigator-export")
async def export_navigator_layer(current_user=Depends(get_current_user)):
    heatmap = await mitre_service.get_coverage_heatmap(current_user.tenant_id or "default")
    layer = mitre_service.generate_navigator_layer(heatmap)
    return JSONResponse(
        content=layer,
        headers={"Content-Disposition": "attachment; filename=omni-agent-attack-layer.json"}
    )
