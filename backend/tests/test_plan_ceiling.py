"""Phase 88 plan 03: the plan is a screen ceiling (D-27..D-30, D-46).

Each test states its card: protects=<observable>; fails_when=<wrong result it rejects>.
The seed half is pure; the ceiling half uses real MongoDB (private mongod via MONGO_TEST_URL).
"""
import importlib.util
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import tenant_features as tf

ROOT = Path(__file__).resolve().parent.parent.parent
SCRIPT = ROOT / "backend" / "scripts" / "generate_plan_screen_seed.py"
SEED_FILE = ROOT / "shared" / "plan-screen-seed.json"


def _generator():
    spec = importlib.util.spec_from_file_location("generate_plan_screen_seed", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


# --- D-29 / D-46: the seed ------------------------------------------------------------------------

def test_seed_has_the_reviewed_counts_and_is_nested():
    """protects=D-29 counts 19/88/208 and Free within Pro within Enterprise = every switch;
    fails_when=a rule drifts and a screen lands in the wrong plan."""
    seed = _generator().build_seed()
    assert [len(seed[k]) for k in ("Free", "Pro", "Enterprise")] == [19, 88, 208]
    assert all(seed[k] == sorted(seed[k]) for k in seed)
    assert set(seed["Free"]) <= set(seed["Pro"]) <= set(seed["Enterprise"])
    assert seed["Enterprise"] == sorted(tf.SWITCHABLE)


def test_seed_places_known_screens_in_their_plans():
    """protects=D-29 sample placements; fails_when=Overview/Agents leave Free, Reporting enters Free,
    or Settings management leaves Enterprise-only."""
    seed = _generator().build_seed()
    for key in ("screen:dashboard", "view:agents", "screen:agents"):
        assert key in seed["Free"]
    assert "view:reporting" in seed["Pro"] and "view:reporting" not in seed["Free"]
    assert "manage:settings" in seed["Enterprise"] and "manage:settings" not in seed["Pro"]


def test_committed_seed_file_is_what_the_script_writes():
    """protects=T-88-08 (a hand edit is visible); fails_when=the committed JSON differs from the
    generator's output byte for byte."""
    seed = _generator().build_seed()
    expected = json.dumps({"version": 1, "rule": "D-29", "plans": seed}, indent=2) + "\n"
    assert SEED_FILE.read_text(encoding="utf-8") == expected
