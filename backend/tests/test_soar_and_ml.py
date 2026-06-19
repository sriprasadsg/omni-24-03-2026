"""
Tests for SOAR Jira connector (update_ticket, add_comment)
and ML training feature extraction (os_age, uptime, historical_success_rate).
"""
import asyncio
import sys
import os
from datetime import datetime, timezone, timedelta
from itertools import cycle
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# Make backend importable when run from repo root
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from soar_integrations import JiraConnector


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _jira(extra_config=None):
    cfg = {
        "base_url": "https://example.atlassian.net",
        "api_token": "tok",
        "email": "bot@example.com",
        **(extra_config or {}),
    }
    return JiraConnector(cfg)


def _mock_session(status, json_data=None, side_effect=None):
    """Return a context-manager mock for aiohttp.ClientSession."""
    response = AsyncMock()
    response.status = status
    response.json = AsyncMock(return_value=json_data or {})
    if side_effect:
        response.__aenter__ = AsyncMock(side_effect=side_effect)
    else:
        response.__aenter__ = AsyncMock(return_value=response)
    response.__aexit__ = AsyncMock(return_value=False)

    session = MagicMock()
    session.__aenter__ = AsyncMock(return_value=session)
    session.__aexit__ = AsyncMock(return_value=False)
    session.put = MagicMock(return_value=response)
    session.post = MagicMock(return_value=response)
    return session


# ---------------------------------------------------------------------------
# SOAR — _update_ticket
# ---------------------------------------------------------------------------

class TestUpdateTicket:
    def test_update_ticket_calls_jira_put(self):
        session = _mock_session(status=204)
        connector = _jira()

        with patch("soar_integrations.aiohttp.ClientSession", return_value=session):
            result = asyncio.run(
                connector._update_ticket({"issue_key": "OPS-42", "fields": {"priority": {"name": "High"}}})
            )

        assert result["status"] == "success"
        assert result["issue_key"] == "OPS-42"
        session.put.assert_called_once()
        call_url = session.put.call_args[0][0]
        assert "OPS-42" in call_url
        assert "/rest/api/3/issue/" in call_url

    def test_update_ticket_error_on_non_2xx(self):
        session = _mock_session(status=404)
        connector = _jira()

        with patch("soar_integrations.aiohttp.ClientSession", return_value=session):
            result = asyncio.run(
                connector._update_ticket({"issue_key": "OPS-99", "fields": {}})
            )

        assert result["status"] == "error"
        assert "404" in result["message"]

    def test_update_ticket_missing_issue_key(self):
        connector = _jira()
        result = asyncio.run(
            connector._update_ticket({"fields": {"summary": "x"}})
        )
        assert result["status"] == "error"

    def test_update_ticket_network_exception(self):
        session = MagicMock()
        session.__aenter__ = AsyncMock(side_effect=Exception("network error"))
        session.__aexit__ = AsyncMock(return_value=False)

        connector = _jira()
        with patch("soar_integrations.aiohttp.ClientSession", return_value=session):
            result = asyncio.run(
                connector._update_ticket({"issue_key": "OPS-1", "fields": {}})
            )
        assert result["status"] == "error"


# ---------------------------------------------------------------------------
# SOAR — _add_comment
# ---------------------------------------------------------------------------

class TestAddComment:
    def test_add_comment_calls_jira_post(self):
        session = _mock_session(status=201, json_data={"id": "12345"})
        connector = _jira()

        with patch("soar_integrations.aiohttp.ClientSession", return_value=session):
            result = asyncio.run(
                connector._add_comment({"issue_key": "OPS-42", "comment": "Resolved via playbook."})
            )

        assert result["status"] == "success"
        assert result["comment_id"] == "12345"
        session.post.assert_called_once()
        call_url = session.post.call_args[0][0]
        assert "OPS-42" in call_url
        assert "/comment" in call_url

    def test_add_comment_sends_adf_body(self):
        session = _mock_session(status=201, json_data={"id": "99"})
        connector = _jira()

        with patch("soar_integrations.aiohttp.ClientSession", return_value=session):
            asyncio.run(
                connector._add_comment({"issue_key": "OPS-1", "comment": "hello"})
            )

        _, call_kwargs = session.post.call_args
        body = call_kwargs.get("json", {}).get("body", {})
        assert body.get("type") == "doc"
        assert body["content"][0]["content"][0]["text"] == "hello"

    def test_add_comment_error_on_non_201(self):
        session = _mock_session(status=403)
        connector = _jira()

        with patch("soar_integrations.aiohttp.ClientSession", return_value=session):
            result = asyncio.run(
                connector._add_comment({"issue_key": "OPS-1", "comment": "x"})
            )

        assert result["status"] == "error"
        assert "403" in result["message"]

    def test_add_comment_missing_issue_key(self):
        connector = _jira()
        result = asyncio.run(
            connector._add_comment({"comment": "hello"})
        )
        assert result["status"] == "error"


