import pytest
from backend.siem_engine import SIEMEngine
from backend.ueba_service import UEBAService
from backend.remediation_audit_service import RemediationAuditService

def test_soc_integration_flow():
    siem = SIEMEngine()
    ueba = UEBAService()
    audit = RemediationAuditService()

    # Mock anomaly
    anomaly = {"id": "a1", "type": "brute_force", "user": "test_user"}

    # Trigger integration
    result = siem.process_anomaly(anomaly, ueba, audit)

    assert result["status"] == "remediated"
    assert "audit_id" in result
