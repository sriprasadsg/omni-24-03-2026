# Stack Research

**Domain:** Rust endpoint-agent dependency modernization + Python CSPM posture-check SDKs (multi-tenant compliance/GRC platform)
**Researched:** 2026-07-20
**Confidence:** HIGH (part a — verified via local `cargo check --offline` against the actual shipping tree; part b — HIGH for versions/packages verified via `pip index`/PyPI, MEDIUM for exact security-API method names not exercised locally)

## Context — what's already true in this codebase

Before recommending anything, two facts change the shape of this work:

1. **Rust crate bumps (part a) are already staged, uncommitted, on the shipping tree.** `agent-install/omni-agent-rs/Cargo.toml` (working tree, current branch `feat/rust-agent-2.1.0-and-fixes`) already declares `reqwest 0.13`, `sysinfo 0.39`, `tokio-tungstenite 0.30`, `rusqlite 0.40`, `hostname 0.4`, and `serde_norway 0.9` (replacing `serde_yaml`). `src/config.rs` already calls `serde_norway::from_str`/`to_string`. Running `cargo check --offline` in that directory **succeeds cleanly** — 4 pre-existing unrelated warnings (unused import/variable/mut/dead_code in unrelated files), zero errors. `Cargo.lock` already resolved concrete versions: `reqwest 0.13.4`, `sysinfo 0.39.6`, `tokio-tungstenite 0.30.0`, `rusqlite 0.40.1` (`libsqlite3-sys 0.38.1`), `hostname 0.4.2`, `serde_norway 0.9.42`. This is HANDOFF task 11's "remaining" work — it looks done at the manifest level; what's left is committing it and doing the 2.1.0 exe rebuild, not further crate research. See Recommendations below for the one behavioral risk to verify before shipping (TLS backend default flip).
2. **OCI/Alibaba/Cloudflare Python SDKs are already `pip`-installed dependencies**, and stub ingest modules already exist: `backend/oci_ingest.py`, `backend/cloudflare_ingest.py`, `backend/alibaba_ingest.py`. `backend/requirements.txt` already pins `oci>=2.181.1`, `aliyun-python-sdk-core-v3>=2.13.33`, `cloudflare>=5.4.0`. All three ingest modules are **fully mocked** (`client = "mocked_oci_client"` etc., hardcoded fake findings) — real API calls are commented out or never written. They also write to `security_events` (SIEM-alert domain), not `cloud_findings` (the collection `cloud_checks_service.run_checks()` actually reads to evaluate CSPM checks). Building "real check logic" therefore means wiring real API calls into this existing auth/config shape — not introducing a new stack from scratch.

## Recommended Stack — Part (a): Rust crate bump breaking changes

