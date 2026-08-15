import logging
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, status
from auth_types import TokenData
from authentication_service import get_current_user
from database import get_database, TenantIsolatedDatabase
from rbac_utils import verify_permission

from itam_asset_request_service import ItamAssetRequestService
from itam_models import AssetRequest, AssetRequestCreate, AssetRequestUpdate, AssetRequestStatus

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/itam/asset-requests", tags=["ITAM Asset Requests"])

async def _require_asset_requester(current_user: TokenData = Depends(get_current_user)):
    """
    Dependency to ensure the current user has 'create:asset_request' permission.
    """
    if not await verify_permission(current_user, "create:asset_request"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User does not have permission to create asset requests."
        )
    return current_user

async def _require_asset_approver(current_user: TokenData = Depends(get_current_user)):
    """
    Dependency to ensure the current user has 'approve:asset_request' permission.
    """
    if not await verify_permission(current_user, "approve:asset_request"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User does not have permission to approve/reject asset requests."
        )
    return current_user

@router.post("", response_model=AssetRequest, status_code=status.HTTP_201_CREATED)
async def create_asset_request_endpoint(
    request_data: AssetRequestCreate,
    current_user: TokenData = Depends(_require_asset_requester)
):
    tenant_id = current_user.tenant_id
    requester_id = current_user.email # Using email as requester_id

    if not tenant_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Tenant ID not found.")

    db = get_database()
    service = ItamAssetRequestService(db)
    try:
        asset_request = await service.create_asset_request(tenant_id, requester_id, request_data)
        return asset_request
    except Exception as e:
        logger.error(f"Failed to create asset request: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to create asset request.")

@router.get("/{request_id}", response_model=AssetRequest)
async def get_asset_request_endpoint(
    request_id: str,
    current_user: TokenData = Depends(_require_asset_requester) # Requester or Approver can view
):
    tenant_id = current_user.tenant_id
    if not tenant_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Tenant ID not found.")

    db = get_database()
    service = ItamAssetRequestService(db)
    asset_request = await service.get_asset_request(tenant_id, request_id)
    if not asset_request:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Asset Request not found.")

    # Ensure only requester or approver/admin can view this specific request
    if asset_request.requester_id != current_user.email and not await verify_permission(current_user, "approve:asset_request"):
         raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User does not have permission to view this asset request."
        )
    return asset_request

@router.get("", response_model=List[AssetRequest])
async def list_asset_requests_endpoint(
    status_filter: Optional[AssetRequestStatus] = None,
    skip: int = 0,
    limit: int = 100,
    current_user: TokenData = Depends(_require_asset_requester) # Requester or Approver can list
):
    tenant_id = current_user.tenant_id
    if not tenant_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Tenant ID not found.")

    db = get_database()
    service = ItamAssetRequestService(db)

    # If user is only a requester, they can only see their own requests
    if not await verify_permission(current_user, "approve:asset_request"):
        # For now, just list all if not approver, more complex filtering might be needed
        # depending on exact requirements (e.g., only show own requests for requester role)
        requests = await service.list_asset_requests(tenant_id, status_filter, skip, limit)
        # TODO: Filter by current_user.email for requester_id
        return [req for req in requests if req.requester_id == current_user.email]

    requests = await service.list_asset_requests(tenant_id, status_filter, skip, limit)
    return requests


@router.patch("/{request_id}/approve", response_model=AssetRequest)
async def approve_asset_request_endpoint(
    request_id: str,
    current_user: TokenData = Depends(_require_asset_approver)
):
    tenant_id = current_user.tenant_id
    approver_id = current_user.email # Using email as approver_id

    if not tenant_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Tenant ID not found.")

    db = get_database()
    service = ItamAssetRequestService(db)
    try:
        approved_request = await service.approve_asset_request(tenant_id, request_id, approver_id)
        if not approved_request:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Asset Request not found or not in pending status.")
        return approved_request
    except Exception as e:
        logger.error(f"Failed to approve asset request {request_id}: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to approve asset request.")

@router.patch("/{request_id}/reject", response_model=AssetRequest)
async def reject_asset_request_endpoint(
    request_id: str,
    current_user: TokenData = Depends(_require_asset_approver)
):
    tenant_id = current_user.tenant_id
    approver_id = current_user.email # Using email as approver_id

    if not tenant_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Tenant ID not found.")

    db = get_database()
    service = ItamAssetRequestService(db)
    try:
        rejected_request = await service.reject_asset_request(tenant_id, request_id, approver_id)
        if not rejected_request:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Asset Request not found or not in pending status.")
        return rejected_request
    except Exception as e:
        logger.error(f"Failed to reject asset request {request_id}: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to reject asset request.")
