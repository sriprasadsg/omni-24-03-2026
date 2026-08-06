
"""ITAM Consumable API endpoints (Phase 60, ITAM-LIC-02)."""

from fastapi import APIRouter, Depends, status, Response
from typing import List, Optional

from backend.database import get_database, get_tenant_db
from backend.errors import APIError
from backend.models.shared import InjectedDependencies, PyObjectId
from backend.models.users import User
from backend.security import get_current_user
from backend.dependencies import get_injected_dependencies
from backend.itam_models import Consumable, ConsumableCreate, ConsumableUpdate, ConsumableCheckoutRequest
from backend.itam_consumable_service import ConsumableService, get_consumable_service

router = APIRouter(prefix="/itam/consumables", tags=["ITAM Consumables"])

@router.post(
    "/",
    response_model=Consumable,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new ITAM consumable"
)
async def create_consumable_endpoint(
    consumable_data: ConsumableCreate,
    consumable_service: ConsumableService = Depends(get_consumable_service),
    current_user: User = Depends(get_current_user(required_roles=["admin", "itam_manager"]))
):
    try:
        return await consumable_service.create_consumable(consumable_data)
    except APIError as e:
        raise e
    except Exception as e:
        raise APIError(status_code=500, detail=f"Failed to create consumable: {e}")

@router.get(
    "/",
    response_model=List[Consumable],
    summary="List all ITAM consumables"
)
async def list_consumables_endpoint(
    skip: int = 0,
    limit: int = 100,
    consumable_service: ConsumableService = Depends(get_consumable_service),
    current_user: User = Depends(get_current_user(required_roles=["admin", "itam_manager", "auditor", "viewer"]))
):
    return await consumable_service.get_consumables(skip=skip, limit=limit)

@router.get(
    "/{consumable_id}",
    response_model=Consumable,
    summary="Get a specific ITAM consumable by ID"
)
async def get_consumable_endpoint(
    consumable_id: PyObjectId,
    consumable_service: ConsumableService = Depends(get_consumable_service),
    current_user: User = Depends(get_current_user(required_roles=["admin", "itam_manager", "auditor", "viewer"]))
):
    consumable = await consumable_service.get_consumable(consumable_id)
    if not consumable:
        raise APIError(status_code=status.HTTP_404_NOT_FOUND, detail="Consumable not found")
    return consumable

@router.put(
    "/{consumable_id}",
    response_model=Consumable,
    summary="Update an ITAM consumable"
)
async def update_consumable_endpoint(
    consumable_id: PyObjectId,
    consumable_data: ConsumableUpdate,
    consumable_service: ConsumableService = Depends(get_consumable_service),
    current_user: User = Depends(get_current_user(required_roles=["admin", "itam_manager"]))
):
    consumable = await consumable_service.update_consumable(consumable_id, consumable_data)
    if not consumable:
        raise APIError(status_code=status.HTTP_404_NOT_FOUND, detail="Consumable not found")
    return consumable

@router.delete(
    "/{consumable_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete an ITAM consumable"
)
async def delete_consumable_endpoint(
    consumable_id: PyObjectId,
    consumable_service: ConsumableService = Depends(get_consumable_service),
    current_user: User = Depends(get_current_user(required_roles=["admin", "itam_manager"]))
):
    if not await consumable_service.delete_consumable(consumable_id):
        raise APIError(status_code=status.HTTP_404_NOT_FOUND, detail="Consumable not found")
    return Response(status_code=status.HTTP_204_NO_CONTENT)

@router.post(
    "/{consumable_id}/checkout",
    response_model=Consumable,
    summary="Checkout ITAM consumable quantity"
)
async def checkout_consumable_endpoint(
    consumable_id: PyObjectId,
    request: ConsumableCheckoutRequest,
    consumable_service: ConsumableService = Depends(get_consumable_service),
    current_user: User = Depends(get_current_user(required_roles=["admin", "itam_manager"]))
):
    try:
        return await consumable_service.checkout_consumable(consumable_id, request)
    except APIError as e:
        raise e
    except Exception as e:
        raise APIError(status_code=500, detail=f"Failed to checkout consumable: {e}")

@router.post(
    "/{consumable_id}/checkin",
    response_model=Consumable,
    summary="Check-in ITAM consumable quantity"
)
async def checkin_consumable_endpoint(
    consumable_id: PyObjectId,
    quantity: int,
    consumable_service: ConsumableService = Depends(get_consumable_service),
    current_user: User = Depends(get_current_user(required_roles=["admin", "itam_manager"]))
):
    try:
        return await consumable_service.checkin_consumable(consumable_id, quantity)
    except APIError as e:
        raise e
    except Exception as e:
        raise APIError(status_code=500, detail=f"Failed to check-in consumable: {e}")
