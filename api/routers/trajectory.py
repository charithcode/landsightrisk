"""trajectory.py — Risk trajectory + emerging hotspots router"""
import json
from pathlib import Path
from typing import Optional
from fastapi import APIRouter, Query, HTTPException
from config.aoi import DATA_RUNS

router = APIRouter(prefix="/trajectory", tags=["Trajectory"])


@router.get("")
async def get_trajectory(
    runs: str = Query("T0,T1,T2", description="Comma-separated run IDs (T0=oldest, T2=newest)"),
):
    """
    Trajectory comparison across up to 3 runs.
    Returns: chart series (mean_p per run), emerging hotspots (cells worsening),
    Δcriticality per segment, and T2 persistence baseline label.

    T2 is labeled 'persistence baseline — not a forecast'.
    """
    traj_path = Path(DATA_RUNS) / "trajectory.json"
    if traj_path.exists():
        with open(traj_path) as f:
            return json.load(f)

    # Build from available run dirs
    run_ids = [r.strip() for r in runs.split(",") if r.strip()]
    chart_series = []
    all_run_dirs = sorted(Path(DATA_RUNS).glob("run_*"), key=lambda p: p.name)

    for i, run_dir in enumerate(all_run_dirs[-3:]):
        meta_path = run_dir / "run_meta.json"
        if meta_path.exists():
            with open(meta_path) as f:
                meta = json.load(f)
            label = f"T{i}"
            if i == len(all_run_dirs[-3:]) - 1:
                label = "T2 (persistence baseline — not a forecast)"
            chart_series.append({
                "run_id":        meta.get("run_id"),
                "label":         label,
                "timestamp":     meta.get("timestamp"),
                "n_alert_cells": int(meta.get("full_grid_stats", {}).get("n_alert", meta.get("n_alert_cells", 0))),
                "n_respond_cells": int(meta.get("full_grid_stats", {}).get("n_respond", meta.get("n_respond_cells", 0))),
            })

    if not chart_series:
        raise HTTPException(503, "No runs available for trajectory. Run M2/predict.py.")

    return {
        "chart_series":  chart_series,
        "emerging_hotspots": [],   # M9 pipeline computes this
        "delta_criticality": [],   # M9 pipeline computes this
        "disclaimer":    (
            "T2 is a persistence baseline (T1 with freshness decayed). "
            "It is NOT a forecast. Future landslide timing cannot be predicted."
        ),
    }
