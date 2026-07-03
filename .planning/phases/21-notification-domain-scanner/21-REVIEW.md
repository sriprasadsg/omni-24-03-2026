---
phase: 21-notification-domain-scanner
reviewed: 2026-07-04T00:00:00Z
depth: standard
files_reviewed: 6
files_reviewed_list:
  - backend/notification_service.py
  - backend/notification_endpoints.py
  - backend/domain_scanner_service.py
  - backend/domain_scanner_endpoints.py
  - backend/tests/test_notification_service.py
  - components/NotificationsDashboard.tsx
findings:
  critical: 8
  warning: 7
  info: 3
  total: 18
status: issues_found
---

# Phase 21: Code Review Report

**Reviewed:** 2026-07-04T00:00:00Z
**Depth:** standard
**Files Reviewed:** 6
**Status:** issues_found

## Summary

Reviewed against `.planning/phases/21-notification-domain-scanner/21-01-PLAN.md`'s must-haves, with the legacy `NotificationService` class (SMS/patch-management code above `notification_service.py:409`) correctly treated as pre-existing and out of scope. Every finding below was verified by directly executing the code (not just reading it) — via pytest, direct async-function invocation with mocked collections that mimic real pymongo/motor `insert_one` mutation behavior, and `fastapi.encoders.jsonable_encoder`.

The phase-21 code is broken at multiple independent layers, several of which stack on top of each other:

- `notification_endpoints.py` never imports the `notification_service` module it calls on every one of the four new routes (`POST/GET /channels`, `POST/GET /rules`). Every real request to these routes raises `NameError` and 500s — I reproduced this directly, bypassing the also-broken test auth. This is not a hypothetical: the feature is not reachable in any working state today.
- Even if that `NameError` is fixed, `create_channel`/`create_rule` return the same dict object passed to `insert_one()`, which pymongo/motor mutates in place by injecting a raw `ObjectId` under `_id` (confirmed by reading the installed pymongo source and reproducing the crash with `jsonable_encoder`). `POST /channels` and `POST /rules` would still 500 — this is the exact same defect class already found and documented as CR-04 in `16-REVIEW.md` for a sibling phase in this same codebase.
- `create_channel`/`create_rule` build their document as `{"id": ..., "tenantId": tenant_id, "created_at": ..., **data}` — because `**data` is spread *after* the explicit keys in the dict literal, any `id`/`tenantId`/`created_at` key present in the caller-supplied request body silently overrides the server-assigned value. I reproduced this directly: a caller can plant an arbitrary `tenantId` in the POST body and the resulting document is persisted under that tenant, not the caller's own tenant — a cross-tenant data-injection primitive.
- The new `send_notification()` and `create_channel()` code paths perform zero URL validation before storing or POSTing to attacker/tenant-admin-supplied URLs — confirmed by reading the code and comparing against two working validation patterns that already exist in this codebase (`webhook_url_validator.validate_webhook_url`, used by `scheduled_reports_service.py`; and the flawed-but-present `notification_endpoints._validate_webhook_url`, used only by the unrelated pre-existing `/test/{channel}` route). Neither is called anywhere near the new `/channels` or `send_notification` code paths.
- `send_notification()` unconditionally appends `{"status": "sent"}` for every channel after the `try` block, regardless of whether a URL was even configured (guarded by `if url:` with no `else`) or what HTTP status the remote endpoint returned (the `httpx` response is never inspected). Combined with a frontend bug where the channel-creation form always writes `config.url` regardless of the selected channel type (so `webhook`-type channels never get `config.webhook_url` populated), this means the platform will silently report "sent" for alerts that were never delivered — undermining the entire stated purpose of the feature ("GRC teams get alerted... when compliance events occur").
- `backend/tests/test_notification_service.py`: I ran `pytest` directly — 7 of 7 tests fail (0/7 passing), contradicting the plan's must-have. Six fail with `401 Unauthorized` because `_build_client()` overrides a freshly-constructed `rbac_service.has_permission(...)` closure rather than the object baked into the router at import time (same root cause already diagnosed and fixed as `16-REVIEW.md` CR-02). The seventh (`test_domain_scan_returns_structure`) fails with `TypeError: object MagicMock can't be used in 'await' expression` because `_make_db()`'s mocked `insert_one` on `domain_scans`/`scheduled_domains` collections was never made an `AsyncMock`. The suite also silently substitutes two of the plan's seven required tests (`test_send_notification_routes_to_matching_channels`, `test_severity_filter_excludes_low_severity`) with unrelated validation tests — so even if the auth bug were fixed, the single most important piece of new business logic (severity-filtered routing in `send_notification`) would remain completely untested.
- The domain scanner performs real, synchronous, blocking `socket`/`ssl` I/O (DNS resolution for 23 subdomain candidates with no timeout, 5 sequential port connects, one TLS handshake) directly inside `async def scan_domain`, with no `asyncio.to_thread`/executor offload. Because this is the *only* running event loop for the whole (multi-tenant) FastAPI process, a single `GET /api/domain-scanner/scan` call — reachable by any user with the low-privilege `view:dashboard` permission — freezes every other concurrent request on the server for the duration of the scan.
- The same endpoint accepts an arbitrary caller-supplied `domain` (or literal IP) with no restriction on private/loopback/link-local/reserved ranges, then makes the server itself open real TCP connections and TLS handshakes to it and reflects the results (open ports, TLS cert data) back to the caller — an SSRF-as-a-feature that lets any `view:dashboard` user use the platform's server as a network probe against internal infrastructure (including the cloud metadata endpoint `169.254.169.254`).

## Critical Issues

### CR-01: `notification_service` module is never imported — all four new routes raise `NameError` and 500 on every call

**File:** `backend/notification_endpoints.py:268-306` (imports at `1-12`)
**Issue:** `create_notification_channel`, `list_notification_channels`, `create_notification_rule`, and `list_notification_rules` all call `notification_service.create_channel(...)`, `notification_service.list_channels(...)`, `notification_service.create_rule(...)`, `notification_service.list_rules(...)` — but `notification_service` is never imported anywhere in this file (the import block at lines 1-12 has no `import notification_service` / `from notification_service import ...`). I confirmed this is not a lazy/local import by inspecting the module namespace directly, then reproduced the runtime failure by calling the route handler with a mocked `get_database`:
```
File ".../backend/notification_endpoints.py", line 273, in create_notification_channel
    ch = await notification_service.create_channel(db, get_tenant_id(), payload)
               ^^^^^^^^^^^^^^^^^^^^
