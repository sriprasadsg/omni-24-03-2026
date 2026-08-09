# Phase 31: FAIR Risk Quantification - Research

**Researched:** 2026-07-08
**Domain:** FAIR (Factor Analysis of Information Risk) quantitative risk scoring — Monte Carlo simulation over loss-frequency/loss-magnitude distributions, additive to an existing likelihood×impact risk register (Python/FastAPI/Motor backend, React/TypeScript SPA frontend)
**Confidence:** HIGH (backend extension mechanics, numpy availability, existing risk-register contract — all confirmed by direct in-session reads of this codebase and Phase 26's forward-looking plan documents) / MEDIUM (exact loss-magnitude input categories and whether FAIR output must reconcile numerically with the qualitative score — genuine product decisions, see Open Questions)

<user_constraints>
## User Constraints (from CONTEXT.md)

No CONTEXT.md exists for this phase. This project runs in yolo/auto mode this milestone — no `/gsd-discuss-phase` was run for Phase 31 (or any other v3.0 phase since Phase 29). This research and the resulting plan must proceed from `.planning/REQUIREMENTS.md` + `.planning/ROADMAP.md` + direct codebase inspection (including Phase 26's not-yet-executed plan documents, which define the forward contract this phase extends) only. There are no locked decisions, discretion notes, or deferred ideas to copy verbatim — everything below is this agent's own research-derived recommendation, and items needing a human product decision are called out explicitly in **Open Questions**.
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| FAIR-01 | A risk can optionally be scored using FAIR-style quantitative loss-exceedance inputs (loss magnitude range × event frequency), in addition to the existing qualitative likelihood×impact scoring | See Architecture Patterns → Pattern 1 (additive `fair_inputs`/`fair_results` sub-document on the existing risk doc, computed synchronously via `numpy`-vectorized Monte Carlo — no new dependency, no job queue) |
</phase_requirements>

## Summary

This phase adds a genuinely optional, additive FAIR-style quantitative layer to the risk register `risk_service.py`/`risk_endpoints.py` already extends today, and which **Phase 26 (planned, not yet executed) is simultaneously extending** with inherent/residual qualitative scoring. Both phases touch the same two backend files and the same two frontend components; this research treats Phase 26's plan documents (`26-03-PLAN.md`, `26-05-PLAN.md`) as the forward contract — the `Risk` model this phase extends already has `inherent_risk_score`/`residual_likelihood`/`residual_impact`/`residual_risk_score` fields layered onto `risk_score` by the time Phase 31 lands (assuming Phase 26 executes first, per its Wave-1 → Wave-2 dependency chain and ROADMAP's "Depends on: Phase 26" note for this phase).

**The core FAIR mechanic — LEF (Loss Event Frequency) × LM (Loss Magnitude) → Monte Carlo → Loss Exceedance Curve — needs no new backend dependency.** `numpy>=1.24.0,<3.0.0` is already declared in `backend/requirements.txt` and is already imported and used synchronously inside request-serving code in this exact codebase (`xai_service.py` imports `numpy as np` and calls `np.argsort`/`np.array` directly inside handler logic, with no `BackgroundTasks`/Celery involvement). `scipy` is **not** a dependency today and is not needed — `numpy.random.triangular(min, mode, max, size=N)` is sufficient for both LEF and LM sampling (a `min`/`most-likely`/`max` triangular distribution is the simplest FAIR-compliant input shape and is what most FAIR tooling, including RiskLens/the Open FAIR calculator, accepts as the default elicitation shape). A `pyfair`-style dedicated library is unnecessary — the entire computation (sample LEF, sample LM per iteration, multiply, sort for percentiles, build an exceedance curve) is well under 100 lines of vectorized numpy and fits the codebase's existing "hand-roll only when a library would be overkill for a bounded problem" convention (same reasoning `xai_service.py`, `ueba_engine.py`, and `automl_service.py` already apply for their own numpy-based statistics).

**Where the Monte Carlo runs is the key architectural decision, and the answer is synchronous, in the request/response cycle.** This codebase has a real Celery task-queue (`celery_app.py`/`tasks.py`, MongoDB or Redis broker) already wired for genuinely long-running or fire-and-forget work (agent task dispatch, remediation script execution, scheduled patch scans) — but every one of those existing `.delay()` call sites is either (a) a long-running external I/O operation (agent RPC round-trip) or (b) a periodic/scheduled batch job, never a bounded, pure-CPU numerical computation. A 5,000-iteration vectorized `numpy.random.triangular` + multiply + `numpy.percentile` computation completes in single-digit milliseconds on any modern host — introducing Celery here would add polling/webhook/task-status-endpoint machinery for a calculation that is faster than the network round-trip needed to check on it. The correct, lightest-weight design is a plain synchronous helper function called directly inside the existing `POST`/`PUT /api/risks` (or a new dedicated `POST /api/risks/{id}/fair-simulation`) route handler — no `BackgroundTasks`, no Celery task, no job-status polling endpoint.

**FAIR-01's wording ("in addition to the existing qualitative scoring") and this codebase's additive-only convention (STATE.md decisions spanning 02-01 through 26-03/26-05) both point to the same design: FAIR is a parallel, optional sub-document, not a replacement or a numeric reconciliation of `risk_score`/`inherent_risk_score`/`residual_risk_score`.** A risk keeps its existing qualitative fields untouched; FAIR inputs/outputs live in new, all-optional fields (`fair_inputs`, `fair_results`) that are `None` unless a user explicitly opts in for that risk. This mirrors exactly how Phase 26 added residual scoring alongside — not instead of — the original blended `risk_score`, and avoids inventing any conversion formula between a 1-5×1-5 qualitative score and a dollar-denominated FAIR output (there is no standard, defensible mapping between the two — see Open Questions).

**Primary recommendation:** Extend `risk_service.py`/`risk_endpoints.py` additively with a `fair_inputs` (LEF min/likely/max, per-loss-category LM min/likely/max) sub-document and a `POST /api/risks/{id}/fair-simulation` endpoint that runs a synchronous, `numpy`-vectorized Monte Carlo (default 5,000-10,000 iterations) and returns/persists `fair_results` (mean/median/percentile annual loss exposure + loss-exceedance-curve data points) on the risk doc. No new dependency, no background job, no reconciliation with the qualitative score. Frontend adds an optional "Quantify with FAIR" panel to `RiskFormModal.tsx`/a risk detail view, composing with (not conflicting with) Phase 26's planned Residual Score column.

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| FAIR input capture (LEF/LM min/likely/max per risk) | API / Backend | Browser / Client (form) | Range-validated request model, mirrors the existing `RiskCreate`/`RiskUpdate` pattern; client-side min/max is UX only |
| Monte Carlo simulation execution | API / Backend | — | Pure CPU-bound numerical computation with no I/O dependency; belongs in the request-handling process, not a separate worker — see Summary |
| FAIR results persistence (percentiles, exceedance curve points) | Database / Storage | API / Backend | Stored on the risk doc (or a dedicated `risk_fair_simulations` sub-collection if history-over-time is wanted — see Open Questions) so results survive without re-running the simulation on every read |
| Loss-exceedance curve rendering | Browser / Client | — | Client renders a chart from server-computed percentile/curve data; no client-side statistics |
| Risk register display of FAIR summary (e.g., "$120K-$480K annualized (90% CI)") | Browser / Client | API / Backend | Additive column/badge in `RiskRegister.tsx`, composing with Phase 26's planned Residual Score column — different columns, same table |

## Standard Stack

### Core
No new libraries are required. Every capability FAIR-01 needs is already an installed, in-use dependency:

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| `numpy` | `>=1.24.0,<3.0.0` [VERIFIED: `backend/requirements.txt`, confirmed already imported synchronously in request-path code in `xai_service.py`, `ueba_engine.py`, `automl_service.py`, `ml_service.py`, `ml_service_predict.py`, `model_retraining_service.py`, `train_ml_models.py` this session] | Vectorized random sampling (`np.random.triangular`) + percentile/statistics (`np.percentile`, `np.mean`) for the Monte Carlo core | Already the platform's numerical-computation library; a full FAIR LEF×LM Monte Carlo fits entirely within numpy's stdlib-adjacent API — no reason to add scipy or a dedicated FAIR package |
| FastAPI + Motor (async pymongo) | `fastapi>=0.110.0,<1.0.0`, `motor>=3.3.0,<4.0.0` [VERIFIED: `backend/requirements.txt`, this session] | New request models + endpoint(s) extending `risk_endpoints.py` | Matches `risk_endpoints.py`'s existing shape exactly |
| stdlib `uuid`/`datetime` | n/a | ID/timestamp generation for any FAIR-simulation-history records | Matches the codebase-wide convention used throughout `risk_service.py` and every sibling service |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| `pandas` | `>=2.1.0,<3.0.0` [VERIFIED: `backend/requirements.txt`, already a dependency] | Optional: convenience for building the loss-exceedance-curve data-point table (sorted losses → cumulative exceedance %) | Only if the exceedance-curve construction becomes awkward in raw numpy; a `np.sort` + `np.arange`-based exceedance calculation is a 3-line alternative that avoids pulling pandas into this specific code path unnecessarily — prefer the numpy-only approach unless it proves genuinely harder to read |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| Hand-rolled `numpy.random.triangular` Monte Carlo (recommended) | `pyfair` (PyPI: a dedicated Open-FAIR-modeling Python package) | `pyfair` offers a richer object model (multi-stage risk trees, PERT-beta distributions, built-in exceedance-curve plotting) but is a real external dependency with its own maintenance/version risk for a computation this codebase can implement in under 100 lines using a library (`numpy`) it already trusts and uses elsewhere; **not recommended** — see Package Legitimacy Audit below for the explicit disposition |
| `numpy.random.triangular` for LEF/LM sampling (recommended, simplest FAIR-compliant shape) | PERT (Beta-PERT) distribution via `numpy.random.beta` reparameterized to min/mode/max | PERT places more probability mass near the "most likely" value (smoother, less "spiky" than triangular) and is what some FAIR tooling (RiskLens) defaults to; triangular is simpler to explain to a user filling in three numbers and is an accepted, standard-compliant FAIR input shape too — recommend triangular for v1 simplicity, note PERT as a credible future refinement (see Open Questions) |
| Synchronous in-request computation (recommended) | Celery task (`.delay()` to `tasks.py`, matching the existing `celery_app.py` infrastructure) | Celery is already wired and proven in this codebase, but every existing use case is I/O-bound (agent RPC) or scheduled/periodic — introducing a job-status-polling flow for a sub-100ms pure-CPU computation is unjustified complexity per CLAUDE.md's "nothing more than asked"; only reconsider if iteration counts grow into the hundreds of thousands or the risk register needs bulk/batch re-simulation across all risks at once |
| Storing FAIR results as a sub-document on the existing risk doc (recommended) | A dedicated `risk_fair_simulations` collection tracking simulation history over time | A history collection is the right call if the product wants to show "how has this risk's FAIR estimate changed over time," but FAIR-01's literal wording only asks for the score to exist "in addition to" the qualitative one — start with the simpler embedded-result shape (matches Phase 26's "no versioning needed" reasoning for `trust_profiles` in Phase 29's precedent) and flag history-tracking as a scope question (see Open Questions) |

**Installation:**
```bash
# No new packages required — numpy, pandas, fastapi, motor are all already installed and in use.
```

**Version verification:** `backend/requirements.txt` confirms `numpy>=1.24.0,<3.0.0` [VERIFIED: read directly this session, line 60] and `pandas>=2.1.0,<3.0.0` [VERIFIED: read directly this session]. `numpy` is confirmed actually imported and used synchronously inside handler-adjacent code in 7 existing backend files this session (not merely declared-but-unused). `scipy` is confirmed **absent** from `requirements.txt` and is not recommended for addition — `numpy.random.triangular` covers this phase's distributional needs without it.

## Package Legitimacy Audit

No external packages are being introduced by this phase. `numpy` and `pandas` are pre-existing, already-installed dependencies with years of production use in this exact codebase (7 other backend files import `numpy` directly) — re-running a fresh legitimacy check on an already-vendored, multi-file-proven dependency is unnecessary. `pyfair` (the one plausible new package this domain suggests) was explicitly evaluated and **rejected** as unnecessary — see Alternatives Considered above — so it was never added to the dependency list and does not need a legitimacy check either.

**Packages removed due to [SLOP] verdict:** none (none proposed for installation).
**Packages flagged as suspicious [SUS]:** none.
**Packages considered and explicitly not adopted:** `pyfair` — rejected as unnecessary overhead for a Monte Carlo computation numpy already handles cleanly in this codebase's established style; not run through the legitimacy gate because it is not being recommended for installation.

## Architecture Patterns

### System Architecture Diagram

```
                    TENANT USER (authenticated, existing SPA)
                                    │
                                    ▼
                  ┌──────────────────────────────────────┐
                  │  RiskFormModal.tsx / risk detail view  │
                  │  "Quantify with FAIR" (optional panel) │
                  │  — LEF min/likely/max                  │
                  │  — LM min/likely/max (per category,    │
                  │    or a single blended range for v1)   │
                  └───────────────────┬────────────────────┘
                                      │ api.runFairSimulation(riskId, inputs)
                                      ▼
                  ┌──────────────────────────────────────────────────────┐
                  │  risk_endpoints.py                                    │
                  │  POST /api/risks/{id}/fair-simulation                 │
                  │   └─► validate FairInputs (min ≤ likely ≤ max, V5)    │
                  │   └─► risk_service.run_fair_simulation(...)           │
                  │        (SYNCHRONOUS — no BackgroundTasks, no Celery)  │
                  │        └─► np.random.triangular(min,likely,max,N)     │
                  │             for LEF, same for LM  → N samples         │
                  │        └─► annual_loss = lef_samples * lm_samples     │
                  │        └─► percentiles = np.percentile(annual_loss,   │
                  │             [10,50,90])                               │
                  │        └─► exceedance curve = sorted losses + rank/N  │
                  │   └─► persist fair_inputs + fair_results on the risk  │
                  │        doc (additive fields, tenant-scoped as today)  │
                  │   └─► return updated risk doc                        │
                  └───────────────────┬────────────────────────────────────┘
                                      │
                                      ▼
                        db.risks (existing collection, tenant-scoped)
                        {..., risk_score, inherent_risk_score,           <- Phase 26
                         residual_likelihood, residual_risk_score,       <- Phase 26
                         fair_inputs: {lef:{min,likely,max},             <- Phase 31 (NEW)
                                        lm:{min,likely,max}},
                         fair_results: {mean, p10, p50, p90,
                                        exceedance_curve: [...]}}        <- Phase 31 (NEW)
                                      │
                                      ▼
                  ┌──────────────────────────────────────┐
                  │  RiskRegister.tsx                     │
                  │  — existing Score column (unchanged)  │
                  │  — Residual Score column (Phase 26)   │
                  │  — FAIR badge/column (Phase 31, NEW)  │
                  │    e.g. "$120K–$480K (90% CI)" or      │
                  │    "Not quantified" for risks without  │
                  │    fair_results                        │
                  └────────────────────────────────────────┘
```

### Recommended Project Structure
```
backend/
├── risk_service.py           # MODIFIED — add run_fair_simulation(); additive fair_inputs/fair_results fields
├── risk_endpoints.py         # MODIFIED — add FairInputs request model + POST /api/risks/{id}/fair-simulation route
├── tests/
│   └── test_risk_fair_simulation.py   # NEW — pytest suite (input validation, simulation math, persistence, tenant isolation)

components/
├── RiskFormModal.tsx         # MODIFIED (or a new RiskFairPanel.tsx if line-count pressure — see CLAUDE.md 500-line limit) — optional FAIR input fields
└── RiskRegister.tsx          # MODIFIED — additive FAIR summary column/badge
```

**500-line note (CLAUDE.md compliance):** `risk_service.py` is 82 lines and `risk_endpoints.py` is 75 lines today (both confirmed by direct read this session) — even after Phase 26's additive residual-scoring change and this phase's FAIR addition, both files stay comfortably under the 500-line cap; no file split is anticipated, but the planner should re-check actual line counts after Phase 26 executes (this research was written against Phase 26's plan documents, not its executed code).

### Pattern 1: Additive FAIR sub-document — mirrors Phase 26's inherent/residual precedent exactly
**What:** `fair_inputs` and `fair_results` are new, wholly optional top-level keys on the risk doc, populated only when a user runs a FAIR simulation for that specific risk. No existing field (`risk_score`, `inherent_risk_score`, `residual_risk_score`, `likelihood`, `impact`) is touched, renamed, or removed.
**When to use:** FAIR-01's entire scope.
**Example:**
```python
# Source: pattern mirrors backend/risk_service.py's existing additive style
# (confirmed via 26-03-PLAN.md's identical approach for residual_* fields)
from typing import Optional
import numpy as np

class FairInputs(BaseModel):
    lef_min: float = Field(ge=0)
    lef_likely: float = Field(ge=0)
    lef_max: float = Field(ge=0)
    lm_min: float = Field(ge=0)
    lm_likely: float = Field(ge=0)
    lm_max: float = Field(ge=0)
    iterations: int = Field(default=10000, ge=1000, le=100000)

def run_fair_simulation(inputs: dict) -> dict:
    """Pure function — no I/O, no DB access. Runs synchronously in the request handler."""
    n = inputs.get("iterations", 10000)
    rng = np.random.default_rng()  # np.random.default_rng() is the modern numpy Generator API
    lef_samples = rng.triangular(inputs["lef_min"], inputs["lef_likely"], inputs["lef_max"], n)
    lm_samples = rng.triangular(inputs["lm_min"], inputs["lm_likely"], inputs["lm_max"], n)
    annual_loss = lef_samples * lm_samples
    sorted_losses = np.sort(annual_loss)
    exceedance_curve = [
        {"loss": float(sorted_losses[i]), "probability": float(1 - i / n)}
        for i in range(0, n, max(1, n // 100))  # ~100 points for a chart, not all N
    ]
    return {
        "mean": float(np.mean(annual_loss)),
        "p10": float(np.percentile(annual_loss, 10)),
        "p50": float(np.percentile(annual_loss, 50)),
        "p90": float(np.percentile(annual_loss, 90)),
        "exceedance_curve": exceedance_curve,
    }
```
**Why `np.random.default_rng()` over the legacy `np.random.triangular` module-level function:** the Generator API is numpy's modern, recommended interface (module-level `np.random.*` functions are the legacy `RandomState` API, still supported but not the current best practice) — this codebase's other numpy consumers (`xai_service.py`, `ueba_engine.py`) use array/statistics operations, not random sampling, so there's no existing in-repo precedent to match either way; adopt the modern API for new code. [CITED: numpy.org random Generator documentation]

### Pattern 2: Synchronous computation inside the existing async route — no BackgroundTasks, no Celery
**What:** The Monte Carlo function is a plain (non-async) Python function called directly inside the existing `async def` route handler. FastAPI runs synchronous code in a thread-pool automatically only if it's a `def` (not `async def`) route; since `risk_endpoints.py`'s routes are `async def`, calling a fast synchronous numpy function directly (not via `run_in_threadpool`) is correct and simplest here because the computation is sub-10ms — offloading to a thread pool would add overhead disproportionate to the work.
**When to use:** The FAIR simulation endpoint.
**Example:**
```python
# Source: pattern extends backend/risk_endpoints.py's existing async route shape
@router.post("/{risk_id}/fair-simulation")
async def simulate_fair(
    risk_id: str,
    inputs: FairInputs,
    current_user: TokenData = Depends(get_current_user),
):
    tenant_id = _risk_tenant(current_user)
    results = risk_service.run_fair_simulation(inputs.dict())  # pure, synchronous, ~5-10ms for 10k iterations
    updated = await risk_service.attach_fair_results(risk_id, inputs.dict(), results, tenant_id=tenant_id)
    if not updated:
        raise HTTPException(status_code=404, detail="Risk not found")
    return updated
```

### Anti-Patterns to Avoid
- **Introducing a Celery task (`tasks.py` + `.delay()`) for the Monte Carlo simulation:** Every existing Celery use case in this codebase is I/O-bound or scheduled/periodic; a sub-10ms pure-CPU numpy computation does not need a job queue, and adding one means building a job-status endpoint the frontend has to poll — pure overhead for no latency benefit. Only reconsider if iteration counts or risk-register bulk-recompute needs grow dramatically (see Open Questions).
- **Reconciling or blending the FAIR dollar output with the 1-5×1-5 qualitative `risk_score`/`residual_risk_score`:** There is no standard, defensible mathematical mapping between a dimensionless 1-25 heatmap score and a dollarized annual loss exposure — inventing one would be arbitrary and misleading. Keep them as two independent, parallel views of the same risk (FAIR-01's own wording says "in addition to," not "reconciled with").
- **Adding `pyfair` or any other new PyPI dependency:** `numpy` (already installed, already proven in-repo) is sufficient for this phase's entire computational surface — see Standard Stack → Alternatives Considered.
- **Requiring FAIR inputs on every risk (making the qualitative fields optional instead):** FAIR-01 explicitly says "optionally" — the existing `likelihood`/`impact`/`risk_score` fields must remain the required, always-present baseline; `fair_inputs`/`fair_results` are opt-in per risk, exactly mirroring Phase 26's residual-fields-are-optional-and-default pattern.
- **Running the Monte Carlo inside `create_risk`/`update_risk` unconditionally:** FAIR simulation should be a distinct, explicit action (its own endpoint or an explicit flag in the update payload), not a side effect of every risk save — a risk without FAIR inputs supplied has nothing to simulate.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Random sampling from a min/most-likely/max distribution | A custom PERT/triangular sampler implemented from scratch (inverse-CDF math, etc.) | `numpy.random.Generator.triangular()` (or `.beta()` for a PERT approximation) | numpy's implementation is already vetted, vectorized, and this codebase's established numerical library — reimplementing distribution sampling is a correctness and performance regression with zero benefit |
| Percentile / summary statistics over simulation output | Hand-rolled sorting + manual percentile-index math | `numpy.percentile()`, `numpy.mean()` | Same reasoning — numpy's percentile implementation handles interpolation edge cases correctly; hand-rolling risks off-by-one errors in exactly the kind of number a compliance/risk tool cannot afford to get wrong |
| A dedicated FAIR risk-modeling object system (risk trees, multi-stage LEF decomposition into Threat Event Frequency × Vulnerability, etc.) | `pyfair` or a custom multi-class FAIR ontology | A flat LEF×LM two-factor model (the simplified/beginner-appropriate FAIR shape) | FAIR-01's requirement text describes exactly "loss magnitude range × event frequency" — the full Open FAIR ontology (TEF, Vulnerability, Primary/Secondary Loss, 6 loss forms) is a materially larger scope than what's asked; the two-factor simplification is a legitimate, commonly-used entry point to FAIR (many FAIR tools offer a "simple" vs. "advanced" mode) and matches this codebase's "nothing more than asked" convention |

**Key insight:** Every piece FAIR-01 needs — random sampling, percentile computation, vectorized array math — is already inside `numpy`, already a dependency, already used synchronously in this exact codebase's request-serving code. This phase is composition (extend two existing 75-82 line files additively) plus one bounded, well-understood numerical algorithm, not a new subsystem.

## Runtime State Inventory

> Not applicable — this is a purely additive greenfield feature (new optional fields, new endpoint), not a rename/refactor/migration. No existing data, service config, OS-registered state, secrets, or build artifacts reference "FAIR" today (confirmed by `grep -ri "fair" backend/*.py` returning no domain hits prior to this phase). Omitted per the greenfield exception.

## Common Pitfalls

### Pitfall 1: Colliding with Phase 26's in-flight additive changes to the same two files
**What goes wrong:** Phase 26 (`26-03-PLAN.md`/`26-05-PLAN.md`) is planned but **not yet executed** as of this research. It adds `inherent_risk_score`/`residual_likelihood`/`residual_impact`/`residual_risk_score` to `risk_service.py`'s `create_risk`/`update_risk` and a Residual Score column to `RiskRegister.tsx` plus residual inputs to `RiskFormModal.tsx` — the exact same four files this phase touches. If Phase 31 is planned/executed before Phase 26, the file line numbers and read_first anchors in this research (and any plan built from it) will be stale, and a naive merge could silently drop or corrupt Phase 26's residual fields.
**Why it happens:** ROADMAP.md lists this phase's dependency as "Phase 26 (extends the risk register work from that phase)" but v3.0 phases are being planned sequentially by phase number, not strictly gated on prior-phase *execution* — Phase 26 could still be unexecuted when Phase 31 plans or even executes.
**How to avoid:** The plan for this phase MUST re-read `risk_service.py`/`risk_endpoints.py`/`RiskRegister.tsx`/`RiskFormModal.tsx` fresh at execution time (not rely solely on this research's line-number references, which are anchored to the **pre-Phase-26** file contents read this session) and confirm whether Phase 26's residual fields are present before writing FAIR additions. If Phase 26 has not executed yet, this phase's plan should either (a) explicitly sequence after Phase 26's execution, or (b) write FAIR additions in a way that is independent of exact line numbers (append-only edits, not line-anchored replacements) so execution order doesn't matter.
**Warning signs:** A `grep -q "residual_risk_score" backend/risk_service.py` check that the plan assumes will pass returns nothing, meaning Phase 26 hasn't landed yet and any line-number-anchored task instructions in a naively-generated plan would target the wrong lines.

### Pitfall 2: Triangular distribution parameter ordering / invalid min ≤ likely ≤ max
**What goes wrong:** `numpy.random.Generator.triangular(left, mode, right, size)` raises a `ValueError` if `left > mode` or `mode > right` (numpy enforces `left <= mode <= right`) — or silently produces nonsensical output if the caller passes the arguments in the wrong order relative to their variable names.
**Why it happens:** LEF and LM each have three independent (min, likely, max) inputs; a swapped pair (e.g., `lm_max` typed into the `lm_min` field, or a backend bug passing `(max, likely, min)` positionally) is an easy transcription error, and unlike the existing `likelihood`/`impact` 1-5 `Field(ge=1, le=5)` pattern, these are open-ended floats with no natural upper bound to catch typos.
**How to avoid:** Validate `min <= likely <= max` explicitly for both LEF and LM in the `FairInputs` Pydantic model (a `@model_validator` in pydantic v2, or a manual check in the route/service before calling `numpy`) and return a 422 with a clear message rather than letting numpy's `ValueError` surface as an unhandled 500. This is explicitly called out in the phase's own additional_context ("min ≤ most-likely ≤ max") and is a V5 Input Validation requirement, not optional polish.
**Warning signs:** A 500 error (not a clean 422) when a user submits `lef_min=10, lef_likely=5, lef_max=1`; or a simulation silently returning implausible results (e.g., negative-seeming loss ranges) for a rearranged min/max pair.

### Pitfall 3: Iteration count as an unbounded user input (resource-exhaustion vector)
**What goes wrong:** If `iterations` is accepted from the client with no upper bound, a malicious or careless caller could request an extremely large simulation (e.g., 100 million iterations) that consumes significant CPU/memory synchronously inside a request handler — since this phase deliberately runs the simulation synchronously (Pattern 2), an unbounded iteration count directly translates to a request-thread DoS vector, which is a materially different risk profile than if the work were queued.
**Why it happens:** "More iterations = more statistically stable percentiles" is true in principle, but the phase's own design brief explicitly assumes "a few thousand iterations" completing in low-hundreds-of-milliseconds — nothing in the requirement asks for user-controlled iteration counts at all, and if offered, it needs a hard ceiling.
**How to avoid:** Either omit `iterations` from the client-facing request model entirely (hardcode a sane default like 10,000 server-side), or if exposed, apply `Field(ge=1000, le=100000)` (or a similarly conservative ceiling) exactly as shown in Pattern 1's example — this is the same V5 Input Validation discipline Phase 26 applied to `residual_likelihood`/`residual_impact`'s `Field(ge=1, le=5)`.
**Warning signs:** No upper-bound `Field` constraint on any client-supplied iteration/sample-count parameter.

### Pitfall 4: Forgetting the tenant filter on the new FAIR-simulation endpoint
**What goes wrong:** A new `POST /api/risks/{risk_id}/fair-simulation` endpoint that looks up the risk by `risk_id` alone (without the existing tenant-scoping filter `update_risk`/`delete_risk` already apply) would let a user in tenant A attach FAIR results to — or read simulation output for — a risk belonging to tenant B, simply by guessing/enumerating a `risk_id`.
**Why it happens:** New endpoints are an easy place to forget to copy an existing, already-correct security pattern, especially when the "interesting" part of the code (the numpy math) draws attention away from the boilerplate (the tenant filter).
**How to avoid:** Route the FAIR-simulation persistence through the exact same tenant-filtered lookup/update path `update_risk` already uses (`filt = {"id": risk_id}` plus `filt["tenantId"] = tenant_id` unless the caller's role is in `_RISK_SUPER_ROLES`) — do not write a new, separate risk lookup for this endpoint.
**Warning signs:** The new endpoint's DB query for the target risk does not include `tenantId` in its filter, or role-based super-admin bypass logic is duplicated instead of reused from `_RISK_SUPER_ROLES`/`_risk_tenant`.

## Code Examples

Verified patterns from this codebase (read in full this session):

### Existing tenant-scoped update pattern (the pattern the FAIR endpoint's persistence must reuse — Pitfall 4)
```python
# Source: backend/risk_service.py lines 58-70 (update_risk, existing, read this session)
async def update_risk(self, risk_id: str, updates: Dict[str, Any], tenant_id: Optional[str] = None, role: str = "") -> Optional[Dict]:
    db = self._db()
    filt: Dict[str, Any] = {"id": risk_id}
    if role not in _RISK_SUPER_ROLES:
        filt["tenantId"] = tenant_id
    existing = await db.risks.find_one(filt, {"_id": 0})
    if not existing:
        return None
    merged = {**existing, **updates, "updated_at": datetime.now(timezone.utc).isoformat()}
    if "likelihood" in updates or "impact" in updates:
        merged["risk_score"] = merged.get("likelihood", existing["likelihood"]) * merged.get("impact", existing["impact"])
    await db.risks.replace_one(filt, merged)
    return merged
```

### Existing synchronous numpy usage inside request-adjacent code (confirms the sync-in-process pattern is already established)
```python
# Source: backend/xai_service.py (import at line 25, usage at lines 187/194, read this session)
import numpy as np
# ...
for i in np.argsort(importances)[::-1]:
    ...
x_row = np.array([[values[f] for f in _FEATURES]])
```
No `BackgroundTasks`, no Celery `.delay()` — numpy computation runs directly inline, confirming this is the established, proven pattern for bounded numerical work in this codebase, not a new architectural choice this phase would be introducing.

### Existing Celery task shape (for contrast — NOT the pattern to follow for this phase's Monte Carlo)
```python
# Source: backend/tasks.py line 58 (execute_remediation_script, existing, read this session)
@celery_app.task(name='tasks.execute_remediation_script')
def execute_remediation_script(script_content: str, script_type: str):
    ...  # long-running, I/O-bound (agent RPC), genuinely benefits from async job handling
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|---------------|--------|
| Single qualitative `risk_score` (likelihood × impact, 1-25 scale) | Qualitative score (unchanged) + optional residual score (Phase 26, in-flight) + optional FAIR-style quantitative dollar range (Phase 31, this research) | This phase (31), building on Phase 26 | First time this platform expresses risk in dollar terms rather than only an ordinal heatmap position — enables prioritization conversations with stakeholders who think in budget/loss terms, without discarding the existing heatmap workflow |
| N/A — no prior Monte Carlo/statistical-simulation pattern for user-facing risk data in this codebase | Synchronous, `numpy`-vectorized Monte Carlo, following the same "numpy already proven, no new dependency" pattern as `xai_service.py`/`ueba_engine.py` | This phase | Establishes a reusable in-repo precedent (a bounded, fast numerical simulation running synchronously in the request cycle) other future phases needing similar statistics can clone, rather than defaulting to a job queue for CPU-bound-but-fast work |

**Deprecated/outdated:** Nothing is deprecated by this phase — it is purely additive.

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | A simplified two-factor FAIR model (single LEF × single LM, each as a min/likely/max triangular distribution) is the correct scope for FAIR-01, rather than the full Open FAIR ontology (Threat Event Frequency × Vulnerability decomposing LEF; Primary/Secondary Loss × 6 loss forms decomposing LM) | Don't Hand-Roll, Architecture Patterns → Pattern 1 | If the actual product intent is full Open-FAIR-Institute-certified rigor (e.g., for an audit or certification context), this under-delivers on ontological completeness; the fix is a moderate expansion (add TEF/Vulnerability as two more triangular inputs multiplying into LEF) rather than a rewrite, since the same Monte Carlo core applies — flagged as Open Question 1 |
| A2 | FAIR results are stored as a single current snapshot on the risk doc (`fair_inputs`/`fair_results`), not a versioned history of every simulation run over time | Standard Stack → Alternatives Considered, Architecture Patterns → Pattern 1 | If stakeholders want to track how a risk's dollar exposure trended over time (e.g., after each mitigation), a snapshot-only model loses that history; the fix is a straightforward additive `risk_fair_simulations` collection insert alongside the current-snapshot update — flagged as Open Question 2 |
| A3 | The FAIR dollar output is displayed alongside, and explicitly not reconciled/blended with, the existing 1-25 qualitative `risk_score`/`residual_risk_score` | Architecture Patterns → Anti-Patterns | Low risk — this follows directly from FAIR-01's own wording ("in addition to") and there is no academically standard LEF/LM-to-1-25-scale conversion to invent even if reconciliation were wanted |
| A4 | `numpy.random.triangular` (via the modern `Generator` API) is sufficient distributional fidelity for v1, rather than a Beta-PERT distribution | Architecture Patterns → Pattern 1 | Low-to-moderate risk — triangular is a legitimate, standard-compliant FAIR input shape, but some FAIR practitioners/tools default to PERT for its smoother, more realistic peak-weighting; upgrading later only requires swapping `rng.triangular(...)` for a PERT-reparameterized `rng.beta(...)` call, no schema change — flagged as Open Question 3 |
| A5 | The FAIR-simulation endpoint runs synchronously inside the existing async route handler (no `BackgroundTasks`, no Celery `.delay()`) at a default of ~10,000 iterations | Architecture Patterns → Pattern 2, Common Pitfalls → Pitfall 3 | Low risk at the stated iteration count (single-digit milliseconds, confirmed by the general Monte Carlo/numpy performance characteristics cited in Sources); would need revisiting only if iteration counts grow by orders of magnitude or bulk/portfolio-wide re-simulation across hundreds of risks becomes a requirement |

**If this table is empty:** N/A — see entries above; all are flagged as Open Questions where a human product decision materially changes scope.

## Open Questions (RESOLVED)

1. **Is a simplified two-factor FAIR model (LEF × LM, each min/likely/max) the right scope, or does the product need the fuller Open FAIR ontology (TEF × Vulnerability → LEF; Primary/Secondary Loss × loss forms → LM)?** (RESOLVED)
   - What we know: FAIR-01's requirement text says "loss magnitude range × event frequency" — literally the two-factor shape.
   - What's unclear: Whether "FAIR-style" in the phase goal implies stakeholders expect Open-FAIR-Institute rigor (e.g., for a security/audit team already trained on the full methodology) or just a lightweight quantitative alternative to the heatmap.
   - Recommendation: Build the two-factor model first.
   - **RESOLVED: adopting the recommendation.** The requirement text literally specifies the two-factor shape ("loss magnitude range × event frequency") — building the fuller Open FAIR ontology would be scope creep beyond what FAIR-01 actually asks for, contrary to CLAUDE.md's "do what has been asked; nothing more." Two-factor model it is; the Monte Carlo core supports later expansion without a schema rewrite if ever needed.

2. **Should FAIR results be a single current snapshot per risk, or a timestamped history of every simulation run?** (RESOLVED)
   - What we know: FAIR-01's wording implies "a risk can optionally be scored," not "a risk can track its scoring history over time."
   - What's unclear: Whether re-running a simulation after updating mitigation plans should overwrite the prior result or preserve it for trend analysis.
   - **RESOLVED: adopting the recommendation.** Single current-snapshot `fair_results` field on the risk doc — matches Phase 29's "no versioning needed" precedent for a similarly-shaped feature. A history collection is a clean additive follow-up if trend-over-time is ever confirmed as wanted.

3. **Triangular vs. PERT (Beta-PERT) distribution for LEF/LM sampling?** (RESOLVED)
   - What we know: Both are standard, accepted FAIR input distribution shapes; triangular is simpler to implement and explain to a user filling in three numbers.
   - **RESOLVED: adopting the recommendation.** Triangular for v1 — lower implementation/explanation complexity, same Monte Carlo scaffolding, and a one-line, no-schema-impact change to PERT later if ever needed. Purely a statistical implementation detail, not a product-visible decision.

4. **Does the FAIR output need to numerically reconcile with, or influence, the existing qualitative `risk_score`/`residual_risk_score` in any way?** (RESOLVED)
   - What we know: FAIR-01 says "in addition to," and this codebase's convention (Phase 26's residual work) treats every new scoring dimension as strictly additive/parallel, never derived from or feeding back into another.
   - **RESOLVED: adopting the recommendation.** Fully independent — no conversion formula, no auto-suggestion. Matches both the requirement's literal "in addition to" wording and the established Phase 26 additive-scoring convention.

5. **Loss magnitude input granularity: a single blended LM range per risk, or per-loss-category ranges?** (RESOLVED)
   - What we know: The phase's additional_context describes "loss magnitude range" (singular) — the simplest reading is one LM range per risk.
   - **RESOLVED: adopting the recommendation.** Single blended LM range — matches Q1's two-factor scope resolution and the singular wording. Per-category breakdown remains a natural additive expansion (sum N independent triangular samples) if later required.

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| `numpy` | Monte Carlo sampling, percentile computation | ✓ declared in `backend/requirements.txt` and imported/used in 7 other backend files [VERIFIED: `backend/requirements.txt`, `grep` across backend this session] — **not currently importable in the ad-hoc shell environment probed this session** (`ModuleNotFoundError` when run outside the project's `backend/venv`) [ASSUMED resolved: the project's actual `backend/venv` — confirmed present at `backend/venv` this session — almost certainly has it installed per `requirements.txt`; this session's bare `python3 -c "import numpy"` ran outside that venv] | `>=1.24.0,<3.0.0` | None needed — verify by activating `backend/venv` (or the project's actual runtime environment) before assuming numpy is missing; do not add a redundant numpy install step to the plan without first confirming the venv state |
| `pandas` | Optional convenience for exceedance-curve table construction | ✓ declared in `backend/requirements.txt` [VERIFIED] | `>=2.1.0,<3.0.0` | Not required — pure-numpy exceedance-curve construction (3-line alternative, shown in Pattern 1) avoids the dependency in this specific code path |
| MongoDB (via Motor) | Persisting `fair_inputs`/`fair_results` on the risk doc | ✓ (assumed running — used by every other phase in this milestone) [ASSUMED — not independently re-probed this session, consistent with Phase 29's research] | — | — |

**Missing dependencies with no fallback:** none identified.
**Missing dependencies with fallback:** none — numpy/pandas already declared; the apparent `ModuleNotFoundError` observed this session is an artifact of probing outside the project's own `backend/venv`, not an actual missing dependency. The plan's execution step should run tests via the project's normal `pytest`/venv invocation (matching every other phase's test commands), which will resolve numpy correctly.

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest (project-standard; `pytest.ini` at repo root) [VERIFIED: `pytest.ini` read this session — `testpaths = . backend`, `asyncio_mode = auto`] |
| Config file | `pytest.ini` (repo root) |
| Quick run command | `cd backend && python -m pytest tests/test_risk_fair_simulation.py -x` |
| Full suite command | `cd backend && python -m pytest tests/ -q` |
| Frontend framework | Vitest (`"test": "vitest run"` in `package.json`) [VERIFIED: `package.json` read this session] |

### Phase Requirements → Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| FAIR-01 | Submitting valid FAIR inputs (LEF/LM min/likely/max) to the simulation endpoint returns `fair_results` with `mean`/`p10`/`p50`/`p90`/`exceedance_curve` and persists them on the risk doc | integration | `pytest backend/tests/test_risk_fair_simulation.py -k valid_simulation -x` | ❌ Wave 0 |
| FAIR-01 | `min > likely` or `likely > max` for either LEF or LM returns 422, not a 500 from an unhandled numpy `ValueError` (Pitfall 2) | unit | `pytest backend/tests/test_risk_fair_simulation.py -k invalid_range -x` | ❌ Wave 0 |
| FAIR-01 | Iteration count (if client-exposed) is bounded — a value above the max ceiling returns 422 | unit | `pytest backend/tests/test_risk_fair_simulation.py -k iteration_bound -x` | ❌ Wave 0 |
| FAIR-01 | The FAIR-simulation endpoint is tenant-scoped exactly like `update_risk`/`delete_risk` — a risk in tenant B is unreachable (404, not data leak) from a tenant A caller (Pitfall 4) | unit | `pytest backend/tests/test_risk_fair_simulation.py -k tenant_isolation -x` | ❌ Wave 0 |
| FAIR-01 | A risk with no `fair_inputs`/`fair_results` submitted (i.e., FAIR is never invoked for it) still returns/persists its existing qualitative fields unchanged — the feature is genuinely optional | unit | `pytest backend/tests/test_risk_fair_simulation.py -k optional_no_regression -x` | ❌ Wave 0 |
| FAIR-01 | Monte Carlo output is statistically sane for a known-simple input (e.g., LEF fixed at 1, LM fixed at 100 → mean annual loss ≈ 100, low variance) — a smoke test against the math itself, not just the plumbing | unit | `pytest backend/tests/test_risk_fair_simulation.py -k math_sanity -x` | ❌ Wave 0 |

### Sampling Rate
- **Per task commit:** `cd backend && python -m pytest tests/test_risk_fair_simulation.py -x`
- **Per wave merge:** `cd backend && python -m pytest tests/ -q`
- **Phase gate:** Full suite green before `/gsd-verify-work`; additionally, an actual `TestClient` HTTP call through `POST /api/risks/{id}/fair-simulation` (not just a direct call to `run_fair_simulation()`), matching this codebase's established practice (per the Phase 25/`response: Response` and Phase 29 precedents) of catching route-wiring bugs that pure unit tests of the underlying function cannot.

### Wave 0 Gaps
- [ ] `backend/tests/test_risk_fair_simulation.py` — new file; clone the `_col`/`_db`/`_user`/`_app` helper block from `backend/tests/test_automation_and_baa.py` (same helper convention `26-03-PLAN.md`'s `test_risk_inherent_residual.py` also uses) per this repo's per-file test-helper convention
- [ ] Framework install: none — pytest already present and configured; numpy/pandas already declared dependencies (see Environment Availability note on venv)

## Security Domain

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-------------------|
| V2 Authentication | yes | New FAIR endpoint sits behind the existing `get_current_user` dependency, unchanged from every other route in `risk_endpoints.py` |
| V3 Session Management | no | No new session-management surface introduced |
| V4 Access Control | yes | The FAIR-simulation endpoint MUST reuse `risk_service`'s existing tenant-filter/`_RISK_SUPER_ROLES` pattern for its risk lookup — see Pitfall 4; no new RBAC role is needed (FAIR quantification is available to whoever can already create/update a risk) |
| V5 Input Validation | yes — the central risk of this phase | `FairInputs` MUST validate `min <= likely <= max` for both LEF and LM (Pitfall 2) and bound any client-exposed iteration count (Pitfall 3); all six numeric fields should reject negative values (`Field(ge=0)`) since a negative frequency or loss magnitude is meaningless |
| V6 Cryptography | no | No cryptographic material introduced |

### Known Threat Patterns for this stack

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|----------------------|
| Cross-tenant FAIR-result read/write via crafted `{risk_id}` on the new endpoint | Tampering / Information Disclosure | Reuse `update_risk`'s existing tenant-filter pattern (`filt["tenantId"] = tenant_id` unless `_RISK_SUPER_ROLES`) for the FAIR-simulation risk lookup — do not write a separate, unscoped lookup (Pitfall 4) |
| Out-of-range or inverted min/likely/max causing an unhandled `numpy.ValueError` → 500 (information leakage via stack trace, or a poor UX signal) | Tampering | Explicit `min <= likely <= max` validation in the Pydantic request model, returning a clean 422 before numpy ever runs (Pitfall 2) |
| Unbounded client-supplied iteration count causing synchronous CPU/memory exhaustion on the request thread | Denial of Service | Hardcode a server-side default (recommended) or apply `Field(ge=1000, le=100000)` if client-exposed (Pitfall 3) — this is a materially higher-stakes control here than in a typical endpoint precisely *because* the computation is deliberately synchronous |
| Extremely large or malformed float inputs (e.g., `1e308`) causing numeric overflow in the loss-magnitude multiplication, producing `inf`/`NaN` results silently persisted and displayed | Tampering | Apply a sane practical upper bound to LM inputs (e.g., `Field(le=1_000_000_000)` — one billion dollars, adjustable) in addition to the ordering check; consider an explicit `np.isfinite()` check on the computed results before persisting, refusing to save `NaN`/`inf` output |

## Sources

### Primary (HIGH confidence)
- `backend/risk_service.py` (full file read, this session) — confirmed exact current `Risk` model, `create_risk`/`update_risk`/`delete_risk` shape, tenant-filter pattern, `_RISK_SUPER_ROLES`
- `backend/risk_endpoints.py` (full file read, this session) — confirmed `RiskCreate`/`RiskUpdate` request models, `_risk_tenant` helper, route shapes
- `.planning/phases/26-vendor-and-risk-data-completeness/26-03-PLAN.md` (full file read, this session) — Phase 26's forward-contract for `inherent_risk_score`/`residual_*` fields this phase must compose with, not conflict with
- `.planning/phases/26-vendor-and-risk-data-completeness/26-05-PLAN.md` (full file read, this session) — Phase 26's forward-contract for the frontend Residual Score column / form inputs
- `components/RiskRegister.tsx` (full file read, this session) — confirmed the four existing `risk_score` reads (Critical stat, High-priority stat, level lookup, Score cell) this phase must not disturb
- `components/RiskFormModal.tsx` (full file read, this session) — confirmed existing `formData`/`handleSubmit` shape for the Likelihood/Impact inputs to extend
- `backend/requirements.txt` (read this session) — confirmed `numpy>=1.24.0,<3.0.0` and `pandas>=2.1.0,<3.0.0` already present; confirmed `scipy` absent
- `backend/xai_service.py`, `backend/ueba_engine.py`, `backend/automl_service.py`, `backend/ml_service.py`, `backend/ml_service_predict.py`, `backend/model_retraining_service.py`, `backend/train_ml_models.py` (grep + partial reads, this session) — confirmed numpy is already imported and used synchronously in request-adjacent backend code, establishing the sync-in-process precedent this research recommends following
- `backend/celery_app.py`, `backend/tasks.py` (read this session) — confirmed the existing task-queue infrastructure and that every current use case is I/O-bound or scheduled, contrasted against this phase's bounded-CPU computation
- `backend/router_registry.py` (grep this session) — confirmed `risk_endpoints` is already registered (line 147); no new router-registration step needed, only new routes on the existing router
- `backend/tests/test_automation_and_baa.py` (read this session) — the `_col`/`_db`/`_user`/`_app` test-helper convention this phase's new test file should clone
- `services/apiService.ts` (grep this session) — confirmed `fetchRisks`/`createRisk` shape for the frontend API-call convention a new `runFairSimulation` function would follow
- `.planning/config.json` (read this session) — confirmed `nyquist_validation: true` and `security_enforcement: true`, both applicable to this phase
- `.planning/phases/29-public-trust-center/29-RESEARCH.md` (read this session) — used as the structural/format template for this document, and as the source of the "no versioning needed for a single-snapshot feature" reasoning applied to Assumption A2

### Secondary (MEDIUM confidence)
- [Open FAIR™ Risk Analysis Process Guide — The Open Group](https://pubs.opengroup.org/security/openfair-process-guide/) (WebSearch, this session) — confirms LEF/LM as the two top-level FAIR factors and Monte Carlo as the standard final-stage methodology
- [Factor analysis of information risk — Wikipedia](https://en.wikipedia.org/wiki/Factor_analysis_of_information_risk) (WebSearch, this session) — general FAIR taxonomy background
- [The beta-PERT distribution — RiskAMP](https://www.riskamp.com/beta-pert/) (WebSearch, this session) — PERT vs. triangular distribution shape comparison, informing Assumption A4/Open Question 3
- General numpy/Python Monte Carlo simulation practice (WebSearch, this session, aggregated across multiple sources — [Monte Carlo Simulation and Triangular Distribution in Python — Medium](https://medium.com/@polanitzer/monte-carlo-simulation-and-triangular-distribution-in-python-predict-next-years-sales-volume-d37f419f2dfc), [Risk Engineering: Monte Carlo simulation for project risk assessment](https://risk-engineering.org/notebook/monte-carlo-project-risk.html)) — confirms `numpy`-based triangular-distribution Monte Carlo is standard, well-understood practice, not a novel technique this research is inventing

### Tertiary (LOW confidence)
- None used as authoritative for any Standard Stack or Architecture recommendation — all architectural claims about this specific codebase are grounded in direct, in-session file reads; all FAIR-methodology claims are grounded in the Open Group's own process guide (Secondary, MEDIUM) rather than any single unverified blog source.

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — no new dependencies; numpy's existing in-repo usage confirmed by direct grep/read across 7 files this session; `pyfair` alternative explicitly evaluated and rejected with reasoning
- Architecture: HIGH for the backend extension mechanics, tenant-isolation reuse, and sync-vs-async decision (all directly grounded in this codebase's existing, proven patterns); MEDIUM for the exact FAIR input granularity (single vs. per-category LM, two-factor vs. full ontology) and results-persistence shape (snapshot vs. history), both flagged as Open Questions needing a human product decision
- Pitfalls: HIGH — Pitfall 1 (Phase 26 sequencing collision) is directly observed from this session's own file reads of Phase 26's not-yet-executed plan documents; Pitfall 2/3/4 follow directly from numpy's documented API contract and this codebase's own established tenant-isolation pattern

**Research date:** 2026-07-08
**Valid until:** 30 days (stable internal codebase patterns; re-verify Phase 26's execution status before planning, since this research explicitly assumes its not-yet-executed forward contract — see Pitfall 1)
