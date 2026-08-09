# Phase 41: CSPM Provider Expansion (OCI, Alibaba, Cloudflare) - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-07-20
**Phase:** 41-cspm-provider-expansion-oci-alibaba-cloudflare
**Areas discussed:** Findings collection targeting, Simulated-data fallback, Check catalog scope, Credential input per provider, Compliance score integration

---

## Findings collection targeting

| Option | Description | Selected |
|--------|-------------|----------|
| cloud_findings only | CSPM checks read this collection; matches existing provider pattern. | ✓ (Claude's choice) |
| Dual-write to both | Also write to security_events for SIEM visibility. | |
| You decide | | ✓ |

**User's choice:** You decide → Claude chose cloud_findings only (Recommended)
**Notes:** Single source of truth, avoids dual-write complexity.

---

## Simulated-data fallback

| Option | Description | Selected |
|--------|-------------|----------|
| Match existing pattern | Show labeled simulated results when no real import exists. | ✓ (Claude's choice) |
| No simulated fallback | Require real connected account before showing any results. | |
| You decide | | ✓ |

**User's choice:** You decide → Claude chose match existing pattern (Recommended)
**Notes:** Consistency with AWS/Azure/GCP/DigitalOcean.

---

## Check catalog scope

| Option | Description | Selected |
|--------|-------------|----------|
| Mirror existing categories | Same categories (storage/IAM/encryption/logging) per provider. | ✓ (Claude's choice) |
| Provider-native CIS alignment only | Follow each provider's own benchmark structure. | |
| You decide | | ✓ |

**User's choice:** You decide → Claude chose a blend: shared category structure, provider-native check content within each category.
**Notes:** Not actually in tension — category labels for dashboard consistency, check specifics per-provider for accuracy.

---

## Credential input per provider

| Option | Description | Selected |
|--------|-------------|----------|
| Extend the connect form | Add provider-specific credential fields to existing flow. | ✓ |
| Generic JSON credential blob | One flexible field for all providers. | |
| You decide | | |

**User's choice:** Extend the connect form (Recommended)
**Notes:** Verify what the existing form/endpoint already supports before assuming new fields needed from scratch.

---

## Compliance score integration

| Option | Description | Selected |
|--------|-------------|----------|
| Yes, count toward score | Consistent with all other cloud providers. | ✓ (Claude's choice) |
| No, CSPM dashboard only | Keep siloed until proven reliable. | |
| You decide | | ✓ |

**User's choice:** You decide → Claude chose yes, count toward score (Recommended)
**Notes:** Excluding these 3 would be an inconsistent carve-out.

## Claude's Discretion

- Findings collection targeting (D-01)
- Simulated-data fallback behavior (D-02)
- Compliance score integration (D-05)
- Exact connect-account form field layout/validation
- Precise category → provider-native check mapping

## Deferred Ideas

None — discussion stayed within phase scope.
