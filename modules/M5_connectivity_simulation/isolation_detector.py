"""
isolation_detector.py — M5: Connectivity Failure Simulation
=============================================================
Post-processes village_impacts from failure_simulator to produce
clean village isolation tags and aggregate statistics.

Separation of concerns:
  - failure_simulator.py: runs the graph simulation
  - isolation_detector.py: interprets the results into clean labels

Output per village:
  isolation_flag ∈ {isolated, poorly_connected, accessible, was_unreachable}
  t0, t1, ratio, delta_min

Also produces aggregate metrics for the dashboard StatusBar.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

import pandas as pd
import geopandas as gpd
from loguru import logger

from config.aoi import (
    ISOLATION_RATIO, POOR_CONNECT_RATIO, DATA_PROCESSED,
)


def summarize_isolation(village_impacts: list[dict]) -> dict:
    """
    Compute aggregate isolation metrics from village_impacts list.

    Returns dict suitable for API /connectivity/impact response.
    """
    df = pd.DataFrame(village_impacts)
    if df.empty:
        return {"total": 0, "isolated": 0, "poorly_connected": 0, "accessible": 0}

    flag_counts = df["isolation_flag"].value_counts().to_dict()
    isolated   = flag_counts.get("isolated", 0)
    poor       = flag_counts.get("poorly_connected", 0)
    accessible = flag_counts.get("accessible", 0)
    baseline_unreachable = flag_counts.get("was_unreachable", 0)

    impacted_rows = df[df["isolation_flag"].isin(["isolated", "poorly_connected"])]
    avg_delta = float(impacted_rows["delta_min"].dropna().mean()) if not impacted_rows.empty else 0.0
    max_delta = float(impacted_rows["delta_min"].dropna().max()) if not impacted_rows.empty else 0.0

    return {
        "total":               len(df),
        "isolated":            isolated,
        "poorly_connected":    poor,
        "accessible":          accessible,
        "baseline_unreachable":baseline_unreachable,
        "avg_travel_increase_min": round(avg_delta, 1),
        "max_travel_increase_min": round(max_delta, 1),
        "pct_impacted":        round((isolated + poor) / max(len(df), 1) * 100, 1),
        "isolation_threshold": ISOLATION_RATIO,
        "poor_connect_threshold": POOR_CONNECT_RATIO,
    }


def tag_villages(
    villages_gdf: gpd.GeoDataFrame,
    village_impacts: list[dict],
) -> gpd.GeoDataFrame:
    """
    Merge isolation flags into the villages GeoDataFrame.
    """
    impacts_df = pd.DataFrame(village_impacts)
    if impacts_df.empty or villages_gdf.empty:
        return villages_gdf

    merged = villages_gdf.copy()
    if "snap_node" in merged.columns:
        merged = merged.merge(
            impacts_df[["village_node", "isolation_flag", "t0", "t1", "ratio", "delta_min"]],
            left_on="snap_node",
            right_on="village_node",
            how="left",
        )
    merged["isolation_flag"] = merged.get("isolation_flag", pd.Series("accessible")).fillna("accessible")
    return merged


def detect_isolation(
    village_impacts: list[dict],
    villages_gdf: Optional[gpd.GeoDataFrame] = None,
    run_dir: Optional[Path] = None,
) -> dict:
    """
    Full isolation detection post-processing.

    Args:
        village_impacts: Output from failure_simulator.simulate_deterministic
        villages_gdf:    Village GeoDataFrame for geometry merge
        run_dir:         If provided, saves isolation_report.json there

    Returns:
        dict with isolation_summary and tagged_villages_gdf
    """
    summary = summarize_isolation(village_impacts)
    logger.info(
        f"[M5/ID] Isolation summary: {summary['isolated']} isolated, "
        f"{summary['poorly_connected']} poorly connected, "
        f"avg delay +{summary['avg_travel_increase_min']:.1f} min"
    )

    tagged = None
    if villages_gdf is not None and not villages_gdf.empty:
        tagged = tag_villages(villages_gdf, village_impacts)

    if run_dir is not None:
        out = Path(run_dir) / "isolation_report.json"
        with open(out, "w") as f:
            json.dump(summary, f, indent=2)
        logger.info(f"[M5/ID] Isolation report → {out}")

    return {"isolation_summary": summary, "tagged_villages": tagged}
