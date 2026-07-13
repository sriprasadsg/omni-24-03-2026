import pytest
from unittest.mock import AsyncMock, patch
import risk_service

class TestRiskCreate:
    @patch("risk_service.RiskService._db")
    def test_create_risk_populates_inherent_and_residual(self, mock_db_method):
        db = AsyncMock()
        mock_db_method.return_value = db
        rs = risk_service.RiskService()
        risk_data = {
            "title": "Test Risk",
            "description": "desc",
            "category": "Cyber",
            "status": "Open",
            "likelihood": 4,
            "impact": 5,
            "owner": "owner",
            "residual_likelihood": 2,
            "residual_impact": 3,
        }
        result = rs.synchronous_create(risk_data) if hasattr(rs, "synchronous_create") else None
        # Since create_risk is async, use asyncio
        import asyncio
        result = asyncio.run(rs.create_risk(risk_data, tenant_id="t1"))

        assert result["risk_score"] == 20  # 4 * 5
        assert result["inherent_risk_score"] == 20  # defaults to likelihood*impact
        assert result["residual_risk_score"] == 6  # 2 * 3
        assert result["inherent_likelihood"] == 4
        assert result["inherent_impact"] == 5
        assert result["residual_likelihood"] == 2
        assert result["residual_impact"] == 3
        db.risks.insert_one.assert_called_once()

import asyncio

class TestRiskDefaults:
    @patch("risk_service.RiskService._db")
    def test_residual_defaults_to_inherent_when_omitted(self, mock_db_method):
        db = AsyncMock()
        mock_db_method.return_value = db
        rs = risk_service.RiskService()
        risk_data = {
            "likelihood": 4,
            "impact": 5,
            "title": "t",
            "description": "d",
            "category": "Cyber",
            "status": "Open",
            "owner": "o",
            # No residual fields
        }
        result = asyncio.run(rs.create_risk(risk_data, tenant_id="t1"))
        # residual defaults to inherent
        assert result["residual_risk_score"] == 20
        assert result["residual_likelihood"] == 4
        assert result["residual_impact"] == 5
        assert result["inherent_risk_score"] == 20

class TestRiskUpdate:
    @patch("risk_service.RiskService._db")
    def test_update_recomputes_residual_when_inputs_change(self, mock_db_method):
        db = AsyncMock()
        mock_db_method.return_value = db
        rs = risk_service.RiskService()
        existing = {
            "id": "r1",
            "likelihood": 4,
            "impact": 5,
            "risk_score": 20,
            "inherent_likelihood": 4,
            "inherent_impact": 5,
            "inherent_risk_score": 20,
            "residual_likelihood": 2,
            "residual_impact": 3,
            "residual_risk_score": 6,
        }
        db.risks.find_one = AsyncMock(return_value=existing)
        updates = {"residual_likelihood": 1, "residual_impact": 2}
        result = asyncio.run(rs.update_risk("r1", updates, tenant_id="t1", role="admin"))
        # residual updated
        assert result["residual_risk_score"] == 2  # 1 * 2
        assert result["residual_likelihood"] == 1
        assert result["residual_impact"] == 2
        # inherent unchanged
        assert result["inherent_risk_score"] == 20