NameError: name 'notification_service' is not defined
```
This is independent of, and more severe than, the test-suite's auth bug (CR-06 below) — even with correct authentication, every one of these four routes 500s. NOTIF-01 is not shippable as committed.
**Fix:**
```python
# at top of backend/notification_endpoints.py
import notification_service
```

### CR-02: `create_channel`/`create_rule` return a document containing a raw, non-serializable `ObjectId`

**File:** `backend/notification_service.py:427-433, 440-445`
**Issue:** `insert_one(doc)` is called with the same `doc` dict that is then returned directly. Per the installed pymongo source (`Collection.insert_one`), `insert_one` mutates its argument in place, injecting `document["_id"] = ObjectId()` when `_id` is absent. I reproduced this with a fake collection that mimics real motor/pymongo behavior:
```python
doc = await ns.create_channel(FakeDB(), 'tenant-a', {'type': 'slack', 'name': 'x', 'config': {...}})
# doc == {..., '_id': ObjectId('6a483dc2906e66e27b973142')}
jsonable_encoder({'channel': doc})
# TypeError: 'ObjectId' object is not iterable
```
`notification_endpoints.py`'s `create_notification_channel`/`create_notification_rule` return this dict directly with no `_id` stripping and no `response_model`, so FastAPI's `jsonable_encoder` raises and every successful creation 500s — this is the exact same defect already found and fixed as `16-REVIEW.md` CR-04 for a sibling phase in this codebase; it has recurred here.
**Fix:**
```python
async def create_channel(db, tenant_id: str, data: dict) -> dict:
    typ = data.get("type")
    if typ not in VALID_CHANNEL_TYPES:
        raise ValueError(f"type must be one of {VALID_CHANNEL_TYPES}")
    doc = {"id": _id("chan"), "tenantId": tenant_id, "created_at": _now(), **data}
    await db._db.notification_channels.insert_one(doc)
    doc.pop("_id", None)
    return doc
