export const meta = {
  name: 'execute-phase-32-combined',
  description: 'Execute Phase 32 combined plans for cloud and SaaS provider expansion.',
  phases: [
    { title: 'Discover and Route Plans', detail: 'Identify remaining plans and route to appropriate agents.' },
    { title: 'Execute Plan 32-02', detail: 'Execute M365 + MongoDB Atlas catalogs and gate widening.' },
    { title: 'Execute Plan 32-01', detail: 'Execute OCI/Alibaba/Cloudflare ingest modules.' },
    { title: 'Verify Phase 32', detail: 'Verify all Phase 32 tasks completed successfully.' },
  ],
};

phase('Discover and Route Plans');
log('Discovering remaining Phase 32 plans...');

// Check which plans haven't been executed
const executedPlans = [
  '32-04-PLAN', // Already executed (Attack Path Dashboard - seems unrelated to cloud provider expansion)
];

const planFiles = [
  '/home/user/enterprise-omni-agent-ai-platform/.planning/phases/32-cloud-and-saas-provider-expansion/32-02-PLAN.md',
  '/home/user/enterprise-omni-agent-ai-platform/.planning/phases/32-cloud-and-saas-provider-expansion/32-01-PLAN.md',
];

log(`Will execute ${planFiles.length} remaining plans: ${planFiles.map(f => f.split('/').pop()).join(', ')}`);

phase('Execute Plan 32-02');
log('Executing Phase 32-02 (M365 + MongoDB Atlas catalogs and gate widening)...');
const plan32_02Result = await agent(`Execute Phase 32-02 Plan from ${planFiles[0]}`, {
  agentType: 'gsd-executor',
  isolation: 'worktree',
  prompt: `Load the full Phase 32-02 plan from the absolute path and execute all tasks:

TASK 1: Create cloud_checks_m365.py and cloud_checks_mongodb_atlas.py catalog modules with proper M365 and MongoDB Atlas check definitions, then in cloud_checks_service.py import both catalogs, append to CLOUD_CHECKS, and add "microsoft365" and "mongodb_atlas" to RUNNABLE_PROVIDERS.

TASK 2: Widen the four CSPM provider gates in cloud_account_endpoints.py (_VALID_PROVIDERS), cloud_checks_endpoints.py (provider tuple), mcp_server_endpoints.py (two provider lists), and cloud_checks_service.py (RUNNABLE_PROVIDERS) to include "microsoft365" and "mongodb_atlas". Also add "oci", "alibaba", and "cloudflare" to the three registration/validation gates (_VALID_PROVIDERS, cloud_checks_endpoints.py tuple, mcp_server_endpoints.py tuples) per PROV-01's lockstep fix.

TASK 3: Add the additive simulated provenance flag in run_checks() after fetching findings_raw, computing `has_real_findings = len(findings_raw) > 0` and adding `"simulated": not has_real_findings` to the per-check doc dict that gets upserted into cloud_check_results. This is purely additive - do NOT alter existing PASS/FAIL logic.

TASK 4: Extend test_cloud_checks_expansion.py with:
- test_run_checks_evaluates_microsoft365 and test_run_checks_evaluates_mongodb_atlas
- extended test_coverage_denominator_includes_new_providers
- gate-parity assertions for all four gates
- provenance and no-regression tests for simulated flag

All tests should use mocked SDK clients so no real SDK install is required.

When finished, return: status, list of modified files, commit hashes, commit messages, any deviations, and the actual files modified.

Plan file path: ${planFiles[0]} --- CAVEMAN Terse: no filler, no articles, just facts.`
});

phase('Execute Plan 32-01');
log('Executing Phase 32-01 (OCI/Alibaba/Cloudflare ingest modules)...');
const plan32_01Result = await agent(`Execute Phase 32-01 Plan from ${planFiles[1]}`, {
  agentType: 'gsd-executor',
  isolation: 'worktree',
  prompt: `Load the full Phase 32-01 plan from the absolute path and execute all tasks:

TASK 1: Package legitimacy checkpoint - human approve oci, aliyun-python-sdk-core-v3, and cloudflare packages as legitimate PyPI packages before adding to requirements.txt.

TASK 2: Create three real-poll ingest modules (oci_ingest.py, alibaba_ingest.py, cloudflare_ingest.py) cloning azure_defender_ingest.py's shape exactly with:
- ImportError guards for SDK availability
- Required field gates before API calls
- try/except-return-0 bodies that never raise
- severity mapping to Critical/High/Medium/Low
- _parse_<provider>_alert() helpers returning security_events shape
- async poll_ functions that ingest mocked results into security_events collection

TASK 3: Wire both dispatch blocks in cloud_integrations_endpoints.py:
- test_integration() dispatch ladder with three new elif branches for "oci_cloud_guard", "alibaba_sas", and "cloudflare_zero_trust"
- trigger_cloud_discovery() dispatch block with the same three provider branches
- Add oci_private_key, access_key_secret, and cf_api_token to BOTH _SECRET_FIELDS and _mask_secrets()'s inline secret_keys set

TASK 4: Create backend/tests/test_cloud_integrations.py with:
- Clone _col/_db/_user/_app helper block from test_automation_and_baa.py
- Module-level tests calling poll_* functions directly (SDK availability patched True, client mocked)
- Endpoint tests using TestClient harness for POST /{id}/test and list_integrations() masking validation
- Tests for missing-fields paths and exception handling (return 0, never raise)

All tasks should use the existing azure_defender_ingest.py / azure_defender_ingest.py patterns.

When finished, return: status, list of modified files, commit hashes, commit messages, any deviations, and the actual files modified.

Plan file path: ${planFiles[1]}`
});

phase('Verify Phase 32');
log('Verifying all Phase 32 tasks completed...');

const allCompleted = plan32_02Result?.status === 'completed' && plan32_01Result?.status === 'completed';

if (allCompleted) {
  log('Phase 32 execution completed successfully.');
  return { status: 'completed', message: 'Phase 32 with all cloud provider expansion tasks (32-01, 32-02) completed successfully.' };
} else {
  log('Phase 32 execution failed.');
  return { status: 'failed', message: 'Phase 32 execution failed.' };
}
