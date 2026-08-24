import logging
from typing import List, Dict, Any

from fastapi import APIRouter, Depends, HTTPException, status
from auth_types import TokenData
from authentication_service import get_current_user
from database import get_database, TenantIsolatedDatabase
from rbac_utils import verify_permission
from itam_procurement_service import ItamProcurementService
from itam_models import PurchaseOrder, PurchaseOrderCreate, PurchaseOrderUpdate # Assuming schemas are in itam_models for simplicity based on previous steps

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/itam/purchase-orders", tags=["ITAM Procurement"])

async def _require_procurement_admin(current_user: TokenData = Depends(get_current_user)):
    """
    Dependency to ensure the current user has 'manage:procurement' permission.
    """
    if not await verify_permission(current_user, "manage:procurement"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User does not have permission to manage ITAM procurement."
        )
    return current_user

@router.post("", response_model=PurchaseOrder, response_model_by_alias=False, status_code=status.HTTP_201_CREATED)
async def create_purchase_order_endpoint(
    po_data: PurchaseOrderCreate,
    current_user: TokenData = Depends(_require_procurement_admin)
):
    tenant_id = current_user.tenant_id
    if not tenant_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Tenant ID not found.")

    db = get_database()
    service = ItamProcurementService(db)
    try:
        po = await service.create_purchase_order(tenant_id, po_data)
        return po
    except Exception as e:
        logger.error(f"Failed to create purchase order: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to create purchase order.")

@router.get("/{po_id}", response_model=PurchaseOrder, response_model_by_alias=False)
async def get_purchase_order_endpoint(
    po_id: str,
    current_user: TokenData = Depends(_require_procurement_admin)
):
    tenant_id = current_user.tenant_id
    if not tenant_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Tenant ID not found.")

    db = get_database()
    service = ItamProcurementService(db)
    po = await service.get_purchase_order(tenant_id, po_id)
    if not po:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Purchase Order not found.")
    return po

@router.get("", response_model=List[PurchaseOrder], response_model_by_alias=False)
async def list_purchase_orders_endpoint(
    skip: int = 0,
    limit: int = 100,
    current_user: TokenData = Depends(_require_procurement_admin)
):
    tenant_id = current_user.tenant_id
    if not tenant_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Tenant ID not found.")

    db = get_database()
    service = ItamProcurementService(db)
    pos = await service.list_purchase_orders(tenant_id, skip, limit)
    return pos

@router.put("/{po_id}", response_model=PurchaseOrder, response_model_by_alias=False)
async def update_purchase_order_endpoint(
    po_id: str,
    po_data: PurchaseOrderUpdate,
    current_user: TokenData = Depends(_require_procurement_admin)
):
    tenant_id = current_user.tenant_id
    if not tenant_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Tenant ID not found.")

    db = get_database()
    service = ItamProcurementService(db)
    po = await service.update_purchase_order(tenant_id, po_id, po_data)
    if not po:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Purchase Order not found.")
    return po

@router.delete("/{po_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_purchase_order_endpoint(
    po_id: str,
    current_user: TokenData = Depends(_require_procurement_admin)
):
    tenant_id = current_user.tenant_id
    if not tenant_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Tenant ID not found.")

    db = get_database()
    service = ItamProcurementService(db)
    deleted = await service.delete_purchase_order(tenant_id, po_id)
    if not deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Purchase Order not found.")
    return
