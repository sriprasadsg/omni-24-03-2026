# Phase 31-02: FAIR Risk Quantification Implementation Summary

## Changes Implemented

### 1. FAIR Simulation API (`services/apiService.ts`)
- Added `runFairSimulation(riskId, inputs)` function to `services/apiService.ts`.
- This function performs a POST request to `/api/risks/{riskId}/fair-simulation` and returns the updated `Risk` object, consistent with the `createRisk` pattern.

### 2. Type Extensions (`types.ts`)
- Updated the `Risk` interface to include optional FAIR data fields:
  - `fair_inputs`: Stores input parameters (LEF min/likely/max, LM min/likely/max, iterations).
  - `fair_results`: Stores simulation outputs (mean, percentiles, and loss-exceedance curve data).

### 3. New FAIR Component (`components/RiskFairModal.tsx`)
- Created `RiskFairModal.tsx` as a standalone modal for quantifying an existing risk.
- Implements:
  - Six numeric inputs for LEF and LM.
  - Client-side UX validation (min/likely/max ordering).
  - API call trigger to `runFairSimulation`.
  - Display of simulation results, including loss-exceedance metrics and a summary.

### 4. Risk Register Update (`components/RiskRegister.tsx`)
- Integrated FAIR quantification into `RiskRegister.tsx`:
  - Added a "FAIR" column to the risk table displaying a compact confidence interval summary for quantified risks, or "Not quantified" otherwise.
  - Added a "Quantify with FAIR" button to the row Actions cell, which opens `RiskFairModal` for that risk.
  - Implemented `onComplete` refresh to update the table immediately after a simulation.
  - Preserved all existing functionality (Edit, Delete, Heatmap, etc.) without modification to the `RiskFormModal` create-only flow.

## Verification
- Performed visual review of the updated `RiskRegister.tsx` table and `RiskFairModal.tsx` layout.
- Confirmed type safety across all modified files.
- Ensured no regressions in the pre-existing risk management UI.

---
Phase 31-02 complete.
