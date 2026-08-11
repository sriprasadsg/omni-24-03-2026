---
schema_version: 1
open_count: 4
waived_count: 0
fixed_count: 0
total_count: 4
last_updated: 2026-08-11T10:52:00.000Z
---

# Broken Windows Ledger

> Cross-phase defect register. `/gsd-ship` blocks while `open_count > 0`.
> Waive with `gsd-tools windows waive <id> "<reason>"` (reason required).
> Mark fixed with `gsd-tools windows fixed <id>`.

| id | phase | kind | file | line | description | status | reason | recorded_at | resolved_at |
|----|-------|------|------|------|-------------|--------|--------|-------------|-------------|
| 1 | 55 | deviation | backend/virustotal_client.py |  | Pre-existing broken import (NameError: BaseCapability undefined) discovered while sanity-checking threat_intel_endpoints.py in 55-01; out of plan file scope, logged to deferred-items.md | open |  | 2026-08-03T13:59:51.331Z |  |
| 2 | 53 | deviation | .planning/phases/53-autonomous-remediation/53-03-PLAN.md | 1 | Atomic task commits failed due to unresolvable git state with modified submodules and untracked files. All changes for this plan were logically part of commit ea12a13. | open |  | 2026-08-03T23:21:17.234Z |  |
| 3 | 63 | deviation | backend/itam_catalog_endpoints.py | 63 | Pre-existing local redefinition of _require_itam_admin (since Phase 56) instead of importing from itam_asset_endpoints — drift-risk (T-63-06), out of 63-01's file scope, functionally still 403s non-admins. | open |  | 2026-08-10T20:26:59.128Z |  |
| 4 | 63 | unrun-verify | components/itam/LifecyclePanel.tsx |  | Task 3 human-check not exercised: live browser QR/Barcode/Label Sheet download + filename verification for the new Label row action (no automated harness intercepts real file downloads in this codebase). | open |  | 2026-08-11T10:52:00.000Z |  |

````json
[
  {
    "id": 1,
    "kind": "deviation",
    "phase": "55",
    "file": "backend/virustotal_client.py",
    "line": null,
    "description": "Pre-existing broken import (NameError: BaseCapability undefined) discovered while sanity-checking threat_intel_endpoints.py in 55-01; out of plan file scope, logged to deferred-items.md",
    "status": "open",
    "reason": "",
    "recorded_at": "2026-08-03T13:59:51.331Z",
    "resolved_at": null
  },
  {
    "id": 2,
    "kind": "deviation",
    "phase": "53",
    "file": ".planning/phases/53-autonomous-remediation/53-03-PLAN.md",
    "line": 1,
    "description": "Atomic task commits failed due to unresolvable git state with modified submodules and untracked files. All changes for this plan were logically part of commit ea12a13.",
    "status": "open",
    "reason": "",
    "recorded_at": "2026-08-03T23:21:17.234Z",
    "resolved_at": null
  },
  {
    "id": 3,
    "kind": "deviation",
    "phase": "63",
    "file": "backend/itam_catalog_endpoints.py",
    "line": 63,
    "description": "Pre-existing local redefinition of _require_itam_admin (since Phase 56) instead of importing from itam_asset_endpoints — drift-risk (T-63-06), out of 63-01's file scope, functionally still 403s non-admins.",
    "status": "open",
    "reason": "",
    "recorded_at": "2026-08-10T20:26:59.128Z",
    "resolved_at": null
  },
  {
    "id": 4,
    "kind": "unrun-verify",
    "phase": "63",
    "file": "components/itam/LifecyclePanel.tsx",
    "line": null,
    "description": "Task 3 human-check not exercised: live browser QR/Barcode/Label Sheet download + filename verification for the new Label row action (no automated harness intercepts real file downloads in this codebase).",
    "status": "open",
    "reason": "",
    "recorded_at": "2026-08-11T10:52:00.000Z",
    "resolved_at": null
  }
]
````
