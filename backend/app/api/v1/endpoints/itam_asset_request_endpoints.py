from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from app.schemas.itam_asset_request_schemas import AssetRequestCreate, AssetRequestUpdate, AssetRequestInDB
from app.models.itam import AssetRequestStatus
from app.services.itam_asset_request_service import ItamAssetRequestService
from app.dependencies import get_db, get_current_user
from app.models.user import User as DBUser

router = APIRouter()

@router.post("/asset-requests", response_model=AssetRequestInDB, status_code=status.HTTP_201_CREATED)
def create_asset_request(
    request: AssetRequestCreate,
    db: Session = Depends(get_db),
    current_user: DBUser = Depends(get_current_user)
):
    service = ItamAssetRequestService(db)
    return service.create_asset_request(
        request_data=request,
        requester_id=current_user.id,
        tenant_id=current_user.tenant_id
    )

@router.get("/asset-requests/{request_id}", response_model=AssetRequestInDB)
def get_asset_request(
    request_id: int,
    db: Session = Depends(get_db),
    current_user: DBUser = Depends(get_current_user)
):
    service = ItamAssetRequestService(db)
    asset_request = service.get_asset_request(request_id)
    if not asset_request or asset_request.tenant_id != current_user.tenant_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Asset request not found")
    return asset_request

@router.get("/asset-requests", response_model=List[AssetRequestInDB])
def list_asset_requests(
    status_filter: Optional[AssetRequestStatus] = None,
    db: Session = Depends(get_db),
    current_user: DBUser = Depends(get_current_user)
):
    service = ItamAssetRequestService(db)
    return service.list_asset_requests(tenant_id=current_user.tenant_id, status=status_filter)

@router.post("/asset-requests/{request_id}/approve", response_model=AssetRequestInDB)
def approve_asset_request(
    request_id: int,
    db: Session = Depends(get_db),
    current_user: DBUser = Depends(get_current_user)
):
    if not current_user.is_approver:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized to approve requests")

    service = ItamAssetRequestService(db)
    approved_request = service.approve_asset_request(request_id, current_user.id)
    if not approved_request or approved_request.tenant_id != current_user.tenant_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Asset request not found or not pending")
    return approved_request

@router.post("/asset-requests/{request_id}/reject", response_model=AssetRequestInDB)
def reject_asset_request(
    request_id: int,
    db: Session = Depends(get_db),
    current_user: DBUser = Depends(get_current_user)
):
    if not current_user.is_approver:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized to reject requests")

    service = ItamAssetRequestService(db)
    rejected_request = service.reject_asset_request(request_id, current_user.id)
    if not rejected_request or rejected_request.tenant_id != current_user.tenant_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Asset request not found or not pending")
    return rejected_request