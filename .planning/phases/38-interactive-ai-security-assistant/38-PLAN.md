# Phase 38: Interactive AI Security Assistant - Plan

**Goal:** Add a conversational chat UI where users ask natural-language questions about their compliance/security posture and get answers grounded in live findings data, with sources cited.

**Requirements:** ASSIST-01, ASSIST-02

**Depends on:** Phase 30 (reuses `rag_service.py`, multi-tenant ChromaDB)

**Waves:** 3
- **Wave 1:** Backend Chat API and RAG Integration.
- **Wave 2:** Frontend Chat UI (Streaming).
- **Wave 3:** Integration and Verification.

---
## Plan 38-01: Backend Chat API and RAG Integration

**Goal:** Implement the chat endpoint with grounded responses.

**Tasks:**

1.  **Dependencies:**
    -   Ensure existing AI/ML dependencies are available (from Phase 30).

2.  **Service (`backend/ai_assistant_service.py`):**
    -   Create `backend/ai_assistant_service.py`.
    -   Implement a `chat(query: str, tenant_id: str, history: list)` function.
    -   Flow:
        1.  Retrieve relevant context from `rag_service.query_tenant_knowledge(query, tenant_id, k=5)`.
        2.  Also query live findings/controls from MongoDB (compliance, evidence, risks).
        3.  Build a prompt with retrieved context + chat history.
        4.  Call `ai_service.generate_text` (or streaming variant) with the prompt.
        5.  Return structured response: `{ answer: str, sources: [{type, id, title, snippet}] }`.

3.  **Endpoints (`backend/ai_assistant_endpoints.py`):**
    -   Create `backend/ai_assistant_endpoints.py`.
    -   `POST /api/assistant/chat` (authenticated, tenant-scoped).
    -   Support Server-Sent Events (SSE) for streaming responses:
        -   Stream partial `answer` chunks.
        -   Final event includes `sources`.

4.  **Registration:**
    -   Add to `router_registry.py`.

**Verification:**
-   Chat endpoint returns grounded answers with sources.
-   Streaming works via SSE.

---
## Plan 38-02: Frontend Chat UI

**Goal:** Build the conversational chat interface.

**Tasks:**

1.  **New Component (`components/AIAssistantChat.tsx`):**
    -   Create a full-screen or modal chat interface.
    -   Message list with user/assistant bubbles.
    -   Input area with send button.
    -   Render source citations inline (clickable links to evidence/controls).

2.  **API Service (`services/apiService.ts`):**
    -   Add `chatWithAssistant(query, history, onChunk, onComplete)` using `fetch` + SSE reader.

3.  **Integration:**
    -   Add a "AI Assistant" entry in `Sidebar.tsx` (or top nav).
    -   Route to a new page or open modal.

**Verification:**
-   Chat UI renders and handles streaming.
-   Source citations link to correct resources.

---
## Plan 38-03: Integration and Verification

**Goal:** End-to-end verification.

**Tasks:**

1.  **Tests:**
    -   Create `backend/tests/test_ai_assistant.py`.
    -   Test grounded response includes sources.
    -   Test cross-tenant isolation (cannot query other tenant's data).
    -   Test streaming protocol.

2.  **Human Verification:**
    -   Start dev servers.
    -   Ask questions like "What are my failing controls?" "Show evidence for control X".
    -   Verify answers are grounded and citations work.

**Verification:**
-   All tests pass.
-   Real usage produces grounded, cited responses.