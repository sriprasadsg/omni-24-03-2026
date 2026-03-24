from fastapi import APIRouter, Request, HTTPException, Depends
from typing import List, Dict, Any
import logging
from authentication_service import get_current_user
from auth_types import TokenData

# Setup Logging
logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/system", tags=["System Health"])

@router.get("/routes")
async def get_routes(request: Request, current_user: TokenData = Depends(get_current_user)):
    """
    List all registered API routes and their health status.
    """
    routes = []
    for route in request.app.routes:
        # Filter for API routes only
        if hasattr(route, "path") and route.path.startswith("/api/"):
            routes.append({
                "path": route.path,
                "name": route.name,
                "methods": list(route.methods) if hasattr(route, "methods") else ["GET"],
                "status": "Active" # In a real system, we might ping each one
            })
    return routes

@router.post("/remediate")
async def remediate_route(data: Dict[str, Any], current_user: TokenData = Depends(get_current_user)):
    """
    Analyze a failed route and suggest a fix using AI.
    """
    route = data.get("route")
    error = data.get("error", "Unknown Error")
    
    logger.info(f"Remediation requested for {route} with error: {error}")
    
    # Mock AI Logic (Replace with real LLM call if available)
    # In a real scenario, this would query the 'ai_service' with the traceback
    
    analysis = f"AI Analysis for endpoint '{route}':\n"
    analysis += f"The reported error '{error}' indicates a potential service disruption or configuration issue."
    
    suggestion = "Recommended Actions:\n"
    suggestion += "1. Verify that the dependent database service is running.\n"
    suggestion += "2. Check the backend logs for specific traceback details.\n"
    suggestion += "3. If this is a 500 error, it might be a missing import or syntax error in the endpoint handler."
    
    return {
        "route": route,
        "analysis": analysis,
        "suggestion": suggestion,
        "auto_fix_available": False # Set to True if we can actually run a command
    }
