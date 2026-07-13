"""Tests for OSCAL export endpoint."""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from unittest.mock import AsyncMock, patch
from fastapi import FastAPI
from fastapi.testclient import TestClient
from authentication_service import get_current_user


def _app_with_limiter(router, user):
    """Build a minimal FastAPI app with permissions bypassed."""
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_current_user] = lambda: user
    return app


class TestOscagAssessmentResults:
    @pytest.fixture(autouse=True)
    def setup(self, tenant_user):
        import oscal_endpoints as mod
        self.mod = mod
        self.app = _app_with_limiter(mod.router, tenant_user)
        self.client = TestClient(self.app)

    def test_structure(self):
        """GET /api/oscal/assessment-results returns 200 with valid OSCAL structure."""
        mock_framework = {"id": "soc2", "name": "SOC2"}
        mock_control_rows = [
            {"Control ID": "CC1.1", "Control Name": "Control 1", "Control Status": "Compliant", "Evidence Desc": "Test evidence"}
        ]

        with patch.object(self.mod, "_build_report_data", new=AsyncMock(return_value=(mock_framework, [], mock_control_rows))):
            resp = self.client.get("/api/oscal/assessment-results?framework_id=soc2")

        assert resp.status_code == 200
        body = resp.json()
        assert "assessment-results" in body
        ar = body["assessment-results"]
        assert "uuid" in ar
        assert "metadata" in ar
        assert ar["metadata"]["oscal-version"] == "1.1.2"
        assert "results" in ar
        assert len(ar["results"]) == 1
        assert "findings" in ar["results"][0]

    def test_control_to_finding_mapping(self):
        """Each control maps to exactly one finding."""
        mock_framework = {"id": "soc2", "name": "SOC2"}
        mock_control_rows = [
            {"Control ID": "CC1.1", "Control Name": "Control 1", "Control Status": "Compliant", "Evidence Desc": "Evidence 1"},
            {"Control ID": "CC1.2", "Control Name": "Control 2", "Control Status": "Non-Compliant", "Evidence Desc": "Evidence 2"},
        ]

        with patch.object(self.mod, "_build_report_data", new=AsyncMock(return_value=(mock_framework, [], mock_control_rows))):
            resp = self.client.get("/api/oscal/assessment-results?framework_id=soc2")

        findings = resp.json()["assessment-results"]["results"][0]["findings"]
        assert len(findings) == 2
        control_ids = [f["target"][0]["ref"] for f in findings]
        assert "CC1.1" in control_ids
        assert "CC1.2" in control_ids

    def test_non_compliant_mapped_to_planned(self):
        """Non-Compliant controls map to implementation-status 'planned' (not 'not-applicable')."""
        mock_framework = {"id": "soc2", "name": "SOC2"}
        mock_control_rows = [
            {"Control ID": "CC1.1", "Control Name": "Control 1", "Control Status": "Non-Compliant", "Evidence Desc": "Gap evidence"}
        ]

        with patch.object(self.mod, "_build_report_data", new=AsyncMock(return_value=(mock_framework, [], mock_control_rows))):
            resp = self.client.get("/api/oscal/assessment-results?framework_id=soc2")

        finding = resp.json()["assessment-results"]["results"][0]["findings"][0]
        assert finding["status"]["state"] == "planned"
        assert "remarks" in finding  # gap note present

    def test_tenant_isolation(self, tenant_user):
        """Tenant without tenant_id returns 403."""
        no_tenant_user = type(tenant_user)()
        no_tenant_user.tenant_id = None

        app = _app_with_limiter(self.mod.router, no_tenant_user)
        client = TestClient(app)
        resp = client.get("/api/oscal/assessment-results?framework_id=soc2")
        assert resp.status_code == 403
        assert "Tenant context required" in resp.json().get("detail", "")

    def test_framework_not_found(self):
        """ValueError from _build_report_data surfaces as 404."""
        mock_framework = {"id": "soc2", "name": "SOC2"}

        with patch.object(self.mod, "_build_report_data", new=AsyncMock(side_effect=ValueError("Framework not found"))):
            resp = self.client.get("/api/oscal/assessment-results?framework_id=soc2")

        assert resp.status_code == 404