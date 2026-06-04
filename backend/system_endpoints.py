from fastapi import APIRouter, Request, Depends
from typing import Dict, Any
import logging
from authentication_service import get_current_user
from auth_types import TokenData

# Setup Logging
logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/system", tags=["System Health"])

@router.get("/routes")
async def get_routes(request: Request, current_user: TokenData = Depends(get_current_user)):
    """List all registered API routes with their handler status."""
    routes = []
    for route in request.app.routes:
        if not (hasattr(route, "path") and route.path.startswith("/api/")):
            continue
        # A route is considered healthy if it has at least one endpoint function bound to it
        has_handler = bool(getattr(route, "endpoint", None))
        routes.append({
            "path": route.path,
            "name": route.name,
            "methods": list(route.methods) if hasattr(route, "methods") else ["GET"],
            "status": "Active" if has_handler else "Unregistered",
        })
    return routes

@router.post("/remediate")
async def remediate_route(data: Dict[str, Any], current_user: TokenData = Depends(get_current_user)):
    """Analyze a failed route and suggest a fix using AI."""
    route = data.get("route", "unknown")
    error = data.get("error", "Unknown Error")
    logger.info(f"Remediation requested for {route} with error: {error}")

    analysis = ""
    try:
        from ai_service import get_ai_service
        ai = get_ai_service()
        prompt = (
            f"A FastAPI backend endpoint '{route}' reported this error: {error}\n\n"
            "Provide a concise technical root-cause analysis and 3 specific remediation steps. "
            "Be direct and actionable. Respond in plain text, no markdown."
        )
        analysis = await ai.generate_text(prompt, max_tokens=300)
    except Exception as e:
        logger.debug("AI error analysis failed (non-fatal): %s", e)

    if not analysis:
        analysis = (
            f"Error on '{route}': {error}.\n"
            "1. Check backend logs for the full traceback.\n"
            "2. Verify the database connection and dependent services are running.\n"
            "3. Ensure all required environment variables are set."
        )

    return {
        "route": route,
        "analysis": analysis,
        "suggestion": analysis,
        "auto_fix_available": False,
    }
