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
    db.cloud_findings = AsyncMock()
    return db

@pytest.fixture(autouse=True)
def mock_get_db(mock_db):
    with patch("backend.m365_ingest.get_database", return_value=mock_db), \
         patch("backend.mongodb_atlas_ingest.get_database", return_value=mock_db):
        yield mock_db


@pytest.mark.asyncio
async def test_m365_poll_success():
    config = {"tenant_id": "t", "client_id": "c", "client_secret": "s"}
    mock_app = MagicMock()
    mock_app.acquire_token_for_client.return_value = {"access_token": "tok"}
    mock_resp = MagicMock()
    mock_resp.json.return_value = {"value": [{"controlScores": [{"controlName": "c1", "score": 10}]}]}
    mock_client = AsyncMock()
    mock_client.get.return_value = mock_resp
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock()

    with patch("backend.m365_ingest.msal.ConfidentialClientApplication", return_value=mock_app), \
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
    mock_app.acquire_token_for_client.return_value = {"access_token": "tok"}
    mock_resp = MagicMock()
    mock_resp.raise_for_status.side_effect = Exception("API down")
    mock_client = AsyncMock()
    mock_client.get.return_value = mock_resp
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock()

    with patch("backend.m365_ingest.msal.ConfidentialClientApplication", return_value=mock_app), \
         patch("httpx.AsyncClient", return_value=mock_client):
        count = await poll_m365_secure_scores(config, "acc1", "ten1")
        assert count == 0


@pytest.mark.asyncio
async def test_atlas_poll_success():
    config = {"atlas_public_key": "pk", "atlas_private_key": "prk", "atlas_project_id": "pid"}
    with patch("backend.mongodb_atlas_ingest._atlas_get_sync", return_value={"results": []}):
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


@pytest.mark.asyncio
async def test_scan_account_m365_dispatch(mock_db):
    account = {"id": "acc1", "provider": "microsoft365", "credentials_ref": "enc_creds"}
    mock_db._db.cloud_accounts.find_one = AsyncMock(return_value=account)
    mock_db._db.cloud_accounts.update_one = AsyncMock()

    config_json = '{"tenant_id": "common", "client_id": "c", "client_secret": "s"}'

    with patch("backend.cloud_accounts_service._decrypt", return_value=config_json), \
         patch("backend.m365_ingest.poll_m365_secure_scores", new_callable=AsyncMock) as mock_ingest, \
         patch("backend.cloud_checks_service.cloud_checks_service.run_checks", new_callable=AsyncMock) as mock_run_checks:

        await scan_account(mock_db, "acc1", "ten1")

        # Check if the function was called at all
        assert mock_ingest.called, f"Expected mock_ingest to be called. Call count: {mock_ingest.call_count}"

        mock_ingest.assert_called_once_with(json.loads(config_json), "acc1", "ten1")
        mock_run_checks.assert_called_once_with("acc1", "microsoft365", "ten1")
