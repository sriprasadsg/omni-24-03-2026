"""Integration status and tests for Platform health (integration_status, Wave 6). protects/fails_when/no_claim per
test; HTTP is mocked, MongoDB is real (keys stored on Security Intelligence count).
"""
import json
import os
import sys

import httpx
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import integration_status as ist
from tests._mongo_test_db import mongo_db  # noqa: F401  (fixture)

SECRET = "sk_live_DO_NOT_LEAK_123"
REAL_CLIENT = httpx.AsyncClient


@pytest.fixture(autouse=True)
def clean_env(monkeypatch):
    for spec in ist.INTEGRATIONS.values():
        for var in spec["env"]:
            monkeypatch.delenv(var, raising=False)


def _mock(monkeypatch, handler):
    monkeypatch.setattr(ist.httpx, "AsyncClient", lambda **kw: REAL_CLIENT(transport=httpx.MockTransport(handler), **kw))


@pytest.mark.asyncio
async def test_status_names_each_integration_without_ever_showing_a_value(mongo_db, monkeypatch):  # noqa: F811
    """protects=status lists every integration with its variables and a configured flag, counts a key saved on
    Security Intelligence, and SMTP only when host, user and password are all set; fails_when=a key value
    reaches the browser; no_claim=-"""
    monkeypatch.setenv("STRIPE_SECRET_KEY", SECRET)
    monkeypatch.setenv("SMTP_HOST", "smtp.example.com")
    await mongo_db.security_intel_config.insert_one({"provider": "nvd", "api_key": SECRET})
    out = {i["name"]: i for i in await ist.status(mongo_db)}
    assert set(out) == set(ist.INTEGRATIONS)
    assert out["stripe"]["configured"] and out["nvd"]["configured"] and not out["virustotal"]["configured"]
    assert not out["smtp"]["configured"] and out["smtp"]["missing"] == ["SMTP_USER", "SMTP_PASS"]
    assert SECRET not in json.dumps(out)


@pytest.mark.asyncio
@pytest.mark.parametrize("code,ok,words", [(404, True, "HTTP 404"), (200, True, "HTTP 200"), (401, False, "the key was refused"),
                                           (429, False, "rate limited")])
async def test_a_live_test_reports_the_status_never_the_providers_body(monkeypatch, code, ok, words):
    """protects=a VirusTotal test sends the key as x-apikey on a fixed hash and reports ok or a reason built from
    the status; fails_when=the provider's body (which can echo the key) is shown, or a 401 reads as ok; no_claim=-"""
    monkeypatch.setenv("VIRUSTOTAL_API_KEY", SECRET)
    seen = {}

    def handler(request):
        seen["key"], seen["url"] = request.headers.get("x-apikey"), str(request.url)
        return httpx.Response(code, json={"error": {"message": f"bad key {SECRET}"}})
    _mock(monkeypatch, handler)
    out = await ist.test(None, "virustotal", "me@example.com")
    assert out["ok"] is ok and words in out["detail"] and SECRET not in out["detail"]
    assert seen["key"] == SECRET and ist.EICAR_SHA256 in seen["url"]


@pytest.mark.asyncio
async def test_unconfigured_unknown_unreachable_and_slack_cases(monkeypatch):
    """protects=an unconfigured integration says which variable to set without calling out, an unknown name is
    refused, a network failure is a reason not a 500, Slack gets one test message, SMTP needs a recipient;
    fails_when=a test crashes the route or calls a provider with no key; no_claim=a real SMTP server"""
    called = []
    _mock(monkeypatch, lambda r: called.append(str(r.url)) or httpx.Response(200, text="ok"))
    assert (await ist.test(None, "stripe", None)) == {"ok": False, "detail": "Not configured: set STRIPE_SECRET_KEY"}
    assert called == []
    with pytest.raises(KeyError):
        await ist.test(None, "mailchimp", None)
    monkeypatch.setenv("SLACK_WEBHOOK_URL", "https://hooks.slack.example/services/T0/B0/x")
    assert (await ist.test(None, "slack", None))["ok"] is True and called == ["https://hooks.slack.example/services/T0/B0/x"]

    def down(request):
        raise httpx.ConnectError("no route")
    _mock(monkeypatch, down)
    monkeypatch.setenv("ABUSECH_AUTH_KEY", SECRET)
    assert (await ist.test(None, "abusech", None)) == {"ok": False, "detail": "Could not reach it: ConnectError"}
    for var in ("SMTP_HOST", "SMTP_USER", "SMTP_PASS"):
        monkeypatch.setenv(var, "x")
    assert "no email address" in (await ist.test(None, "smtp", None))["detail"]
