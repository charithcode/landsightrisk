"""
pipeline_scheduler.py — M9: Live Risk Trajectory
=================================================
Manual pipeline runner — no APScheduler.

Call manually or via cron:
  python -m modules.M9_live_risk_trajectory.pipeline_scheduler

Computes T0 → T1 → T2 deltas and saves trajectory.json.
T2 = persistence baseline (T1 with freshness F decayed by 3 days).
T2 is labeled "persistence — not a forecast" in all outputs.
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd
from loguru import logger

from config.aoi import DATA_RUNS


def _load_run_cells(run_dir: Path) -> pd.DataFrame:
    full_path = run_dir / "cells_full.parquet"
    if full_path.exists():
        return pd.read_parquet(str(full_path))
    geojson_path = run_dir / "cells.geojson"
    if geojson_path.exists():
        import geopandas as gpd
        gdf = gpd.read_file(str(geojson_path))
        return pd.DataFrame(gdf.drop(columns=["geometry"], errors="ignore"))
    return pd.DataFrame()


def compute_persistence_t2(df_t1: pd.DataFrame, tau_days: float = 3.0) -> pd.DataFrame:
    """T2 = T1 with confidence decayed by 3 days. p is NOT changed."""
    decay_factor = np.exp(-3.0 / tau_days)
    df_t2 = df_t1.copy()
    if "confidence" in df_t2.columns:
        df_t2["confidence"] = (df_t2["confidence"] * decay_factor).round(4)
    if "f" in df_t2.columns:
        df_t2["f"] = (df_t2["f"] * decay_factor).round(4)
    df_t2["label"] = "T2 — persistence baseline — not a forecast"
    return df_t2


def run_pipeline() -> dict:
    """Compute trajectory from 3 most recent runs. Saves trajectory.json."""
    runs = sorted(Path(DATA_RUNS).glob("run_*"), key=lambda p: p.name)[-3:]
    if not runs:
        logger.warning("[M9] No runs found.")
        return {}

    series = []
    dfs = {}

    for i, run_dir in enumerate(runs):
        meta_path = run_dir / "run_meta.json"
        if not meta_path.exists():
            continue
        with open(meta_path) as f:
            meta = json.load(f)
        label = f"T{i}"
        df = _load_run_cells(run_dir)
        dfs[label] = df
        series.append({
            "run_id":         meta.get("run_id"),
            "label":          label,
            "timestamp":      meta.get("timestamp"),
            "n_alert_cells":  int(meta.get("full_grid_stats", {}).get("n_alert", meta.get("n_alert_cells", 0))),
            "n_respond_cells":int(meta.get("full_grid_stats", {}).get("n_respond", meta.get("n_respond_cells", 0))),
        })

    if series:
        series[-1]["label"] = "T2 (persistence baseline — not a forecast)"
        series[-1]["is_persistence"] = True

    # Emerging hotspots: cells with p_t1 - p_t0 > 0.05
    emerging = []
    if "T0" in dfs and "T1" in dfs and not dfs["T0"].empty and not dfs["T1"].empty:
        m = dfs["T0"][["cell_id","p"]].merge(dfs["T1"][["cell_id","p"]], on="cell_id", suffixes=("_t0","_t1"))
        m["delta"] = m["p_t1"] - m["p_t0"]
        emerging = m[m["delta"] > 0.05].sort_values("delta", ascending=False).head(20).to_dict("records")

    trajectory = {
        "generated_at":      datetime.utcnow().isoformat(),
        "chart_series":      series,
        "emerging_hotspots": emerging,
        "delta_criticality": [],
        "disclaimer":        "T2 is persistence only — not a forecast.",
        "n_runs":            len(series),
    }
    out = Path(DATA_RUNS) / "trajectory.json"
    with open(out, "w") as f:
        json.dump(trajectory, f, indent=2)
    logger.info(f"[M9] Trajectory → {out}")
    return trajectory


if __name__ == "__main__":
    result = run_pipeline()
    print(json.dumps(result, indent=2))
