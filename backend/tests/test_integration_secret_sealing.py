"""
SIEM / ticketing / chat integration secrets are encrypted at rest.

integration_configs and integrations used to hold API tokens, passwords and
webhook URLs in clear text. They are sealed on every save ("enc:" + Fernet
with INTEGRATION_ENCRYPTION_KEY, like cloud integrations), masked in API
responses, decrypted only where the external call is made, and migration 010
seals what was stored before. Hermetic.
"""
import importlib
import os
import sys
from unittest.mock import AsyncMock, MagicMock

import pytest
from cryptography.fernet import Fernet

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import integration_service as svc


@pytest.fixture(autouse=True)
def _key(monkeypatch):
    monkeypatch.setenv("INTEGRATION_ENCRYPTION_KEY", Fernet.generate_key().decode())


CONFIG = {
    "tenantId": "t1", "type": "ticketing", "platform": "jira", "enabled": True,
    "url": "https://acme.atlassian.net", "api_token": "tok-123", "password": "pw",
    "config": {"apiUrl": "https://acme.atlassian.net", "apiToken": "nested-tok", "projectKey": "SEC"},
}


def test_secrets_are_sealed_and_everything_else_is_left_alone():
    sealed = svc.seal_config(CONFIG)
    assert sealed["api_token"].startswith("enc:") and "tok-123" not in sealed["api_token"]
    assert sealed["password"].startswith("enc:")
    assert sealed["config"]["apiToken"].startswith("enc:")
    assert sealed["url"] == CONFIG["url"]
    assert sealed["config"]["projectKey"] == "SEC"
    assert CONFIG["api_token"] == "tok-123"  # input not mutated


def test_sealing_is_idempotent_and_round_trips():
    once = svc.seal_config(CONFIG)
    assert svc.seal_config(once) == once
    assert svc.unseal_config(once) == CONFIG


def test_legacy_plaintext_passes_through_unseal():
    assert svc.unseal_config(CONFIG) == CONFIG


def test_a_secret_sealed_under_another_key_is_not_used(monkeypatch):
    sealed = svc.seal_config(CONFIG)
    monkeypatch.setenv("INTEGRATION_ENCRYPTION_KEY", Fernet.generate_key().decode())
    assert svc.unseal_config(sealed)["api_token"] == ""


def test_the_mask_is_never_sealed():
    assert svc.seal_config({"api_token": svc.SECRET_MASK})["api_token"] == svc.SECRET_MASK


class _Collection:
    def __init__(self):
        self.doc = None

    async def find_one(self, *_a, **_k):
        return dict(self.doc) if self.doc else None

    async def update_one(self, _key, update, upsert=False):
        self.doc = {**(self.doc or {}), **update["$set"]}


async def test_service_stores_sealed_masks_on_read_and_decrypts_for_use():
    db = MagicMock()
    db.integration_configs = _Collection()
    service = svc.IntegrationService(db)
    await service.save_config("t1", {k: v for k, v in CONFIG.items() if k != "tenantId"})
    assert db.integration_configs.doc["api_token"].startswith("enc:")

    db.integration_configs.find = MagicMock()
    db.integration_configs.find.return_value.to_list = AsyncMock(return_value=[db.integration_configs.doc])
    listed = (await service.get_all_configs("t1"))[0]
    assert listed["api_token"] == svc.SECRET_MASK

    used = await service._get_integration_config("ticketing", "jira")
    assert used["api_token"] == "tok-123"
    assert used["config"]["apiToken"] == "nested-tok"

    # A UI round-trip of the masked config keeps the stored secret.
    await service.save_config("t1", {"type": "ticketing", "platform": "jira", "api_token": svc.SECRET_MASK})
    assert (await service._get_integration_config("ticketing", "jira"))["api_token"] == "tok-123"


class _Cursor:
    def __init__(self, docs):
        self._docs = list(docs)

    def __aiter__(self):
        return self

    async def __anext__(self):
        if not self._docs:
            raise StopAsyncIteration
        return self._docs.pop(0)


async def test_migration_010_seals_both_collections():
    mig = importlib.import_module("migrations.010_encrypt_integration_config_secrets")
    already = svc.seal_config({"_id": 3, "token": "x"})
    collections = {
        "integration_configs": [{"_id": 1, **CONFIG}, already],
        "integrations": [{"_id": 2, "id": "slack", "config": {"webhookUrl": "https://hooks.slack.com/x"}}],
    }
    db = MagicMock()
    _collections = {}
    for name, docs in collections.items():
        coll = MagicMock()
        coll.find = MagicMock(return_value=_Cursor(docs))
        coll.update_one = AsyncMock()
        _collections[name] = coll
    db.__getitem__.side_effect = lambda n: _collections[n]

    await mig.up(db)

    ic = _collections["integration_configs"].update_one
    ic.assert_awaited_once()  # the already-sealed doc is left alone
    flt, update = ic.await_args.args
    assert flt == {"_id": 1}
    assert update["$set"]["api_token"].startswith("enc:")
    assert update["$set"]["config"]["apiToken"].startswith("enc:")
    assert "url" not in update["$set"]  # only changed fields are written
    (flt, update), _ = _collections["integrations"].update_one.await_args
    assert update["$set"]["config"]["webhookUrl"].startswith("enc:")
