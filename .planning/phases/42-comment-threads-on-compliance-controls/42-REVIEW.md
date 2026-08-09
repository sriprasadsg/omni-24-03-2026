---
phase: 42-comment-threads-on-compliance-controls
reviewed: 2026-07-27T00:00:00Z
depth: standard
files_reviewed: 5
files_reviewed_list:
  - backend/control_comments_service.py
  - backend/control_comments_endpoints.py
  - backend/notification_service.py
  - components/ControlCommentsPanel.tsx
  - services/apiService.ts
findings:
  critical: 0
  warning: 1
  info: 3
  total: 4
status: issues_found
---

# Phase 42: Code Review Report

**Reviewed:** 2026-07-27
**Depth:** standard
**Files Reviewed:** 5
**Status:** issues_found

## Summary

Compliance-control comment threads (CMT-01). One document per comment in a dedicated
`control_comments` collection, tenant-scoped via `TenantIsolatedCollection`. POST is
role-gated (`admin`/`super_admin`/`compliance_reviewer`) and re-enforced server-side;
GET is open to any authenticated tenant user. `@mention` regex is re.escape'd before
building the Mongo `$regex`, so there is no NoSQL/regex injection. Free-text is stored
raw and safe-rendered on the frontend (split/map, no `dangerouslySetInnerHTML`) — XSS
surface is closed. The `channels=None` vs `channels=[]` fix in `notification_service`
correctly separates "default to email" from "explicit no-dispatch".

## Warnings

### WR-01: Unbounded `@mention` resolution — up to 3 DB queries per token, no token cap

**File:** `backend/control_comments_service.py:39-48`
**Issue:** `resolve_mentions` runs up to three sequential `find_one` queries per
extracted `@token`. `text` is capped at 2000 chars but the number of `@tokens` inside
it is not bounded, so a single comment like `@a @b @c ...` can trigger hundreds of
serial queries on the POST path. An authenticated reviewer can use this to load the DB
per comment.
**Fix:** Cap the number of resolved mentions per comment (e.g. first 20 unique tokens),
and/or batch the lookup into one `$or` query:
```python
tokens = list(dict.fromkeys(extract_mention_tokens(text)))[:20]
users = await db.users.find({"$or": [
    {"username": {"$in": tokens}},
    {"email": {"$regex": f'^({"|".join(map(re.escape, tokens))})@'}},
]}).to_list(length=40)
```

## Info

### IN-01: `resolve_mentions` re-instantiates the notification service per recipient

**File:** `backend/control_comments_endpoints.py:73-84`
**Issue:** `get_notification_service(db)` is called inside the per-mention loop, so it
is rebuilt once per recipient. Harmless but wasteful.
**Fix:** Hoist `svc = get_notification_service(db)` above the loop.

### IN-02: Blanket `except Exception: pass` on notification dispatch

**File:** `backend/control_comments_endpoints.py:85-89`
**Issue:** Non-fatal by design (matches the tickets convention), but swallowing every
exception silently means a misconfigured notification backend is invisible.
**Fix:** `logger.debug(...)` the swallowed exception so failures are discoverable.

### IN-03: `list_comments` hard-caps at 200 with no pagination

**File:** `backend/control_comments_service.py:67-68`
**Issue:** `.to_list(length=200)` silently truncates a control's thread at 200 comments,
oldest-first, so the newest comments vanish from the UI once the thread exceeds 200.
**Fix:** Paginate, or sort newest-first if the cap must stay.

---

_Reviewed: 2026-07-27_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
