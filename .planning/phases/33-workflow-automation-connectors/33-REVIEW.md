---
phase: 33-workflow-automation-connectors
reviewed: 2026-07-27T00:00:00Z
depth: standard
files_reviewed: 4
files_reviewed_list:
  - backend/api_key_auth.py
  - backend/tenant_endpoints.py
  - backend/webhook_endpoints.py
  - backend/webhook_service.py
findings:
  critical: 2
  warning: 1
  info: 1
  total: 4
status: issues_found
---

# Phase 33: Code Review Report

**Reviewed:** 2026-07-27
**Depth:** standard
**Files Reviewed:** 4
**Status:** issues_found

## Summary

API-key auth path (SHA-256 hash-at-rest lookup, revoked check, tenant scoping) and outbound HMAC signing are correctly done — the signing signs the exact `content=` bytes, so receiver verification will match. However, the SSRF protection has two real bypasses: the delivery-time guard does not resolve hostnames, and the update endpoint does not re-validate the URL at all.

## Critical Issues

### CR-01: SSRF — delivery-time URL guard never resolves hostnames

**File:** `backend/webhook_service.py:29-52`
**Issue:** In the actual delivery path (`trigger_webhook` → `_send_single_webhook` → `_is_safe_webhook_url`), only **IP-literal** hosts are checked against `_BLOCKED_NETWORKS`. For a hostname, `ipaddress.ip_address(host)` raises `ValueError` and the code `pass`es and returns `True` — the comment says "DNS resolution happens at request time" but no resolution is performed. A hostname that resolves to `169.254.169.254` (cloud metadata) or an internal address is delivered to. Combined with DNS rebinding after the creation-time check, this is a live SSRF to internal services.
**Fix:** Resolve the hostname and validate every returned address at delivery time:
```python
for info in socket.getaddrinfo(host, None):
    addr = ipaddress.ip_address(info[4][0])
    if any(addr in net for net in _BLOCKED_NETWORKS):
        return False
```

### CR-02: update_webhook (PUT) sets a new URL without SSRF validation

**File:** `backend/webhook_endpoints.py:156-187`
**Issue:** `create_webhook` validates the URL with `_is_safe_webhook_url`, but `update_webhook` writes `data["url"]` straight into `update_fields` with no safety check. A user creates a webhook with a public URL (passes creation), then PUTs an internal URL (`http://169.254.169.254/...`) — the guard is fully bypassed.
**Fix:** Apply the same `_is_safe_webhook_url` check to the incoming `url` in `update_webhook` before persisting.

## Warnings

### WR-01: API-key auth does not check tenant/key lifecycle beyond `revoked`

**File:** `backend/api_key_auth.py:16-29`
**Issue:** The key lookup checks only `matched_key.revoked`. There is no expiry check and no verification that the owning tenant is active/not suspended, so a key belonging to a disabled tenant still authenticates. SHA-256 without salt is acceptable for high-entropy random keys but note the lookup returns the whole matched element by projection — confirm no extra secret fields leak.
**Fix:** Add an `expiresAt` check on the key and a tenant-status check after `find_one`.

## Info

### IN-01: Naive timestamps in webhook_service
**File:** `backend/webhook_service.py:79, 112, 140, 153` — `datetime.now().isoformat()` is timezone-naive; other modules use `datetime.now(timezone.utc)`. Use tz-aware for consistency.

---

_Reviewed: 2026-07-27_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
