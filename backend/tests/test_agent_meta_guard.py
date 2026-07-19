"""Unit tests for the per-agent meta payload guard in agent_core_endpoints.py.

Guards the /api/agents response so one pathological agent document can't bloat
or truncate the whole response (ERR_CONTENT_LENGTH_MISMATCH backstop).
"""
import copy
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import agent_core_endpoints as ace


class TestCapAgentMeta:
    def test_oversized_single_key_is_stubbed(self):
        agent = {"meta": {"blob": "x" * (ace._META_KEY_MAX_BYTES + 5000)}}
        ace._cap_agent_meta(agent)
        assert agent["meta"]["blob"]["_truncated"] is True
        assert agent["meta"]["blob"]["_original_bytes"] > ace._META_KEY_MAX_BYTES

    def test_predictive_health_always_preserved(self):
        agent = {"meta": {"predictive_health": {"predictions": [1, 2, 3]},
                          "blob": "y" * (ace._META_KEY_MAX_BYTES + 1)}}
        ace._cap_agent_meta(agent)
        assert agent["meta"]["predictive_health"] == {"predictions": [1, 2, 3]}

    def test_small_meta_left_untouched(self):
        agent = {"meta": {"cap": {"status": "Active"}, "n": 3}}
        before = copy.deepcopy(agent)
        ace._cap_agent_meta(agent)
        assert agent == before

    def test_whole_meta_backstop_drops_nonpreserved(self):
        # many medium keys sum past the whole-object cap without any single one
        # tripping the per-key cap
        keys = {f"k{i}": "z" * 2000 for i in range(60)}
        keys["predictive_health"] = {"p": 1}
        agent = {"meta": keys}
        ace._cap_agent_meta(agent)
        assert agent["meta"]["_truncated"] is True
        assert "predictive_health" in agent["meta"]
        assert len(agent["meta"]["_dropped_keys"]) == 60

    def test_non_dict_meta_is_safe(self):
        for bad in (None, "str", 42, ["list"]):
            agent = {"meta": bad}
            ace._cap_agent_meta(agent)  # must not raise
            assert agent["meta"] == bad

    def test_missing_meta_is_safe(self):
        agent = {"name": "a"}
        ace._cap_agent_meta(agent)
        assert "meta" not in agent

    def test_odd_value_does_not_crash(self):
        agent = {"meta": {"weird": object()}}
        ace._cap_agent_meta(agent)  # json default=str renders it small -> kept
        assert "weird" in agent["meta"]
