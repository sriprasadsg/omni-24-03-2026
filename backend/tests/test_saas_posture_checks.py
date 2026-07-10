import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from saas_posture_checks_service import saas_posture_checks_service

# Test harness based on _chain/_mkdb convention
def _chain(result):
    c = MagicMock()
    c.to_list = AsyncMock(return_value=result)
    return c

def _mkdb():
    db = MagicMock()
    db.saas_check_results = MagicMock()
    db.saas_check_results.update_one = AsyncMock(return_value=MagicMock(modified_count=1))
    return db

@pytest.mark.asyncio
async def test_run_posture_checks_reshaping():
    """Assert fail->FAIL, pass->PASS, missing->NO-DATA mapping."""
    db = _mkdb()
    connection = {
        "id": "conn-1",
        "tenant_id": "tenant-a",
        "provider": "github"
    }

    # Mock pull_all_evidence to return canned data
    # GITHUB_POSTURE_CHECKS look for _CTRL_SECURE_DEV, _CTRL_SOURCE_CODE, _CTRL_SEC_PATCH
    mock_evidence = [
        {"control_id": "Secure Development & Coding Simulation", "status": "fail", "content": "fail detail"},
        {"control_id": "Access to Source Code Simulation", "status": "pass", "content": "pass detail"}
        # _CTRL_SEC_PATCH missing -> should map to NO-DATA
    ]

    with patch("saas_integration_service.saas_integration_service.pull_all_evidence", new_callable=AsyncMock, return_value=mock_evidence):
        result = await saas_posture_checks_service.run_posture_checks(connection, db)

    assert result["ran"] == 3  # 3 checks defined for GitHub

    # Assert calls to upsert (there should be 3)
    assert db.saas_check_results.update_one.call_count == 3

    # Check one FAIL, one PASS, one NO-DATA
    # Note: update_one is called 3 times, we need to inspect call args
    upserts = [call[0][1]["$set"] for call in db.saas_check_results.update_one.call_args_list]

    # Map by checkId
    results_by_id = {u["checkId"]: u["result"] for u in upserts}
    assert results_by_id["gh-sd-001"] == "FAIL" # SECURE_DEV (fail)
    assert results_by_id["gh-sc-001"] == "PASS" # SOURCE_CODE (pass)
    assert results_by_id["gh-sp-001"] == "NO-DATA" # SEC_PATCH (missing)