```
Apply the same `doc.pop("_id", None)` fix to `create_rule`.

### CR-03: Caller-supplied `tenantId`/`id`/`created_at` silently override server-assigned values — cross-tenant data injection

**File:** `backend/notification_service.py:431, 443`
**Issue:** `doc = {"id": _id("chan"), "tenantId": tenant_id, "created_at": _now(), **data}` spreads the caller-supplied `data` dict *after* the server-assigned keys in the literal, so any of `id`, `tenantId`, or `created_at` present in the request body wins over the server-generated value (standard Python dict-literal-with-spread semantics). I reproduced this directly:
```python
doc = await ns.create_channel(FakeDB(), 'tenant-a',
    {'type': 'slack', 'name': 'evil', 'tenantId': 'tenant-victim', 'id': 'chan-fixed'})
# {'id': 'chan-fixed', 'tenantId': 'tenant-victim', ...}
```
Any authenticated user holding `manage:settings` in their own tenant can plant a channel or rule document under a *different* tenant's `tenantId` simply by including that key in the JSON body — a straightforward cross-tenant isolation bypass with no additional privileges required. The same pattern applies to `create_rule` (line 443).
**Fix:** Strip caller-controlled identity fields from `data` before merging, or set the authoritative fields *after* the spread:
```python
doc = {**data, "id": _id("chan"), "tenantId": tenant_id, "created_at": _now()}
```

### CR-04: New notification-channel code path has zero SSRF protection

**File:** `backend/notification_service.py:427-433 (create_channel), 452-480 (send_notification)`
**Issue:** `create_channel` persists whatever `config` dict is supplied with no validation of any kind — not even a URL scheme check. `send_notification` then `httpx.AsyncClient().post()`s directly to `ch["config"]["url"]` (slack) / `ch["config"]["webhook_url"]` (webhook) with no validation before the outbound request. This codebase already has two working validation patterns for exactly this problem: `backend/webhook_url_validator.py`'s `validate_webhook_url()` (requires `https://` and DNS-resolves the hostname to reject private/loopback/link-local/reserved/multicast targets, used correctly by `scheduled_reports_service.py` at both save and delivery time), and `notification_endpoints.py`'s own pre-existing `_validate_webhook_url()` (line 15, used by the unrelated `/test/{channel}` route). Neither is called anywhere near `create_channel`, `create_rule`, or `send_notification`. A tenant admin (or anyone with `manage:settings`) can point a channel at `http://169.254.169.254/latest/meta-data/` or any internal service, and every matching compliance event (`finding_created`, `control_failed`, etc.) will trigger a real outbound request to it — a working SSRF primitive triggered by ordinary product usage, not just a misconfiguration. This is a regression of a bug class already found and fixed in this exact codebase (commit `6bcbfff`, "fix(13): WR-06 validate webhook/Slack/Teams URLs... to close SSRF surface").
**Fix:** Validate at both save time and delivery time using the existing shared module:
```python
# notification_service.py
from webhook_url_validator import validate_webhook_url

async def create_channel(db, tenant_id: str, data: dict) -> dict:
    typ = data.get("type")
    if typ not in VALID_CHANNEL_TYPES:
        raise ValueError(f"type must be one of {VALID_CHANNEL_TYPES}")
    if typ in ("slack", "webhook"):
        url = data.get("config", {}).get("url") or data.get("config", {}).get("webhook_url")
        await validate_webhook_url(url)  # raises ValueError on unsafe/invalid URL
    ...
```
and re-validate immediately before each `cl.post(...)` call in `send_notification` (URLs can be edited between save and send, or a save-time check bypassed if it's ever added inconsistently).

### CR-05: `send_notification` reports `"status": "sent"` even when nothing was sent or delivery failed

**File:** `backend/notification_service.py:460-480`
**Issue:** `results.append({"channel_id": ch["id"], "status": "sent"})` (line 475) executes unconditionally after the `if/elif/else` block, regardless of whether the inner `if url:` guard (lines 464, 469) was true. If a channel's `config` is missing the expected key (e.g. a `webhook` channel whose `config` only has `url` instead of `webhook_url` — which is exactly what the current frontend produces, see WR-02), no HTTP request is made at all, yet the channel is still recorded as `"sent"`. Separately, even when a request *is* made, the `httpx` response is never inspected (no status-code check, no `raise_for_status()`) — a 404/500 from the remote Slack/webhook endpoint is still reported as `"sent"` because `httpx` does not raise on non-2xx responses by default. For a compliance-alerting feature whose entire purpose is "GRC teams get alerted... when compliance events occur," this means the system can silently fail to notify anyone while reporting total success.
**Fix:**
```python
if ch["type"] == "slack":
    url = ch.get("config", {}).get("url", "")
    if not url:
        results.append({"channel_id": ch["id"], "status": "failed", "error": "no url configured"})
        continue
    async with httpx.AsyncClient() as cl:
        resp = await cl.post(url, json={...}, timeout=10)
    status = "sent" if resp.status_code < 400 else "failed"
    results.append({"channel_id": ch["id"], "status": status, "http_status": resp.status_code})
    continue
# ... same pattern for webhook; only reach the unconditional append for the email/log branch
```

### CR-06: Test suite is fully broken — 0 of 7 tests pass (must-have violation)

**File:** `backend/tests/test_notification_service.py:23-34, 67-77`
**Issue:** I ran `backend/venv/bin/python -m pytest backend/tests/test_notification_service.py -v` directly: **7 of 7 tests fail**.
- Six fail with `401 Unauthorized`. `_build_client()` (lines 23-34) does `app.dependency_overrides[rbac_service.has_permission("manage:settings")] = lambda: t` — `has_permission(...)` is a factory that returns a brand-new closure on every call, so the override key here is a different object than the one baked into the router at import time. FastAPI matches overrides by exact callable identity, so the override never applies and the real (un-mocked) auth dependency runs, rejecting every request with 401. This is the identical bug already diagnosed and fixed as CR-02 in `.planning/phases/16-program-control-grouping/16-REVIEW.md`.
- The seventh, `test_domain_scan_returns_structure` (lines 67-77), fails with `TypeError: object MagicMock can't be used in 'await' expression` — `_make_db()` only makes `insert_one` an `AsyncMock` for `find`-chain purposes via a plain `MagicMock`; `db._db.domain_scans.insert_one` (called inside `scan_domain`) is never mocked at all and defaults to a synchronous `MagicMock`, which cannot be awaited.
- Additionally, the plan's TDD spec requires `test_send_notification_routes_to_matching_channels` and `test_severity_filter_excludes_low_severity` as tests 3 and 4. The committed suite substitutes `test_invalid_channel_type` and `test_invalid_event_type` instead — so even after the auth/mock bugs are fixed, the single most important piece of new business logic in this phase (severity-filtered routing in `send_notification`) has **zero** test coverage.

This directly contradicts the plan's must-have "All 7 tests in test_notification_service.py pass green." Actual pass rate: 0/7.
**Fix:** Override the stable `get_current_user` singleton (not a freshly-constructed `has_permission(...)` closure), per the established working pattern elsewhere in this codebase:
```python
from authentication_service import get_current_user
app.dependency_overrides[get_current_user] = lambda: t
```
Make every collection method actually used by the code under test an `AsyncMock` (including `insert_one` on `domain_scans`), and replace `test_invalid_channel_type`/`test_invalid_event_type` with the plan-mandated `test_send_notification_routes_to_matching_channels` and `test_severity_filter_excludes_low_severity`, asserting on `send_notification`'s return value (`matched_rules`, `sent`, `results`) with concrete mocked rules/channels.

### CR-07: Domain scan performs synchronous blocking I/O directly inside the async event loop — single-request denial of service

**File:** `backend/domain_scanner_service.py:11-18, 31-45, 48-59, 62-78`
**Issue:** `scan_domain` is `async def`, but everything it calls — `_passive_discover` (up to 23 `socket.getaddrinfo` calls with no explicit timeout, relying on OS defaults which can be tens of seconds each on an unresponsive resolver), `_check_ports` (5 sequential blocking `socket.connect_ex` calls, 2s timeout each), and `_check_tls` (blocking `socket.connect` + TLS handshake, 5s timeout) — are all plain synchronous functions run inline, with no `asyncio.to_thread`/executor offload. This backend runs a single-threaded asyncio event loop shared by all tenants and all requests; any blocking call inside a coroutine stalls that entire loop, not just the calling request. `GET /api/domain-scanner/scan` requires only the low-privilege `view:dashboard` permission, so any authenticated low-privilege user can freeze the entire platform (all tenants, all endpoints) for several seconds to potentially much longer per call, and can repeat this indefinitely with no rate limiting.
**Fix:** Offload all blocking socket/ssl work:
```python
async def scan_domain(db, tenant_id: str, domain: str) -> dict:
    subdomains = await asyncio.to_thread(_passive_discover, domain)
    ports = await asyncio.to_thread(_check_ports, subdomains[0] if subdomains else domain)
    tls = await asyncio.to_thread(_check_tls, domain)
    dns = await asyncio.to_thread(_get_dns, domain)
    ...
```
and add explicit timeouts to every `socket.getaddrinfo` call in `_passive_discover` (e.g. via `socket.setdefaulttimeout` in the worker thread, or a `concurrent.futures` timeout wrapper) so a single unresponsive DNS server cannot hang the scan indefinitely.

### CR-08: Domain scanner performs unrestricted outbound TCP/TLS probes against caller-controlled targets — internal network / cloud metadata probing

**File:** `backend/domain_scanner_service.py:48-59 (_check_ports), 62-78 (_check_tls)`; `backend/domain_scanner_endpoints.py:15-19`
**Issue:** `domain` is only constrained by FastAPI's `Query(..., min_length=1, max_length=253)` — no format/hostname validation, and nothing rejects a literal IP address or a hostname resolving to a private/loopback/link-local/reserved range. `_check_ports(host)` and `_check_tls(domain)` then open real TCP connections and perform a real TLS handshake directly against whatever the caller supplied, and reflect the results (open/closed per port, TLS cert issuer/expiry/SAN) straight back in the API response. Any authenticated user with only `view:dashboard` can pass `domain=169.254.169.254` (or any internal hostname/IP the server's network can reach) and get back a live open-port/TLS fingerprint of internal infrastructure the caller could not otherwise reach directly — the application server acts as an SSRF pivot with structured output, by design of this feature with no allow/deny-list.
**Fix:** Before probing, resolve the domain and reject private/loopback/link-local/reserved/multicast targets, mirroring the pattern already used by `webhook_url_validator.py`:
```python
import socket as _socket
from ipaddress import ip_address

def _is_safe_target(host: str) -> bool:
    try:
        infos = _socket.getaddrinfo(host, None)
    except OSError:
        return False
    for info in infos:
        ip = ip_address(info[4][0])
        if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved or ip.is_multicast:
            return False
    return True
```
and call it in `scan_domain` before invoking `_check_ports`/`_check_tls`, returning a 400/422 for unsafe targets.

