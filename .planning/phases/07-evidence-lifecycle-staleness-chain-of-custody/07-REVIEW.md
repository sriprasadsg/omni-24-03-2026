---
phase: 07-evidence-lifecycle-staleness-chain-of-custody
reviewed: 2026-06-21T20:33:14Z
depth: standard
files_reviewed: 13
files_reviewed_list:
  - backend/evidence_staleness.py
  - backend/evidence_coc.py
  - backend/tests/test_evidence_lifecycle.py
  - backend/database.py
  - backend/compliance_evidence_lifecycle_endpoints.py
  - backend/compliance_evidence_endpoints.py
  - backend/router_registry.py
  - components/ChainOfCustodyPanel.tsx
  - components/EvidenceSettings.tsx
  - components/AssetComplianceList.tsx
  - components/SettingsDashboard.tsx
  - components/FrameworkDetail.tsx
  - services/apiService.ts
findings:
  critical: 3
  warning: 6
  info: 3
  total: 12
status: issues_found
---

# Phase 07: Code Review Report

**Reviewed:** 2026-06-21T20:33:14Z
**Depth:** standard
**Files Reviewed:** 13
**Status:** issues_found

## Summary

This phase implements evidence staleness tracking, chain-of-custody (CoC) audit logging, and related settings/UI. The backend core logic in `evidence_staleness.py` and `evidence_coc.py` is solid. The two critical security findings are: a path-traversal guard omission in `delete_control_direct_evidence` that could allow a crafted filename to delete files outside the upload directory, and the `delete_compliance_evidence` endpoint silently returning `None` (no HTTP response body) on unhandled exceptions. A third critical finding is that `get_staleness_threshold` can return a stored value of `0` or a negative integer from the database, causing every evidence item to be immediately flagged stale regardless of age, which will produce misleading compliance data.

The six warnings cover: the `compliance_evidence_endpoints` module missing from `router_registry.py` registration (its routes are loaded by a different mechanism that must be verified); role-set inconsistencies across the two endpoint files; the CoC fire-and-forget suppression hiding operational failures silently; the `EvidenceSettings` component not handling HTTP error responses from the API; `file.text()` being called on binary evidence files during ingestion; and the stale-badge display using array index as React key.

---

## Critical Issues

### CR-01: Path-traversal guard missing `os.sep` in `delete_control_direct_evidence`

**File:** `backend/compliance_evidence_endpoints.py:492`
**Issue:** The path-confinement check for disk cleanup in `delete_control_direct_evidence` uses a bare `startswith(str(_safe_dir))` without appending `os.sep`. If the upload directory is `/app/uploads`, a file whose resolved path falls in `/app/uploads_evil/` would satisfy the check because `"/app/uploads_evil/x".startswith("/app/uploads")` is `True`. An attacker who can supply a crafted `url` in a evidence record (e.g. via a compromised CoC snapshot, a direct DB write, or any future injection path) could cause an arbitrary file outside the upload directory to be deleted.

The same endpoint's sibling in `delete_compliance_evidence` (line 312) correctly uses `str(_safe_dir) + os.sep`, and the download handler (line 207) also uses the correct form. Only line 492 is vulnerable.

```python
# Current (line 492) — VULNERABLE
if str(resolved).startswith(str(_safe_dir)):
    resolved.unlink(missing_ok=True)

# Fix — match the pattern used in delete_compliance_evidence (line 312)
if str(resolved).startswith(str(_safe_dir) + os.sep) or resolved == _safe_dir:
    resolved.unlink(missing_ok=True)
```

---

### CR-02: `delete_compliance_evidence` returns `None` (no HTTP response) on unhandled exception

**File:** `backend/compliance_evidence_endpoints.py:318-320`
**Issue:** The outer `except Exception` block logs the error but falls off the end of the function without returning anything or raising an `HTTPException`. FastAPI will serialise a `None` return as HTTP 200 with a `null` body — not a 500. The caller receives a success-like status code for a failed deletion, and the evidence record is left in an unknown state (the DB `$pull` may or may not have run before the exception). This is a correctness/data-integrity bug; the client cannot distinguish success from failure.

```python
# Current (lines 317-320)
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Delete evidence error: %s", e)
        # Falls off here — no return, no raise

# Fix
    except Exception as e:
        logger.error("Delete evidence error: %s", e)
        raise HTTPException(status_code=500, detail="Internal server error")
```

---

### CR-03: `get_staleness_threshold` does not enforce its documented minimum of 1

