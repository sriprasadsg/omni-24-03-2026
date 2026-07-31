---
status: complete
phase: 41-cspm-provider-expansion-oci-alibaba-cloudflare
source: [41-01-SUMMARY.md, 41-02-SUMMARY.md, 41-03-SUMMARY.md, 41-04-SUMMARY.md, 41-05-SUMMARY.md]
started: 2026-07-21T07:07:51.000Z
updated: 2026-07-21T07:40:00.000Z
---

## Current Test

[testing complete]

## Tests

### 1. Add OCI Cloud Account (credential round-trip)
expected: In the Cloud Accounts dashboard, click "Add Account", pick OCI as the provider, fill tenancy OCID / user OCID / fingerprint / private key, save. Account appears in the list. In Mongo, the new cloud_accounts doc has a non-empty encrypted credentials_ref (not silently discarded).
result: issue (found + fixed during verification)
reported: "Verified via live API call (POST /api/cloud-accounts) reproducing the exact payload AddCloudAccountModal.tsx sends. Bug found: the OCI credential form only collected 4 of the 6 fields poll_oci_cspm_findings requires (CLOUD_FINDINGS_REQUIRED_OCI_FIELDS in oci_ingest.py also needs oci_region and oci_compartment_id). Every OCI scan would silently stay simulated forever regardless of valid credentials — the missing-config guard would always short-circuit before the real SDK call. Fixed by adding oci_region and oci_compartment_id fields to AddCloudAccountModal.tsx (state, inputs, buildCredentials()). Re-verified live: account creation stores a non-empty encrypted credentials_ref (548 chars), and a subsequent scan now reaches the real oci.cloud_guard.CloudGuardClient auth path (confirmed via server log — fails only on the placeholder private key format, which is correct fail-closed behavior, not a missing-config short-circuit)."
severity: major

### 2. Add Alibaba Cloud Account (credential round-trip)
expected: Same flow with Alibaba selected — access key id / access key secret / region id fields shown, saved, account appears with a non-empty credentials_ref.
result: pass
reported: "Verified live via API: account created with all 3 fields, credentials_ref stored encrypted. Field names match _ALIBABA_V2_REQUIRED_FIELDS exactly — no gap."

### 3. Add Cloudflare Cloud Account (credential round-trip)
expected: Same flow with Cloudflare selected — API token / account id fields shown, saved, account appears with a non-empty credentials_ref.
result: pass
reported: "Verified live via API: account created, credentials_ref stored encrypted. cf_account_id correctly falls back to satisfy the zone_id requirement per cloudflare_ingest.py's fallback logic."

### 4. Trigger OCI Posture Scan
expected: From the connected OCI account, trigger a posture scan. Cloud Checks dashboard shows results from real CIS OCI Foundations-aligned checks (iam/storage/encryption/logging categories), not the old dropdown-only stub.
result: pass
reported: "Live scan triggered 10 real check evaluations (oci-iam-001..004, oci-storage-*, etc.) via /api/cloud-accounts/{id}/scan, results retrievable via the exact /api/cloud-checks/results endpoint the dashboard calls. Real-checks pipeline confirmed end-to-end (catalog -> run_checks -> real SDK call attempt). Genuine non-simulated data requires a live Oracle Cloud tenant, which this sandbox does not have access to — that portion remains an inherent live-account gate, unchanged from 41-VALIDATION.md's own manual-only framing, and is not a code defect."

### 5. Trigger Alibaba Posture Scan
expected: From the connected Alibaba account, trigger a posture scan. Cloud Checks dashboard shows results from real checks via the Config/Security Center V2 API.
result: pass
reported: "Live scan triggered 9 check evaluations. Server log confirms a real outbound HTTPS call to Alibaba's actual SAS endpoint (cn-shanghai.aliyuncs.com), returning InvalidAccessKeyId.NotFound for the placeholder key — proves the V2 typed SDK path is live, not a stub. Same live-account caveat as Test 4 applies to obtaining genuinely-passing findings."

### 6. Trigger Cloudflare Posture Scan
expected: From the connected Cloudflare account, trigger a posture scan. Cloud Checks dashboard shows results from real checks aligned to Cloudflare's Security Center taxonomy (SSL mode, min TLS version, WAF toggle).
result: pass
reported: "Live scan triggered 10 check evaluations. Server log confirms a real outbound HTTPS call to api.cloudflare.com/client/v4/zones/.../settings/ssl, returning a 404 for the placeholder zone — proves the real Cloudflare SDK path is live. Same live-account caveat as Test 4 applies."

### 7. SIMULATED Badge on Fresh Account
expected: For an account with zero imported findings, results in the Cloud Checks dashboard show a visible SIMULATED badge wherever result.simulated is true — never presented as real data.
result: pass
reported: "Confirmed simulated:true on all results for all 3 fresh test accounts (OCI/Alibaba/Cloudflare, 29 results total) via the exact /api/cloud-checks/results endpoint the dashboard fetches. Confirmed CloudChecksScanner.tsx renders the SIMULATED badge conditionally on r.simulated (line 224) and that CheckResult's simulated field is never stripped between API and render. Never presented as real."

## Summary

total: 7
passed: 6
issues: 1 (found and fixed during this session — not left open)
pending: 0
skipped: 0

## Gaps

- truth: "A tenant with a connected OCI account can trigger a posture scan and see results from real CIS OCI Foundations-aligned checks"
  status: fixed
  reason: "AddCloudAccountModal.tsx's OCI credential fieldset omitted oci_region and oci_compartment_id, both required by oci_ingest.py's CLOUD_FINDINGS_REQUIRED_OCI_FIELDS — every OCI scan would silently stay simulated=true forever, even with fully valid OCI credentials, since the missing-config guard in poll_oci_cspm_findings would always short-circuit before attempting the real API call."
  severity: major
  test: 1
  artifacts: [components/AddCloudAccountModal.tsx]
  missing: [oci_region field, oci_compartment_id field]
  fix: "Added ociRegion/ociCompartmentId state, corresponding input fields (Region, Compartment OCID), and included both keys in buildCredentials(). Re-verified live: scan now reaches the real oci.cloud_guard.CloudGuardClient construction/auth path instead of short-circuiting on missing config."
