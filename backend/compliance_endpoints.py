from fastapi import APIRouter

# Re-export for backward compatibility — imported by agent_heartbeat_endpoints,
# agent_tasks_endpoints, and generate_compliance_excel.
from compliance_evidence_processor import process_automated_evidence  # noqa: F401

from compliance_artifacts_endpoints import router as artifacts_router
from compliance_evidence_endpoints import router as evidence_router
from compliance_framework_mgmt_endpoints import router as framework_mgmt_router
from compliance_reports_endpoints import router as reports_router
from compliance_scans_endpoints import router as scans_router

router = APIRouter()
router.include_router(artifacts_router)
router.include_router(evidence_router)
router.include_router(framework_mgmt_router)
router.include_router(reports_router)
router.include_router(scans_router)
