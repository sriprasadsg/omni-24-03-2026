"""
Cache Management Endpoints
Provides API for cache statistics and management
"""

from fastapi import APIRouter, Depends, HTTPException
from typing import Dict
from cache_service import cache, invalidate_cache
from authentication_service import get_current_user

router = APIRouter(prefix="/api/cache", tags=["Cache"])

_CACHE_ADMIN_ROLES = {"Super Admin", "super_admin", "platform-admin"}


def _get_role(user):
    return getattr(user, "role", None) or (user.get("role") if isinstance(user, dict) else None)


@router.get("/stats")
async def get_cache_stats(current_user=Depends(get_current_user)) -> Dict:
    """Get cache statistics (admin only)"""
    if _get_role(current_user) not in _CACHE_ADMIN_ROLES:
        raise HTTPException(status_code=403, detail="Admin access required")
    return cache.get_stats()


@router.post("/clear")
async def clear_cache(
    pattern: str = "*",
    current_user=Depends(get_current_user),
) -> Dict:
    """Clear cache by pattern (admin only)"""
    if _get_role(current_user) not in _CACHE_ADMIN_ROLES:
        raise HTTPException(status_code=403, detail="Admin access required")
    if pattern == "*":
        cache.clear_all()
        return {"message": "All cache cleared", "pattern": pattern}
    else:
        invalidate_cache(pattern)
        return {"message": f"Cache cleared for pattern: {pattern}", "pattern": pattern}


@router.post("/invalidate/agents")
async def invalidate_agents_cache(current_user: dict = Depends(get_current_user)) -> Dict:
    """Invalidate agents cache"""
    if _get_role(current_user) not in _CACHE_ADMIN_ROLES:
        raise HTTPException(status_code=403, detail="Admin access required")
    invalidate_cache("agents:*")
    return {"message": "Agents cache invalidated"}


@router.post("/invalidate/assets")
async def invalidate_assets_cache(current_user: dict = Depends(get_current_user)) -> Dict:
    """Invalidate assets cache"""
    if _get_role(current_user) not in _CACHE_ADMIN_ROLES:
        raise HTTPException(status_code=403, detail="Admin access required")
    invalidate_cache("assets:*")
    return {"message": "Assets cache invalidated"}


@router.post("/invalidate/patches")
async def invalidate_patches_cache(current_user: dict = Depends(get_current_user)) -> Dict:
    """Invalidate patches cache"""
    if _get_role(current_user) not in _CACHE_ADMIN_ROLES:
        raise HTTPException(status_code=403, detail="Admin access required")
    invalidate_cache("patches:*")
    return {"message": "Patches cache invalidated"}


@router.post("/invalidate/vulnerabilities")
async def invalidate_vulns_cache(current_user: dict = Depends(get_current_user)) -> Dict:
    """Invalidate vulnerabilities cache"""
    if _get_role(current_user) not in _CACHE_ADMIN_ROLES:
        raise HTTPException(status_code=403, detail="Admin access required")
    invalidate_cache("vulnerabilities:*")
    return {"message": "Vulnerabilities cache invalidated"}
