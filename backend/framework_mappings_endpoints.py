"""Cross-framework mapping endpoints — /api/frameworks/*

Serves the NIST CSF 2.0 tree, the D3FEND defensive taxonomy, and the
ATT&CK -> D3FEND -> CSF crosswalk added in framework_mappings_service.py
(gap #3). Read-only reference data; auth-gated for consistency with
mitre_endpoints.py but not tenant-scoped (the taxonomy is global).
"""
from fastapi import APIRouter, Depends

from authentication_service import get_current_user
import framework_mappings_service as fm

router = APIRouter(prefix="/api/frameworks", tags=["Framework Mappings"])


@router.get("/nist-csf")
async def nist_csf(current_user=Depends(get_current_user)):
    """NIST CSF 2.0 — all 6 functions and their categories."""
    return fm.get_nist_csf()


@router.get("/d3fend")
async def d3fend(current_user=Depends(get_current_user)):
    """MITRE D3FEND defensive tactics and techniques."""
    return {"tactics": fm.get_d3fend()}


@router.get("/crosswalk")
async def crosswalk(current_user=Depends(get_current_user)):
    """Full ATT&CK -> D3FEND/CSF crosswalk, resolved to names."""
    return {"crosswalk": fm.get_crosswalk()}


@router.get("/technique/{attack_id}")
async def technique_mapping(attack_id: str, current_user=Depends(get_current_user)):
    """Resolve one ATT&CK technique id to its D3FEND countermeasures + CSF
    categories. Unknown ids return `mapped: false`, not a 404 — an unmapped
    technique is a data gap, not a client error."""
    return fm.map_technique(attack_id)
