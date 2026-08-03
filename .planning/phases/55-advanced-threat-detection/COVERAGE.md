# Phase 55 — API Coverage Declaration

**Detector result:** `detected: true` (signal: `wrap webhook`).

## No external API integration: reasoned false-positive

The api-coverage detector fired on the word "webhook" in RESEARCH.md
("every new call site MUST wrap `trigger_webhook(...)`"). This is **not** an
integration of a new external API, SDK, or third-party service:

- COMM-01 (D-03) is **outbound-only** and reuses the platform's **own existing**
  `webhook_service.WebhookService.trigger_webhook()` unchanged — the same
  internal component Phases 21/33 already ship. No new external service is
  onboarded, no new SDK/client is added, no new credentials are introduced.
- The HTTP destination is an **operator-configured** SIEM/syslog URL supplied
  via the existing `POST /api/webhooks` contract (`events: []` subscription);
  the platform is the caller, and the URL is already validated by the existing
  `_is_safe_webhook_url` SSRF blocklist and signed with the existing per-webhook
  HMAC-SHA256. There is no external-API surface for this phase to "cover."
- RESEARCH.md `## Package Legitimacy Audit` confirms **zero** new third-party
  packages this phase; `httpx` is already in use.

No capability coverage matrix is applicable. This phase adds new **event_type**
strings and new **call sites** to existing internal infrastructure — not a new
external API dependency.

---

## VirusTotal API v3 integration (gap-closure 55-05, INT-04)

**Scope:** The 55-05 gap-closure plan implements the missing
`backend/virustotal_client.py` `get_virustotal_client()` factory + client
(the whole `threat_intel_endpoints.py` module fails to import without it, so
`POST /api/threat-intel/correlate-native` never mounts). This IS a genuine new
external-API integration (real outbound VirusTotal API v3 calls, `x-apikey`
from the `VIRUSTOTAL_API_KEY` env var) — distinct from the outbound-webhook
false-positive above — so it needs its own coverage decision.

**Baseline required by existing callers** (`threat_endpoints.py`,
`threat_intel_endpoints.py`, `soar_engine.py`, `agent_security_endpoints.py`):
synchronous reputation lookups only — `scan_ip`, `scan_domain`, `scan_url`,
`scan_file_hash`, and a bulk `enrich_file_hashes`.

| capability | decision | reason |
|---|---|---|
| IP reputation lookup (`scan_ip`, `GET /ip_addresses/{ip}`) | `INTEGRATE` | required by `threat_endpoints`/`soar_engine`/`threat_intel_endpoints` |
| Domain reputation lookup (`scan_domain`, `GET /domains/{d}`) | `INTEGRATE` | required by `threat_endpoints`/`threat_intel_endpoints` |
| URL reputation lookup (`scan_url`, `GET /urls/{id}`) | `INTEGRATE` | required by `threat_endpoints`/`threat_intel_endpoints` |
| File-hash reputation lookup (`scan_file_hash`, `GET /files/{hash}`) | `INTEGRATE` | required by `threat_intel_endpoints /scan` + `enrich_file_hashes` |
| Bulk file-hash enrichment (`enrich_file_hashes`, N× hash lookups) | `INTEGRATE` | required by `agent_security_endpoints` FIM/YARA enrichment |
| URL submission for fresh scan (`POST /urls`) | `OPT-OUT` | this phase does reputation lookup over existing analysis only; no live re-submission — absent analysis returns an `Unknown` verdict, never a fabricated one |
| File upload for detonation (`POST /files`) | `OPT-OUT` | platform never uploads artifact bodies to VT (privacy; agent hashes locally) — hash-lookup only |
| Behavioural/sandbox reports (`/files/{id}/behaviours`) | `OPT-OUT` | no sandbox-detonation consumer in the correlation/enrichment paths this phase serves |
| Comments / votes (`/comments`, `/votes`) | `OPT-OUT` | community metadata is not consumed by any caller |
| Relationship/graph pivots (`/{id}/relationships`) | `OPT-OUT` | pivot-graph exploration is not a correlation-engine input this phase |
| Livehunt / Retrohunt / IoC feeds | `OPT-OUT` | premium streaming feeds; INT-04 correlation consumes native v3.4 findings, not VT feeds |

**API-key-absent behavior (decided):** graceful degradation. When
`VIRUSTOTAL_API_KEY` is unset, the client constructs fine (no import/startup
hard-fail) and every lookup returns `{"error": "VirusTotal API key not
configured"}` — it MUST NOT fabricate a `Harmless`/`Clean` verdict. This is
what lets all four caller files and the new tests run in a keyless test/CI
environment while keeping a missing key an honest, visible failure at call
time (existing callers already branch on `"error" in result`).
