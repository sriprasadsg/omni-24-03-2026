"""ITAM Component API endpoints (Phase 60, ITAM-LIC-03)."""

from fastapi import APIRouter, Depends, status
from typing import List

from errors import APIError
from dependencies import PyObjectId
from auth_types import TokenData
from itam_asset_endpoints import _require_itam_admin
from itam_audit_service import log_itam_action
from itam_models import Component, ComponentCreate, ComponentUpdate
from itam_component_service import ComponentService, get_component_service

router = APIRouter(prefix="/api/itam/components", tags=["ITAM Components"])

# Asset-scoped sub-resource, mirroring itam_lifecycle_endpoints.py's
# GET /api/assets/{asset_id}/history — the in-repo shape for "list a
# sub-resource scoped by its parent's id in the URL path" (60-RESEARCH.md
# Pattern 3). Without this, ROADMAP Phase 60 success criterion 3 ("see it
# listed on that asset's record") has no real hydrated listing — only a
# bare array of component-id strings riding along on the generic asset GET.
asset_components_router = APIRouter(prefix="/api/assets", tags=["ITAM Components"])


@asset_components_router.get(
    "/{asset_id}/components",
    response_model=List[Component],
    response_model_by_alias=False,
    summary="List components attached to a parent asset",
)
async def list_asset_components_endpoint(
    asset_id: str,
    component_service: ComponentService = Depends(get_component_service),
    current_user: TokenData = Depends(_require_itam_admin),
):
    return await component_service.list_components_for_asset(asset_id, current_user=current_user)


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
    current_user: TokenData = Depends(_require_itam_admin),
):
    component = await component_service.create_component(component_data, current_user=current_user)
    await log_itam_action(
        current_user,
        action="itam_component.create",
        resource_type="itam_component",
        resource_id=component.id,
        details=f"Created component {component.name}",
    )
    return component


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
    current_user: TokenData = Depends(_require_itam_admin),
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
    current_user: TokenData = Depends(_require_itam_admin),
):
    component = await component_service.attach_component(component_id, asset_id, current_user=current_user)
    await log_itam_action(
        current_user,
        action="itam_component.attach",
        resource_type="itam_component",
        resource_id=component_id,
        details=f"Attached to asset {asset_id}",
    )
    return component


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
    current_user: TokenData = Depends(_require_itam_admin),
):
    component = await component_service.detach_component(component_id, asset_id, current_user=current_user)
    await log_itam_action(
        current_user,
        action="itam_component.detach",
        resource_type="itam_component",
        resource_id=component_id,
        details=f"Detached from asset {asset_id}",
    )
    return component
