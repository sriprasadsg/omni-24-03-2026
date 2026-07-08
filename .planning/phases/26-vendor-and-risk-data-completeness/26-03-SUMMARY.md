---
plan: 03
phase: 26
status: complete
---
# SUMMARY — 26-03 Inherent vs Residual Risk Scoring

- Added additive residual fields to `risk_service.py`
  - `inherent_likelihood`, `inherent_impact`, `inherent_risk_score`
  - `residual_likelihood`, `residual_impact`, `residual_risk_score`
- `create_risk` populates both inherent and residual scores (residual defaults to inherent if omitted)
- `update_risk` recomputes residual score when residual inputs change
- Kept `risk_score` field unchanged (additive-only — no rename/removal)
- Added residual fields to `RiskCreate` and `RiskUpdate` Pydantic models in `risk_endpoints.py`
- Created `backend/tests/test_risk_inherent_residual.py` (TDD)