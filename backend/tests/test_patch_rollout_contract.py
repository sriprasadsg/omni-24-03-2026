"""Staged patch rollouts, plan 84-02: the agent contract for rollouts.

Value: protects=PTCH-04 / PTCH-06: the names a published agent will accept and report for rollouts live in
shared/agent-response-contract.json (read by the backend and the Rust tests); a patch outcome that was deferred
because it cannot be reversed never reads as installed; fails_when=a pre-existing contract key changes value,
the first ten tokens move, a rollout name is missing, an example uses a status or code the contract does not
list, or a deferred result clears a package from the host's pending list;
no_claim=the Rust agent (it implements these names in 84-07 and 84-11) or the live database.
"""
import hashlib
import json
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tests._mongo_test_db import mongo_db  # noqa: F401  (fixture)

CONTRACT_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
                             "shared", "agent-response-contract.json")

# The ten tokens of agent 2.1.16, in order. 84-07 and 84-11 append to the list, so only this prefix is pinned.
FIRST_TOKENS = ["block_ip_ttl", "block_ip_range", "quarantine_file", "unquarantine_file", "kill_process_exe",
                "restart_service", "service_failures", "isolate_host", "restore_host", "reboot_host"]

# sha256 (first 16 hex) of each pre-existing key's value as canonical JSON, taken from the file before this plan.
# A change to any of them is a change to a released agent, so it has to be a deliberate edit of this table.
SNAPSHOT = {
    "version": "6b86b273ff34fce1",
    "description": "4718902feeb51da5",
    "commandToken": "6d46a34b1207f39f",
    "rangeToken": "4d358f9c1dfbc0b6",
    "blockTtlSeconds": "8dce2e147ae8a6a1",
    "isolationRevertSeconds": "5be21fec7f4c958e",
    "rebootDelaySeconds": "657e7b95b6487b4c",
    "stillRunningCap": "2747b7c718564ba5",
    "outcomes": "6ef42efdf8ab3a96",
    "checks": "7633263768467a14",
    "protectedPaths": "967f5faae1774614",
    "criticalServices": "2cfef753be20e8f2",
    "examples": "b948f15f541ae292",
}

PATCH_EXAMPLE_NAMES = ["install_ok", "install_ok_reboot", "install_deferred_not_reversible", "install_failed",
                       "revert_ok", "revert_not_uninstallable", "revert_version_not_offered", "revert_not_changed"]
BODY_KEYS = {"status", "job_id", "total", "successful", "failed", "results", "timestamp"}


def contract():
    with open(CONTRACT_PATH, encoding="utf-8") as handle:
        return json.load(handle)


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()[:16]


# ---------------------------------------------------------------- shape

def test_the_file_loads_and_the_first_ten_tokens_are_unchanged_in_order():
    assert contract()["tokens"][:10] == FIRST_TOKENS


@pytest.mark.parametrize("key", sorted(SNAPSHOT))
def test_every_pre_existing_key_other_than_tokens_is_unchanged(key):
    assert digest(contract()[key]) == SNAPSHOT[key], key


def test_rollout_names_are_the_agreed_ones():
    data = contract()
    assert sorted(data["rolloutTokens"].values()) == ["patch_reversible_check", "patch_revert_by_job", "service_state"]
    assert data["rolloutTokens"] == {"reversibleCheck": "patch_reversible_check",
                                     "revertByJob": "patch_revert_by_job", "serviceState": "service_state"}
    assert data["rolloutParams"] == {"requireReversible": "require_reversible", "revertOf": "revert_of"}
    assert data["patchStatuses"] == ["success", "failed", "skipped", "deferred"]
    assert data["patchCodes"] == ["not_reversible", "reverted", "not_uninstallable", "version_not_offered",
                                  "not_changed_by_job", "not_applicable"]


def test_the_service_state_heartbeat_shape():
    state = contract()["serviceState"]
    assert state["key"] == "service_state"
    assert state["states"] == ["running", "stopped", "failed", "unknown"]
    example = state["example"]
    assert example["v"] == 1 and isinstance(example["at"], int)
    assert example["services"] == [{"name": "sshd", "state": "running"}, {"name": "nginx", "state": "stopped"}]
    for service in example["services"]:
        assert service["state"] in state["states"]


