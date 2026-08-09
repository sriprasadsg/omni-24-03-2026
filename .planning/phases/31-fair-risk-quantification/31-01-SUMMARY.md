# Plan 31-01 Summary: FAIR Risk Quantification

## Overview
Implemented the backend FAIR (Factor Analysis of Information Risk) quantitative layer. This includes a synchronous Monte Carlo simulation engine and a tenant-aware persistence mechanism, exposed through a validated API endpoint.

## Implementation Details

### `backend/risk_fair_service.py`
- Implemented `run_fair_simulation(inputs)` using numpy's `triangular` distribution.
- Added a `_sample_triangular` helper to handle degenerate cases (min=max).
- Implemented `RiskService.attach_fair_results` to persist FAIR inputs and results while enforcing tenant isolation, mirroring existing risk update patterns.
- Extended the `Risk` Pydantic model to include `fair_inputs` and `fair_results` as optional fields.

### `backend/risk_fair_endpoints.py`
- Created `FairInputs` Pydantic model with comprehensive validation:
  - Range constraints (`ge=0`, `le=1_000_000_000` for LM).
  - Iteration ceiling (`ge=1000`, `le=100000`).
  - `@model_validator` ensuring `min <= likely <= max` for both LEF and LM inputs.
- Created `POST /api/risks/{risk_id}/fair-simulation` route:
  - Enforces tenant-scoping.
  - Maps `ValueError` (from validator or simulation) to 422 HTTP status.
  - Maps missing risks to 404.

### `backend/router_registry.py`
- Registered `risk_fair_endpoints` to expose the new functionality via `/api/risks/{risk_id}/fair-simulation`.

## Testing & Verification
- Created `tests/test_risk_fair.py` implementing 6 test cases:
  1. `test_math_sanity`: Verifies simulation accuracy for known inputs.
  2. `test_valid_simulation`: Confirms 200 OK and data persistence.
  3. `test_invalid_range`: Confirms 422 for bad LEF/LM ordering.
  4. `test_iteration_bound`: Confirms 422 for excessive iterations.
  5. `test_tenant_isolation`: Confirms 404 and tenant filtering for cross-tenant access.
  6. `test_optional_no_regression`: Confirms existing risks remain unchanged when no FAIR simulation is run.
- All tests passed, ensuring full compliance with FAIR-01 requirements.
