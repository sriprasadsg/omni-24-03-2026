# Phase 25: Cloud Checks Execution Gaps - Research

**Researched:** 2026-07-06
**Domain:** Backend wiring gaps + regex-based static-analysis rule engine (Python, FastAPI, MongoDB via Motor)
**Confidence:** HIGH

## Summary

This phase closes three narrow, well-understood gaps in existing code — it is a wiring/rule-authoring phase, not a new-technology phase. No new libraries are required.

**CHK-01** (K8s + DigitalOcean execution): `cloud_checks_service.py` already defines and imports `K8S_CHECKS` (20 checks) and `DO_CHECKS` (10 checks) into the combined `CLOUD_CHECKS` list, but `run_checks()` hard-gates on `RUNNABLE_PROVIDERS = ("aws", "azure", "gcp")` and returns an error for any other provider. Fixing this is **not a one-file change**: there are four independent `("aws", "azure", "gcp")` allowlists across the codebase that must all be updated in lockstep, or the feature will be reachable in some code paths and silently rejected in others (see Architecture Patterns, Pattern 1).

**CHK-02** (CloudFormation rule engine): `iac_scanner_service.py` already has a clean, proven pattern — a flat list of dict-based rules with `pattern` (must-match) + `negative_pattern` (mitigation-or-violation marker) + optional `vulnerable_marker`/`scope_lines`, evaluated by one shared `scan_code()` function. Adding CloudFormation support means (a) adding ~18 CFN rule dicts following the exact same shape as the 17 existing Terraform rules, translated to `AWS::*` resource/property syntax, and (b) fixing a real bug in `_detect_provider()` — it currently can *only* detect CloudFormation from JSON-extension files containing a literal `"Type" : "AWS::` substring, so a YAML-format CFN template (which the frontend dashboard explicitly advertises as a supported option — `template.yaml (CloudFormation)`) is silently misclassified as `"unknown"` today and researched CFN rules would never run against it without this detection fix.

**CHK-03** (container scan labeling): `container_scanner_service.py` already carries a `trivy: bool` flag and a human-readable `note` string when Trivy is unavailable — this is 80% of the "don't lie about simulated data" fix already in place. The gap is presentation, not data: the frontend only surfaces `note` in one place (a small yellow banner under the image input box) and never on the results table, the CVE list, or the scan-history entries — so a user glancing at the CVE table or the history list sees no visual distinction between a real Trivy scan and six hardcoded fake CVEs (`CVE-2024-0001`..`0006`). **Failing closed (returning no data) is explicitly the wrong fix** — two of the eight existing `test_iac_scanner.py` tests (`test_container_scan_image`, `test_container_vuln_severity_counts`) assert that `scan_image()` still returns non-empty `vulns`/`total` when Trivy is mocked absent; a fail-closed change would regress passing IAC-02 tests. The correct fix is: add an explicit `"simulated": true` field (clearer contract than overloading `trivy: false`) and make the UI visually loud about it everywhere simulated data appears.

