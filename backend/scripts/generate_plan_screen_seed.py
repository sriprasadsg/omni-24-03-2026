"""Generate shared/plan-screen-seed.json, the reviewed D-29 screen seed per plan (Phase 88, D-46).

Run once and commit the output; the runtime never computes the seed (screen_ceiling.seed_screens reads
the committed file, and the Super Admin edits the stored plans afterwards). The rule, in order:

1. The catalogue tier of a permission is the lowest ``minTier`` (Free 0, Pro 1, Enterprise 2) among the
   feature_catalog.FEATURE_CATALOG entries that carry that permission.
2. A switch's own tier is the first rule that applies: (A) its key is a catalogue permission; (B) for
   ``screen:<view>``, the permission its manifest entry needs (tenant_features.SCREEN_SWITCHES) is a
   catalogue permission; (C) for ``screen:<view>``, a catalogue key whose letters and digits, lower-cased,
   equal the view's.
3. The final tier is the own tier raised to at least the parent's final tier; no own tier takes the
   parent's final tier; neither gives Enterprise.
4. Lists are cumulative (Free = tier 0, Pro = tiers 0..1, Enterprise = every switch), each sorted.
"""
import json
import re
import sys
from pathlib import Path
from typing import Dict, List, Optional

BACKEND = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND))

import feature_catalog  # noqa: E402
import tenant_features  # noqa: E402

OUT_PATH = BACKEND.parent / "shared" / "plan-screen-seed.json"
TIERS = {"Free": 0, "Pro": 1, "Enterprise": 2}
PLAN_ORDER = ("Free", "Pro", "Enterprise")


def _squash(text: str) -> str:
    return re.sub(r"[^a-z0-9]", "", text.lower())


def _catalogue_tiers() -> Dict[str, int]:
    """Permission -> lowest tier among the catalogue entries that carry it."""
    tiers: Dict[str, int] = {}
    for entry in feature_catalog.FEATURE_CATALOG.values():
        perm = entry.get("permission")
        if perm:
            tiers[perm] = min(tiers.get(perm, 2), TIERS[entry["minTier"]])
    return tiers


def _own_tier(switch: str, by_permission: Dict[str, int], by_key: Dict[str, int]) -> Optional[int]:
    if switch in by_permission:  # rule A
        return by_permission[switch]
    if switch.startswith(tenant_features.SCREEN_PREFIX):
        view = switch[len(tenant_features.SCREEN_PREFIX):]
        needed = tenant_features.SCREEN_SWITCHES.get(view)
        if needed in by_permission:  # rule B
            return by_permission[needed]
        return by_key.get(_squash(view))  # rule C
    return None


def build_seed() -> Dict[str, List[str]]:
    """``{"Free": [...], "Pro": [...], "Enterprise": [...]}`` per the D-29 rule above."""
    by_permission = _catalogue_tiers()
    by_key = {_squash(key): TIERS[entry["minTier"]] for key, entry in feature_catalog.FEATURE_CATALOG.items()}
    final: Dict[str, int] = {}

    def tier_of(switch: str) -> int:
        if switch not in final:
            own = _own_tier(switch, by_permission, by_key)
            parent = tenant_features.SWITCH_PARENTS.get(switch)
            parent_tier = tier_of(parent) if parent else None
            if own is None:
                final[switch] = parent_tier if parent_tier is not None else TIERS["Enterprise"]
            else:
                final[switch] = max(own, parent_tier) if parent_tier is not None else own
        return final[switch]

    switches = sorted(tenant_features.SWITCHABLE)
    return {plan: sorted(s for s in switches if tier_of(s) <= TIERS[plan]) for plan in PLAN_ORDER}


def main() -> None:
    seed = build_seed()
    document = {"version": 1, "rule": "D-29", "plans": seed}
    OUT_PATH.write_text(json.dumps(document, indent=2) + "\n", encoding="utf-8")
    print(" ".join(f"{plan}={len(seed[plan])}" for plan in PLAN_ORDER))


if __name__ == "__main__":
    main()
