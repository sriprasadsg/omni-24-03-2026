"""MITRE ATT&CK Endpoints — /api/mitre/*"""
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse
import datetime
from authentication_service import get_current_user
import mitre_service

router = APIRouter(prefix="/api/mitre", tags=["MITRE ATT&CK"])


@router.get("/matrix")
async def get_matrix(current_user=Depends(get_current_user)):
    return mitre_service.get_full_matrix()


@router.get("/coverage")
async def get_coverage(current_user=Depends(get_current_user)):
    heatmap = await mitre_service.get_coverage_heatmap(current_user.tenant_id or None)
    return {
        "heatmap": heatmap,
        "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
    }


@router.post("/coverage/refresh")
async def force_refresh_coverage(current_user=Depends(get_current_user)):
    """Recompute heatmap and push to all connected clients via WebSocket."""
    tenant_id = current_user.tenant_id or None
    heatmap = await mitre_service.get_coverage_heatmap(tenant_id)
    if tenant_id:
        try:
            from websocket_manager import broadcast_mitre_heatmap
            await broadcast_mitre_heatmap(tenant_id, heatmap)
        except Exception:
            pass
    return {
        "heatmap": heatmap,
        "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
    }


@router.get("/technique/{technique_id}")
async def get_technique(technique_id: str, current_user=Depends(get_current_user)):
    result = mitre_service.get_technique_detail(technique_id)
    if isinstance(result, dict) and "error" in result:
        raise HTTPException(status_code=404, detail=result["error"])
    return result


@router.get("/techniques")
async def get_techniques(current_user=Depends(get_current_user)):
    """Alias — returns full matrix (tactics + techniques)."""
    return mitre_service.get_full_matrix()


@router.get("/tactics")
async def get_tactics(current_user=Depends(get_current_user)):
    """Alias — returns tactics list from the full matrix."""
    matrix = mitre_service.get_full_matrix()
    tactics = matrix.get("tactics", []) if isinstance(matrix, dict) else []
    return {"tactics": tactics}


@router.get("/heatmap")
async def get_heatmap(current_user=Depends(get_current_user)):
    """Alias — returns coverage heatmap."""
    heatmap = await mitre_service.get_coverage_heatmap(current_user.tenant_id or None)
    return {
        "heatmap": heatmap,
        "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
    }


@router.get("/navigator-export")
async def export_navigator_layer(current_user=Depends(get_current_user)):
    heatmap = await mitre_service.get_coverage_heatmap(current_user.tenant_id or None)
    layer = mitre_service.generate_navigator_layer(heatmap)
    return JSONResponse(
        content=layer,
        headers={"Content-Disposition": "attachment; filename=omni-agent-attack-layer.json"}
    )