**Primary recommendation:** Treat this as three independent, additive changes to existing files — no new dependencies, no new services, no schema migrations. Preserve every existing passing test; add new tests following the exact `test_iac_scanner.py` TDD pattern (module-level `_mkdb`/`_mkuser`/`_build` helpers, `TestClient` with `dependency_overrides` on `get_current_user`).

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| CHK-01 | Kubernetes and DigitalOcean checks, already defined in `cloud_checks_service.py`, are actually evaluated by `run_checks()` instead of being catalog-only | Architecture Patterns — Pattern 1 identifies all 4 provider-allowlist gates (`cloud_checks_service.py`, `cloud_checks_endpoints.py`, `cloud_account_endpoints.py`, `mcp_server_endpoints.py`) that must be updated in lockstep; Common Pitfalls 1–2 cover the registration-gate trap and the coverage-denominator recompute |
| CHK-02 | CloudFormation IaC scanning implements a real rule engine at rule-count parity with the existing Terraform/Kubernetes checks | Architecture Patterns — Pattern 2 provides a ready-to-use 18-rule CFN ruleset (parity with Terraform's 17) following the exact existing rule-dict shape, backed by AWS-doc-verified property defaults; Pattern 3 fixes the pre-existing YAML-CFN detection bug that would otherwise silently prevent these rules from ever firing |
| CHK-03 | Container image scanning fails closed with an explicit "Trivy not available" result, or clearly labels simulated CVE data as simulated, instead of presenting fallback data as real | Architecture Patterns — Pattern 4 recommends the labeling approach (not fail-closed) with rationale in Common Pitfalls 4 (fail-closed regresses 2 existing passing tests); gives the exact `simulated: true` field addition and the 3 UI surfaces in `IacContainerDashboard.tsx` that need the badge |
</phase_requirements>

## Project Constraints (from CLAUDE.md)

- **Keep files under 500 lines.** `iac_scanner_service.py` (129 lines) and `container_scanner_service.py` (100 lines) both have ample headroom to add ~18 CFN rule dicts and one new field without approaching the limit. `cloud_checks_service.py` (146 lines) likewise has headroom for the RUNNABLE_PROVIDERS widening.
- **Validate input at system boundaries.** Existing 500KB code-size cap (`iac_scanner_endpoints.py`) and image-name regex allowlist (`container_scanner_endpoints.py`) are already in place and must remain intact; new CFN patterns must use `scope_lines` bounding per Pitfall 5 rather than unscoped matching over the full boundary-validated payload.
- **Do what has been asked; nothing more, nothing less.** Do not build a new CFN parser/library, a new "data provenance" abstraction, or a shared allowlist-constants module — see Don't Hand-Roll. Widen the existing 4 gates and extend the existing 2 rule-shape patterns only.
- **NEVER create files unless absolutely necessary — prefer editing existing files.** All three requirements (CHK-01/02/03) are satisfiable by editing existing backend files plus `IacContainerDashboard.tsx`; the one exception is `backend/tests/test_cloud_checks_expansion.py`, which already exists as an empty stub and should be filled in, not replaced with a new file.
- **ALWAYS read a file before editing it.** All files this research touches were read in full this session (see Sources).

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| K8s/DO check execution against imported findings | API / Backend (`cloud_checks_service.py`) | Database (`cloud_findings`, `cloud_check_results` collections) | Pure server-side matching logic against already-stored findings; no new client surface |
| Cloud account registration (provider allowlist) | API / Backend (`cloud_account_endpoints.py`) | — | Input validation gate; must stay in sync with the execution-tier allowlist or accounts can be registered that can never be scanned (or vice versa) |
| CloudFormation rule engine | API / Backend (`iac_scanner_service.py`) | — | Stateless regex evaluation over submitted code string; no DB/network dependency |
| Provider detection (`_detect_provider`) | API / Backend (`iac_scanner_service.py`) | — | Pure text classification, must run before rule dispatch |
| Simulated-data labeling | API / Backend (data contract: add `simulated` field) | Browser/Client (`IacContainerDashboard.tsx` — visual badge) | Backend must emit an unambiguous machine-readable flag; frontend must render it prominently — mislabeling is a trust/compliance-integrity bug, not just cosmetic |

## Standard Stack

No new libraries. This phase extends existing modules using only stdlib (`re`, `json`, `uuid`, `datetime`) already imported by `iac_scanner_service.py` and `container_scanner_service.py`.

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| `re` (stdlib) | builtin | Regex pattern matching for IaC rule engine | Already the established pattern for all 26 existing Terraform/K8s checks — CFN rules must match this convention for planner/reviewer consistency |
| FastAPI | (existing pin) | Endpoint layer, unchanged | Already used by `cloud_checks_endpoints.py`, `iac_scanner_endpoints.py`, `container_scanner_endpoints.py` |
| Motor (async MongoDB) | (existing pin) | `cloud_check_results`, `iac_scan_results`, `container_scan_results` collections | Already the persistence layer for all three services touched |

### Supporting
None — no supporting libraries needed.

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| Hand-written regex rules for CloudFormation | A real CFN parser (`cfn-lint`, `cfn_flip` to normalize YAML→JSON then walk `Resources`) | A real parser would be more robust (handles CFN intrinsic functions like `!Ref`, `!Sub`, multi-document YAML) but is a new dependency + architecture change inconsistent with the existing regex-based Terraform/K8s engine. Out of scope for a Tier-1 "quick fix" phase — flagged as an Open Question below for a future hardening pass. |

**Installation:** None required — no new packages.

**Version verification:** N/A — no external packages added in this phase.

## Package Legitimacy Audit

**Not applicable.** This phase adds zero new third-party dependencies (no `pip install`, no `package.json` changes). All work is additions to existing first-party modules (`cloud_checks_service.py`, `iac_scanner_service.py`, `container_scanner_service.py`, `cloud_checks_endpoints.py`, `cloud_account_endpoints.py`, `mcp_server_endpoints.py`, `IacContainerDashboard.tsx`) using only already-imported stdlib and already-pinned framework libraries.

**Packages removed due to [SLOP] verdict:** none
**Packages flagged as suspicious [SUS]:** none

## Architecture Patterns

### System Architecture Diagram

```
                    ┌─────────────────────────────────────────┐
                    │        POST /api/cloud-accounts          │
                    │  (cloud_account_endpoints.py)            │
                    │  _VALID_PROVIDERS = {aws,azure,gcp}  ◄───┼── GATE 1 (registration)
                    └───────────────┬───────────────────────────┘
                                    │ writes cloud_accounts doc {provider: "..."}
                                    ▼
                    ┌─────────────────────────────────────────┐
       trigger scan │   POST /api/cloud-accounts/{id}/scan     │
      (3 entry pts) │   POST /api/cloud-checks/run             │◄── GATE 2 (direct run)
                    │   POST /api/mcp/execute/run_cloud_check  │◄── GATE 3 (MCP tool)
                    └───────────────┬───────────────────────────┘
                                    │ all three call the same function:
                                    ▼
                    ┌─────────────────────────────────────────┐
                    │  cloud_checks_service.run_checks()       │
                    │  if provider not in RUNNABLE_PROVIDERS:  │◄── GATE 4 (execution — the one
                    │      return {"error": ...}               │    named in the phase description)
                    │  else: match CLOUD_CHECKS[provider] vs   │
                    │        cloud_findings collection         │
                    │        upsert cloud_check_results        │
                    └───────────────┬───────────────────────────┘
                                    │
                                    ▼
                    ┌─────────────────────────────────────────┐
                    │  GET /api/cloud-checks/summary            │
                    │  coverage = total / _RUNNABLE_CHECKS_COUNT│◄── denominator must be recomputed
                    └─────────────────────────────────────────┘

  ── Separately, IaC/Container scanning (stateless, no account registration) ──

  POST /api/iac/scan {code, filename}
        │
        ▼
  _detect_provider(code, ext) ──► "terraform" | "kubernetes" | "cloudformation" | "unknown"
        │  (currently: CFN only detected via JSON-ext + literal substring —
        │   YAML CFN always falls through to "unknown")
        ▼
  scan_code(): filter IAC_CHECKS by provider, regex-match each rule ──► findings[]
        │
        ▼
  save_result() → iac_scan_results (tenant-scoped)


  POST /api/container/scan {image_name}
        │
        ▼
  _find_trivy() found? ──yes──► subprocess Trivy JSON ──► _parse_trivy_output()
        │no
        ▼
  _simulated_results() ──► {trivy: false, note: "...", vulns: [6 hardcoded CVEs]}
        │
        ▼  (today: "note" only rendered in one small banner)
  IacContainerDashboard.tsx renders result ──► needs "simulated" badge on
        summary panel + CVE table + history rows, not just the input banner
```

### Recommended Project Structure

No new files/folders — all changes are edits to existing files:
```
backend/
├── cloud_checks_service.py       # RUNNABLE_PROVIDERS tuple + _RUNNABLE_CHECKS_COUNT (CHK-01)
├── cloud_checks_endpoints.py     # POST /run provider validation tuple (CHK-01)
├── cloud_account_endpoints.py    # _VALID_PROVIDERS set (CHK-01 — registration gate)
├── mcp_server_endpoints.py       # run_cloud_check tool provider validation (CHK-01)
├── iac_scanner_service.py        # + ~18 CFN rules in IAC_CHECKS, fix _detect_provider() (CHK-02)
├── container_scanner_service.py  # rename/add explicit "simulated" field (CHK-03)
├── tests/
│   └── test_cloud_checks_expansion.py  # currently an EMPTY STUB — fill with CHK-01 tests
│   └── test_iac_scanner.py             # extend with CFN + simulated-labeling tests (CHK-02/03)
components/
└── IacContainerDashboard.tsx     # simulated-data badge on summary/table/history (CHK-03)
```

### Pattern 1: The Four-Gate Provider Allowlist (CHK-01 — critical wiring finding)

**What:** `("aws", "azure", "gcp")` is duplicated as an independent literal/tuple/set in **four** separate files. All four must change together or the fix is incomplete.

**When to use:** Any time you're "just adding a provider" to an existing multi-gate system — grep for every occurrence of the current allowlist before declaring done.

**The four gates found by direct grep (`grep -rn '"aws", "azure", "gcp"' backend/`):**

```python
# Source: backend/cloud_checks_service.py:34 — GATE 4, the execution gate named in the phase description
RUNNABLE_PROVIDERS = ("aws", "azure", "gcp")
_RUNNABLE_CHECKS_COUNT = len([c for c in CLOUD_CHECKS if c["provider"] in RUNNABLE_PROVIDERS])
# run_checks() returns {"error": f"provider must be one of {RUNNABLE_PROVIDERS}", "ran": 0} otherwise

# Source: backend/cloud_checks_endpoints.py:73-74 — GATE 2, direct-run HTTP endpoint validation
if payload.provider not in ("aws", "azure", "gcp"):
    raise HTTPException(status_code=400, detail="provider must be aws, azure, or gcp")

# Source: backend/cloud_account_endpoints.py:13 — GATE 1, account REGISTRATION validation
# (without this, you can never even create a cloud_accounts doc with provider="kubernetes"
#  or "digitalocean" — so scan_account()'s call into run_checks() for those providers is
#  unreachable through the standard multi-account flow no matter what Gate 4 says)
_VALID_PROVIDERS = {"aws", "azure", "gcp"}

# Source: backend/mcp_server_endpoints.py:78-79 — GATE 3, MCP tool-calling entry point
if provider not in ("aws", "azure", "gcp"):
    raise HTTPException(status_code=400, detail="provider must be aws, azure, or gcp")
# also mcp_server_endpoints.py:24 has a stale tool-schema description string
# "params": {"provider": "string (aws/azure/gcp)", ...} — cosmetic but should be updated
# for consistency once k8s/digitalocean become valid inputs.
```

**Verification that Gate 1 (registration) is real and blocking:** `cloud_accounts_service.py:98-108` `scan_account()` reads `account.get("provider", "aws")` from a `cloud_accounts` document and passes it straight into `cloud_checks_service.run_checks()`. If Gate 1 never let a `provider="kubernetes"` document exist, Gate 4 being fixed is necessary but not sufficient for the multi-account scan flow (`POST /api/cloud-accounts/{id}/scan`) — only the *direct* `POST /api/cloud-checks/run` endpoint (Gate 2) would become reachable for k8s/DO, since it takes `accountId`+`provider` as separate payload fields rather than reading `provider` off a stored account doc. **The planner must decide and document which of the three trigger paths (account-scan / direct-run / MCP tool) are in scope for CHK-01** — recommend widening all four gates for consistency, since leaving Gate 1 narrower than Gate 4 creates exactly the kind of "reachable via API but not through normal UI flow" gap this phase exists to close.

### Pattern 2: CloudFormation Rule Dict Shape (CHK-02 — matches existing Terraform convention exactly)

**What:** Every existing IaC rule is a flat dict: `id`, `name`, `description`, `provider`, `severity`, `pattern` (regex that must match for the rule to be "relevant"), `negative_pattern` (regex checked within the match, or globally, or in a scoped line window), optional `vulnerable_marker: True` (negative_pattern presence = FAIL) vs. absent (negative_pattern presence = PASS/mitigated), optional `scope_lines` (limits the negative_pattern search to N lines around the match instead of the whole file).

**When to use:** For every new CloudFormation rule — do not invent a new rule shape or a new evaluation function. `scan_code()` is provider-agnostic already; it just filters `IAC_CHECKS` by `check["provider"] == provider`.

**Recommended CloudFormation ruleset (18 rules — parity with Terraform's 17), YAML+JSON tolerant patterns:**

CloudFormation templates can be authored as YAML (`Type: AWS::S3::Bucket`) or JSON (`"Type": "AWS::S3::Bucket"`). Patterns below use `"?` optional-quote and flexible whitespace/colon-spacing so a single pattern matches both serializations — this mirrors how `_detect_provider()` already handles the JSON case and must be extended for YAML.

```python
# Source: AWS CloudFormation Template Reference (see Sources section for URLs)
CFN_CHECKS = [
    {"id": "cfn-s3-public-access", "name": "S3 Bucket Public Access Not Blocked", "description": "S3 bucket should have PublicAccessBlockConfiguration blocking public ACLs/policies", "provider": "cloudformation", "severity": "critical", "pattern": r'Type"?\s*:?\s*"?AWS::S3::Bucket', "negative_pattern": r'PublicAccessBlockConfiguration', "scope_lines": 15},
    {"id": "cfn-s3-public-acl", "name": "S3 Bucket Public ACL", "description": "S3 bucket AccessControl should not be PublicRead/PublicReadWrite", "provider": "cloudformation", "severity": "critical", "pattern": r'Type"?\s*:?\s*"?AWS::S3::Bucket', "negative_pattern": r'AccessControl"?\s*:\s*"?PublicRead', "vulnerable_marker": True, "scope_lines": 15},
    {"id": "cfn-iam-wildcard-action", "name": "IAM Policy Wildcard Action", "description": "IAM policy Statement.Action should not be \"*\"", "provider": "cloudformation", "severity": "critical", "pattern": r'Type"?\s*:?\s*"?AWS::IAM::(Policy|Role)', "negative_pattern": r'Action"?\s*:\s*\[?\s*"?\*"?', "vulnerable_marker": True, "scope_lines": 20},
    {"id": "cfn-sg-open-ssh", "name": "Security Group Open SSH", "description": "SecurityGroupIngress should not allow 0.0.0.0/0 on port 22", "provider": "cloudformation", "severity": "critical", "pattern": r'Type"?\s*:?\s*"?AWS::EC2::SecurityGroup', "negative_pattern": r'CidrIp"?\s*:\s*"?0\.0\.0\.0/0.*(FromPort"?\s*:\s*22|ToPort"?\s*:\s*22)', "vulnerable_marker": True, "scope_lines": 15},
    {"id": "cfn-sg-open-rdp", "name": "Security Group Open RDP", "description": "SecurityGroupIngress should not allow 0.0.0.0/0 on port 3389", "provider": "cloudformation", "severity": "critical", "pattern": r'Type"?\s*:?\s*"?AWS::EC2::SecurityGroup', "negative_pattern": r'CidrIp"?\s*:\s*"?0\.0\.0\.0/0.*(FromPort"?\s*:\s*3389|ToPort"?\s*:\s*3389)', "vulnerable_marker": True, "scope_lines": 15},
    {"id": "cfn-ebs-not-encrypted", "name": "EBS Volume Encryption Disabled", "description": "AWS::EC2::Volume should have Encrypted: true", "provider": "cloudformation", "severity": "high", "pattern": r'Type"?\s*:?\s*"?AWS::EC2::Volume', "negative_pattern": r'Encrypted"?\s*:\s*false', "vulnerable_marker": True, "scope_lines": 10},
    {"id": "cfn-rds-not-encrypted", "name": "RDS Storage Encryption Disabled", "description": "AWS::RDS::DBInstance StorageEncrypted should be true", "provider": "cloudformation", "severity": "high", "pattern": r'Type"?\s*:?\s*"?AWS::RDS::DBInstance', "negative_pattern": r'StorageEncrypted"?\s*:\s*false', "vulnerable_marker": True, "scope_lines": 20},
    {"id": "cfn-eks-public-endpoint", "name": "EKS Cluster Public Endpoint", "description": "EndpointPublicAccess should be false (defaults to true if omitted)", "provider": "cloudformation", "severity": "high", "pattern": r'Type"?\s*:?\s*"?AWS::EKS::Cluster', "negative_pattern": r'EndpointPublicAccess"?\s*:\s*true', "vulnerable_marker": True, "scope_lines": 20},
    {"id": "cfn-ec2-public-ip", "name": "EC2 Instance with Public IP", "description": "NetworkInterfaces should not set AssociatePublicIpAddress: true", "provider": "cloudformation", "severity": "high", "pattern": r'Type"?\s*:?\s*"?AWS::EC2::Instance', "negative_pattern": r'AssociatePublicIpAddress"?\s*:\s*true', "vulnerable_marker": True, "scope_lines": 20},
    {"id": "cfn-elb-http-listener", "name": "Load Balancer HTTP Listener (no redirect)", "description": "ALB/NLB Listener should not use plain HTTP on port 80 without a redirect action", "provider": "cloudformation", "severity": "high", "pattern": r'Type"?\s*:?\s*"?AWS::ElasticLoadBalancingV2::Listener', "negative_pattern": r'Port"?\s*:\s*80\b', "vulnerable_marker": True, "scope_lines": 15},
    {"id": "cfn-kms-rotation-disabled", "name": "KMS Key Rotation Disabled", "description": "EnableKeyRotation defaults to false if omitted — should be explicitly true", "provider": "cloudformation", "severity": "medium", "pattern": r'Type"?\s*:?\s*"?AWS::KMS::Key', "negative_pattern": r'EnableKeyRotation"?\s*:\s*true', "scope_lines": 10},
    {"id": "cfn-s3-logging-disabled", "name": "S3 Bucket Logging Disabled", "description": "S3 bucket should configure LoggingConfiguration", "provider": "cloudformation", "severity": "medium", "pattern": r'Type"?\s*:?\s*"?AWS::S3::Bucket', "negative_pattern": r'LoggingConfiguration', "scope_lines": 15},
    {"id": "cfn-vpc-flow-logs-missing", "name": "VPC Flow Logs Disabled", "description": "A VPC resource should have an accompanying AWS::EC2::FlowLog", "provider": "cloudformation", "severity": "medium", "pattern": r'Type"?\s*:?\s*"?AWS::EC2::VPC\b', "negative_pattern": r'Type"?\s*:?\s*"?AWS::EC2::FlowLog'},
    {"id": "cfn-hardcoded-secret", "name": "Hardcoded AWS Access Key", "description": "AWS access key literal should not be hardcoded in template", "provider": "cloudformation", "severity": "critical", "pattern": r'AKIA[0-9A-Z]{16}'},
    {"id": "cfn-plaintext-secret-param", "name": "Secret Parameter Without NoEcho", "description": "Password/secret/token Parameters should set NoEcho: true", "provider": "cloudformation", "severity": "critical", "pattern": r'(?i)(Password|Secret|Token|ApiKey|Credential)"?\s*:\s*\{?\s*"?Type"?\s*:\s*"?String', "negative_pattern": r'NoEcho"?\s*:\s*true', "scope_lines": 6},
    {"id": "cfn-ec2-admin-userdata", "name": "EC2 UserData References Admin/Root", "description": "EC2 instance UserData should not reference admin/root elevation", "provider": "cloudformation", "severity": "high", "pattern": r'Type"?\s*:?\s*"?AWS::EC2::Instance', "negative_pattern": r'UserData.*(admin|root)', "scope_lines": 15},
    {"id": "cfn-s3-versioning-disabled", "name": "S3 Versioning Disabled", "description": "S3 bucket should configure VersioningConfiguration Status: Enabled", "provider": "cloudformation", "severity": "medium", "pattern": r'Type"?\s*:?\s*"?AWS::S3::Bucket', "negative_pattern": r'VersioningConfiguration', "scope_lines": 15},
    {"id": "cfn-rds-deletion-protection-disabled", "name": "RDS Deletion Protection Disabled", "description": "DeletionProtection defaults to false if omitted — should be explicitly true", "provider": "cloudformation", "severity": "medium", "pattern": r'Type"?\s*:?\s*"?AWS::RDS::DBInstance', "negative_pattern": r'DeletionProtection"?\s*:\s*true', "scope_lines": 20},
]
```

**AWS-verified property facts backing the rules above** (see Sources — all `[CITED: docs.aws.amazon.com]`):
- `PublicAccessBlockConfiguration` has 4 boolean sub-properties (`BlockPublicAcls`, `BlockPublicPolicy`, `IgnorePublicAcls`, `RestrictPublicBuckets`); `AccessControl` is a *separate*, sibling top-level `AWS::S3::Bucket` property, not nested under it.
- `AWS::RDS::DBInstance.DeletionProtection` **defaults to false (disabled)** when omitted — an absent property is itself a finding, which is why the CFN rule (like its Terraform counterpart `tf-rds-deletion-protection`) treats "no explicit `true`" as FAIL via `vulnerable_marker`-style negative-match-means-fail logic.
- `AWS::EKS::Cluster.ResourcesVpcConfig.EndpointPublicAccess` **defaults to true (public)** when omitted — same "absence is a finding" pattern as the Terraform `tf-eks-public` check.
- `AWS::KMS::Key.EnableKeyRotation` **defaults to false** when omitted, and is only valid for symmetric keys.

### Pattern 3: `_detect_provider()` Bug Fix — YAML CloudFormation is Currently Undetectable

**What:** Current logic (`iac_scanner_service.py:94-107`):
```python
def _detect_provider(code: str, ext: str) -> str:
    if ext in ("tf", "tfvars"):
        return "terraform"
    if ext in ("yaml", "yml"):
        if re.search(r'kind:\s*(Pod|Deployment|Service|...)', code):
            return "kubernetes"
        # <-- falls through to the generic checks below with NO CFN check for YAML
    if ext in ("json", "template"):
        if '"Type" : "AWS::' in code or '"Type": "AWS::' in code:
            return "cloudformation"
    if re.search(r'resource\s+"aws_', code):
        return "terraform"
    if re.search(r'apiVersion:\s*(v1|apps/|batch/|rbac/)', code):
        return "kubernetes"
    return "unknown"
```
A `.yaml`/`.yml` file containing `Resources:\n  MyBucket:\n    Type: AWS::S3::Bucket` (the standard, and far more common, CFN authoring format) is never matched — it falls through every branch and returns `"unknown"`. This directly contradicts the dashboard's own UI, which offers `template.yaml (CloudFormation)` as a selectable file type (`IacContainerDashboard.tsx:232`).

**Fix:** Add a YAML-tolerant CFN detection branch and a generic fallback that works regardless of extension, using a single pattern that matches `Type: AWS::` (YAML) or `"Type": "AWS::` / `"Type" : "AWS::` (JSON):
```python
_CFN_TYPE_RE = re.compile(r'"?Type"?\s*:\s*"?AWS::')

def _detect_provider(code: str, ext: str) -> str:
    if ext in ("tf", "tfvars"):
        return "terraform"
    if ext in ("yaml", "yml"):
        if re.search(r'kind:\s*(Pod|Deployment|Service|Namespace|ConfigMap|Secret|NetworkPolicy|Ingress)', code):
            return "kubernetes"
        if _CFN_TYPE_RE.search(code):
            return "cloudformation"
    if ext in ("json", "template") and _CFN_TYPE_RE.search(code):
        return "cloudformation"
    if re.search(r'resource\s+"aws_', code):
        return "terraform"
    if re.search(r'apiVersion:\s*(v1|apps/|batch/|rbac/)', code):
        return "kubernetes"
    if _CFN_TYPE_RE.search(code):  # extension-less/unknown-extension fallback
        return "cloudformation"
    return "unknown"
```

### Pattern 4: Explicit `simulated` Flag Over Implicit `trivy: false` (CHK-03)

**What:** `container_scanner_service.py`'s `_simulated_results()` already returns `trivy: false` and a `note` string. The gap the requirement (CHK-03) targets is *presentation*, not data availability. Add a same-value, more explicitly-named field so frontend code and any consumer of the API contract doesn't have to know that `trivy: false` is the "this is fake data" signal — it should say so in its own name.

```python
# Source: backend/container_scanner_service.py — _simulated_results(), extend the returned dict
result = {
    "scan_id": scan_id, "image": image_name,
    "trivy": False, "simulated": True,  # <-- new explicit field, same semantics as trivy:false
    "note": note or "Trivy not installed — simulated results",
    "vulns": vulns, "total": len(vulns), "critical": c, "high": h, "medium": m, "low": l,
    "scanned_at": _now(),
}
```
Also add `"simulated": False` (or omit — frontend should treat missing key as falsy) to the real-Trivy return path in `_parse_trivy_output()` for a consistent contract shape.

**Frontend — the existing UI contract must NOT break.** `IacContainerDashboard.tsx`'s `ContainerScanResponse` interface already has `trivy: boolean` and `note?: string`; extend it with `simulated?: boolean` and surface it in three places it's currently missing:
1. **Vulnerability Summary panel header** (currently only shows `containerResult.image`) — add a persistent badge when `containerResult.simulated`.
2. **Vulnerabilities table** (currently plain CVE rows) — add a "SIMULATED" chip in the table header/caption when the whole result set is simulated (all vulns share one scan's simulated flag — no need to tag individual rows).
3. **Scan History list** (`containerHistory.map(...)`) — each history entry should show a small "sim" tag when that entry's `simulated` is true, so a user scrolling history isn't misled by old scans either.

### Anti-Patterns to Avoid
- **Fail-closed for container scanning:** Returning an error/empty result when Trivy is absent instead of labeling simulated data — this **will break 2 of 8 existing IAC-02 tests** (`test_container_scan_image`, `test_container_vuln_severity_counts`), which assert `scan_image()` returns real, non-empty vuln data even when Trivy is mocked absent. Confirmed by reading `test_iac_scanner.py:69-76,103-107` directly.
- **Widening only Gate 4 (`RUNNABLE_PROVIDERS`) and calling CHK-01 done:** Leaves Gate 1 (account registration) still rejecting `provider=kubernetes`/`digitalocean`, meaning the multi-account scan flow (`POST /api/cloud-accounts` → `.../scan`) still can't reach the new code path even though direct `POST /api/cloud-checks/run` calls now would. See Pattern 1.
- **Inventing a new IaC rule dict shape or a separate `scan_cloudformation()` function:** `scan_code()` is provider-agnostic by design (`[c for c in IAC_CHECKS if c["provider"] == provider]`) — CFN rules are just more entries in the same `IAC_CHECKS` list with `"provider": "cloudformation"`.
- **Unscoped regex over the full 500KB code payload for negative_pattern matches:** the existing pattern already guards two Terraform rules (`tf-hardcoded-key`, `tf-plaintext-secret`) with `scope_lines` specifically to avoid an unrelated mitigation elsewhere in a large file masking a real, nearby violation — and to bound backtracking cost. New CFN rules with multi-line/greedy negative_patterns (e.g. `UserData.*(admin|root)` with DOTALL) should use `scope_lines` the same way rather than searching the whole document.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| CloudFormation rule evaluation | A new `cfn_scanner_service.py` or new `scan_cloudformation()` function | Add rows to the existing `IAC_CHECKS` list + reuse `scan_code()` | The existing engine is already provider-dispatch-based; a parallel implementation would immediately create two divergent rule engines, doubling maintenance and violating the CLAUDE.md 500-line-file discipline unnecessarily |
| "Is this real or fake data" signaling | A new generic `DataProvenance` service/model | A plain `simulated: bool` field on the existing result dict, following the same shape already used by `finops_service.py`'s `_generate_simulated_spend()` (logs a warning + returns a differently-sourced-but-same-shaped dict) | Simplest possible contract; matches the one precedent already in the codebase for "no real data available, return a clearly-flagged deterministic substitute" |
| Provider-allowlist consistency checking | A shared constants module imported by all 4 gate files (over-engineering for a Tier-1 quick-fix phase) | Update all 4 literals directly, verified by grep before/after | The four allowlists live in different concerns (registration validation, direct-run validation, execution gate, MCP tool validation) — introducing a shared import here is a bigger refactor than the phase's Tier-1 scope justifies; document the four locations instead (this file does) |

**Key insight:** Every piece of this phase already has a proven, working pattern somewhere in the codebase (Terraform rules for CFN rules, `finops_service.py`'s simulated-spend labeling for container simulated-CVE labeling). The right move is disciplined imitation of the existing pattern, not new abstractions.

## Common Pitfalls

### Pitfall 1: Fixing Gate 4 only and declaring CHK-01 complete
**What goes wrong:** `cloud_checks_service.RUNNABLE_PROVIDERS` gets widened, tests pass for direct `run_checks()` calls, but `POST /api/cloud-accounts` still rejects `provider=kubernetes` at registration, so the feature is unreachable through the primary UI flow (Multi-Account Cloud Scanning, Phase 20's dashboard).
**Why it happens:** The phase description and code comment both point at `run_checks()` specifically, making it easy to treat as the only gate.
**How to avoid:** Grep for the literal allowlist string across `backend/` before writing the plan (already done in this research — 4 gates found) and explicitly decide/document which entry points are in scope.
**Warning signs:** A manual test that registers a DO account and calls `/scan` still 400s even after `run_checks()` accepts the provider.

### Pitfall 2: Coverage-percentage math breaking silently
**What goes wrong:** `get_summary()`'s `coverage` field is computed as `total / max(_RUNNABLE_CHECKS_COUNT, 1) * 100`. `_RUNNABLE_CHECKS_COUNT` is computed once at import time from `RUNNABLE_PROVIDERS`. If `RUNNABLE_PROVIDERS` is widened but the module-level `_RUNNABLE_CHECKS_COUNT` recomputation is missed (e.g., someone edits the tuple in a different spot or the constant gets hardcoded elsewhere), coverage percentages silently become wrong (denominator too small → coverage >100%, or too large → never reaches 100%).
**Why it happens:** `_RUNNABLE_CHECKS_COUNT` is a derived, cached-at-import-time value, not lazily computed — easy to forget it needs to move in lockstep with `RUNNABLE_PROVIDERS`.
**How to avoid:** Keep `_RUNNABLE_CHECKS_COUNT = len([c for c in CLOUD_CHECKS if c["provider"] in RUNNABLE_PROVIDERS])` as one line immediately after the tuple definition (already the current pattern) — just widen the tuple, the count recomputes for free since both are evaluated at the same import time.
**Warning signs:** `coverage` field in `/api/cloud-checks/summary` response exceeding 100 or never reaching it despite all provider results being present.

### Pitfall 3: YAML CloudFormation templates silently mis-detected as "unknown" (pre-existing bug, must fix as part of CHK-02)
**What goes wrong:** A CFN template authored in YAML (the more common CFN authoring style) hits `_detect_provider()`'s `ext in ("yaml","yml")` branch, fails the Kubernetes `kind:` regex, and falls through with `provider = "unknown"` — even after CFN rules are added to `IAC_CHECKS`, they will never fire for YAML-format templates.
**Why it happens:** The original CFN detection logic assumed CFN is always JSON (`.json`/`.template` + literal `"Type" : "AWS::` substring), which was a reasonable-looking but incomplete assumption given AWS supports both formats equally and the dashboard itself offers a `.yaml` CFN option.
**How to avoid:** See Pattern 3 above — add a generic `Type: AWS::`/`"Type": "AWS::` regex check that runs regardless of extension, checked before returning `"unknown"`.
**Warning signs:** A manual UI test pasting YAML CFN content with an obviously public S3 bucket returns 0 findings with no warning (looks identical to "clean template").

### Pitfall 4: Regressing existing container-scanner tests with a fail-closed CHK-03 fix
**What goes wrong:** Implementing CHK-03 as "return an error when Trivy is missing" breaks `test_container_scan_image` (asserts `r["total"] > 0`) and `test_container_vuln_severity_counts` (asserts severity counts sum to `total`), both of which explicitly patch `_find_trivy` to return `None` and expect `scan_image()` to still succeed with simulated data.
**Why it happens:** The requirement text offers fail-closed as one of two valid options ("fails closed... or clearly labels simulated"), and fail-closed sounds like the more "secure" choice in isolation.
**How to avoid:** Re-run `pytest backend/tests/test_iac_scanner.py -v` after any container_scanner_service.py change — both tests must still pass. Choose the labeling approach (Pattern 4).
**Warning signs:** `pytest backend/tests/test_iac_scanner.py::test_container_scan_image` fails after the change.

### Pitfall 5: ReDoS / catastrophic-backtracking risk from unscoped CFN negative_patterns
**What goes wrong:** New CFN rules that use greedy multi-line patterns (e.g., matching `UserData.*(admin|root)` with `re.DOTALL` across a full 500KB template) can be slow or pathological on adversarial input, and unrelated matches elsewhere in a large template can mask/unmask findings incorrectly.
**Why it happens:** Copy-pasting a Terraform rule's `negative_pattern` without also copying its `scope_lines` guard.
**How to avoid:** Every CFN rule with a `.*`-style negative_pattern should set `scope_lines` the same way `tf-hardcoded-key`/`tf-plaintext-secret` do, bounding both correctness risk and regex cost. The 500KB size cap already enforced by `iac_scanner_endpoints.py:16` (`if len(code) > 500000: raise HTTPException(413, ...)`) provides an outer bound, but scoped matching is still the correct per-rule practice.
**Warning signs:** Slow `/api/iac/scan` response times on large templates; a rule flags/misses a finding that's far away from the actual resource block.

## Code Examples

### Existing Terraform rule (verbatim, for pattern reference)
```python
# Source: backend/iac_scanner_service.py:12
{"id": "tf-s3-public-acl", "name": "S3 Bucket Public ACL", "description": "S3 bucket should not have public ACL", "provider": "terraform", "severity": "critical", "pattern": r'resource\s+"aws_s3_bucket"\s+"([^"]+)"', "negative_pattern": r'acl\s*=\s*"public-read"|acl\s*=\s*"public-read-write"', "vulnerable_marker": True},
```

### Existing test pattern to replicate for new CHK-01/02/03 tests
```python
# Source: backend/tests/test_iac_scanner.py:42-47 — no DB/HTTP needed for pure rule-engine tests
def test_iac_scan_terraform_s3_public_acl():
    code = 'resource "aws_s3_bucket" "bad" { bucket = "public-bucket"; acl = "public-read" }'
    r = iac.scan_code(code, "main.tf")
    s3 = [f for f in r["findings"] if f["check_id"] == "tf-s3-public-acl"]
    assert len(s3) > 0, f"No S3 findings in {r['findings']}"
    assert s3[0]["status"] == "FAIL"

# For CFN, follow the identical shape:
def test_iac_scan_cfn_s3_public_acl():
    code = 'Resources:\n  MyBucket:\n    Type: AWS::S3::Bucket\n    Properties:\n      AccessControl: PublicRead'
    r = iac.scan_code(code, "template.yaml")
    assert r["provider"] == "cloudformation"
    s3 = [f for f in r["findings"] if f["check_id"] == "cfn-s3-public-acl"]
    assert len(s3) > 0
    assert s3[0]["status"] == "FAIL"
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|---------------|--------|
| CFN scanning returns `warning: "not yet implemented"` | Real regex rule engine matching Terraform/K8s parity | This phase (25) | Feature-parity closure vs. Checkov/Prowler per the 2026-07-06 audit |
| K8s/DO checks catalog-only | Actually evaluated via `run_checks()` across all 4 gates | This phase (25) | Coverage metric and multi-account scan flow become meaningful for these 2 providers |
| Simulated container CVEs indistinguishable from real Trivy output | Explicit `simulated: true` flag + prominent UI labeling | This phase (25) | Prevents auditors/users from treating fabricated CVE-2024-000x findings as real evidence |

**Deprecated/outdated:** None — no libraries or APIs are being deprecated in this phase.

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | The recommended 18 CloudFormation rules provide adequate "parity" coverage vs. Terraform's 17 rules for CHK-02's requirement text ("at rule-count parity") | Architecture Patterns — Pattern 2 | If a stricter numeric or coverage-area interpretation of "parity" is expected (e.g., 1:1 rule-for-rule equivalents, or CFN-specific concerns like Nested Stacks/StackSets), the planner may need to add/adjust rules; low risk since 18 ≥ 17 |
| A2 | Widening all 4 provider gates (registration + direct-run + execution + MCP tool) is the correct scope for CHK-01, vs. only widening the execution gate named in the phase description | Architecture Patterns — Pattern 1 | If the planner scopes CHK-01 narrowly to just `run_checks()`, the multi-account UI flow remains broken for k8s/DO even though the requirement's own account text implies end-to-end reachability; recommend planner explicitly confirms scope with the four-gate finding in mind |
| A3 | Adding an explicit `simulated: true` field (rather than only enhancing UI labeling of the existing `trivy: false`) is worth the schema addition, vs. just improving frontend rendering of the existing field | Architecture Patterns — Pattern 4 | Low risk either way — `simulated` is additive and backward compatible; if omitted, the UI fix must derive "is this simulated" from `!trivy` instead, which is a slightly less obvious contract but functionally equivalent |

**If this table is empty:** N/A — see rows above; all are low-risk, additive judgment calls, not core factual claims.

## Open Questions

1. **Should the CloudFormation rule engine eventually use a real CFN parser instead of regex?**
   - What we know: The existing Terraform and Kubernetes engines are both regex-based and have shipped through Phase 24's review (16 findings fixed, 8/8 tests passing) — regex is the established, working pattern for this codebase.
   - What's unclear: Regex CFN detection can't resolve intrinsic functions (`!Ref`, `!Sub`, `!GetAtt`) or catch multi-resource relationships (e.g., "is this S3 bucket's logging target bucket itself compliant"). This limits rule sophistication but matches the existing Terraform engine's same limitation.
   - Recommendation: Ship the regex-based approach for this Tier-1 phase (consistent, fast, zero new dependencies); note a future hardening phase could adopt `cfn-lint`/`cfn_flip` if CFN-specific false-negative rates become a problem in practice.

2. **Which of the three CHK-01 trigger paths (account-scan, direct-run, MCP tool) does the phase's Definition of Done require to be end-to-end functional for k8s/DO?**
   - What we know: All three currently gate on the same three-provider allowlist independently (Pattern 1).
   - What's unclear: The phase description's minimal-fix framing suggests just `run_checks()`, but the requirement text ("actually evaluated by run_checks() instead of being catalog-only") is satisfied by Gate 4 alone; whether account *registration* (Gate 1) needs to widen too is a scope decision, not a research fact.
   - Recommendation: Default to widening all 4 gates for full consistency (lowest risk of a half-fixed feature) unless the planner has an explicit reason to scope narrower.

## Environment Availability

Skipped — this phase has no new external tool/service/runtime dependency. Trivy CLI availability (`_find_trivy`) is an existing, already-handled runtime check inside `container_scanner_service.py` itself (the very code this phase is improving, not a new environment dependency to probe).

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest (`pytest.ini` at repo root: `testpaths = . backend`, `asyncio_mode = auto`) |
| Config file | `/home/user/enterprise-omni-agent-ai-platform/pytest.ini` |
| Quick run command | `cd backend && python -m pytest tests/test_iac_scanner.py -v` |
| Full suite command | `cd backend && python -m pytest tests/ -v` |

### Phase Requirements → Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| CHK-01 | K8s check evaluated by `run_checks()` for a registered k8s cloud account | unit | `pytest backend/tests/test_cloud_checks_expansion.py::test_run_checks_evaluates_kubernetes -x` | ❌ Wave 0 (file exists but is an empty stub — REQUIREMENTS.md confirms 0 tests today) |
| CHK-01 | DigitalOcean check evaluated by `run_checks()` for a registered DO cloud account | unit | `pytest backend/tests/test_cloud_checks_expansion.py::test_run_checks_evaluates_digitalocean -x` | ❌ Wave 0 |
| CHK-01 | `cloud_check_results` coverage percentage recomputes correctly once k8s/DO are runnable | unit | `pytest backend/tests/test_cloud_checks_expansion.py::test_coverage_denominator_includes_new_providers -x` | ❌ Wave 0 |
| CHK-01 | Cloud account registration accepts `provider=kubernetes`/`digitalocean` (if scoped in) | integration | `pytest backend/tests/test_cloud_accounts.py::test_register_kubernetes_account -x` | ❌ Wave 0 (existing file only tests aws/gcp registration today) |
| CHK-02 | CloudFormation S3/IAM/SG/RDS/EKS/KMS rules fire FAIL on vulnerable YAML+JSON templates | unit | `pytest backend/tests/test_iac_scanner.py::test_iac_scan_cfn_* -x` | ❌ Wave 0 (new test functions) |
| CHK-02 | `_detect_provider` correctly classifies YAML-format CloudFormation as `"cloudformation"`, not `"unknown"` | unit | `pytest backend/tests/test_iac_scanner.py::test_detect_provider_yaml_cloudformation -x` | ❌ Wave 0 |
| CHK-03 | `_simulated_results()` output includes `simulated: true` and existing `test_container_scan_image`/`test_container_vuln_severity_counts` still pass unmodified | unit | `pytest backend/tests/test_iac_scanner.py -k container -x` | ✅ (2 existing tests must keep passing; add 1 new assertion test for the `simulated` field) |

### Sampling Rate
- **Per task commit:** `cd backend && python -m pytest tests/test_iac_scanner.py tests/test_cloud_checks_expansion.py tests/test_cloud_accounts.py -v`
- **Per wave merge:** `cd backend && python -m pytest tests/ -v`
- **Phase gate:** Full suite green before `/gsd-verify-work`

### Wave 0 Gaps
- [ ] `backend/tests/test_cloud_checks_expansion.py` — currently a 0-line empty stub (confirmed by direct read); needs the entire CHK-01 test suite (this is also a pre-existing Phase 17 test-coverage gap this phase is well-positioned to close, per REQUIREMENTS.md's own note: "remains an empty stub ... a real test-coverage gap worth filling")
- [ ] New test functions in `backend/tests/test_iac_scanner.py` for CFN rules and the `simulated` field — no new fixture files needed, reuse existing `_mkdb`/`_mkuser`/`_build` helpers already in that file
- [ ] Framework install: none — pytest already configured and passing 8/8 for this exact test file

## Security Domain

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-------------------|
| V2 Authentication | no | Unchanged — all touched endpoints already require `get_current_user` / `rbac_service.has_permission(...)` |
| V3 Session Management | no | Not touched by this phase |
| V4 Access Control | yes | Provider-allowlist widening must not accidentally loosen tenant isolation — `run_checks()` and `scan_account()` both already tenant-scope by `tenantId` in every DB query; verify this scoping is untouched when the allowlist tuples are edited |
| V5 Input Validation | yes | New CFN regex patterns operate on up to 500KB of user-submitted code (`iac_scanner_endpoints.py`'s existing 413 guard) — must use `scope_lines`-bounded matching per Pitfall 5 to avoid catastrophic backtracking (ReDoS) on adversarial templates |
| V6 Cryptography | no | Not touched — no crypto code in this phase |

### Known Threat Patterns for {stack}

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|----------------------|
| ReDoS via crafted CloudFormation template with pathological nested repetition feeding a greedy/DOTALL negative_pattern | Denial of Service | `scope_lines`-bounded regex windows (existing pattern from `tf-hardcoded-key`/`tf-plaintext-secret`) + the existing 500KB body-size cap in `iac_scanner_endpoints.py` |
| Presenting fabricated CVE data as authoritative scan evidence (compliance-integrity risk, not a classic STRIDE category but material to this platform's core value proposition) | Spoofing (of scan authenticity) | Explicit `simulated: true` field + prominent, unmissable UI labeling everywhere simulated results are rendered (Pattern 4) |
| Widening a provider allowlist in one gate but not another, creating an inconsistent authorization surface (e.g., MCP tool accepts a provider the REST endpoint rejects, or vice versa) | Tampering / inconsistent enforcement | Update and test all 4 gates together (Pattern 1); add a cross-gate consistency test if feasible |

## Sources

### Primary (HIGH confidence)
- Direct codebase reads: `backend/cloud_checks_service.py`, `backend/cloud_checks_endpoints.py`, `backend/cloud_account_endpoints.py`, `backend/cloud_accounts_service.py`, `backend/mcp_server_endpoints.py`, `backend/iac_scanner_service.py`, `backend/container_scanner_service.py`, `backend/iac_scanner_endpoints.py`, `backend/container_scanner_endpoints.py`, `backend/tests/test_iac_scanner.py`, `backend/tests/test_cloud_checks_expansion.py`, `backend/tests/test_cloud_accounts.py`, `components/IacContainerDashboard.tsx`, `pytest.ini`, `.planning/config.json` — all read in full this session, `[VERIFIED: codebase grep + direct read]`

### Secondary (MEDIUM confidence)
- [AWS::S3::Bucket PublicAccessBlockConfiguration — AWS CloudFormation Template Reference](https://docs.aws.amazon.com/AWSCloudFormation/latest/TemplateReference/aws-properties-s3-bucket-publicaccessblockconfiguration.html) `[CITED]`
- [AWS::RDS::DBInstance — AWS CloudFormation Template Reference](https://docs.aws.amazon.com/AWSCloudFormation/latest/TemplateReference/aws-resource-rds-dbinstance.html) `[CITED]`
- [AWS::EKS::Cluster ResourcesVpcConfig — AWS CloudFormation User Guide](https://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/aws-properties-eks-cluster-resourcesvpcconfig.html) `[CITED]`
- [AWS::KMS::Key — AWS CloudFormation Template Reference](https://docs.aws.amazon.com/AWSCloudFormation/latest/TemplateReference/aws-resource-kms-key.html) `[CITED]`

### Tertiary (LOW confidence)
- None — every non-codebase claim in this research is backed by an official AWS documentation URL.

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — no new libraries; existing stack fully verified by direct file reads
- Architecture: HIGH — all 4 provider gates and both bugs (YAML CFN detection, fail-closed test regression risk) found by direct grep/read, not inference
- Pitfalls: HIGH — every pitfall traces to a specific line number in an existing file or an existing passing test that would regress

**Research date:** 2026-07-06
**Valid until:** 2026-08-05 (30 days — stable internal codebase + stable AWS CloudFormation resource schema, not a fast-moving external dependency)
