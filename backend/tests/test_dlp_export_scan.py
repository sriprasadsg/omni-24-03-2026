"""DLP export scan (Phase 86 review CR-01): a block policy must fire wherever its match sits in the export,
on the characters the admin wrote, and however many policies the tenant has."""
from types import SimpleNamespace

import dlp_service


class _Policies:
    """dlp_policies.find(...).to_list(n) that honours ``n`` the way Motor does (None = everything)."""

    def __init__(self, docs):
        self.docs = docs
        self.lengths = []

    def find(self, query, projection=None):
        docs, lengths = [d for d in self.docs if d.get("enabled")], self.lengths

        class _Cursor:
            async def to_list(self, length):
                lengths.append(length)
                return docs if length is None else docs[:length]

        return _Cursor()


def _use_policies(monkeypatch, docs):
    coll = _Policies(docs)
    monkeypatch.setattr(dlp_service, "get_database", lambda: SimpleNamespace(_db=SimpleNamespace(dlp_policies=coll)))
    return coll


def _block(name, pattern, **extra):
    return {"policy_id": name, "name": name, "pattern": pattern, "action": "block", "enabled": True,
            "severity": "high", **extra}


async def test_a_block_hit_after_the_first_two_megabytes_still_blocks(monkeypatch):
    _use_policies(monkeypatch, [_block("zeus", r"PROJECT-ZEUS")])
    rows = [{"note": "x" * 1000} for _ in range(2500)] + [{"note": "PROJECT-ZEUS plans"}]

    blocking, _ = await dlp_service.scan_export(rows, "t1")

    assert [f["policy_id"] for f in blocking] == ["zeus"]


async def test_a_pattern_with_non_ascii_characters_matches_the_original_text(monkeypatch):
    _use_policies(monkeypatch, [_block("name", r"Müller"), _block("city", r"東京")])

    blocking, _ = await dlp_service.scan_export([{"owner": "José Müller", "site": "東京 office"}], "t1")

    assert sorted(f["policy_id"] for f in blocking) == ["city", "name"]


async def test_the_hundred_and_first_enabled_policy_still_applies(monkeypatch):
    docs = [_block("p%03d" % i, r"never-matches-%03d" % i) for i in range(100)] + [_block("p100", r"SECRET")]
    coll = _use_policies(monkeypatch, docs)

    blocking, _ = await dlp_service.scan_export([{"v": "SECRET"}], "t1")

    assert [f["policy_id"] for f in blocking] == ["p100"]
    assert coll.lengths == [None]


def test_a_policy_hitting_in_several_chunks_is_reported_once():
    rows = [{"v": "card-%d SECRET" % i} for i in range(40)]

    blocking, alerting = dlp_service._scan_export_rows(
        rows, [_block("b", r"SECRET"), {**_block("a", r"card-"), "action": "alert"}], limit=50)

    assert [f["policy_id"] for f in blocking] == ["b"] and [f["policy_id"] for f in alerting] == ["a"]


def test_a_block_policy_that_cannot_be_evaluated_still_fails_closed():
    blocking, _ = dlp_service._scan_export_rows([{"v": "anything"}], [_block("bad", r"(")])

    assert [(f["type"], f["policy_id"]) for f in blocking] == [("POLICY_UNEVALUATED", "bad")]


def test_an_alert_policy_that_cannot_be_evaluated_raises_nothing():
    policy = {**_block("bad", r"("), "action": "alert"}

    assert dlp_service._scan_export_rows([{"v": "anything"}], [policy]) == ([], [])


def test_a_built_in_key_seen_in_two_chunks_is_reported_once():
    rows = [{"v": "AKIAABCDEFGHIJKLMNOP"}, {"pad": "x" * 80}, {"v": "AKIAABCDEFGHIJKLMNOP"}]

    _, alerting = dlp_service._scan_export_rows(rows, [], limit=60)

    assert [f["type"] for f in alerting] == ["AWS_KEY"]


def test_chunks_split_only_between_rows_and_keep_every_row():
    rows = [{"i": i, "v": "y" * 30} for i in range(10)]

    chunks = list(dlp_service._export_chunks(rows, limit=100))

    assert len(chunks) > 1
    assert sum(len(chunk.splitlines()) for chunk in chunks) == 10
