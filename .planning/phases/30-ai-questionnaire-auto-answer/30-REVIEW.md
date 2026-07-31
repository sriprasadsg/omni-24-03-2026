---
phase: 30-ai-questionnaire-auto-answer
reviewed: 2026-07-27T00:00:00Z
depth: standard
files_reviewed: 11
files_reviewed_list:
  - backend/rag_service.py
  - backend/ai_service.py
  - backend/ai_providers.py
  - backend/questionnaire_inbound_service.py
  - backend/questionnaire_inbound_endpoints.py
  - backend/questionnaire_answer_review_service.py
  - backend/questionnaire_answer_review_endpoints.py
  - backend/questionnaire_answer_draft_service.py
  - backend/questionnaire_answer_draft_endpoints.py
findings:
  critical: 1
  warning: 3
  info: 3
  total: 7
status: issues_found
---

# Phase 30: Code Review Report

**Reviewed:** 2026-07-27
**Depth:** standard
**Files Reviewed:** 11
**Status:** issues_found

## Summary

Tenant-scoped RAG, inbound intake, answer-review state machine, grounded draft shim. T3 submit guard and server-derived reviewer identity are correctly implemented. But the T1 tenant-isolation fix is opt-in (fails open when caller omits tenant_id), file parsing/upload has unguarded crash and race paths, and the 30-01 generation-control claim (temperature/max_tokens) is absent from the reviewed provider code.

## Critical Issues

### CR-01: RAG tenant isolation fails open when tenant_id omitted

**File:** `backend/rag_service.py:74-77`
**Issue:** `query(query_text, n_results, tenant_id=None)` only applies the `$or` tenant filter `if tenant_id`. Any caller that forgets to pass `tenant_id` (default `None`) gets an **unfiltered** cross-tenant result set — the exact T1 leak the phase claims to close. Isolation should be fail-closed, not dependent on every caller remembering the argument.
**Fix:**
```python
def query(self, query_text, n_results=3, tenant_id=None):
    if not self.collection:
        return []
    if not tenant_id:
        raise ValueError("tenant_id is required for scoped RAG queries")
    query_kwargs = {
        "query_texts": [query_text],
        "n_results": n_results,
        "where": {"$or": [{"tenantId": tenant_id}, {"tenantId": "global"}]},
    }
    ...
```

## Warnings

### WR-01: Upload parsing crashes on bad input (500 instead of 4xx)

**File:** `backend/questionnaire_inbound_service.py:57`, `backend/questionnaire_inbound_endpoints.py:40`
**Issue:** `content_bytes.decode("utf-8")` raises `UnicodeDecodeError` on non-UTF-8 CSVs → unhandled 500. `parse_upload(file.filename, ...)` calls `filename.endswith(...)` with no guard; `UploadFile.filename` can be `None` → `AttributeError` 500.
**Fix:** Wrap decode in try/except → `HTTPException(400)`; guard `if not file.filename: raise HTTPException(400, "filename required")`.

### WR-02: Upload endpoint read-modify-write race + unbounded read

**File:** `backend/questionnaire_inbound_endpoints.py:35-48`
**Issue:** Fetch → `questions.extend()` → `update_one($set questions=...)` is a non-atomic read-modify-write; concurrent uploads to the same set lose questions. `await file.read()` loads the whole file into memory with no size cap (memory-exhaustion DoS).
**Fix:** Use `$push: {questions: {$each: new_questions}}` for an atomic append; enforce a max upload size before `read()`.

### WR-03: Silent swallow of all DB errors in RAG path

**File:** `backend/rag_service.py:54-56, 99-101`
**Issue:** `ingest_text`/`query` catch bare `Exception` and return `{"error":...}` / `[]`. A DB outage yields "no evidence" and the pipeline drafts an insufficient-evidence answer instead of surfacing failure — indistinguishable from a legitimately empty corpus.
**Fix:** Let infrastructure errors propagate (or return a typed error the caller can branch on) rather than collapsing to empty results.

## Info

### IN-01: Stale absolute path in comment
**File:** `backend/rag_service.py:11` — `d:/Downloads/...` leftover comment; remove.

### IN-02: Claimed generation controls absent
**File:** `backend/ai_providers.py:20, 159-177`; `backend/ai_service.py:217` — 30-01 SUMMARY says `temperature`/`max_tokens` were plumbed through all providers, but `AIProvider.generate(self, prompt: str)` and `generate_text(...)` take no such params and `AnthropicProvider` hardcodes `max_tokens: 1024`. Either a regression or a stale summary.

### IN-03: create_review has no reviewer gate / no dedupe
**File:** `backend/questionnaire_answer_review_endpoints.py:38-47`; `backend/questionnaire_answer_review_service.py:34-53` — any tenant user can create review records and nothing prevents multiple pending reviews per draft. Confirm this is intended (create ≠ decide) or add a uniqueness guard.

---

_Reviewed: 2026-07-27_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
