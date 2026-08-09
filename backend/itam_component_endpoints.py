"""ITAM Component API endpoints (Phase 60, ITAM-LIC-03)."""

from fastapi import APIRouter, Depends, status
from typing import List

from errors import APIError
from dependencies import PyObjectId
from authentication_service import get_current_user
from itam_models import Component, ComponentCreate, ComponentUpdate
from itam_component_service import ComponentService, get_component_service

router = APIRouter(prefix="/api/itam/components", tags=["ITAM Components"])


@router.post(
    "",
    response_model=Component,
    response_model_by_alias=False,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new ITAM component",
)
async def create_component_endpoint(
    component_data: ComponentCreate,
    component_service: ComponentService = Depends(get_component_service),
    current_user = Depends(get_current_user),
):
    return await component_service.create_component(component_data, current_user=current_user)


@router.get(
    "",
    response_model=List[Component],
    response_model_by_alias=False,
    summary="List all ITAM components",
)
async def list_components_endpoint(
    skip: int = 0,
    limit: int = 100,
    component_service: ComponentService = Depends(get_component_service),
    current_user = Depends(get_current_user)
):
    return await component_service.get_components(skip=skip, limit=limit, current_user=current_user)


@router.post(
    "/{component_id}/attach/{asset_id}",
    response_model=Component,
    response_model_by_alias=False,
    summary="Attach a component to an asset",
)
async def attach_component_endpoint(
    component_id: str,
    asset_id: str,
    component_service: ComponentService = Depends(get_component_service),
    current_user = Depends(get_current_user),
):
    return await component_service.attach_component(component_id, asset_id, current_user=current_user)


@router.post(
    "/{component_id}/detach/{asset_id}",
    response_model=Component,
    response_model_by_alias=False,
    summary="Detach a component from an asset",
)
async def detach_component_endpoint(
    component_id: str,
    asset_id: str,
    component_service: ComponentService = Depends(get_component_service),
    current_user = Depends(get_current_user),
):
    return await component_service.detach_component(component_id, asset_id, current_user=current_user)
