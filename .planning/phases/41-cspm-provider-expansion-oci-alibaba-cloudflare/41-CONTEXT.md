# Phase 41: CSPM Provider Expansion (OCI, Alibaba, Cloudflare) - Context

**Gathered:** 2026-07-20
**Status:** Ready for planning

<domain>
## Phase Boundary

Replace the dropdown-only OCI, Alibaba, and Cloudflare provider stubs with real CSPM check catalogs wired into the existing `run_checks()` evaluation engine, matching the rigor already applied to AWS/Azure/GCP/DigitalOcean. `RUNNABLE_PROVIDERS` in `cloud_checks_service.py` currently allowlists all three with zero check logic behind them — the gate itself is one stale tuple, not four (per PITFALLS.md, this is the same "duplicated gate" bug class Phase 25/CHK-01 already fixed once).

</domain>

<decisions>
## Implementation Decisions

### Findings collection targeting
- **D-01:** Write real findings to `cloud_findings` only (not dual-write to `security_events`). Matches how AWS/Azure/GCP/DigitalOcean already work — single source of truth, no dual-write complexity or risk of conflicting views between SIEM and CSPM dashboards. The existing `oci_ingest.py`/`cloudflare_ingest.py`/`alibaba_ingest.py` stubs currently write to `security_events` — this phase corrects that target, it doesn't add a second write path.

### Simulated-data fallback
- **D-02:** Match the existing pattern — show labeled `"simulated": true` results when no real import exists for a provider, exactly like AWS/Azure/GCP/DigitalOcean already do. Never present simulated data as real; badge it the same way the existing dashboard does.

### Check catalog scope
- **D-03:** Structure the new check catalogs (~8-10 checks each) around the same categories the existing providers use (storage exposure, IAM policy, encryption, logging) for dashboard consistency, but the actual check *content* within each category follows each provider's own alignment: CIS OCI Foundations for OCI, Alibaba Cloud Config/Security Center baseline for Alibaba, Cloudflare Security Center taxonomy for Cloudflare. Category structure is shared; check specifics are provider-native — these aren't in tension.

### Credential input per provider
- **D-04:** Extend the existing "Connect Cloud Account" form with provider-specific credential fields — OCI (tenancy OCID, user OCID, fingerprint, private key), Alibaba (access key ID + secret, using the V2 typed SDK per STACK.md — not the legacy V1 `AcsClient`), Cloudflare (API token). Verify during planning/research what the existing form/endpoint already supports (`cloud_account_endpoints.py` already allowlists all 3 providers per PITFALLS.md) before assuming new fields are needed from scratch.

### Compliance score integration
- **D-05:** Yes — OCI/Alibaba/Cloudflare check results count toward the tenant's overall compliance score, consistent with every other cloud provider already integrated. Excluding these 3 would be an inconsistent carve-out with no stated reason.

### Claude's Discretion
- Exact field layout/validation for the extended connect-account form (D-04) — verify what the form currently supports before designing new fields.
- Precise mapping of category → provider-native check within each of the ~8-10 checks per provider.

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Milestone research (v3.2)
- `.planning/research/STACK.md` — OCI/Cloudflare SDK versions (live-PyPI-verified), Alibaba V2 typed SDK packages (`alibabacloud_config20200907`, `alibabacloud_sas20181203`, `alibabacloud_tea_openapi`, `alibabacloud_credentials` — NOT the legacy V1 `aliyun-python-sdk-core-v3` client, which is alerts-only)
- `.planning/research/ARCHITECTURE.md` — confirms new `cloud_checks_oci.py`/`cloud_checks_alibaba.py`/`cloud_checks_cloudflare.py` modules + one `RUNNABLE_PROVIDERS` tuple update is the full scope; existing `oci_ingest.py`/`cloudflare_ingest.py`/`alibaba_ingest.py` stubs already define the auth-config shape needed
- `.planning/research/PITFALLS.md` — the provider-allowlist gate is only 1 of up to 4 historically duplicated gates; `cloud_checks_endpoints.py` and `cloud_account_endpoints.py` already list all 3 providers, only `cloud_checks_service.py`'s `RUNNABLE_PROVIDERS` is stale — grep all provider-list literals before assuming which gates need touching

### Codebase maps
- `.planning/codebase/INTEGRATIONS.md` — existing cloud-integration shape (Azure Defender, GCP SCC ingest) as prior-art pattern for the 3 new provider integrations

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `backend/oci_ingest.py`, `backend/cloudflare_ingest.py`, `backend/alibaba_ingest.py` — existing (mocked) ingest stubs with the exact auth-config shape needed; retarget their write destination from `security_events` to `cloud_findings` per D-01.
- `cloud_checks_service.py`'s `DO_CHECKS` — the reference pattern for new provider check-definition modules.
- `run_checks()` — existing evaluation engine; new providers plug into this unchanged.

### Established Patterns
- `RUNNABLE_PROVIDERS` in `cloud_checks_service.py` is the actual execution gate — `cloud_checks_endpoints.py`'s `/run` allowlist and `cloud_account_endpoints.py`'s `_VALID_PROVIDERS` are separate, already-correct allowlists.
- Simulated-data labeling (`"simulated": true`) is set when no findings have been imported for a provider — existing convention to preserve per D-02.

### Integration Points
- `cloud_account_endpoints.py` — where new provider credential fields attach (D-04).
- Compliance score aggregation logic (wherever it reads cloud check results) — needs to pick up the 3 new providers per D-05; locate during research/planning.

</code_context>

<specifics>
## Specific Ideas

- Alibaba: use the V2 typed SDK (`alibabacloud_config20200907` + `alibabacloud_sas20181203`), not the already-installed legacy V1 `aliyun-python-sdk-core-v3` — the V1 client is Security-Center-alerts-only, not the config-compliance surface this phase needs.

</specifics>

<deferred>
## Deferred Ideas

None — discussion stayed within phase scope.

</deferred>

---

*Phase: 41-cspm-provider-expansion-oci-alibaba-cloudflare*
*Context gathered: 2026-07-20*
