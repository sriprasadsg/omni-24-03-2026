"""OT / ICS security endpoints — /api/ot-ics/*  (gap #4)

Reference taxonomies (IEC 62443, Purdue model, ICS protocol risk) plus an
asset risk-assessment that maps OT exposure to IEC 62443 and NIST CSF. GRC
assessment content — no live OT-network scanning.
"""
from typing import Any

from fastapi import APIRouter, Depends

from authentication_service import get_current_user
import ot_ics_service as ot

router = APIRouter(prefix="/api/ot-ics", tags=["OT/ICS Security"])


@router.get("/reference")
async def reference(current_user=Depends(get_current_user)):
    """IEC 62443 security levels, Purdue model levels, and ICS protocol risks."""
    return ot.get_reference()


@router.post("/assess")
async def assess(body: dict[str, Any], current_user=Depends(get_current_user)):
    """Assess an OT asset descriptor into IEC 62443 / NIST CSF findings.

    Body: {
        "protocols": ["modbus", "dnp3", ...],   # ICS protocol keys
        "purdue_level": "1",                      # Purdue level (default "2")
        "internet_exposed": false,                # default false
    }
    """
    return ot.assess_asset(
        protocols=body.get("protocols") or [],
        purdue_level=str(body.get("purdue_level", "2")),
        internet_exposed=bool(body.get("internet_exposed", False)),
    )
