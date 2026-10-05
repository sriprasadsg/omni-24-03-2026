"""Built-in YARA rules: seeding (app_startup._seed_yara_rules) and false-positive guards.

The rule files live in agent/capabilities/yara_rules/ and drive both the agent's
RuntimeSecurity auto-kill and the backend's built-in rules. Rules that matched
ordinary binaries (Chromium, Claude Code, Node, Go tools) got those processes
killed, so the sample tests below pin real detections AND known benign strings.
"""
import re
from pathlib import Path
from types import SimpleNamespace

import pytest

import app_startup

RULES_DIR = Path(__file__).resolve().parents[2] / "agent" / "capabilities" / "yara_rules"
RULE_NAMES = sorted(
    name for f in RULES_DIR.glob("*.yar") for name in re.findall(r"^rule\s+(\w+)", f.read_text(), re.M)
)


class _FakeRules:
    """Minimal async stand-in for raw_db.custom_yara_rules keyed by `id`."""

    def __init__(self):
        self.docs = {}

    async def find_one(self, filt, projection=None):
        doc = self.docs.get(filt["id"])
        return dict(doc) if doc else None

    async def update_one(self, filt, update, upsert=False):
        doc = self.docs.get(filt["id"])
        if doc is None:
            if upsert and "$setOnInsert" in update:
                self.docs[filt["id"]] = dict(update["$setOnInsert"])
            return
        doc.update(update.get("$set", {}))


def _db():
    return SimpleNamespace(custom_yara_rules=_FakeRules())


@pytest.mark.asyncio
async def test_seed_extracts_every_rule_whole():
    db = _db()
    await app_startup._seed_yara_rules(db)
    docs = db.custom_yara_rules.docs.values()
    assert sorted(d["name"] for d in docs) == RULE_NAMES
    for d in docs:
        # The old non-greedy parser cut rules at the first "}" of a hex string.
        assert d["content"].count("{") == d["content"].count("}"), d["name"]
        assert "condition:" in d["content"] and d["content"].endswith("}"), d["name"]
        assert d["seedHash"] and d["source"] == "builtin" and d["enabled"] is True


@pytest.mark.asyncio
async def test_seed_refreshes_legacy_truncated_rule():
    db = _db()
    doc_id = "builtin_injectors_shellcodepatterns"
    db.custom_yara_rules.docs[doc_id] = {
        "id": doc_id, "name": "ShellcodePatterns", "source": "builtin", "enabled": False,
        "content": "rule ShellcodePatterns {\n    strings:\n        $fc_e8 = { FC E8 }",  # truncated, no seedHash
    }
    await app_startup._seed_yara_rules(db)
    doc = db.custom_yara_rules.docs[doc_id]
    assert "condition:" in doc["content"] and doc["seedHash"]
    assert doc["enabled"] is False  # user toggle is preserved


@pytest.mark.asyncio
async def test_seed_never_overwrites_admin_edit():
    db = _db()
    await app_startup._seed_yara_rules(db)
    doc_id = "builtin_ransomware_ransomwaregeneric"
    edited = 'rule RansomwareGeneric { strings: $a = "custom" condition: $a }'
    db.custom_yara_rules.docs[doc_id]["content"] = edited  # edit via the API keeps the old seedHash
    await app_startup._seed_yara_rules(db)
    assert db.custom_yara_rules.docs[doc_id]["content"] == edited


# ── Detection quality (needs yara-python) ────────────────────────────────────

POSITIVE = {
    "RansomwareGeneric": b"YOUR FILES HAVE BEEN ENCRYPTED! Read HOW_TO_DECRYPT.txt",
    "LockerRansomware": b"CryptEncrypt Your files are locked. Send 0.5 Bitcoin to 1BoatSLRHtKNngkdXEeobR76b53LETtpyT",
    "LaZagneCredentialDumper": b"lazagne.softwares.browsers.mozilla",
    "PassTheHashPatterns": b"Administrator:500:aad3b435b51404eeaad3b435b51404ee:31d6cfe0d16ae931b73c59d7e0c089c0:::",
    "ShellcodePatterns": bytes.fromhex("FCE88200000060 89E531C0648B5030".replace(" ", "")),
    "C2BeaconCobaltStrike": b"\\\\.\\pipe\\MSSE-4821-server",
    "RemoteServiceCreation": b'sc \\\\FILESRV01 create evilsvc binPath= "c:\\x.exe"',
    "TorC2Communication": b"http://duckduckgogg42xjoc72x3sjasowoarfbgcmvfimaftt6twagswzczad.onion/",
}

# Strings taken from the binaries that were being killed or flagged.
BENIGN = [
    b".Locked .Encrypted .crypt .enc bitcoin Decrypt CredentialManager /pth CreateService StartService",
    b"_ZN2v814CaptureContextEP8ucontext 11ArrayBuffer15GetBackingStoreEv EVP_aes_256_cbc AES_set_encrypt_key",
    b"\xfc\xe8\x31\xc9\x08\x00" + b"\x00" * 64 + b"\x55\xaa" + b"A" * 32,
    b"psExec curl/8.5 Go-http-client/1.1 .onion RUBEUS NETMAN httpTunnel TaskScheduler Empire \\\\.\\pipe\\mojo",
    b"MbimPacketServiceAction TDL4 org.freedesktop.NetworkManager.iodine zeroaccessToken BOOTMGR",
]


@pytest.fixture(scope="module")
def compiled_rules():
    yara = pytest.importorskip("yara")
    return yara.compile(filepaths={f.stem: str(f) for f in RULES_DIR.glob("*.yar")})


@pytest.mark.parametrize("rule,data", list(POSITIVE.items()), ids=list(POSITIVE))
def test_rule_still_detects(compiled_rules, rule, data):
    assert rule in {m.rule for m in compiled_rules.match(data=data)}


@pytest.mark.parametrize("data", BENIGN)
def test_benign_strings_do_not_match(compiled_rules, data):
    assert [m.rule for m in compiled_rules.match(data=data)] == []
