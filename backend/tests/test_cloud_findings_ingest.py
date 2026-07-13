import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from backend.m365_ingest import poll_m365_secure_scores
from backend.mongodb_atlas_ingest import poll_mongodb_atlas_findings
from backend.cloud_accounts_service import scan_account
import json


@pytest.fixture
def mock_db():
    db = MagicMock()
    db._db.cloud_accounts.find_one = AsyncMock()
    db._db.cloud_accounts.update_one = AsyncMock()
    db.cloud_findings = MagicMock()
    db.cloud_findings.insert_many = AsyncMock()
    # Default to_list returns empty list for findings.query chain
    db.cloud_findings.find.return_value.to_list = AsyncMock(return_value=[])
    db.cloud_check_results = MagicMock()
    db.cloud_check_results.update_one = AsyncMock(return_value=MagicMock(modified_count=1))
    return db


@pytest.fixture(autouse=True)
def mock_get_db(mock_db):
    with patch("backend.m365_ingest.get_database", return_value=mock_db), \
         patch("backend.mongodb_atlas_ingest.get_database", return_value=mock_db):
        yield mock_db


# --- Task 1: Ingest module unit tests ---

@pytest.mark.asyncio
async def test_m365_poll_success():
    """M365 poll with mocked msal+httpx returns 1 finding."""
    config = {"tenant_id": "t", "client_id": "c", "client_secret": "s"}
    mock_app = MagicMock()
    mock_app.acquire_token_for_client.return_value = {"access_token": "tok"}

    # Mock secureScoreControlProfiles response shape
    mock_resp = MagicMock()
    mock_resp.json.return_value = {
        "value": [
            {"id": "c1", "controlName": "MFA for Admins", "currentScore": 0, "maxScore": 100, "controlCategory": "Identity"}
        ]
    }
    mock_resp.raise_for_status = MagicMock()

    mock_client = AsyncMock()
    mock_client.get.return_value = mock_resp
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock()

    with patch("backend.m365_ingest.ConfidentialClientApplication", return_value=mock_app), \
         patch("httpx.AsyncClient", return_value=mock_client):
        count = await poll_m365_secure_scores(config, "acc1", "ten1")
        assert count == 1


@pytest.mark.asyncio
async def test_m365_poll_missing_config():
    assert await poll_m365_secure_scores({}, "acc1", "ten1") == 0


@pytest.mark.asyncio
async def test_m365_poll_raise_returns_0():
    config = {"tenant_id": "t", "client_id": "c", "client_secret": "s"}
    mock_app = MagicMock()
    mock_app.acquire_token_for_client.side_effect = Exception("Auth failed")

    with patch("backend.m365_ingest.ConfidentialClientApplication", return_value=mock_app), \
         patch("httpx.AsyncClient"):
        count = await poll_m365_secure_scores(config, "acc1", "ten1")
        assert count == 0


@pytest.mark.asyncio
async def test_atlas_poll_success():
    config = {"atlas_public_key": "pk", "atlas_private_key": "prk", "atlas_project_id": "pid"}
    with patch("backend.mongodb_atlas_ingest._atlas_get_sync", return_value={"results": [{"name": "c1"}]}):
        count = await poll_mongodb_atlas_findings(config, "acc1", "ten1")
        assert count == 1


@pytest.mark.asyncio
async def test_atlas_poll_missing_config():
    assert await poll_mongodb_atlas_findings({}, "acc1", "ten1") == 0


@pytest.mark.asyncio
async def test_atlas_poll_raise_returns_0():
    config = {"atlas_public_key": "pk", "atlas_private_key": "prk", "atlas_project_id": "pid"}
    with patch("backend.mongodb_atlas_ingest._atlas_get_sync", side_effect=Exception("API down")):
        count = await poll_mongodb_atlas_findings(config, "acc1", "ten1")
        assert count == 0


# --- Task 2: scan_account dispatch + end-to-end ---

@pytest.mark.asyncio
async def test_scan_account_m365_dispatch(mock_db):
    account = {"id": "acc1", "provider": "microsoft365", "credentials_ref": "enc_creds"}
    mock_db._db.cloud_accounts.find_one = AsyncMock(return_value=account)
    mock_db._db.cloud_accounts.update_one = AsyncMock()

    config_json = '{"tenant_id": "common", "client_id": "c", "client_secret": "s"}'

    with patch("backend.cloud_accounts_service._decrypt", return_value=config_json), \
         patch("backend.m365_ingest.poll_m365_secure_scores", new_callable=AsyncMock) as mock_ingest_backend, \
         patch("m365_ingest.poll_m365_secure_scores", new_callable=AsyncMock) as mock_ingest, \
         patch("backend.cloud_accounts_service.cloud_checks_service.run_checks", new_callable=AsyncMock) as mock_run_checks:

        await scan_account(mock_db, "acc1", "ten1")

        assert mock_ingest.called or mock_ingest_backend.called
        mock_run_checks.assert_called_once_with("acc1", "microsoft365", "ten1")