def test_there_is_one_full_body_per_patch_outcome():
    examples = contract()["patchExamples"]
    assert sorted(examples) == sorted(PATCH_EXAMPLE_NAMES) and len(examples) == 8


@pytest.mark.parametrize("name", PATCH_EXAMPLE_NAMES)
def test_every_patch_example_is_a_full_body_that_uses_only_listed_statuses_and_codes(name):
    data = contract()
    body = data["patchExamples"][name]
    assert BODY_KEYS <= set(body), name
    assert body["status"] in ("completed", "partial", "failed")
    assert body["total"] == len(body["results"]) >= 1
    assert body["successful"] == sum(1 for r in body["results"] if r["status"] == "success")
    assert body["failed"] == sum(1 for r in body["results"] if r["status"] == "failed")
    for result in body["results"]:
        assert {"patch_id", "status", "message", "reboot_required", "timestamp"} <= set(result), name
        assert result["status"] in data["patchStatuses"], name
        if "code" in result:
            assert result["code"] in data["patchCodes"], name


def test_the_examples_say_what_each_outcome_is():
    examples = contract()["patchExamples"]

    def only(name):
        return examples[name]["results"][0]

    assert (only("install_ok")["status"], only("install_ok")["reboot_required"]) == ("success", False)
    assert (only("install_ok_reboot")["status"], only("install_ok_reboot")["reboot_required"]) == ("success", True)
    assert (only("install_deferred_not_reversible")["status"], only("install_deferred_not_reversible")["code"]) == (
        "deferred", "not_reversible")
    assert examples["install_deferred_not_reversible"]["status"] == "completed"
    assert examples["install_deferred_not_reversible"]["successful"] == 0
    assert examples["install_deferred_not_reversible"]["failed"] == 0
    assert only("install_failed")["status"] == "failed" and "code" not in only("install_failed")
    assert (only("revert_ok")["status"], only("revert_ok")["code"]) == ("success", "reverted")
    assert (only("revert_not_uninstallable")["status"], only("revert_not_uninstallable")["code"]) == (
        "failed", "not_uninstallable")
    assert only("revert_not_uninstallable")["patch_id"].startswith("KB")
    assert (only("revert_version_not_offered")["status"], only("revert_version_not_offered")["code"]) == (
        "failed", "version_not_offered")
    assert (only("revert_not_changed")["status"], only("revert_not_changed")["code"]) == (
        "skipped", "not_changed_by_job")


# ---------------------------------------------------------------- a deferred result is not a cleared one

def test_deferred_is_not_a_cleared_status():
    import deployment_result_endpoints as mod
    assert "deferred" not in mod._CLEARED_STATUSES
    assert {"success", "skipped"} == set(mod._CLEARED_STATUSES)


async def _host_with_pending(db, pending):
    await db.agents.insert_one({"id": "a1", "tenantId": "t1", "hostname": "h1",
                                "meta": {"system_patching": {"pending_update_count": len(pending),
                                                             "pending_updates": [{"id": p, "title": p} for p in pending]}}})
    await db.patch_deployment_jobs.insert_one({"id": "job-1", "tenantId": "t1", "type": "Patch Deployment",
                                               "dispatchedAgents": ["a1"], "status": "In Progress"})


async def _pending_ids(db):
    agent = await db.agents.find_one({"id": "a1"})
    return [i["id"] for i in agent["meta"]["system_patching"]["pending_updates"]]


async def test_a_not_reversible_deferral_leaves_the_package_pending(mongo_db):
    from deployment_result_endpoints import record_agent_patch_result
    await _host_with_pending(mongo_db, ["openssl", "curl"])
    body = contract()["patchExamples"]["install_deferred_not_reversible"]
    final = await record_agent_patch_result(mongo_db, "job-1", "a1", body)
    assert final == "Completed"
    assert await _pending_ids(mongo_db) == ["openssl", "curl"]


async def test_a_successful_install_removes_the_package_from_the_pending_list(mongo_db):
    from deployment_result_endpoints import record_agent_patch_result
    await _host_with_pending(mongo_db, ["openssl", "curl"])
    body = contract()["patchExamples"]["install_ok"]
    await record_agent_patch_result(mongo_db, "job-1", "a1", body)
    assert await _pending_ids(mongo_db) == ["curl"]
