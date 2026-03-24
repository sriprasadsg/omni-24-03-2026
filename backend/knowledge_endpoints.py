from fastapi import APIRouter, HTTPException, Depends, Body
from typing import List, Dict, Any
from authentication_service import get_current_user
from auth_types import TokenData
from rbac_service import rbac_service
import prompt_service

router = APIRouter(prefix="/api/knowledge", tags=["Knowledge Base"])

@router.post("/ingest")
async def ingest_knowledge(
    data: Dict[str, Any] = Body(...),
    current_user: TokenData = Depends(rbac_service.has_permission("manage:ai_risks"))
):
    """
    Ingest content into the knowledge base.
    """
    content = data.get("content")
    source = data.get("source", "manual")
    
    if not content:
        raise HTTPException(status_code=400, detail="Content is required")
        
    doc_id = await prompt_service.ingest_knowledge(content, source)
    return {"success": True, "doc_id": doc_id}

@router.post("/query")
async def query_knowledge(
    data: Dict[str, Any] = Body(...),
    current_user: TokenData = Depends(rbac_service.has_permission("view:ai_governance"))
):
    """
    Query the knowledge base.
    """
    query = data.get("query")
    if not query:
        raise HTTPException(status_code=400, detail="Query is required")
        
    results = await prompt_service.query_knowledge(query)
    return {"results": results}