**File:** `backend/evidence_staleness.py:43-57`
**Issue:** The docstring states "minimum 1", but no enforcement exists. If the `system_settings` collection contains `{"thresholdDays": 0}` or a negative integer, `isinstance(doc.get("thresholdDays"), int)` returns `True` and the value is returned as-is. `compute_stale` will then mark every evidence item stale immediately (`age_days >= 0` is always true for non-future dates), generating false-positive stale badges across the entire compliance dashboard. A misconfiguration or a direct DB write can silently corrupt all staleness computations.

The `StalenessThresholdUpdate` Pydantic model enforces `ge=1` on write via the API, but a direct DB edit or a race with an older record bypasses this.

```python
# Current (lines 50-57) — no minimum enforcement
    if doc and isinstance(doc.get("thresholdDays"), int):
        return doc["thresholdDays"]
    ...
    return 7

# Fix — enforce minimum on read
    def _safe_threshold(raw_val: int) -> int:
        return max(1, raw_val)

    if doc and isinstance(doc.get("thresholdDays"), int):
        return _safe_threshold(doc["thresholdDays"])
    ...
    return 7
```

---

## Warnings

### WR-01: `compliance_evidence_endpoints` is not registered in `router_registry.py`

**File:** `backend/router_registry.py:119-130`
**Issue:** `router_registry.py` registers `compliance_evidence_lifecycle_endpoints` (line 130) but there is no `_load(app, "compliance_evidence_endpoints", ...)` call anywhere in the file. The routes for evidence upload, download, per-asset compliance, and evidence deletion are absent from the registry. If this module is only loaded by another mechanism (e.g., direct `include_router` in `app.py`) that is fine, but the registry is the declared single source of truth for routing. A future refactor that trusts the registry exclusively would silently drop all evidence CRUD endpoints. This should either be added to the registry or documented with a comment explaining the alternate load path.

**Fix:** Add an explicit registration entry at line 129, directly before the lifecycle endpoints:
```python
_load(app, "compliance_evidence_endpoints", "router")
_load(app, "compliance_evidence_lifecycle_endpoints", "router")
```

---

### WR-02: Inconsistent `_SUPER_ROLES` sets across endpoint files

**File:** `backend/compliance_evidence_lifecycle_endpoints.py:24` and `backend/compliance_evidence_endpoints.py:20`
**Issue:** The two files define different sets for what constitutes a super/admin role:

- `compliance_evidence_lifecycle_endpoints.py` line 24: `{"Super Admin", "superadmin", "super_admin", "platform-admin"}` — includes `superadmin` but not `admin`
- `compliance_evidence_endpoints.py` line 20: `{"Super Admin", "super_admin", "admin", "platform-admin"}` — includes `admin` but not `superadmin`
- `compliance_evidence_endpoints.py` line 139: a third inline set `{"Super Admin", "superadmin", "super_admin", "platform-admin"}` — includes both but inconsistently

A user with role `admin` will bypass tenant isolation in `compliance_evidence_endpoints.py` but will be treated as a regular tenant user in `compliance_evidence_lifecycle_endpoints.py` and be denied the CoC audit log for evidence they uploaded. Conversely, a role named `superadmin` gets no bypass in the CRUD endpoint. This will cause silent, role-dependent authorization inconsistencies.

**Fix:** Extract a single shared constant, or import from a shared auth module:
```python
# shared_roles.py
SUPER_ROLES: frozenset[str] = frozenset({"Super Admin", "superadmin", "super_admin", "admin", "platform-admin"})
```
Then import and use it in both endpoint files.

---

### WR-03: CoC fire-and-forget swallows failures silently in a compliance audit trail

**File:** `backend/evidence_coc.py:44-45`
**Issue:** `_append_coc_entry` is documented as "fire-and-forget" and intentionally swallows all exceptions, logging them at `ERROR` level. For a generic operational log this is acceptable, but the CoC log is a compliance audit trail. Silently losing a create/update/delete audit event is a compliance gap: the system will appear to have written an immutable audit trail but may have gaps. There is no counter, metric, or alert emitted — only a log line that could scroll off in high-volume deployments.

**Fix:** At minimum, increment a metrics counter on failure so an alerting rule can detect sustained CoC write failures:
```python
except Exception as e:
    logging.getLogger(__name__).error("CoC append failed: %s", e)
    # Increment a prometheus/statsd counter or raise a background alert
    # metrics.increment("coc.append.failure")
```
Consider whether compliance requirements demand a dead-letter queue or transactional outbox pattern instead.

---

### WR-04: `EvidenceSettings` does not handle non-OK HTTP responses from `fetchStalenessThreshold`

**File:** `components/EvidenceSettings.tsx:10`
**Issue:** The `useEffect` calls `api.fetchStalenessThreshold().then(d => setThreshold(d.thresholdDays ?? 7))` without a `.catch()`. The corresponding `apiService.ts` implementation (lines 4323-4329) catches network errors and returns the default, but does not check `res.ok` before calling `res.json()`. If the server returns a 401 (token expiry), 403, or 500, `res.json()` will parse the error body and `d.thresholdDays` will be `undefined`, silently falling back to `7` — hiding an authentication or server error from the user.

