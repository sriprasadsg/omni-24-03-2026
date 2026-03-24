from fastapi import APIRouter, Depends, Query
from typing import List, Dict, Any
from authentication_service import get_current_user
from tracing_service import get_tracing_service
from database import get_database

router = APIRouter(prefix="/api/tracing", tags=["Distributed Tracing"])

@router.get("/traces")
async def get_traces(
    limit: int = 50,
    current_user: dict = Depends(get_current_user)
):
    """Get recent distributed traces."""
    db = get_database()
    service = get_tracing_service(db)
    return await service.get_traces(limit)

@router.get("/service-map")
async def get_service_map(
    current_user: dict = Depends(get_current_user)
):
    """Get the live service dependency map."""
    db = get_database()
    service = get_tracing_service(db)
    return await service.get_service_map()