# ---------------------------------------------------------------------------
# ML training — _load_real_patch_data feature extraction
# ---------------------------------------------------------------------------

def _make_db_mock(asset_created_days_ago=180, uptime_hours=48, total_deps=10, success_deps=9):
    """Build a minimal MongoDB mock for train_ml_models._load_real_patch_data."""
    created_at = (datetime.now(timezone.utc) - timedelta(days=asset_created_days_ago)).isoformat()

    asset = {"id": "asset-1", "createdAt": created_at, "uptime_hours": uptime_hours}
    patch_doc = {"id": "patch-1", "severity": "High", "cvss_score": 7.5, "size_mb": 5, "requiresReboot": False}
    deployment = {"status": "completed", "patch_ids": ["patch-1"], "asset_ids": ["asset-1"]}

    db = MagicMock()
    # find() for deployments — return list with 60+ entries so threshold passes
    deployments_cursor = MagicMock()
    deployments_cursor.to_list = AsyncMock(return_value=[deployment] * 60)
    db.patch_deployment_jobs.find = MagicMock(return_value=deployments_cursor)

    # find_one for patch
    db.patches.find_one = AsyncMock(return_value=patch_doc)
    # find_one for asset
    db.assets.find_one = AsyncMock(return_value=asset)
    # count_documents for historical rate — cycles for all 60 deployments
    db.patch_deployment_jobs.count_documents = AsyncMock(side_effect=cycle([total_deps, success_deps]))

    return db


class TestMLFeatureExtraction:
    def test_os_age_from_asset_created_at(self):
        db = _make_db_mock(asset_created_days_ago=180, uptime_hours=48)

        import train_ml_models
        with patch("train_ml_models.get_database", return_value=db):
            X, y = asyncio.run(
                train_ml_models._load_real_patch_data()
            )

        assert X is not None
        # Feature index 2 is os_age — should be ~180 days (allow ±2 for test timing)
        assert abs(X[0][2] - 180) <= 2

    def test_uptime_hours_from_asset(self):
        db = _make_db_mock(uptime_hours=48)

        import train_ml_models
        with patch("train_ml_models.get_database", return_value=db):
            X, _ = asyncio.run(
                train_ml_models._load_real_patch_data()
            )

        assert X is not None
        # Feature index 3 is uptime
        assert X[0][3] == 48

    def test_historical_success_rate_computed(self):
        db = _make_db_mock(total_deps=10, success_deps=8)

        import train_ml_models
        with patch("train_ml_models.get_database", return_value=db):
            X, _ = asyncio.run(
                train_ml_models._load_real_patch_data()
            )

        assert X is not None
        # Feature index 4 is historical_success_rate = 8/10 = 0.8
        assert abs(X[0][4] - 0.8) < 0.01

    def test_missing_asset_uses_defaults(self):
        db = _make_db_mock()
        db.assets.find_one = AsyncMock(return_value=None)
        # count_documents won't be called when asset_id resolves but asset is None
        # os_age falls back to 365, uptime to 72, rate to 0.8

        import train_ml_models
        with patch("train_ml_models.get_database", return_value=db):
            X, _ = asyncio.run(
                train_ml_models._load_real_patch_data()
            )

        assert X is not None
        assert X[0][2] == 365  # os_age default
        assert X[0][3] == 72   # uptime default
        assert X[0][4] == 0.8  # historical_success_rate default
