---
phase: 21-notification-domain-scanner
reviewed: 2026-07-04T12:00:00Z
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
  critical: 10
  warning: 7
  info: 5
  total: 22
status: issues_found
---

# Phase 21: Code Review Report

**Reviewed:** 2026-07-04T12:00:00Z
**Depth:** standard
**Files Reviewed:** 6
**Status:** issues_found

## Summary

This is a fresh, independent re-review of the current on-disk state of all six files. A `21-REVIEW.md` already existed on disk with 18 findings (8 critical/7 warning/3 info) from an earlier pass; no `REVIEW-FIX.md` exists and no fix commits have landed against these files (`git log` shows the last commit touching every one of them is still the original `feat(phase-16): implement program control grouping` commit). I did not assume the prior findings were stale — I re-verified the load-bearing ones directly (running `pytest`, invoking the route handlers with mocked dependencies, and inspecting the installed `pymongo` source for `insert_one` mutation semantics) and they all still reproduce exactly as before. I also found several additional defects not previously documented, listed below (CR-04, CR-05, CR-06, WR-04, IN-04, IN-05).

Net assessment: this phase is not shippable. The four new "channels"/"rules" routes 500 on every call today (`CR-01`), and even past that immediate blocker there is a second, independent 500 waiting (`CR-02`), a cross-tenant document-injection primitive (`CR-03`), a credential-disclosure endpoint (`CR-04`), a cross-tenant alert-leak in the pre-existing alerting class that this feature shares a collection with (`CR-05`/`CR-06`), an SSRF primitive in the new channel/webhook code (`CR-07`), and a second, more direct SSRF-as-a-feature in the domain scanner that also freezes the whole multi-tenant event loop on every call (`CR-08`/`CR-09`). The test suite that is supposed to catch all of this is 0/7 passing (`CR-10`), so none of it was ever actually exercised.

## Critical Issues

### CR-01: `notification_service` module is never imported — the four new routes raise `NameError` on every call

**File:** `backend/notification_endpoints.py:273, 283, 295, 305` (import block: `1-12`)
**Issue:** `create_notification_channel`, `list_notification_channels`, `create_notification_rule`, and `list_notification_rules` all call `notification_service.create_channel(...)` / `.list_channels(...)` / `.create_rule(...)` / `.list_rules(...)`, but the module `notification_service` is never imported anywhere in this file — not at module scope (lines 1-12) and not locally inside these four handlers (they instead do a redundant local `from database import get_database`, see WR-04). I reproduced the crash directly, bypassing auth entirely, by invoking the handler with a patched `database.get_database`:
```
NameError: name 'notification_service' is not defined
```
Every real request to `POST/GET /api/notifications/channels` and `POST/GET /api/notifications/rules` 500s today. This is not a hypothetical — it's the current, reachable behavior of the shipped code.
**Fix:**
```python
# top of backend/notification_endpoints.py
import notification_service
```

### CR-02: `create_channel`/`create_rule` return a document mutated in place with a raw, non-JSON-serializable `ObjectId`

**File:** `backend/notification_service.py:427-433, 440-445`
**Issue:** `await db._db.notification_channels.insert_one(doc)` is called on the same `doc` dict that is returned immediately after. I confirmed via the installed `pymongo` (`4.17.0`) source for `Collection.insert_one` that it mutates its argument in place:
```python
if not (isinstance(document, RawBSONDocument) or "_id" in document):
    document["_id"] = ObjectId()
```
So even once `CR-01` is fixed, `doc` returned from `create_channel`/`create_rule` will contain a live `bson.ObjectId` under `_id`. `notification_endpoints.py`'s handlers return this dict directly (no `response_model`, no `_id` stripping), so FastAPI's `jsonable_encoder` will raise `TypeError` on the very next successful call — every "successful" channel/rule creation still 500s, just one layer deeper.
**Fix:**
```python
await db._db.notification_channels.insert_one(doc)
doc.pop("_id", None)
return doc
```
Apply the same fix to `create_rule`.