**Fix:** In `apiService.ts`:
```typescript
export const fetchStalenessThreshold = async (): Promise<{ thresholdDays: number }> => {
    try {
        const res = await authFetch(`${API_BASE}/settings/evidence-staleness`);
        if (!res.ok) return { thresholdDays: 7 };   // add this check
        return await res.json();
    } catch {
        return { thresholdDays: 7 };
    }
};
```

---

### WR-05: `file.text()` called on binary evidence files (PDF, DOCX, XLSX) during ingestion

**File:** `components/AssetComplianceList.tsx:51`
**Issue:** `handleFileChange` calls `file.text()` on the uploaded file, then passes the result as `content` to `onIngestEvidence`. For binary files (PDF, DOCX, XLSX — which are explicitly accepted), `file.text()` returns garbage: it decodes binary bytes as UTF-8, producing mojibake. This content is then ingested into the RAG knowledge base with a malformed string, poisoning the knowledge index for this evidence item. Text extraction for binary formats requires a server-side parser.

**Fix:** Skip the text ingestion step for non-plain-text files, or limit ingestion to `.txt`/`.md` files client-side:
```typescript
const isTextFile = file.type === 'text/plain' || file.name.endsWith('.txt') || file.name.endsWith('.md');
if (isTextFile) {
    const text = await file.text();
    await onIngestEvidence(selectedAssetId, file.name, text);
}
// For PDF/DOCX/XLSX: skip client-side ingestion; let the server extract text
```

---

### WR-06: `ChainOfCustodyPanel` uses array index as React list key

**File:** `components/ChainOfCustodyPanel.tsx:112`
**Issue:** `entries.map((entry, idx) => <div key={idx} ...>` uses the array index as the `key` prop. CoC entries have a stable natural key: the combination of `evidenceId` + `timestamp` (both present on every entry per the schema). Using index keys causes React to re-render the wrong DOM nodes when the list is filtered, sorted, or an entry is prepended. While this panel does not currently support filtering, it is a fragile pattern that will silently misbehave if the entry list ever changes.

**Fix:**
```tsx
entries.map((entry) => {
    const key = `${entry.evidenceId}-${entry.timestamp}`;
    return <div key={key} className="px-4 py-3">
    ...
```

---

## Info

### IN-01: `get_staleness_threshold` docstring promises minimum-1 enforcement that does not exist

**File:** `backend/evidence_staleness.py:43`
**Issue:** The docstring states "int — threshold days (minimum 1, default 7)" implying callers can rely on never receiving `0`. The code does not enforce this (see CR-03). The discrepancy between the documented contract and the implementation is a maintainability hazard independent of the correctness bug.

**Fix:** Either enforce the minimum (see CR-03 fix), or remove the "(minimum 1)" claim from the docstring until it is enforced.

---

### IN-02: Snapshot data rendered as raw JSON in CoC panel for `update` events

**File:** `components/ChainOfCustodyPanel.tsx:128-133`
**Issue:** For `action_type === 'update'` entries, the panel renders `JSON.stringify(snapshot, null, 2)` directly in a `<pre>` block. The `snapshot_after` field is a full evidence document which may contain the `url` (internal file path), `uploaded_by` (email address), and `tenantId`. Exposing these raw fields in a client-rendered block is an unnecessary information disclosure: compliance auditors should see a human-readable diff, not raw document dumps. This is lower-risk now because the CoC endpoint is already gated by `canViewCoC` permission, but the pattern does not scale safely.

**Fix:** Render a curated subset of fields (actor, action, evidenceId, name) rather than the raw snapshot object.

---

### IN-03: `SettingsDashboard` "Evidence" tab has no permission gate

**File:** `components/SettingsDashboard.tsx:288`
**Issue:** The "Evidence" tab button renders unconditionally (no `canManageSettings` or role check), and the `EvidenceSettings` component mounts for all users regardless of role (line 354-356). Any authenticated user who navigates to Settings can see and submit the staleness threshold form. The server enforces the admin gate correctly (PATCH returns 403 for non-admins), but the UI silently accepts the form submission and only fails when the API call returns 403 — with the error swallowed in `EvidenceSettings.handleSave`'s catch block where a `showToast` is shown. While not a security bypass (server enforces), it is a confusing UX and violates the principle of least privilege in the frontend.

**Fix:** Wrap the Evidence tab button and content with the same `canManageSettings` check used by the Integrations, Alerts, and Email tabs.

---

_Reviewed: 2026-06-21T20:33:14Z_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