## Warnings

### WR-01: Frontend channel form always writes `config.url`, mismatching the backend's per-type config keys

**File:** `components/NotificationsDashboard.tsx:91-96`
**Issue:** The single "URL/Email" input always sets `config: {url: e.target.value}` (line 95), regardless of the `type` selected in the dropdown above it. But `send_notification` (`notification_service.py:463, 468`) reads `config.url` only for `slack` channels and `config.webhook_url` for `webhook` channels; the `email` branch reads `config.email`. Any `webhook` or `email` channel created through this UI will have the wrong config key populated, so `send_notification` will silently find an empty string and (per CR-05) still report `"status": "sent"` — this is a real, reachable end-to-end failure of the feature via the only UI provided for it, not a hypothetical misuse.
**Fix:** Render a type-specific input (or at least write to the correct key based on `chanForm.type`):
```jsx
onChange={e => setChanForm({
  ...chanForm,
  config: chanForm.type === 'webhook' ? { webhook_url: e.target.value }
        : chanForm.type === 'email' ? { email: e.target.value }
        : { url: e.target.value },
})}
```

### WR-02: Frontend reports "success" for channel/rule/schedule creation regardless of actual HTTP outcome

**File:** `components/NotificationsDashboard.tsx:44-56, 68-74`
**Issue:** `submitChannel`, `submitRule`, and `scheduleDomain` all call `.json()` on the response and immediately show a success toast, with no check of `response.ok`/`response.status`. `authFetch` (`services/apiService.ts:198-214`) returns the raw `Response` for any status code and does not throw on 4xx/5xx. Given CR-01/CR-02 currently make `POST /channels` and `POST /rules` 500 with a JSON error body, `.json()` resolves without throwing, the `catch` block never fires, and the user sees "Channel created"/"Rule created" even though nothing was created. This is the same defect pattern already documented as CR-06 in `16-REVIEW.md` for a sibling phase.
**Fix:**
```javascript
const submitChannel = async () => {
  try {
    const res = await authFetch('/api/notifications/channels', { method: 'POST', headers: {'Content-Type':'application/json'}, body: JSON.stringify(chanForm) });
    if (!res.ok) throw new Error(await res.text());
    showToast('Channel created', 'success'); setShowChanForm(false); setChanForm({}); fetchData();
  } catch { showToast('Failed', 'error'); }
};
```
Apply the same pattern to `submitRule` and `scheduleDomain`.

