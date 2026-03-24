from fastapi import APIRouter, HTTPException, BackgroundTasks
from typing import Dict, Any, List
from data_lake_service import data_lake_service
import uuid

router = APIRouter()

@router.post("/api/data-lake/ingest")
async def ingest_data(data: Dict[str, Any], category: str = "general", zone: str = "raw", background_tasks: BackgroundTasks = None):
    """
    Ingest data into the Data Lake.
    """
    file_id = str(uuid.uuid4())
    filename = f"{file_id}.json"
    
    # Run I/O in background to ensure API responsiveness
    if background_tasks:
        background_tasks.add_task(data_lake_service.ingest_data, data, zone, category, filename)
    else:
        # Fallback for synchronous execution if needed
        await data_lake_service.ingest_data(data, zone, category, filename)

    return {"success": True, "file_id": file_id, "message": "Data queued for ingestion"}

@router.get("/api/data-lake/files")
async def list_files(category: str, zone: str = "raw"):
    """
    List files in the Data Lake.
    """
    files = await data_lake_service.list_files(zone, category)
    return {"success": True, "count": len(files), "files": files}

@router.get("/api/data-lake/stats")
async def get_stats():
    """
    Get Data Lake statistics.
    """
    return await data_lake_service.get_stats()
