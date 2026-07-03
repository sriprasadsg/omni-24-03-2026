"""
Schema/contract tests for every module exported from backend/frameworks/__init__.py.

Added per phase 19 code review (WR-01): the 14 framework modules added in phase
19 (ens, mas_trm, irap, iso_27017, iso_27018, bsi_c5, ffiec, owasp_top10,
tisax, aws_well_architected, rbi_csf, tic_3_0, kisa_isms, fedramp_high) had no
test coverage at all. This file is parametrized over every module in
`frameworks.__all__` (not just the 14 new ones) so it also guards the
pre-existing modules' contract going forward.

Contract asserted per module:
  - FRAMEWORK_ID / FRAMEWORK_NAME / FRAMEWORK_VERSION are non-empty strings.
  - CONTROLS is a list. Some pre-existing modules (gdpr, dora, cobit, ...)
    intentionally ship an empty static CONTROLS list and load their controls
    from the seeded `compliance_frameworks` Mongo collection at evaluation
    time instead (see frameworks/_db_eval.py) -- that is a legitimate,
    pre-existing pattern unrelated to phase 19 and is not treated as a
    violation here. When CONTROLS is non-empty, every entry must be a dict
    with non-empty "id", "title", "description" keys, and ids must be
    unique within the module.
  - evaluate_controls(db) is defined and awaitable, and returns exactly one
    result per entry in CONTROLS when run against a mocked db.
"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import asyncio
import inspect
import pytest

import frameworks


def _run(coro):
    return asyncio.run(coro)


# ---------------------------------------------------------------------------
# Minimal fake MongoDB — every collection access returns an object whose
# count_documents/find_one/distinct methods are awaitable and return "empty"
# results. This lets evaluate_controls() run to completion for any check_type
# dispatch pattern used across the framework family without needing a real
# database connection.
# ---------------------------------------------------------------------------

class _FakeCollection:
    async def count_documents(self, *args, **kwargs):
        return 0

    async def find_one(self, *args, **kwargs):
        return None

    async def distinct(self, *args, **kwargs):
        return []


class _FakeDB:
    def __getitem__(self, name):
        return _FakeCollection()

    def __getattr__(self, name):
        return _FakeCollection()


@pytest.fixture
def fake_db():
    return _FakeDB()


def _is_db_driven(mod):
    """True if evaluate_controls delegates to frameworks/_db_eval.py's
    evaluate_from_db() instead of iterating the module's own CONTROLS list.

    Some pre-existing modules (cobit, dora, gdpr, eu_ai_act, ...) read their
    controls from the seeded `compliance_frameworks` Mongo collection at
    evaluation time rather than from a static CONTROLS list -- for those,
    "one result per CONTROLS entry" is not a meaningful invariant (a couple,
    like eu_ai_act, even ship a non-empty but effectively vestigial static
    CONTROLS list that evaluate_controls never consults). Detected
    structurally (by code object) rather than via CONTROLS emptiness, since
    emptiness and DB-driven-ness don't always coincide.
    """
    try:
        return "evaluate_from_db" in mod.evaluate_controls.__code__.co_names
    except Exception:
        return False


ALL_FRAMEWORK_MODULES = [getattr(frameworks, name) for name in frameworks.__all__]
ALL_FRAMEWORK_IDS = list(frameworks.__all__)


@pytest.mark.parametrize("mod", ALL_FRAMEWORK_MODULES, ids=ALL_FRAMEWORK_IDS)
class TestFrameworkModuleSchema:
    def test_required_metadata_present(self, mod):
        for attr in ("FRAMEWORK_ID", "FRAMEWORK_NAME", "FRAMEWORK_VERSION"):
            value = getattr(mod, attr, None)
            assert isinstance(value, str) and value.strip(), (
                f"{mod.__name__}.{attr} must be a non-empty string, got {value!r}"
            )

    def test_controls_is_a_list(self, mod):
        controls = getattr(mod, "CONTROLS", None)
        assert isinstance(controls, list), f"{mod.__name__}.CONTROLS must be a list"

    def test_controls_shape_and_unique_ids_when_present(self, mod):
        controls = mod.CONTROLS
        if not controls:
            pytest.skip(f"{mod.__name__} uses the DB-driven CONTROLS=[] pattern (see _db_eval.py)")

        seen_ids = set()
        for ctrl in controls:
            assert isinstance(ctrl, dict), f"{mod.__name__}: control entry must be a dict, got {ctrl!r}"
            for key in ("id", "title", "description"):
                value = ctrl.get(key)
                assert isinstance(value, str) and value.strip(), (
                    f"{mod.__name__}: control {ctrl.get('id')!r} missing non-empty {key!r}"
                )
            assert ctrl["id"] not in seen_ids, f"{mod.__name__}: duplicate control id {ctrl['id']!r}"
            seen_ids.add(ctrl["id"])

    def test_evaluate_controls_is_defined_and_awaitable(self, mod):
        assert hasattr(mod, "evaluate_controls"), f"{mod.__name__} must define evaluate_controls(db)"
        assert inspect.iscoroutinefunction(mod.evaluate_controls), (
            f"{mod.__name__}.evaluate_controls must be an async function"
        )

    def test_evaluate_controls_returns_one_result_per_control(self, mod, fake_db):
        results = _run(mod.evaluate_controls(fake_db))
        assert isinstance(results, list)

        if _is_db_driven(mod):
            # DB-driven modules read controls from the seeded Mongo collection at
            # evaluation time, not from the static CONTROLS list -- against a fake
            # db with no seeded doc, an empty result list is the correct behavior.
            return

        assert len(results) == len(mod.CONTROLS), (
            f"{mod.__name__}.evaluate_controls returned {len(results)} results "
            f"for {len(mod.CONTROLS)} controls"
        )
        for ctrl, result in zip(mod.CONTROLS, results):
            assert result.get("id") == ctrl["id"]
            assert result.get("status") in ("pass", "partial", "fail", "not_applicable"), (
                f"{mod.__name__}: control {ctrl['id']!r} returned unexpected status {result.get('status')!r}"
            )


# ---------------------------------------------------------------------------
# Focused checks for the 14 frameworks added in phase 19 -- these must have
# real, non-empty static CONTROLS (they are NOT part of the DB-driven
# pattern), unlike the pre-existing DB-driven modules skipped above.
# ---------------------------------------------------------------------------

PHASE_19_FRAMEWORK_IDS = [
    "ens", "mas_trm", "irap", "iso_27017", "iso_27018", "bsi_c5", "ffiec",
    "owasp_top10", "tisax", "aws_well_architected", "rbi_csf", "tic_3_0",
    "kisa_isms", "fedramp_high",
]


@pytest.mark.parametrize("framework_id", PHASE_19_FRAMEWORK_IDS)
def test_phase19_frameworks_have_static_controls(framework_id):
    mod = getattr(frameworks, framework_id)
    assert mod.CONTROLS, f"{framework_id} must ship a non-empty static CONTROLS list"
    assert mod.FRAMEWORK_ID == framework_id, (
        f"{framework_id}: FRAMEWORK_ID {mod.FRAMEWORK_ID!r} must match module name "
        f"(this is the key convention compliance_frameworks_endpoints._REGISTRY relies on)"
    )


@pytest.mark.parametrize("framework_id", PHASE_19_FRAMEWORK_IDS)
def test_phase19_frameworks_registered_in_endpoint_registry(framework_id):
    """CR-01 regression guard: every phase 19 framework must be reachable via the API."""
    import compliance_frameworks_endpoints as endpoints

    assert framework_id in endpoints._REGISTRY, (
        f"{framework_id} is missing from compliance_frameworks_endpoints._REGISTRY "
        f"-- it would be unreachable via GET /api/frameworks/{{id}}"
    )
    assert endpoints._REGISTRY[framework_id] is getattr(frameworks, framework_id)