### CR-03: Caller-supplied `id`/`tenantId`/`created_at` silently override server-assigned values — cross-tenant document injection

**File:** `backend/notification_service.py:431, 443`
**Issue:** `doc = {"id": _id("chan"), "tenantId": tenant_id, "created_at": _now(), **data}` spreads caller-supplied `data` *after* the server-assigned keys in the dict literal — standard Python semantics mean any of `id`, `tenantId`, or `created_at` present in the request body silently wins over the server-generated value. Any authenticated user holding `manage:settings` in their own tenant can POST `{"type": "slack", "tenantId": "some-other-tenant", ...}` to `/api/notifications/channels` and have the document persisted under a tenant they do not belong to — a straightforward tenant-isolation bypass requiring no additional privilege. Same pattern in `create_rule` (line 443).
**Fix:** Put the authoritative fields *after* the spread so they cannot be overridden:
```python
doc = {**data, "id": _id("chan"), "tenantId": tenant_id, "created_at": _now()}
```

### CR-04: `GET /api/notifications/channels` returns unredacted secrets to any user with only `view:dashboard`

**File:** `backend/notification_endpoints.py:279-284`; `backend/notification_service.py:436-437`
**Issue:** `list_channels` returns raw `notification_channels` documents (`{"_id": 0}` projection only — no field redaction) and the route requires only `view:dashboard`, a much lower bar than the `manage:settings` permission required to create a channel. A channel's `config` dict routinely holds a Slack incoming-webhook URL (itself a bearer credential — anyone holding it can post to that Slack channel), a generic webhook URL, or a `secret` used as `X-OmniAgent-Secret` (see `notification_endpoints.py:229-230`). This file already implements exactly the right pattern one endpoint away — `get_notification_config` (lines 98-112) explicitly redacts `webhook_url`, `auth_token`, `routing_key`, `account_sid`, `secret` via `_REDACTED_FIELDS` before returning — but `list_channels` was added without the same treatment, so every low-privilege viewer can read every configured channel's raw credentials.
**Fix:** Redact nested `config` secrets before returning, reusing `_REDACTED_FIELDS`:
```python
@router.get("/channels")
async def list_notification_channels(...):
    items = await notification_service.list_channels(db, get_tenant_id())
    for it in items:
        cfg = it.get("config") or {}
        for field in _REDACTED_FIELDS:
            if field in cfg:
                cfg[field] = "***"
    return {"items": items, "count": len(items)}
```

### CR-05: `_send_slack` loads the Slack webhook config with no tenant filter — cross-tenant alert leakage

**File:** `backend/notification_service.py:202`
**Issue:** `config = await self.db.notification_config.find_one({"type": "slack"}, {"_id": 0})` queries by `type` only — no `tenantId` in the filter, unlike every other query touching this collection in the codebase (e.g. `notification_endpoints.get_notification_config`/`update_notification_config` both scope by `tenantId`). `_send_slack` is invoked by `send_alert`, which in turn backs `send_sla_breach_alert`, `send_critical_patch_alert`, and `send_deployment_complete_alert` — all real, currently-wired alerting flows. In a multi-tenant deployment, whichever tenant's Slack config document Mongo returns first for `{"type": "slack"}` becomes the *only* Slack destination for every tenant's SLA-breach, critical-patch, and deployment-complete alerts — leaking one tenant's patch names, CVSS scores, asset counts, and deployment results into a completely different tenant's Slack channel.
**Fix:** Thread `tenant_id` through `NotificationService`/`send_alert`/`_send_slack` and filter by it:
```python
config = await self.db.notification_config.find_one(
    {"type": "slack", "tenantId": tenant_id}, {"_id": 0}
)
```

### CR-06: `send_alert` inserts notification records without `tenantId` — alerts become permanently invisible and unmanageable

