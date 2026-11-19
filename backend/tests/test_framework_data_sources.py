"""Framework checks read data the platform actually writes.

Value: protects=a compliance control that can pass or fail on real evidence instead of a collection no production
code ever writes (such a check can only fail, or pass on nothing); fails_when=a framework module starts reading
another never-written collection, or the EDR checks go back to the dead edr_agents collection;
no_claim=that each check's threshold is right, or that the screens writing the other collections are used.
"""
import asyncio
import os
import re
import sys
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from frameworks import _common_checks  # noqa: E402

BACKEND = os.path.join(os.path.dirname(__file__), "..")
READ = re.compile(r"db(?:\._db)?\.([a-z][a-z0-9_]+)\.(?:find_one|find|count_documents|aggregate|distinct)\b")
_WRITE_OPS = r"(?:insert_one|insert_many|update_one|update_many|replace_one|bulk_write|find_one_and_update)\b"
WRITE = re.compile(r"db(?:\._db)?(?:\.([a-z][a-z0-9_]+)|\[[\'\"]([a-z][a-z0-9_]+)[\'\"]\])\." + _WRITE_OPS)
SKIP_DIRS = {"venv", "tests", "__pycache__", "frameworks", "scripts"}
SKIP_PREFIXES = ("test_", "seed", "fix_", "debug", "clear_", "cleanup")

# Read by framework checks, written by nothing in production (2026-11-19). The list is exact: a collection retargeted at
# real data leaves it, and nothing may join it.
STILL_UNWRITTEN = {
    "network_topology", "compliance_policies", "security_baselines", "api_keys",
    "dr_runbooks", "iam_policies", "devices", "employees", "gdpr_records",
    "ai_governance_assessments", "ai_risk_assessments", "pqc_configs", "ueba_events",
    "privacy_records", "model_registry", "approvals", "network_segments", "code_repositories",
}


def _framework_reads():
    reads = set()
    for name in os.listdir(os.path.join(BACKEND, "frameworks")):
        if name.endswith(".py"):
            reads |= set(READ.findall(open(os.path.join(BACKEND, "frameworks", name), encoding="utf-8").read()))
    return reads


def _production_writes():
    writes = set()
    for root, dirs, files in os.walk(BACKEND):
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
        for f in files:
            if f.endswith(".py") and not f.startswith(SKIP_PREFIXES):
                text = open(os.path.join(root, f), encoding="utf-8", errors="ignore").read()
                writes |= {dotted or bracketed for dotted, bracketed in WRITE.findall(text)}
    return writes


def test_framework_checks_read_no_new_never_written_collection():
    unwritten = _framework_reads() - _production_writes()
    assert not unwritten - STILL_UNWRITTEN, f"framework checks read collections nothing writes: {sorted(unwritten - STILL_UNWRITTEN)}"
    assert not STILL_UNWRITTEN - unwritten, f"retargeted, take them off STILL_UNWRITTEN: {sorted(STILL_UNWRITTEN - unwritten)}"


def test_edr_checks_count_reporting_agents_not_a_dead_collection():
    assert "edr_agents" not in _framework_reads()


def test_an_endpoint_counts_as_protected_when_its_agent_reported_this_week():
    seen = {}

    class _Agents:
        async def count_documents(self, query):
            seen["query"] = query
            return 3

    class _Db:
        agents = _Agents()

    assert asyncio.run(_common_checks.reporting_agent_count(_Db())) == 3
    by_type = {type(c["lastSeen"]["$gte"]): c["lastSeen"]["$gte"] for c in seen["query"]["$or"]}
    cutoff = by_type[datetime]
    assert timedelta(days=6, hours=23) < datetime.now(timezone.utc) - cutoff < timedelta(days=7, minutes=1)
    assert by_type[str] == cutoff.isoformat()