@pytest.mark.asyncio
async def test_scan_account_atlas_dispatch(mock_db):
    account = {"id": "acc1", "provider": "mongodb_atlas", "credentials_ref": "enc_creds"}
    mock_db._db.cloud_accounts.find_one = AsyncMock(return_value=account)
    mock_db._db.cloud_accounts.update_one = AsyncMock()

    config_json = '{"atlas_public_key": "pub", "atlas_private_key": "priv", "atlas_project_id": "pid"}'

    with patch("backend.cloud_accounts_service._decrypt", return_value=config_json), \
         patch("backend.mongodb_atlas_ingest.poll_mongodb_atlas_findings", new_callable=AsyncMock) as mock_ingest_backend, \
         patch("mongodb_atlas_ingest.poll_mongodb_atlas_findings", new_callable=AsyncMock) as mock_ingest, \
         patch("backend.cloud_accounts_service.cloud_checks_service.run_checks", new_callable=AsyncMock) as mock_run_checks:

        await scan_account(mock_db, "acc1", "ten1")

        assert mock_ingest.called or mock_ingest_backend.called
        mock_run_checks.assert_called_once_with("acc1", "mongodb_atlas", "ten1")



@pytest.mark.asyncio
async def test_scan_account_m365_simulated_false_end_to_end(mock_db):
    """End-to-end: findings present in cloud_findings -> run_checks sets simulated=False."""
    account = {"id": "acc1", "provider": "microsoft365", "credentials_ref": "enc_creds"}
    mock_db._db.cloud_accounts.find_one = AsyncMock(return_value=account)
    mock_db._db.cloud_accounts.update_one = AsyncMock()

    # Cloud_findings already populated (simulating real ingested findings)
    mock_db.cloud_findings.find.return_value.to_list = AsyncMock(return_value=[
        {"accountId": "acc1", "tenantId": "ten1", "severity": "critical", "title": "M365 Critical Finding", "checkId": "M365-001"}
    ])

    # Do NOT mock run_checks — let it run naturally against the findings mock
    config_json = '{"tenant_id": "common", "client_id": "c", "client_secret": "s"}'

    with patch("backend.cloud_accounts_service._decrypt", return_value=config_json), \
         patch("backend.m365_ingest.poll_m365_secure_scores", new_callable=AsyncMock), \
         patch("m365_ingest.poll_m365_secure_scores", new_callable=AsyncMock):

        result = await scan_account(mock_db, "acc1", "ten1")

        assert "error" not in result, f"scan_account failed: {result}"
        assert result.get("ran", 0) > 0

        for call_args in mock_db.cloud_check_results.update_one.call_args_list:
            doc = call_args[0][1]["$set"]
            assert doc.get("simulated") is False, f"Expected simulated=False, got {doc.get('simulated')}"


@pytest.mark.asyncio
async def test_scan_account_aws_no_ingest_unchanged(mock_db):
    """Existing provider (aws) triggers no ingest call."""
    account = {"id": "acc1", "provider": "aws", "credentials_ref": "enc_creds"}
    mock_db._db.cloud_accounts.find_one = AsyncMock(return_value=account)
    mock_db._db.cloud_accounts.update_one = AsyncMock()
    mock_db.cloud_findings.find.return_value.to_list = AsyncMock(return_value=[])

    with patch("backend.cloud_accounts_service._decrypt", return_value="{}"), \
         patch("m365_ingest.poll_m365_secure_scores", new_callable=AsyncMock) as mock_m365_ingest, \
         patch("mongodb_atlas_ingest.poll_mongodb_atlas_findings", new_callable=AsyncMock) as mock_atlas_ingest, \
         patch("backend.cloud_checks_service.cloud_checks_service.run_checks", new_callable=AsyncMock) as mock_run_checks:

        await scan_account(mock_db, "acc1", "ten1")

        mock_m365_ingest.assert_not_called()
        mock_atlas_ingest.assert_not_called()
        mock_run_checks.assert_called_once_with("acc1", "aws", "ten1")