**File:** `backend/notification_service.py:74-77`
**Issue:** `send_alert` builds `results` (no `tenantId` key anywhere in it) and does `await self.db.notifications.insert_one({**results, "metadata": metadata})`. But `notification_endpoints.py`'s `get_notifications` (line 46-49), `mark_as_read` (line 57-58), and `delete_notification` (line 91) all filter strictly on `{"tenantId": tenant_id, ...}`. Every alert sent through `send_alert` — i.e. every SLA-breach, critical-patch, and deployment-complete alert — is persisted with no `tenantId` field, so it can never match those filters: it will never appear in `GET /api/notifications`, and `PUT /{id}/read` / `DELETE /{id}` against it will always 404 (`matched_count`/`deleted_count` of 0). The write and read sides of the same collection, in the same review scope, are simply incompatible.
**Fix:** Pass and persist `tenantId` on every inserted notification:
```python
await self.db.notifications.insert_one({
    **results, "tenantId": tenant_id, "metadata": metadata,
})
```
(requires threading `tenant_id` into `send_alert` and its three callers, same as CR-05).

### CR-07: New channel/notification code path has zero SSRF/URL validation before persisting or POSTing

**File:** `backend/notification_service.py:427-433 (create_channel), 452-480 (send_notification)`; `backend/notification_endpoints.py:268-276 (create_notification_channel)`
**Issue:** `create_channel` persists whatever `config` dict is supplied with no validation whatsoever — not even a scheme check. `send_notification` then does `httpx.AsyncClient().post(url, ...)` directly against `ch["config"]["url"]` (slack) or `ch["config"]["webhook_url"]` (webhook) with no check before the outbound request. This file already contains a working SSRF guard, `_validate_webhook_url` (`notification_endpoints.py:15-35`), but it is only wired into the pre-existing `/test/{channel}` route (lines 160, 173, 226) — it is never called from `create_channel`, `create_rule`, or `send_notification`. Any user with `manage:settings` can create a channel pointed at `http://169.254.169.254/latest/meta-data/` (or any internal service), and it will receive a real outbound POST the next time a matching compliance event fires.
**Fix:** Call `_validate_webhook_url` (or a DNS-resolving equivalent) both at save time in `create_channel` and again immediately before each outbound POST in `send_notification` (URLs can be edited after save, or the save-time check bypassed if ever added asymmetrically).

### CR-08: Domain scanner accepts arbitrary caller-controlled hosts/IPs with no restriction — SSRF-as-a-feature

**File:** `backend/domain_scanner_service.py:48-59 (_check_ports), 62-78 (_check_tls)`; `backend/domain_scanner_endpoints.py:15-19`
**Issue:** `domain` is constrained only by FastAPI's `Query(..., min_length=1, max_length=253)` — no hostname-format check, and nothing rejects a literal IP or a name resolving into a private/loopback/link-local/reserved range. `_check_ports`/`_check_tls` then open real TCP connections and perform a real TLS handshake directly against whatever was supplied, and reflect the results (per-port open/closed, TLS issuer/expiry/SAN) back in the API response. `GET /api/domain-scanner/scan` requires only the low-privilege `view:dashboard` permission, so any authenticated user — not just an admin — can pass `domain=169.254.169.254` (cloud metadata) or any internal hostname/IP the server can reach, and get back a structured open-port/TLS fingerprint of infrastructure they could not otherwise reach. This is a live SSRF pivot reachable through ordinary, documented product use of the feature, not a misconfiguration.
**Fix:** Resolve and reject unsafe targets before probing:
```python
from ipaddress import ip_address
def _is_safe_target(host: str) -> bool:
    try:
        infos = socket.getaddrinfo(host, None)
    except OSError:
        return False
    return all(
        not (ip_address(info[4][0]).is_private or ip_address(info[4][0]).is_loopback
             or ip_address(info[4][0]).is_link_local or ip_address(info[4][0]).is_reserved)
        for info in infos
    )
```
and call it in `scan_domain` before `_check_ports`/`_check_tls`, returning 400/422 for unsafe targets.

### CR-09: Domain scan runs synchronous, blocking socket/TLS/DNS I/O directly inside the async event loop — single request freezes the whole platform

