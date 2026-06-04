from fastapi import APIRouter

from patch_core_endpoints import router as core_router
from patch_enrichment_endpoints import router as enrichment_router
from patch_integrity_endpoints import router as integrity_router
from patch_software_endpoints import router as software_router

router = APIRouter()
router.include_router(core_router)
router.include_router(enrichment_router)
router.include_router(integrity_router)
router.include_router(software_router)
