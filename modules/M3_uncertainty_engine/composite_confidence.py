"""
composite_confidence.py — M3: Confidence Component Scorer
===========================================================
Computes four transparent confidence axes per grid cell per run.

REJECTED DESIGN (§7): confidence = 0.4·model + 0.3·data + 0.25·… 
Reason: arbitrary weights are indefensible and conflate four different questions.

ADOPTED DESIGN:
  p  — predictive probability (calibrated)           — from M2
  DQ — data quality (input completeness)             — computed here
  F  — freshness (recency of dynamic inputs)         — computed here
  S  — stability (wobble under input perturbation)   — computed here

  confidence = p · g(DQ, F)
  where g(DQ, F) = DQ · F  (multiplicative penalty, bounded [0,1])
  Justification: missing/stale data bounds confidence from above regardless of p;
  multiplication is the minimal function with that property.

  S is displayed separately — never collapsed into confidence.

MEANING:
  p         answers "how likely is this cell to slide?"
  confidence answers "how much should we ACT on p here?"
  They are not interchangeable. Both are displayed in the UI.

Note: confidence does NOT replace p for the model evaluation metrics.
      It is an operational annotation for decision makers.

Output per cell:
  {cell_id, p, confidence, dq, f, s, is_synthetic}
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd
from loguru import logger

from config.aoi import (
    DATA_PROCESSED, DATA_RUNS,
    FRESHNESS_TAU_DAYS, FRESHNESS_FRESH_HOURS,
)


# ── DQ: Data Quality ──────────────────────────────────────────────────────────

def compute_dq(
    dem_valid: np.ndarray,
    rain_valid: np.ndarray,
) -> np.ndarray:
    """
    Data Quality score per cell: product of source validity masks.

    Sources and their contributions:
      - DEM valid (Copernicus coverage):       binary 0/1
      - Rainfall valid (IMD coverage):         binary 0/1
        (0 = synthetic or missing; 0.8 = coarse 0.25° only; 1.0 = real)

    DQ = dem_valid · rain_valid_scaled

    This means:
      DQ=1.0 → real DEM + real IMD rainfall
      DQ=0.8 → real DEM + coarse rainfall (IMD only, no IMERG)
      DQ=0.0 → synthetic/missing DEM (cell is excluded at inference anyway)

    Note: rain_valid is stored as 1.0 (real) or 0.0 (synthetic).
    For real IMD-only data (no IMERG), we scale to 0.8 to reflect coarseness.
    """
    dem_v   = np.asarray(dem_valid,  dtype=float)
    rain_v  = np.asarray(rain_valid, dtype=float)

    # Rain quality: 1.0 → real, but scale to 0.8 for coarse-only IMD
    # (If IMERG is added later, update to 1.0)
    rain_quality = np.where(rain_v > 0, 0.8, 0.0)   # IMD = 0.8 (coarse ~27km)

    dq = dem_v * rain_quality
    return np.clip(dq, 0.0, 1.0)


# ── F: Freshness ──────────────────────────────────────────────────────────────

def compute_f(
    last_ingest_ts: Optional[datetime] = None,
    tau_days: float = FRESHNESS_TAU_DAYS,
    fresh_hours: float = FRESHNESS_FRESH_HOURS,
) -> float:
    """
    Freshness score: how recent are the dynamic (rainfall) inputs?

    F = exp(-(now - last_ingest) / tau)
    F = 1.0 if last_ingest was ≤ fresh_hours ago.

    Args:
        last_ingest_ts: UTC datetime of last rainfall data ingest.
                        Read from data/processed/rainfall_meta.json if None.
        tau_days:       Decay time constant (3 days per blueprint §7).
        fresh_hours:    Within this window, F = 1.0 exactly.

    Returns:
        Scalar float in [0, 1].
    """
    if last_ingest_ts is None:
        meta_path = Path(DATA_PROCESSED) / "rainfall_meta.json"
        if meta_path.exists():
            with open(meta_path) as f:
                meta = json.load(f)
            ts_str = meta.get("last_ingest_ts")
            if ts_str:
                last_ingest_ts = datetime.fromisoformat(ts_str)
                if meta.get("synthetic"):
                    return 0.5   # synthetic data → degraded freshness
        if last_ingest_ts is None:
            logger.warning("[M3] No rainfall ingest timestamp found — F = 0.5")
            return 0.5

    delta_hours = (datetime.utcnow() - last_ingest_ts).total_seconds() / 3600.0

    if delta_hours <= fresh_hours:
        return 1.0

    delta_days = delta_hours / 24.0
    f = float(np.exp(-delta_days / tau_days))
    return round(float(np.clip(f, 0.0, 1.0)), 4)


def compute_f_per_cell(
    n_cells: int,
    last_ingest_ts: Optional[datetime] = None,
) -> np.ndarray:
    """Broadcast scalar F to an array of length n_cells."""
    f_scalar = compute_f(last_ingest_ts)
    return np.full(n_cells, f_scalar)


# ── S: Stability ──────────────────────────────────────────────────────────────

def compute_s(
    p_full: np.ndarray,
    p_climatology: Optional[np.ndarray] = None,
    tau_alert: Optional[float] = None,
) -> np.ndarray:
    """
    Stability: does the prediction wobble under plausible input variation?

    Two components:
    1. Rain-climatology agreement: how much does p change when rainfall is
       set to local climatology (median monsoon) instead of actual?
       s_rain = 1 - |p_full - p_climo| / 0.5

    2. Tier stability: does the cell stay in the same tier when threshold
       is perturbed by ±0.02?
       s_tier = 1.0 if tier is stable, 0.5 if borderline.

    S = mean(s_rain, s_tier)

    If p_climatology is None (most cases at MVP), S = 0.5 (neutral).
    """
    n = len(p_full)

    if p_climatology is None:
        # Neutral stability — M9 will fill this in properly
        return np.full(n, 0.5)

    p_climo = np.asarray(p_climatology, dtype=float)
    s_rain = 1.0 - np.clip(np.abs(p_full - p_climo) / 0.5, 0.0, 1.0)

    if tau_alert is not None:
        # Check tier stability: ±0.02 perturbation
        perturb = 0.02
        tier_full  = (p_full >= tau_alert).astype(int)
        tier_up    = (p_full >= tau_alert + perturb).astype(int)
        tier_down  = (p_full >= tau_alert - perturb).astype(int)
        s_tier = np.where((tier_full == tier_up) & (tier_full == tier_down), 1.0, 0.5)
    else:
        s_tier = np.full(n, 0.75)

    return np.clip((s_rain + s_tier) / 2.0, 0.0, 1.0).round(4)


# ── Confidence (main) ─────────────────────────────────────────────────────────

def compute_confidence(
    p: np.ndarray,
    dq: np.ndarray,
    f: float | np.ndarray,
) -> np.ndarray:
    """
    confidence = p · (DQ · F)

    Interpretation:
      - If DQ=0, confidence=0 regardless of p (bad data → don't act)
      - If F≈0, confidence≈0 (stale data → don't act)
      - Only when both sources are high-quality AND fresh does confidence reach p

    This is the full formula; S is displayed alongside but not collapsed in.
    """
    p_arr  = np.asarray(p,  dtype=float)
    dq_arr = np.asarray(dq, dtype=float)
    f_arr  = np.asarray(f,  dtype=float) if hasattr(f, "__len__") else np.full(len(p_arr), float(f))

    g = np.clip(dq_arr * f_arr, 0.0, 1.0)   # penalty function g(DQ,F)
    confidence = np.clip(p_arr * g, 0.0, 1.0)
    return np.minimum(confidence.round(4), p_arr)


# ── Full pipeline ─────────────────────────────────────────────────────────────

def compute_confidence_layer(
    cells_df: pd.DataFrame,
    last_ingest_ts: Optional[datetime] = None,
    p_climatology: Optional[np.ndarray] = None,
    tau_alert: Optional[float] = None,
) -> pd.DataFrame:
    """
    Compute all confidence axes for a batch of cells.

    Args:
        cells_df:       DataFrame with columns [cell_id, p, dem_valid, rain_valid]
        last_ingest_ts: UTC datetime of last rainfall ingest
        p_climatology:  Optional calibrated p values with climatology rainfall
                        (for stability; None → S = 0.5)
        tau_alert:      Alert threshold (for tier stability check in S)

    Returns:
        cells_df with added columns [confidence, dq, f, s]
    """
    n = len(cells_df)
    p   = cells_df["p"].values
    dq  = compute_dq(
        cells_df.get("dem_valid",  pd.Series(np.ones(n))).values,
        cells_df.get("rain_valid", pd.Series(np.ones(n))).values,
    )
    f   = compute_f_per_cell(n, last_ingest_ts)
    s   = compute_s(p, p_climatology, tau_alert)
    conf = compute_confidence(p, dq, f)

    result = cells_df.copy()
    result["dq"]         = dq.round(4)
    result["f"]          = f.round(4)
    result["s"]          = s
    result["confidence"] = conf

    logger.info(
        f"[M3] Confidence computed for {n} cells: "
        f"mean_p={p.mean():.3f}, mean_conf={conf.mean():.3f}, "
        f"mean_dq={dq.mean():.3f}, f={f[0]:.3f}"
    )
    return result


def save_confidence_layer(cells_with_conf: pd.DataFrame, run_dir: Path) -> None:
    """Save confidence layer to run artifact directory."""
    conf_cols = [c for c in ["cell_id", "p", "confidence", "dq", "f", "s", "risk_tier"]
                 if c in cells_with_conf.columns]
    out = run_dir / "confidence.parquet"
    cells_with_conf[conf_cols].to_parquet(str(out), index=False)
    logger.info(f"[M3] Confidence layer → {out}")


if __name__ == "__main__":
    # Quick smoke test
    rng = np.random.default_rng(42)
    n = 100
    test_df = pd.DataFrame({
        "cell_id":    range(n),
        "p":          rng.uniform(0, 1, n),
        "dem_valid":  rng.choice([0.0, 1.0], n, p=[0.1, 0.9]),
        "rain_valid": rng.choice([0.0, 1.0], n, p=[0.2, 0.8]),
        "risk_tier":  rng.choice(["none","watch","alert","respond"], n),
    })
    result = compute_confidence_layer(test_df)
    print(result[["cell_id","p","confidence","dq","f","s"]].head(10))
    print(f"\nMean confidence: {result['confidence'].mean():.3f}")
    print(f"Cells where conf < p: {(result['confidence'] < result['p']).sum()}")
    print("All confidence ≤ p:", (result["confidence"] <= result["p"] + 1e-6).all())