**File:** `backend/domain_scanner_service.py:11-18, 31-45, 48-59, 62-78`
**Issue:** `scan_domain` is `async def`, but `_passive_discover` (up to 23 sequential `socket.getaddrinfo` calls with no explicit timeout — subject to whatever the OS resolver default is, which can be tens of seconds per unresponsive lookup), `_check_ports` (5 sequential blocking `connect_ex` calls, 2s timeout each), and `_check_tls` (blocking connect + TLS handshake, 5s timeout) are plain synchronous functions invoked inline with no `asyncio.to_thread`/executor offload — unlike `notification_service._send_email`, elsewhere in this same review scope, which correctly wraps its blocking SMTP call in `asyncio.to_thread`. Because this backend runs a single asyncio event loop shared by every tenant, any blocking call inside a coroutine stalls that loop for everyone. Combined with `CR-08`, any authenticated `view:dashboard` user can repeatedly freeze the entire multi-tenant API for several seconds to potentially much longer per call, with no rate limiting on the endpoint.
**Fix:**
```python
async def scan_domain(db, tenant_id: str, domain: str) -> dict:
    subdomains = await asyncio.to_thread(_passive_discover, domain)
    ports = await asyncio.to_thread(_check_ports, subdomains[0] if subdomains else domain)
    tls = await asyncio.to_thread(_check_tls, domain)
    dns = await asyncio.to_thread(_get_dns, domain)
    ...
```
and add an explicit timeout around each `socket.getaddrinfo` call in `_passive_discover`.

### CR-10: Test suite is fully broken — 0 of 7 tests pass

**File:** `backend/tests/test_notification_service.py:23-34, 67-77`
**Issue:** Running `python3 -m pytest backend/tests/test_notification_service.py -v` today gives **7 failed, 0 passed**. Root causes, both confirmed:
1. `_build_client` (lines 23-34) does `app.dependency_overrides[rbac_service.has_permission("manage:settings")] = lambda: t`. `has_permission(...)` (`rbac_service.py:115-129`) is a factory that returns a brand-new closure on every call, so the object used as the override key is never the same object baked into the router at import time — FastAPI's `dependency_overrides` matches by exact callable identity, so the override never applies. Every authenticated test hits the real (un-mocked) auth dependency chain and gets `401 Unauthorized`. Six of the seven tests fail this way.
2. `test_domain_scan_returns_structure` (line 71) fails with `TypeError: object MagicMock can't be used in 'await' expression`. `_make_db()` (lines 13-20) only wires `insert_one` as an `AsyncMock` for `notification_channels`, `notification_rules`, and `scheduled_domains` — it never touches `domain_scans`, the collection `scan_domain` actually writes to, so `db._db.domain_scans.insert_one(...)` resolves to a synchronous auto-`MagicMock` and cannot be awaited.

Zero of the seven tests exercise anything meaningful about this phase's behavior — they can't get past auth or the mock setup to reach the actual logic (including the CR-01/CR-02/CR-03 bugs above, which real requests would hit).
**Fix:** Override the stable dependency object actually referenced by the router (e.g. re-export a module-level `has_permission_manage_settings = rbac_service.has_permission("manage:settings")` singleton and use that both in the route decorator and in the test override, or override `get_current_user` directly). Make `_make_db()` mock every collection actually touched by code under test, including `domain_scans`.

## Warnings

### WR-01: Frontend declares success without checking HTTP status

**File:** `components/NotificationsDashboard.tsx:44-56, 68-74`
**Issue:** `submitChannel`, `submitRule`, and `scheduleDomain` all call `.json()` on the `authFetch` response and immediately show a success toast, with no check of `response.ok`. `authFetch` (`services/apiService.ts:198-214`) returns the raw `Response` object regardless of status code and does not throw on 4xx/5xx. Given `CR-01`/`CR-02` currently make these endpoints 500 with a valid JSON error body, `.json()` resolves without throwing, the `catch` block never runs, and the user sees "Channel created"/"Rule created" even though nothing was persisted.
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

### WR-02: Frontend channel form always writes `config.url`, mismatching the backend's per-type config keys

