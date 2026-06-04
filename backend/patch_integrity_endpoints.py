import base64
import logging
from fastapi import APIRouter, HTTPException, Depends
from database import get_database
from security_service import get_security_service
from authentication_service import get_current_user
from auth_types import TokenData

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/patches", tags=["Patch Management"])


@router.post("/{patch_id}/verify-integrity")
async def verify_patch_integrity(
    patch_id: str,
    data: dict,
    _current_user: TokenData = Depends(get_current_user),
):
    """Verify patch file integrity using checksums."""
    try:
        security_service = get_security_service()
        result = security_service.verify_patch_integrity(
            patch_file_path=data.get("file_path"),
            expected_checksums=data.get("expected_checksums", {}),
        )
        db = get_database()
        await security_service.audit_security_event(
            db=db,
            event_type="patch_integrity_verified" if result["valid"] else "patch_integrity_failed",
            details={
                "patch_id":           patch_id,
                "valid":              result["valid"],
                "verified_checksums": result["verified_checksums"],
                "failed_checksums":   result["failed_checksums"],
            },
            severity="info" if result["valid"] else "warning",
        )
        return result
    except Exception as e:
        logger.error("Error verifying patch integrity: %s", e)
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/{patch_id}/generate-checksums")
async def generate_patch_checksums(
    patch_id: str,
    data: dict,
    _current_user: TokenData = Depends(get_current_user),
):
    """Generate checksums for a patch file."""
    try:
        security_service = get_security_service()
        checksums = security_service.generate_patch_checksum(patch_file_path=data.get("file_path"))
        db = get_database()
        await db.patches.update_one({"id": patch_id}, {"$set": {"checksums": checksums}})
        return {"success": True, "patch_id": patch_id, "checksums": checksums}
    except Exception as e:
        logger.error("Error generating checksums: %s", e)
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/{patch_id}/verify-signature")
async def verify_patch_signature(
    patch_id: str,
    data: dict,
    _current_user: TokenData = Depends(get_current_user),
):
    """Verify digital signature of a patch."""
    try:
        security_service = get_security_service()
        db = get_database()
        key_record = await db.signing_keys.find_one({"id": data.get("public_key_id")}, {"_id": 0})
        if not key_record:
            raise HTTPException(status_code=404, detail="Public key not found")

        p_data = base64.b64decode(data.get("patch_data"))
        signature = base64.b64decode(data.get("signature"))
        public_key_pem = key_record["public_key"].encode()

        result = security_service.verify_patch_signature(
            patch_data=p_data,
            signature=signature,
            public_key_pem=public_key_pem,
        )
        await security_service.audit_security_event(
            db=db,
            event_type="signature_verified" if result["valid"] else "signature_invalid",
            details={"patch_id": patch_id, "valid": result["valid"], "key_id": data.get("public_key_id")},
            severity="info" if result["valid"] else "critical",
        )
        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error verifying signature: %s", e)
        raise HTTPException(status_code=500, detail="Internal server error")
