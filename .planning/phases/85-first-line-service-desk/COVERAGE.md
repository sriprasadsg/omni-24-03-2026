# API Coverage — Ollama local HTTP API (loopback only)

> Full coverage by default. Opt-outs are explicit, reasoned decisions.
> The service desk calls Ollama only through `backend/service_desk/model.py`, only on 127.0.0.1 / ::1 / localhost (D-15).

| capability | decision | reason |
|---|---|---|
| generate | INTEGRATE | |
| tags | INTEGRATE | |
| ps | INTEGRATE | |
| chat | OPT-OUT | not needed: each ticket gets one single-turn answer (D-04), generate covers it |
| embed | OPT-OUT | explicitly out of scope: retrieval is a fixed, tested TF-IDF score (D-18), never a model score |
| show | OPT-OUT | not needed: the exact-tag check uses tags |
| pull | OPT-OUT | explicitly out of scope: installing and pulling the model is the operator's step |
| push | OPT-OUT | explicitly out of scope: the platform never publishes models |
| create | OPT-OUT | explicitly out of scope: no custom model files are built |
| copy | OPT-OUT | explicitly out of scope: model management stays with the operator |
| delete | OPT-OUT | explicitly out of scope: model management stays with the operator |
| blobs | OPT-OUT | explicitly out of scope: only used to create models |
| version | OPT-OUT | not needed: availability is decided by tags plus the exact model tag (DESK-04) |
| streaming responses | OPT-OUT | not needed: an answer is checked and posted only when complete (D-19, D-21) |