**File:** `components/NotificationsDashboard.tsx:95`
**Issue:** The single "URL/Email" input always sets `config: {url: e.target.value}`, regardless of which `type` is selected in the dropdown above it. But `send_notification` (`notification_service.py:463, 468, 474`) reads `config.url` only for `slack` channels, `config.webhook_url` for `webhook` channels, and `config.email` for the email/log branch. Any `webhook` or `email` channel created through this UI ends up with the wrong key populated, so at delivery time the URL/address is always empty — and because of `WR-03` below, this failure is silently swallowed and still reported as "sent".
**Fix:** Write to the correct key based on the selected type:
```jsx
onChange={e => setChanForm({
  ...chanForm,
  config: chanForm.type === 'webhook' ? { webhook_url: e.target.value }
        : chanForm.type === 'email' ? { email: e.target.value }
        : { url: e.target.value },
})}
```

### WR-03: `send_notification` reports `"status": "sent"` unconditionally, regardless of whether a URL existed or the remote call succeeded

**File:** `backend/notification_service.py:462-475`
**Issue:** `results.append({"channel_id": ch["id"], "status": "sent"})` runs unconditionally after the `if/elif/else` block, even when the inner `if url:` guard was false (channel has no usable URL, e.g. due to `WR-02`) and even when the outbound `cl.post(...)` succeeds at the transport level but the remote returns a 4xx/5xx (the `httpx` response is never inspected — no status check, no `raise_for_status()`). The feature's entire purpose is to alert GRC teams when compliance events occur; as written it can silently fail to deliver while reporting universal success.
**Fix:** Inspect the response/URL presence per branch and only append `"sent"` when a request actually succeeded; append `"failed"` with a reason otherwise (see code sketch in the corresponding section of prior review history for this file).

### WR-04: Four new endpoints locally re-import `get_database`, bypassing the module-level import and the file's established test-mocking pattern

**File:** `backend/notification_endpoints.py:270-271, 281-282, 293-294, 303-304`
**Issue:** `create_notification_channel`, `list_notification_channels`, `create_notification_rule`, and `list_notification_rules` each do `from database import get_database` *inside the function body*, then call it locally — unlike every other handler in this file (e.g. `get_notifications`, `mark_as_read`) which uses the module-level `get_database` imported at line 4. This is inconsistent with the rest of the file, and it directly defeats `test_notification_service.py`'s mocking strategy: `patch(f"{module_name}.get_database", return_value=mock_db)` patches the name bound in `notification_endpoints`'s module namespace, but these four handlers re-resolve `get_database` fresh from the `database` module inside the function body, so the patch never takes effect for them even when other bugs (CR-10) are fixed.
**Fix:** Remove the local imports and use the module-level `get_database` already imported at the top of the file, consistent with the rest of the router.

### WR-05: `_check_ports`/`_check_tls` leak the socket file descriptor when an exception occurs before `close()`

**File:** `backend/domain_scanner_service.py:48-59, 62-78`
**Issue:** In both functions, `s = socket.socket(...)` is created, then several operations that can raise (`connect_ex`, `connect`, `wrap_socket`) run before the corresponding `s.close()` on the following line. If any of them raises (caught by the surrounding `except OSError`/`except Exception`), execution jumps past `s.close()` and the socket is never closed, leaking a file descriptor per failed attempt.
**Fix:** Use `with socket.socket(...) as s:` or wrap in `try/finally` so the socket is always closed regardless of outcome.

### WR-06: Rule `channel_ids` parsed via naive `split(',')` with no trimming

**File:** `components/NotificationsDashboard.tsx:112`
**Issue:** `onChange={e => setRuleForm({...ruleForm, channel_ids: e.target.value.split(',')})}` — a common input like `"chan-abc, chan-def"` produces `["chan-abc", " chan-def"]`. The leading space on the second entry will never match a real channel `id` in `notification_service.send_notification`'s `{"id": {"$in": rule.get("channel_ids", [])}}` query, so the rule silently fails to route to that channel with no error surfaced anywhere.
**Fix:** `channel_ids: e.target.value.split(',').map(s => s.trim()).filter(Boolean)`