### WR-03: `send_notification` is never invoked by any compliance-event trigger in the codebase

**File:** `backend/notification_service.py:452-480`
**Issue:** Grepping the entire backend for callers of this new module-level `send_notification` finds none outside the test file — no code path for finding creation, control failure, evidence expiry, review-overdue, or cert-expiring events calls it. (There is a separate, unrelated, pre-existing `notification_manager.send_notification` in `backend/notification_manager.py` used by the agent/threat-quarantine subsystem — different function, different purpose, not connected to this feature.) As committed, the phase's stated objective — "lets GRC teams get alerted in Slack/email/webhook when compliance events occur" — is not actually achieved: an admin can configure channels and rules, but no real event will ever trigger a notification until something is wired to call this function.
**Fix:** Either wire `send_notification` into the relevant event-producing code paths (finding creation, control status transitions, evidence expiry job, etc.) as part of this phase, or explicitly document this as deferred follow-up work so it isn't mistaken for a completed capability.

### WR-04: No schema validation on channel/rule request bodies beyond the `type`/`event_type` enum check

**File:** `backend/notification_endpoints.py:268-276, 290-298`; `backend/notification_service.py:427-445`
**Issue:** CLAUDE.md requires "Validate input at system boundaries." Both `create_channel` and `create_rule` accept a raw `dict = Body(...)` with only a single enum check on `type`/`event_type`. `name` is never required to be present or non-empty; `config` is never validated to contain the fields the declared `type` needs; `channel_ids`/`severity_filter` on a rule are never validated to be lists. A caller sending `"channel_ids": "chan-abc"` (a string, not a list) would have it silently accepted and later iterated character-by-character wherever it's consumed (e.g. `{"$in": rule.get("channel_ids", [])}` in `send_notification`), producing confusing, hard-to-debug non-matches instead of a clear 422 at creation time.
**Fix:** Use Pydantic request models, e.g.:
```python
class ChannelCreate(BaseModel):
    type: Literal["slack", "email", "webhook"]
    name: str
    config: dict

class RuleCreate(BaseModel):
    event_type: Literal["finding_created", "control_failed", "evidence_expired", "review_overdue", "cert_expiring"]
    channel_ids: list[str] = []
    severity_filter: list[str] = []
```

