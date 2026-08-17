"""FAIR (Factor Analysis of Information Risk) Monte Carlo simulation engine.

Pure-computation layer: given Loss Event Frequency (LEF) and Loss Magnitude (LM)
three-point estimates, run a Monte Carlo simulation over triangular distributions
and return annualized-loss statistics plus a loss exceedance curve.

Persistence lives in risk_service.RiskService.attach_fair_results; this module holds
no database state so it stays trivially unit-testable.
"""
from typing import Dict, Any, List
import numpy as np

# Exceedance-curve sample points, expressed as percentiles of the simulated
# annual-loss distribution. Highest loss first so the UI's "Top Risks" slice
# reads worst-case → best-case.
_EXCEEDANCE_PERCENTILES = [99, 95, 90, 75, 50]


def _sample_triangular(rng: np.random.Generator, lo: float, mode: float, hi: float, n: int) -> np.ndarray:
    """Draw n triangular samples, degrading gracefully when the range collapses.

    numpy's triangular requires lo <= mode <= hi and lo < hi; a point estimate
    (lo == hi) is a valid FAIR input meaning "no uncertainty", so return a constant.
    """
    if hi <= lo:
        return np.full(n, lo, dtype=float)
    mode = min(max(mode, lo), hi)
    return rng.triangular(lo, mode, hi, n)


def run_fair_simulation(inputs: Dict[str, Any]) -> Dict[str, Any]:
    """Run the FAIR Monte Carlo simulation.

    inputs: lef_min/lef_likely/lef_max (events/year), lm_min/lm_likely/lm_max (USD),
    iterations (sample count). Ordering and bounds are validated upstream by the
    FairInputs Pydantic model; this raises ValueError only on structurally bad data.

    Returns: {mean, p10, p50, p90, exceedance_curve: [{loss, probability}]}.
    """
    iterations = int(inputs.get("iterations", 10000))
    if iterations < 1:
        raise ValueError("iterations must be >= 1")

    rng = np.random.default_rng()
    lef = _sample_triangular(
        rng, float(inputs["lef_min"]), float(inputs["lef_likely"]), float(inputs["lef_max"]), iterations
    )
    lm = _sample_triangular(
        rng, float(inputs["lm_min"]), float(inputs["lm_likely"]), float(inputs["lm_max"]), iterations
    )

    # Annualized loss = expected events per year × loss per event.
    annual_loss = np.clip(lef, 0.0, None) * np.clip(lm, 0.0, None)

    p10, p50, p90 = (float(x) for x in np.percentile(annual_loss, [10, 50, 90]))

    exceedance_curve: List[Dict[str, float]] = []
    seen_losses = set()
    for pct in _EXCEEDANCE_PERCENTILES:
        loss = float(np.percentile(annual_loss, pct))
        loss_rounded = round(loss)
        if loss_rounded in seen_losses:
            continue
        seen_losses.add(loss_rounded)
        probability = float(np.mean(annual_loss >= loss))
        exceedance_curve.append({"loss": loss_rounded, "probability": round(probability, 4)})

    return {
        "mean": float(np.mean(annual_loss)),
        "p10": p10,
        "p50": p50,
        "p90": p90,
        "exceedance_curve": exceedance_curve,
    }
