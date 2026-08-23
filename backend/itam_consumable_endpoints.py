"""ITAM Consumable API endpoints (Phase 60, ITAM-LIC-02)."""

from fastapi import APIRouter, Depends, status, Response
from typing import List

from errors import APIError
from dependencies import PyObjectId
from auth_types import TokenData
from itam_asset_endpoints import _require_itam_admin, _require_itam_viewer
from itam_audit_service import log_itam_action
from itam_models import Consumable, ConsumableCreate, ConsumableUpdate, ConsumableCheckoutRequest
from itam_consumable_service import ConsumableService, get_consumable_service

router = APIRouter(prefix="/api/itam/consumables", tags=["ITAM Consumables"])


@router.post(
    "",
    response_model=Consumable,
    response_model_by_alias=False,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new ITAM consumable",
)
async def create_consumable_endpoint(
    consumable_data: ConsumableCreate,
    consumable_service: ConsumableService = Depends(get_consumable_service),
    current_user: TokenData = Depends(_require_itam_admin),
):
    consumable = await consumable_service.create_consumable(consumable_data, current_user=current_user)
    await log_itam_action(
        current_user,
        action="itam_consumable.create",
        resource_type="itam_consumable",
        resource_id=consumable.id,
        details=f"Created consumable {consumable.name}",
    )
    return consumable


@router.get(
    "",
    response_model=List[Consumable],
    response_model_by_alias=False,
    summary="List all ITAM consumables",
)
async def list_consumables_endpoint(
    skip: int = 0,
    limit: int = 100,
    consumable_service: ConsumableService = Depends(get_consumable_service),
    current_user: TokenData = Depends(_require_itam_viewer),
):
    return await consumable_service.get_consumables(skip=skip, limit=limit, current_user=current_user)


@router.get(
    "/{consumable_id}",
    response_model=Consumable,
    response_model_by_alias=False,
    summary="Get a specific ITAM consumable by ID",
)
async def get_consumable_endpoint(
    consumable_id: str,
    consumable_service: ConsumableService = Depends(get_consumable_service),
    current_user: TokenData = Depends(_require_itam_viewer),
):
    consumable = await consumable_service.get_consumable(consumable_id, current_user=current_user)
    if not consumable:
        raise APIError(status_code=status.HTTP_404_NOT_FOUND, detail="Consumable not found")
    return consumable


@router.put(
    "/{consumable_id}",
    response_model=Consumable,
    response_model_by_alias=False,
    summary="Update an ITAM consumable",
)
async def update_consumable_endpoint(
    consumable_id: str,
    consumable_data: ConsumableUpdate,
    consumable_service: ConsumableService = Depends(get_consumable_service),
    current_user: TokenData = Depends(_require_itam_admin),
):
    consumable = await consumable_service.update_consumable(consumable_id, consumable_data, current_user=current_user)
    if not consumable:
        raise APIError(status_code=status.HTTP_404_NOT_FOUND, detail="Consumable not found")
    await log_itam_action(
        current_user,
        action="itam_consumable.update",
        resource_type="itam_consumable",
        resource_id=consumable_id,
        details=f"Updated fields: {', '.join(sorted(consumable_data.model_dump(exclude_none=True).keys()))}",
    )
    return consumable


@router.delete(
    "/{consumable_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete an ITAM consumable",
)
async def delete_consumable_endpoint(
    consumable_id: str,
    consumable_service: ConsumableService = Depends(get_consumable_service),
    current_user: TokenData = Depends(_require_itam_admin),
):
    if not await consumable_service.delete_consumable(consumable_id, current_user=current_user):
        raise APIError(status_code=status.HTTP_404_NOT_FOUND, detail="Consumable not found")
    await log_itam_action(
        current_user,
        action="itam_consumable.delete",
        resource_type="itam_consumable",
        resource_id=consumable_id,
        details=f"Deleted consumable {consumable_id}",
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/{consumable_id}/checkout",
    response_model=Consumable,
    response_model_by_alias=False,
    summary="Checkout ITAM consumable quantity",
)
async def checkout_consumable_endpoint(
    consumable_id: str,
    request: ConsumableCheckoutRequest,
    consumable_service: ConsumableService = Depends(get_consumable_service),
    current_user: TokenData = Depends(_require_itam_admin),
):
    consumable = await consumable_service.checkout_consumable(consumable_id, request, current_user=current_user)
    await log_itam_action(
        current_user,
        action="itam_consumable.checkout",
        resource_type="itam_consumable",
        resource_id=consumable_id,
        details=f"Checked out quantity {request.quantity} to {request.assignedToType} {request.assignedTo}",
    )
    return consumable


@router.post(
    "/{consumable_id}/checkin",
    response_model=Consumable,
    response_model_by_alias=False,
    summary="Check-in ITAM consumable quantity",
)
async def checkin_consumable_endpoint(
    consumable_id: str,
    quantity: int,
    consumable_service: ConsumableService = Depends(get_consumable_service),
    current_user: TokenData = Depends(_require_itam_admin),
):
    consumable = await consumable_service.checkin_consumable(consumable_id, quantity, current_user=current_user)
    await log_itam_action(
        current_user,
        action="itam_consumable.checkin",
        resource_type="itam_consumable",
        resource_id=consumable_id,
        details=f"Checked in quantity {quantity}",
    )
    return consumable
