from fastapi import APIRouter, Depends, BackgroundTasks
import logging
from typing import Dict, Any
from data_lake_service import data_lake_service
from authentication_service import get_current_user
from auth_types import TokenData
import uuid

router = APIRouter()
logger = logging.getLogger(__name__)


@router.post("/api/data-lake/ingest")
async def ingest_data(
    data: Dict[str, Any],
    category: str = "general",
    zone: str = "raw",
    background_tasks: BackgroundTasks = None,
    current_user: TokenData = Depends(get_current_user),
):
    """Ingest data into the Data Lake."""
    file_id = str(uuid.uuid4())
    filename = f"{file_id}.json"
    if background_tasks:
        background_tasks.add_task(data_lake_service.ingest_data, data, zone, category, filename)
    else:
        await data_lake_service.ingest_data(data, zone, category, filename)
    return {"success": True, "file_id": file_id, "message": "Data queued for ingestion"}


@router.get("/api/data-lake/files")
async def list_files(
    category: str,
    zone: str = "raw",
    current_user: TokenData = Depends(get_current_user),
):
    """List files in the Data Lake."""
    files = await data_lake_service.list_files(zone, category)
    return {"success": True, "count": len(files), "files": files}


@router.get("/api/data-lake/stats")
async def get_stats(current_user: TokenData = Depends(get_current_user)):
    """Get Data Lake statistics."""
    return await data_lake_service.get_stats()