### WR-05: Email notification log omits the actual message content, deviating from the plan's spec

**File:** `backend/notification_service.py:473-474`
**Issue:** The plan's must-have states: "Email sending: log to app logger as INFO with formatted message." The implementation logs only the recipient placeholder and event type — `logging.getLogger(__name__).info("[NOTIF EMAIL] To: %s | Event: %s", ch.get("config", {}).get("email", "unknown"), event_type)` — never including `payload.get("message")` or any other content from the triggering event. Since this is the only observable output for email channels (actual SMTP is explicitly deferred per the plan), the log is currently useless for verifying *what* would have been emailed.
**Fix:**
```python
logging.getLogger(__name__).info(
    "[NOTIF EMAIL] To: %s | Event: %s | Message: %s",
    ch.get("config", {}).get("email", "unknown"), event_type, payload.get("message", ""),
)
```

### WR-06: `_validate_webhook_url` in this file only rejects raw IP-literal hosts — no DNS resolution

**File:** `backend/notification_endpoints.py:15-35`
**Issue:** This pre-existing helper (used by the unrelated `/test/{channel}` route, lines 160/173/226) parses the URL's `hostname` and, via `ipaddress.ip_address(hostname)`, rejects private/loopback/link-local/reserved targets — but only when the hostname is already a raw IP literal. Any DNS name (e.g. `localhost`, or an attacker-controlled domain that resolves to `127.0.0.1`/`169.254.169.254`) falls into the `except ValueError: pass  # hostname is a domain name — allow` branch at line 31 and is treated as safe, since this function never calls `socket.getaddrinfo`/DNS resolution the way `webhook_url_validator.validate_webhook_url` does. This is out of scope as a standalone fix for phase 21 (the function predates this phase and is used only by the pre-existing `/test/{channel}` route), but it should not be used as the template for closing CR-04 — use `webhook_url_validator.validate_webhook_url` instead, which resolves DNS correctly.
**Fix:** When addressing CR-04, do not copy this function's pattern; use the DNS-resolving `webhook_url_validator.validate_webhook_url` for both `/channels` and `send_notification`. Separately, consider replacing this function's body with a call to the same shared validator for consistency.

