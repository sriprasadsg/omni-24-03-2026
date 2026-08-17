"""Firmware/hardware attestation endpoints — /api/firmware-attestation/*  (gap #5)

The attestation-posture complement to firmware_driver_service's version
inventory: Secure Boot / TPM / Measured Boot / DMA-protection posture mapped to
NIST CSF. Descriptors come from agent-collected evidence upstream.
"""
from typing import Any

from fastapi import APIRouter, Depends

from authentication_service import get_current_user
import firmware_attestation_service as fa

router = APIRouter(prefix="/api/firmware-attestation", tags=["Firmware Attestation"])


@router.get("/checks")
async def checks(current_user=Depends(get_current_user)):
    """The attestation check catalog (Secure Boot, TPM, Measured Boot, …)."""
    return {"checks": fa.get_checks()}


@router.post("/assess")
async def assess(body: dict[str, Any], current_user=Depends(get_current_user)):
    """Assess a firmware/hardware descriptor against the attestation checks.

    Body: {"descriptor": {"secure_boot": true, "tpm_present": true,
    "tpm_2_0": true, "measured_boot": false, "dma_protection": true, ...}}
    Missing keys are reported as 'unknown', never assumed secure.
    """
    return fa.assess_posture(body.get("descriptor") or {})
