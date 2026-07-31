---
phase: 38-interactive-ai-security-assistant
reviewed: 2026-07-27T00:00:00Z
depth: standard
files_reviewed: 5
files_reviewed_list:
  - backend/ai_assistant_service.py
  - backend/ai_assistant_endpoints.py
  - services/apiService.ts
  - components/AIAssistantChat.tsx
  - backend/tests/test_ai_assistant.py
findings:
  critical: 2
  warning: 2
  info: 3
  total: 7
status: issues_found
---

# Phase 38: Code Review Report

**Reviewed:** 2026-07-27
**Depth:** standard
**Files Reviewed:** 5
**Status:** issues_found

## Summary

Phase 38 wires an interactive AI security assistant: a backend service
(`ai_assistant_service.chat`, now a shim over the LangChain agent),
JSON + SSE endpoints, a `chatWithAssistant` streaming client, and a React chat
UI. The backend auth/tenant scoping is correct (permission dependency + tenant
context, fail-closed service contract). But the **frontend streaming path is
broken end-to-end**: the client calls the non-streaming endpoint yet parses the
response as SSE, and even if that were fixed, the completion handler discards the
streamed answer via a stale-closure bug. Two Critical, two Warning, three Info.

Note: `history.slice(0, -1)` in `AIAssistantChat.sendMessage` is **correct**, not
a bug — it strips the just-appended current message because the question is sent
separately as `q`; keeping it would duplicate the turn.

## Critical Issues

### CR-01: `chatWithAssistant` calls the non-streaming endpoint but parses SSE

**File:** `services/apiService.ts:3191`
**Issue:** The function is the streaming client (reads `res.body.getReader()`,
splits on `data: ` frames, handles `[DONE]`), but it POSTs to
`${API_BASE}/assistant/chat` — the **non-streaming** JSON route
(`ai_assistant_endpoints.py:26`). That route returns a plain JSON body
`{"answer": ..., "sources": ...}` with no `data:` framing. The reader loop finds
no line starting with `data: `, so `onChunk` never fires and `finalSources`
stays `[]`. `onComplete([])` runs at stream end and the assistant bubble is
finalized empty. The chat renders nothing. The correct route is
`/assistant/chat/stream`.
**Fix:**
```typescript
const res = await fetch(`${API_BASE}/assistant/chat/stream`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json',
               ...(token ? { Authorization: `Bearer ${token}` } : {}),
               'X-Tenant-ID': tenantId },
    body: JSON.stringify({ query, history }),
    signal: abortController.signal,
});
```

### CR-02: `onComplete` finalizes the message with a stale, empty `streamingContent`

**File:** `components/AIAssistantChat.tsx:42-57`
**Issue:** During streaming, chunks accumulate via
`setStreamingContent(prev => prev + chunk)` (functional update — correct). But the
`onComplete` callback reads the `streamingContent` **variable** captured in the
`sendMessage` closure, which is the `''` from the render where `sendMessage` was
created (it was just reset by `setStreamingContent('')` on line 31). So the final
write is `content: (last.content || '') + (streamingContent || '')` → `'' + '' =
''`. The entire streamed answer is thrown away the moment the stream completes;
the bubble that was showing live text goes blank. This is a data-loss/correctness
bug independent of CR-01 — fixing the endpoint alone still yields an empty final
message.
**Fix:** Accumulate the answer in the functional updater instead of reading the
captured state. E.g. keep the streamed text in a `ref` that `onChunk` appends to,
and read `streamRef.current` in `onComplete`:
```typescript
const streamRef = useRef('');
// on send: streamRef.current = '';
// onChunk: streamRef.current += chunk; setStreamingContent(streamRef.current);
// onComplete:
next[next.length - 1] = { role: 'assistant',
    content: (last.content || '') + streamRef.current, sources };
```

## Warnings

### WR-01: `_stream_answer` fakes streaming — buffers the whole answer, then dribbles words

**File:** `backend/ai_assistant_endpoints.py:55-83`
**Issue:** The SSE generator first `await assistant_chat(...)` to completion, then
splits the finished answer on whitespace and yields word frames with
`asyncio.sleep(0.02)` between each. There is no real token streaming — the client
waits the full model latency before the first byte, then the artificial delay
adds `0.02 * word_count` seconds on top (a 500-word answer adds ~10s of pure
sleep while holding the connection open). It defeats the purpose of SSE and can
trip proxy/client idle behavior.
**Fix:** Stream tokens from the agent as they are produced (LangChain
`astream`/`astream_events`) and yield each as a `chunk` frame; drop the
`asyncio.sleep`.

### WR-02: Stream error frame leaks raw exception text to the client

**File:** `backend/ai_assistant_endpoints.py:66-70`
**Issue:** On failure `_stream_answer` yields `{'error': str(exc)}` straight to
the browser. Raw exception strings can disclose internal details (paths, driver
errors). The service layer already resolves its own errors to a safe shape, so
this branch mostly catches infrastructure faults whose messages are exactly the
ones you don't want to surface.
**Fix:** Log `exc` server-side; send a generic client message
(`{'error': 'The assistant is temporarily unavailable.'}`).

## Info

### IN-01: Service `except Exception` returns the exception text as the answer

**File:** `backend/ai_assistant_service.py:53-55`
**Issue:** `return {"answer": f"Error generating response: {exc}", "sources": []}`
places the raw exception into user-visible answer text. Documented as an
intentional fail-closed second line of defense, which is reasonable, but the
`{exc}` interpolation can leak internals to the UI.
**Fix:** Keep the fail-closed shape but use a generic answer string; log `exc`.

### IN-02: Redundant `sources: []` initializer on the assistant bubble

**File:** `components/AIAssistantChat.tsx:34`
**Issue:** The placeholder assistant message sets `sources: []`, which is
immediately overwritten in `onComplete`. Harmless; minor noise.
**Fix:** Optional — drop the initializer.

### IN-03: `X-Tenant-ID` derived from `sessionStorage('tenantId') || 'default'`

**File:** `services/apiService.ts:3189,3196`
**Issue:** The client stamps `X-Tenant-ID` from client-controlled storage,
falling back to `'default'`. The backend derives tenant from
`get_tenant_id()`/the authenticated token (correct), so this header should be
advisory only — confirm the server never trusts it for scoping.
**Fix:** None if the server ignores the header for authz; otherwise remove
client-supplied tenant trust.

---

_Reviewed: 2026-07-27_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