### WR-07: Unused `json` import inside `send_notification`'s email branch

**File:** `backend/notification_service.py:473`
**Issue:** `import json, logging` — `json` is imported but never used in this branch (only `logging` is referenced).
**Fix:** `import logging`

## Info

### IN-01: Unexplained magic-number result caps with no pagination

**File:** `backend/notification_service.py:437, 449, 454, 459`; `backend/domain_scanner_service.py:28`
**Issue:** `to_list(length=100)` / `length=50` / `length=20` are hardcoded with no named constant or comment explaining the choice. A tenant with more channels/rules/scheduled domains than the cap will have results silently truncated with no indication to the caller (same pattern flagged as `16-REVIEW.md` IN-03).
**Fix:** Extract to named constants (e.g. `_MAX_CHANNELS = 100`) or implement real pagination.

### IN-02: Function-local re-imports instead of module-level imports

**File:** `backend/notification_service.py:452 (httpx), 473, 477 (logging)`
**Issue:** `send_notification` imports `httpx` and `logging` inside the function body on every call, inconsistent with the rest of the file (and the codebase convention) of importing at module scope. Not a bug, but adds avoidable per-call overhead and inconsistency.
**Fix:** Move `import httpx` and `import logging` to the top of `notification_service.py`.

### IN-03: Loose `any` typing throughout the dashboard component

**File:** `components/NotificationsDashboard.tsx:11, 13, 15, 17, 20, 22`
**Issue:** `useState<any[]>([])` / `useState<any>({})` are used for channels, rules, scan results, and form state despite this being a TypeScript file with well-defined backend document schemas (see plan's channel/rule schema). No compile-time safety against typos like the `config.url`/`config.webhook_url` mismatch in WR-01.
**Fix:** Define `interface NotificationChannel { id: string; type: 'slack'|'email'|'webhook'; name: string; config: Record<string, string> }` and equivalent `NotificationRule`/`ScanResult` interfaces, and use them in place of `any`.

---

_Reviewed: 2026-07-04T00:00:00Z_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