### WR-07: No request-body schema validation for channel/rule creation beyond a single enum check

**File:** `backend/notification_endpoints.py:268-276, 290-298`; `backend/notification_service.py:427-445`
**Issue:** CLAUDE.md requires validating input at system boundaries. Both endpoints accept a raw `dict = Body(...)` and only validate `type`/`event_type` against an enum — `name` is never required, `config`'s shape is never checked against what the declared `type` needs, and `channel_ids`/`severity_filter` are never validated to be lists (a caller sending `"channel_ids": "chan-abc"` as a bare string would be accepted and later iterated character-by-character wherever consumed).
**Fix:** Introduce Pydantic request models (`ChannelCreate`, `RuleCreate`) with `Literal` type/event_type fields and typed `config`/`channel_ids`/`severity_filter`.

## Info

### IN-01: Hardcoded `to_list(length=...)` caps with no pagination

**File:** `backend/notification_service.py:437, 449, 454, 459`; `backend/domain_scanner_service.py:28`
**Issue:** `length=100` / `50` / `20` are magic numbers with no named constant, and results are silently truncated past the cap with no indication to the caller.
**Fix:** Extract to named constants or implement real pagination/cursor support.

### IN-02: Redundant duplicate imports

**File:** `backend/notification_service.py:91 (asyncio), 151 (aiohttp), 416-417 (uuid, datetime, timezone), 473 (json, unused)`
**Issue:** `asyncio`, `aiohttp`, `datetime`, and `timezone` are already imported at module scope (lines 6-9) and are re-imported locally inside `_send_email`/`_send_sms` and again at the bottom of the module before the channel/rule helper section. `send_notification`'s email branch does `import json, logging` but never references `json`.
**Fix:** Remove the redundant local/duplicate imports; drop the unused `json` import.

### IN-03: Loose `any` typing throughout the dashboard component

**File:** `components/NotificationsDashboard.tsx:11, 13, 15, 17, 20, 22`
**Issue:** `useState<any[]>([])` / `useState<any>({})` are used for channels, rules, scan results, and both form objects, in a TypeScript file, with no compile-time protection against exactly the kind of key-name mismatch documented in `WR-02`.
**Fix:** Define `NotificationChannel`, `NotificationRule`, and `ScanResult` interfaces matching the backend document shapes and use them in place of `any`.

### IN-04: UI event-type dropdown exposes only 3 of the 5 backend-supported event types; tenant-isolation test doesn't test isolation

**File:** `components/NotificationsDashboard.tsx:109-111`; `backend/tests/test_notification_service.py:86-90`
**Issue:** The rule form's `<select>` only offers `finding_created`, `control_failed`, `evidence_expired`, while `VALID_EVENTS` in `notification_service.py` also supports `review_overdue` and `cert_expiring` — those two event types can never be selected through the UI. Separately, `test_tenant_isolation_channels` only asserts a single tenant's request returns `200`; it never creates data under a second tenant and verifies it is excluded, so it does not actually verify tenant isolation despite its name.
**Fix:** Add the two missing `<option>`s to the dropdown; rewrite the isolation test to seed a channel under `tenant-b` and assert a `tenant-a` client's `GET /channels` does not include it.

### IN-05: Unit test performs live network I/O against a real external host

**File:** `backend/tests/test_notification_service.py:67-77`
**Issue:** `test_domain_scan_returns_structure` calls `svc.scan_domain(db, "tenant-a", "example.com")` directly, which performs real DNS resolution (up to 23 lookups), real TCP connects, and a real TLS handshake against `example.com` over the network. This makes the test slow, non-hermetic, and dependent on outbound network access being available in the CI/sandbox environment (which, combined with `CR-09`'s lack of timeouts on `_passive_discover`, risks the test itself hanging).
**Fix:** Monkeypatch `_passive_discover`/`_check_ports`/`_check_tls`/`_get_dns` to return canned data for this test, and add a separate, explicitly-marked integration test (skipped by default) for real network behavior if needed.

---

_Reviewed: 2026-07-04T12:00:00Z_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
