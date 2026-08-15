from fastapi import APIRouter

from app.api.v1.endpoints import itam_asset_request_endpoints
from app.api.v1.endpoints import itam_procurement_endpoints

api_router = APIRouter()

api_router.include_router(itam_asset_request_endpoints.router, prefix="/itam", tags=["ITAM - Asset Requests"])
api_router.include_router(itam_asset_request_endpoints.router, prefix="/itam", tags=["ITAM - Asset Requests"])
api_router.include_router(itam_procurement_endpoints.router, prefix="/itam", tags=["ITAM - Procurement"])