| Crate | From → To | Resolved version (this repo's Cargo.lock) | Breaking changes | Impact on this codebase |
|-------|-----------|---------------------------------------------|-------------------|--------------------------|
| `reqwest` | 0.12 → 0.13 | 0.13.4 | (1) **Default TLS backend flips from native-tls to rustls** when no explicit TLS feature is selected. (2) `RequestBuilder::query()`/`form()` become optional features (need `serde`-gated feature flags if you don't already depend on serde — not an issue here, serde is already a direct dep). (3) `reqwest::RedirectPolicy` moved to `reqwest::redirect::Policy`; `redirect::Attempt::loop_detected`/`too_many_redirect` removed, replaced by a generic error method. (4) Drops `i686-pc-windows-gnu` default-feature support. (5) Most `ClientBuilder` methods renamed (old names soft-deprecated, still compile). | **Verify before shipping, don't just trust the green compile:** `Cargo.toml` declares `reqwest = { version = "0.13", features = ["json", "blocking"] }` with no explicit TLS feature — under 0.12 this defaulted to native-tls (Windows Schannel / system cert store), under 0.13 it now defaults to rustls (bundled webpki/ring roots). This agent runs as a Windows service talking to a backend over TLS; if any target environment relies on a corporate-installed root CA (MITM proxy, internal CA) trusted via the Windows cert store, rustls will NOT pick that up automatically and the agent will start failing TLS handshakes at runtime — `cargo check` cannot catch this, only a live network test can. Either pin `features = ["json", "blocking", "native-tls"]` explicitly to keep prior behavior, or confirm rustls' bundled roots are acceptable for all deployment targets. None of the redirect-policy or ClientBuilder renames are used in `registration.rs`/`heartbeat.rs`/`instructions.rs`/`agent_update.rs` (grep confirms no `RedirectPolicy`/`redirect::Attempt` usage), so those breaking changes are inert here. |
| `sysinfo` | 0.32 → 0.39 | 0.39.6 | (1) `System::refresh_process`, `refresh_process_specifics`, `refresh_pids` **removed**; replaced by `refresh_processes(ProcessesToUpdate)`/`refresh_processes_specifics(...)`. (2) Global CPU snapshot now reports only CPU usage (other fields dropped). (3) `TermalSensorType` renamed to `ThermalSensorType` (typo fix). (4) Process names now `OsString` instead of `String`. (5) Crate split into opt-in features (only enable subsystems you use). | **Zero impact confirmed locally.** `grep -rn "refresh_process\|refresh_pids\|ProcessesToUpdate\|TermalSensorType" src/` returns nothing; the only refresh call in the codebase is `sys.refresh_all()` in `src/lib.rs:79`, which is unaffected. The 16 files under `src/capabilities/` that reference `sysinfo::` (process_monitor, metrics, ebpf_tracing, etc.) compiled clean per `cargo check`. If any of those later call per-process refresh or thermal sensors, re-check against the removed-API list above. |
| `tokio-tungstenite` | 0.23 → 0.30 | 0.30.0 | Runtime error instead of silent failure when a `wss://` URL is used without a TLS feature enabled; buffering behavior changes for `Sink::send()`/`Sink::feed()`; underlying `tungstenite` bumped through 0.25/0.26 in the same window (message-handling API tightening). | Only consumer is `src/capabilities/remote_access.rs`; compiled clean. `Cargo.toml` already specifies `features = ["native-tls"]` explicitly for this crate (unlike reqwest), so the wss-without-TLS-feature error path doesn't apply. |
| `rusqlite` | 0.32 → 0.40 | 0.40.1 (bundled `libsqlite3-sys 0.38.1`) | Breaking changes are concentrated in the **virtual-table (VTab) API**: VTab macros replaced by constructors, `VTab::best_index`/`VTab::connect`/`create` signatures fixed/changed across several point releases. | **Zero impact.** `src/buffer.rs` only uses `rusqlite::{Connection, params}` and `Connection::open()` — no VTab usage anywhere in the codebase. `features = ["bundled"]` is preserved, so the bump also carries a newer vendored SQLite via `libsqlite3-sys`. |
| `hostname` | 0.3 → 0.4 | 0.4.2 | MSRV raised to Rust 1.74+ (declared as a breaking change since the crate treats MSRV bumps as semver-breaking). No API signature changes found for the `get()` function. | Zero impact — `hostname::get()` in `src/heartbeat.rs` is the only call site and is unchanged. Confirm your Rust toolchain is ≥1.74 (edition 2021 + `cargo 1.97.0` present locally, so this is already satisfied). |
| `serde_yaml` → `serde_norway` | 0.9.34+deprecated → 0.9.42 | `serde_yaml` is archived/unmaintained (last release tagged `+deprecated`, no fixes). `serde_norway` is the maintained fork using `unsafe-libyaml-norway`; API is source-compatible for the common `from_str`/`to_string` surface used here. | Already migrated in `src/config.rs` (2 call sites: `load()`, `save()`), plus a doc-comment update. **Do not use `serde_yml`** as an alternative — it was the other popular fork, but per RustSec advisory `RUSTSEC-2025-0068` it is itself now flagged unsound/unmaintained (its final release is a thin compatibility shim over an abandoned codebase). `serde_norway` (the choice already made here) is the currently-recommended maintained fork; `serde-saphyr` and `yaml-rust2` are lower-level alternatives not needed for this simple struct (de)serialization use case. |

**Bottom line for part (a):** no further crate research is needed to make this compile — it already does, verified locally. The one thing worth a deliberate decision before the 2.1.0 exe rebuild ships is the reqwest TLS-backend default flip (native-tls → rustls) — pin the feature explicitly rather than relying on the new default, given Windows deployment.

## Recommended Stack — Part (b): OCI / Alibaba / Cloudflare CSPM posture checks

### Core SDKs

| Technology | Version | Purpose | Why Recommended |
|------------|---------|---------|-----------------|
| `oci` (Oracle's official Python SDK) | `>=2.181.1` (already pinned in `requirements.txt`; latest on PyPI is `2.182.0`) | OCI API client, including `oci.cloud_guard.CloudGuardClient` and `oci.config` | Already a direct dependency; `oci_ingest.py` already imports it behind a try/except availability guard and already has the exact auth config shape (`oci_tenancy_ocid`, `oci_user_ocid`, `oci_private_key`, `oci_fingerprint`, `oci_region` — API-key/PEM-based auth, OCI's standard SDK config dict). Real work is un-mocking `_make_oci_client()` (currently returns the literal string `"mocked_oci_client"`) to construct `oci.cloud_guard.CloudGuardClient(oci_config)` and un-mocking the `list_problems(compartment_id=...)` call that's already sketched in a comment. |
| `cloudflare` (official Cloudflare Python library) | `>=5.4.0` (already pinned; latest on PyPI is `5.5.0`) | Cloudflare API v4 client — zone settings, WAF, SSL/TLS config, DNS | Already a direct dependency; official SDK (supersedes the older community `python-cloudflare`/`pycloudflare` wrappers — do not add those, they're the deprecated predecessors this org's SDK replaced). Sync and async clients both available (built on `httpx`); built-in retry for 429/5xx. `cloudflare_ingest.py` already has the auth shape (`cf_account_id`, `cf_api_token` — scoped API token auth, Cloudflare's recommended auth over legacy Global API Key). |
| `aliyun-python-sdk-core-v3` | `>=2.13.33` (already pinned and already at latest) | Legacy (V1.0) Alibaba Cloud SDK core — `AcsClient` + `CommonRequest`/action-based calls | Already used by `alibaba_ingest.py` for Security Center (SAS) alert polling via AK/SK auth (`access_key_id`, `access_key_secret`, `region_id`). Alibaba has publicly stated V1.0 SDKs are moving to "Basic Security Maintenance" (bugfixes only, no new features) in favor of the V2.0 modular SDKs — see next row. Keep this one only for whatever continues to use `AcsClient`-style generic action calls; don't extend it with new call sites. |
| `alibabacloud_config20200907` | `4.2.3` (new dependency — not yet in `requirements.txt`) | Alibaba Cloud **Config** service SDK (V2.0/Tea-based) — the actual compliance/config-drift API, analogous to AWS Config / Azure Policy | This is the correct SDK for CSPM-style checks (resource compliance state, not alert streams). The V1 `aliyun-python-sdk-core-v3` used by the ingest stub is for Security Center threat alerts, a different domain; reusing it for config-compliance checks would mean hand-building action requests instead of using Alibaba's typed V2 client. Officially recommended replacement path per Alibaba's own SDK repo. |
| `alibabacloud_sas20181203` | `9.3.3` (new dependency) | Alibaba Cloud **Security Center (Threat Detection)** SDK (V2.0) — includes baseline/compliance check APIs (`DescribeSecurityCheckSchedule`, `DescribeCheckWarningSummary`, etc.), not just alerts | Complements `alibabacloud_config20200907`: Security Center's baseline-check module is Alibaba's actual CSPM surface (posture scoring, check pass/fail per resource) and maps most directly to the DO_CHECKS pattern (named checks with pass/fail + severity + remediation). Use this for the posture-check definitions; keep the existing V1 `AcsClient` path in `alibaba_ingest.py` untouched for its current SIEM-alert job. |
| `alibabacloud_tea_openapi` | `0.4.5` (transitive/direct — required by every `alibabacloud_*` V2 service package) | Shared request/config plumbing for the V2.0 SDK family (`Config`, `open_api_client`) | Required peer dependency of any `alibabacloud_<service><version>` package; pull in explicitly since `requirements.txt` doesn't already have it (unlike the V1 core SDK, which is self-contained). |
| `alibabacloud_credentials` | `1.0.10` (transitive/direct) | AK/SK / STS credential provider for the V2.0 SDK family | Same reasoning — required peer dependency for `alibabacloud_config20200907`/`alibabacloud_sas20181203`. Reuse the same `access_key_id`/`access_key_secret`/`region_id` config fields already defined in `alibaba_ingest.py` so both the old ingest path and the new CSPM path share one credential shape per tenant. |

### Relevant security/posture API surface (scoped, not full SDK)

| Provider | Auth mechanism | Rate limit notes | Relevant security-config endpoints/methods |
|----------|-----------------|-------------------|----------------------------------------------|
| OCI | API-signing-key auth: tenancy OCID + user OCID + PEM private key + key fingerprint + region, assembled into an `oci.config` dict (exact shape already defined in `oci_ingest.py`) | OCI Cloud Guard: `Create`/`Update`/`Delete` operations restricted to the reporting region of the tenancy; `Read` operations (list problems, list detector recipes) can run from any region — plan client construction per-region accordingly. No hard published RPS limit surfaced in this research pass; use the SDK's built-in retry/backoff (`oci.retry` module) rather than hand-rolling. | `oci.cloud_guard.CloudGuardClient.list_problems(compartment_id=...)` — posture findings, already stubbed as a comment in `oci_ingest.py`. `list_detector_recipes` / `list_responder_recipes` for check-definition metadata. `oci.cloud_guard.CloudGuardClient` also covers Security Zones (policy-enforced compartments) if broader posture coverage is wanted later. |
| Alibaba Cloud | AK/SK (access_key_id/access_key_secret) or STS token, region-scoped — same shape as existing `alibaba_ingest.py` | Alibaba enforces per-account/per-API QPS throttling (varies by API and account tier); the V2 SDKs surface throttling as typed exceptions — catch and backoff rather than assuming unlimited calls, especially for `DescribeCheckWarningSummary` on large accounts. | `alibabacloud_config20200907`: `GetComplianceSummary`, `ListConfigRules` / `GetConfigRule`, `ListDiscoveredResources` — config-drift / rule-compliance state per resource, the closest analog to AWS Config rules used in `cloud_checks_aws`. `alibabacloud_sas20181203`: `DescribeCheckWarningSummary` (baseline check pass/fail counts), `DescribeSecurityCheckSchedule` (which baseline checks are enabled) — maps directly to a `ALIBABA_CHECKS` list shaped like `DO_CHECKS`. |
| Cloudflare | Scoped API Token (`cf_api_token`) + `cf_account_id`, Bearer-auth — same shape as existing `cloudflare_ingest.py`; prefer scoped tokens over the legacy Global API Key (broader blast radius, being phased out account-wide) | SDK auto-retries 429/408/409/5xx by default; still worth capping check-run concurrency per zone since Cloudflare's plan-tier rate limits apply per token, not per call site. | Zone-level settings resource (`client.zones.settings.get(...)` / list) covers SSL mode (`ssl` — off/flexible/full/strict, the security-relevant setting), TLS 1.3 enablement, "Always Use HTTPS", minimum TLS version, HSTS. WAF managed-rules status is under the zone's firewall/WAF resource. These map cleanly to DO-style checks: "Cloudflare Zone Enforces Full(Strict) SSL", "Cloudflare Zone Minimum TLS 1.2+", "Cloudflare WAF Managed Rules Enabled". |

### What NOT to add

| Avoid | Why | Use Instead |
|-------|-----|--------------|
| `python-cloudflare` / `pycloudflare` (community v1-style wrappers) | Superseded by the official `cloudflare` package already installed; older wrappers target the deprecated v4 REST shape without typed models. | The already-pinned `cloudflare>=5.4.0` official SDK. |
| Extending `aliyun-python-sdk-core-v3`/`AcsClient` with new hand-built `CommonRequest` calls for Config/Security-Center compliance data | It's the legacy V1 SDK (Basic Security Maintenance only per Alibaba); works but means manually constructing action names/params with no typed response models, more error-prone for new code. | The typed V2 packages `alibabacloud_config20200907` / `alibabacloud_sas20181203` for any *new* CSPM call sites; leave the existing `AcsClient` usage in `alibaba_ingest.py` as-is (not broken, just not the pattern to extend). |
| A brand-new `serde_yml` dependency for the Rust YAML migration | It's now itself flagged unsound/unmaintained per RustSec `RUSTSEC-2025-0068` — trading one deprecated dependency for another. | `serde_norway` — already the choice made in this codebase's uncommitted working tree. |
| Rebuilding Jira/ServiceNow ticketing auth for the remediation-ticketing bridge | Out of scope for this milestone's stack — `backend/ticketing_service.py` and `backend/integration_service_ticketing.py` already implement Jira/ServiceNow auth + create-ticket calls; this is a wiring/reuse task (extend `compliance_remediation_service` to call the existing connector), not a new-library task. No new package needed. | Reuse `ticketing_service.py` / `integration_service_ticketing.py` directly. |
| Rebuilding the generic ticketing SLA/escalation logic in `tickets_escalation_service.py` for compliance remediation tasks | Per PROJECT.md's own milestone note, that service is scoped to a different domain (support tickets) and "not reusable as-is" for `compliance_remediation_tasks`'s `due_date`-breach semantics — but that's an architecture/service-boundary decision, not a stack/library decision. No new package needed either way; this is plain Python datetime comparison + the existing WebSocket broadcast pattern (`broadcast_remediation_update`) already in the codebase. | Flag for ARCHITECTURE/phase planning, not a new dependency. |

## Installation

```bash
# Rust — agent-install/omni-agent-rs (already staged uncommitted in Cargo.toml/Cargo.lock;
# nothing further to install, just verify + commit)
cd agent-install/omni-agent-rs
cargo check          # already verified green locally
cargo build --release  # do this before the 2.1.0 exe rebuild step

# Python backend — only the new Alibaba V2 SDK packages are missing from requirements.txt;
# oci, cloudflare, aliyun-python-sdk-core-v3 are already installed
pip install alibabacloud_config20200907==4.2.3 \
            alibabacloud_sas20181203==9.3.3 \
            alibabacloud_tea_openapi==0.4.5 \
            alibabacloud_credentials==1.0.10
```

Add to `backend/requirements.txt` under the existing `# ── Cloud Security Integrations ──` block:

```
alibabacloud_config20200907>=4.2.3    # Alibaba Cloud Config — resource compliance state
alibabacloud_sas20181203>=9.3.3       # Alibaba Security Center — baseline check pass/fail
alibabacloud_tea_openapi>=0.4.5       # Required peer dep for alibabacloud_* V2 SDKs
alibabacloud_credentials>=1.0.10      # Required peer dep for alibabacloud_* V2 SDKs
```

Optionally bump the two SDKs that already have newer patch releases available (not required, current pins work):
```
oci>=2.182.0          # was >=2.181.1
cloudflare>=5.5.0     # was >=5.4.0
```

## Alternatives Considered

| Recommended | Alternative | When to Use Alternative |
|-------------|-------------|---------------------------|
| `serde_norway` for YAML | `noyalib` | If future needs shift to the *exact* `serde_yml`-style API surface (`Value`, `Mapping`) rather than `serde_yaml`'s original API shape — not the case here, `config.rs` only uses `from_str`/`to_string`. |
| `serde_norway` for YAML | `serde-saphyr` | If the config file only ever needs `from_str::<Config>` (read-only, no `to_string` serialization) and a smaller dependency footprint is prioritized — not applicable here since `config.rs::save()` also serializes. |
| `alibabacloud_sas20181203` (V2 typed SDK) for Alibaba posture checks | Keep using `aliyun-python-sdk-core-v3`'s `AcsClient` with `CommonRequest` | If avoiding any new dependency is a hard constraint for this specific phase; the trade-off is manually building/parsing untyped API requests instead of typed client calls. |
| Explicit `native-tls` feature pin for `reqwest` 0.13 | Accept the new rustls default | If all deployment targets are confirmed to need only public-CA-signed certs (no corporate MITM/internal CA reliance) — verify this with whoever owns endpoint deployment before accepting the new default silently. |

## Stack Patterns by Variant

**If the CSPM check-evaluation architecture stays "match against imported `cloud_findings`"** (as `cloud_checks_service.run_checks()` currently does for AWS/Azure/GCP/DO):
- Still need the SDKs above, but as a *findings importer* (new `oci_cspm_ingest`-style function or extending `oci_ingest.py`) that writes to `cloud_findings` instead of `security_events`.
- Use `OCI_CHECKS`/`ALIBABA_CHECKS`/`CLOUDFLARE_CHECKS` static definition lists shaped exactly like `DO_CHECKS` (id/name/description/provider/service/severity/frameworks/remediation).

**If the check-evaluation architecture shifts to live-poll-per-check** (call the cloud API at check-run time rather than matching pre-imported findings):
- Same SDKs, but `run_checks()` itself needs a provider dispatch branch calling `_make_oci_client()`/etc. directly instead of `cloud_findings` lookup — a larger architectural change than the milestone brief implies ("closes real gaps... currently allowlisted but zero check logic" reads as filling in the existing findings-import pattern, not a rearchitecture).

This choice is an architecture/roadmap decision, not a stack decision — flagged here so the roadmap phase that plans this feature makes it explicitly rather than defaulting into whichever a coder picks first.

## Version Compatibility

| Package A | Compatible With | Notes |
|-----------|------------------|-------|
| `reqwest 0.13.4` | `rustls 0.23.42` (per commit `7e050f6`'s lockfile refresh notes) | Confirmed resolvable together in this repo's `Cargo.lock`; both `rustls` and `native-tls` crates end up present in the lock (native-tls pulled transitively via `tokio-tungstenite`'s `native-tls` feature) — no conflict, but confirms reqwest itself is on the rustls path by default. |
| `rusqlite 0.40.1` | `libsqlite3-sys 0.38.1` | Resolved together via the `bundled` feature; no system SQLite dependency needed. |
| `alibabacloud_config20200907 4.2.3` / `alibabacloud_sas20181203 9.3.3` | `alibabacloud_tea_openapi 0.4.5`, `alibabacloud_credentials 1.0.10` | All four should be added together; the service-specific packages depend on the two shared packages at install time. |
| Python 3.12–3.13 (repo's stated recommended range) | `oci 2.182.0`, `cloudflare 5.5.0`, `alibabacloud_*` V2 packages | No known Python-version incompatibilities surfaced in this research pass for any of these packages on 3.12/3.13. |

## Sources

- Local verification (HIGH confidence — direct execution, not third-party claim): `cargo check --offline` and `cargo build --release --offline` run against `agent-install/omni-agent-rs` working tree, 2026-07-20; `Cargo.lock` inspected for resolved versions; `grep` across `src/` for usage of every API named in upstream breaking-change notes.
- [reqwest CHANGELOG.md](https://github.com/seanmonstar/reqwest/blob/master/CHANGELOG.md) — MEDIUM (community/maintainer-authored, cross-checked against 2 independent blog posts on the 0.13 rustls-default change)
- [reqwest v0.13 — rustls by default (seanmonstar.com)](https://seanmonstar.com/blog/reqwest-v013-rustls-default/) — MEDIUM (maintainer's own blog, authoritative for this specific change)
- [sysinfo CHANGELOG.md](https://github.com/GuillaumeGomez/sysinfo/blob/main/CHANGELOG.md) — MEDIUM
- [tokio-tungstenite CHANGELOG.md](https://github.com/snapview/tokio-tungstenite/blob/master/CHANGELOG.md) — MEDIUM (version-0.30-specific entries not directly confirmed in search snippet; general trend across 0.25–0.29 confirmed, treat 0.30-specific notes as LOW standalone but the local `cargo check` pass is the operative confirmation for this codebase)
- [rusqlite Changelog.md](https://github.com/rusqlite/rusqlite/blob/master/Changelog.md) — MEDIUM
- [hostname crate on crates.io/docs.rs](https://docs.rs/hostname/latest/hostname/) — MEDIUM
- [RUSTSEC-2025-0068: serde_yml unsound and unmaintained](https://rustsec.org/advisories/RUSTSEC-2025-0068.html) — HIGH (official RustSec advisory database)
- [rustsec/advisory-db#2132: serde_yaml is unmaintained](https://github.com/rustsec/advisory-db/issues/2132) — HIGH (official advisory tracking issue)
- `pip index versions` run locally against live PyPI, 2026-07-20, for `oci`, `cloudflare`, `alibabacloud_sas20181203`, `alibabacloud_config20200907`, `alibabacloud_tea_openapi`, `alibabacloud_credentials`, `aliyun-python-sdk-core-v3` — HIGH (direct registry query)
- [OCI Cloud Guard Python SDK docs (CloudGuardClient)](https://oracle-cloud-infrastructure-python-sdk.readthedocs.io/en/latest/api/cloud_guard/client/oci.cloud_guard.CloudGuardClient.html) — MEDIUM
- [Cloudflare official Python SDK — GitHub](https://github.com/cloudflare/cloudflare-python) — MEDIUM
- [alibabacloud-python-sdk — GitHub (V2.0 SDK, official)](https://github.com/aliyun/alibabacloud-python-sdk) — MEDIUM
- [aliyun-openapi-python-sdk — GitHub (V1.0 SDK, maintenance-mode notice)](https://github.com/aliyun/aliyun-openapi-python-sdk) — MEDIUM
- Codebase inspection (HIGH — primary source): `backend/requirements.txt`, `backend/oci_ingest.py`, `backend/cloudflare_ingest.py`, `backend/alibaba_ingest.py`, `backend/cloud_checks_service.py`, `backend/cloud_account_endpoints.py`, `.planning/HANDOFF.json`

---
*Stack research for: Enterprise OmniAgent — Security & Compliance Portal, v3.2 milestone*
*Researched: 2026-07-20*
