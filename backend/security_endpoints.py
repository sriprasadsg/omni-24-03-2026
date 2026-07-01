from fastapi import APIRouter

from security_cases_endpoints import router as cases_router
from security_keys_endpoints import router as keys_router
from security_ops_endpoints import router as ops_router
from security_scans_endpoints import router as scans_router

router = APIRouter()
router.include_router(cases_router)
router.include_router(keys_router)
router.include_router(ops_router)
router.include_router(scans_router)
