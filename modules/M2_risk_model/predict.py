"""
predict.py — M2: Landslide Risk Model
=======================================
Load trained XGBoost model + isotonic calibrator and run batch inference
over the current feature matrix. Saves precomputed run artifacts.

Design:
  - Validates AOI/CRS in meta.json matches current config before serving.
  - Applies calibration to ensure p means something.
  - Assigns risk tiers (watch/alert/respond) from persisted thresholds.
  - Saves to data/runs/run_{timestamp}/ for artifact-serving API.

Usage:
    python -m modules.M2_risk_model.predict
    python -m modules.M2_risk_model.predict --synthetic
"""

from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional

import joblib
import numpy as np
import pandas as pd
import geopandas as gpd
from loguru import logger

try:
    import xgboost as xgb
    XGB_AVAILABLE = True
except ImportError:
    XGB_AVAILABLE = False

from config.aoi import (
    SAVED_MODELS_DIR, FEATURE_MATRIX_PATH, DATA_RUNS, DATA_PROCESSED,
    TAU_WATCH, TAU_ALERT, TAU_RESPOND, CRS_PROJECTED, CRS_GEOGRAPHIC,
    AOI_BBOX_WGS84, CRITICALITY_WEIGHTS,
)
from modules.M1_data_ingestion.feature_engineer import FEATURE_COLS, LABEL_COL

MODELS_DIR    = Path(SAVED_MODELS_DIR)
MODEL_PATH    = MODELS_DIR / "model.json"
CALIBRATOR_P  = MODELS_DIR / "calibrator.pkl"
THRESHOLDS_P  = MODELS_DIR / "thresholds.json"
META_PATH     = MODELS_DIR / "meta.json"
FEATURE_LIST_P= MODELS_DIR / "feature_list.json"


def _load_thresholds() -> dict:
    if THRESHOLDS_P.exists():
        with open(THRESHOLDS_P) as f:
            return json.load(f)
    logger.warning("[M2/predict] No thresholds.json found; using config defaults")
    return {"tau_watch": TAU_WATCH, "tau_alert": TAU_ALERT, "tau_respond": TAU_RESPOND}


def _load_model():
    """Load XGBoost or fallback pkl model."""
    if MODEL_PATH.exists() and XGB_AVAILABLE:
        model = xgb.XGBClassifier()
        model.load_model(str(MODEL_PATH))
        return model
    pkl_path = MODEL_PATH.with_suffix(".pkl")
    if pkl_path.exists():
        return joblib.load(str(pkl_path))
    raise FileNotFoundError(
        f"No model found in {MODELS_DIR}. Run: python -m modules.M2_risk_model.train"
    )


def _validate_meta() -> None:
    """Assert model meta matches current AOI config."""
    if not META_PATH.exists():
        logger.warning("[M2/predict] meta.json not found — skipping validation")
        return
    with open(META_PATH) as f:
        meta = json.load(f)
    stored_aoi = tuple(meta.get("aoi_bbox_wgs84", []))
    if stored_aoi and stored_aoi != tuple(AOI_BBOX_WGS84):
        raise ValueError(
            f"[M2/predict] Model AOI {stored_aoi} ≠ current config {AOI_BBOX_WGS84}. "
            "Retrain the model with the correct AOI."
        )
    stored_crs = meta.get("crs_projected", "")
    if stored_crs and stored_crs != CRS_PROJECTED:
        raise ValueError(
            f"[M2/predict] Model CRS {stored_crs} ≠ current config {CRS_PROJECTED}."
        )
    logger.info("[M2/predict] ✓ meta.json AOI/CRS validated")


def assign_tier(p: float, tau_watch: float, tau_alert: float, tau_respond: float) -> str:
    if p >= tau_respond:
        return "respond"
    if p >= tau_alert:
        return "alert"
    if p >= tau_watch:
        return "watch"
    return "none"


def run_inference(
    feature_df: Optional[pd.DataFrame] = None,
    synthetic: bool = False,
    scenario_date: str = "2020-07-15",
    run_dir: Optional[Path] = None,
    use_full_grid: bool = True,
) -> gpd.GeoDataFrame:
    """
    Run full-grid wall-to-wall calibrated inference and orchestrate M3→M7.

    Distinct Datasets:
      - training_sample.parquet: 232 cells (strictly for M2 training/validation)
      - full_grid_inference: all 588,952 cells (strictly for wall-to-wall spatial prediction)

    Args:
        feature_df:    Optional legacy feature DataFrame. If None and use_full_grid is True,
                       executes full-grid inference over all 588,952 cells.
        synthetic:     If True and no model exists, trains on synthetic data first.
        scenario_date: ISO date string for rainfall conditioning (default: 2020-07-15 peak monsoon).
        run_dir:       Optional output directory.
        use_full_grid: If True (default), runs wall-to-wall 588,952-cell inference.

    Returns:
        GeoDataFrame of alert & respond cells with p, confidence, risk_tier.
    """
    # Auto-train only if no model exists. Real training requires training_sample.parquet
    # unless --synthetic was passed explicitly.
    if not MODEL_PATH.exists() and not MODEL_PATH.with_suffix(".pkl").exists():
        logger.info("[M2/predict] No model found — training now")
        from modules.M2_risk_model.train import run_training_pipeline
        run_training_pipeline(synthetic=synthetic)

    _validate_meta()
    thresholds = _load_thresholds()
    tau_watch   = thresholds["tau_watch"]
    tau_alert   = thresholds["tau_alert"]
    tau_respond = thresholds["tau_respond"]

    model_meta = {}
    if META_PATH.exists():
        with open(META_PATH) as f:
            model_meta = json.load(f)

    # Setup run directory
    ts = datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")
    if run_dir is None:
        run_dir = Path(DATA_RUNS) / f"run_{ts}"
    else:
        run_dir = Path(run_dir)
        if run_dir.name.startswith("run_"):
            ts = run_dir.name.replace("run_", "", 1)
    run_dir.mkdir(parents=True, exist_ok=True)

    if use_full_grid and feature_df is None:
        logger.info(f"[M2/predict] Executing wall-to-wall full-grid inference (588,952 cells) for {scenario_date}")
        from modules.M2_risk_model.full_grid_inference import run_full_grid_inference
        grid_res = run_full_grid_inference(scenario_date=scenario_date, run_dir=run_dir)

        alert_gdf = grid_res["alert_gdf"]
        p_2d = grid_res["p_2d"]
        conf_2d = grid_res["conf_2d"]
        raster_transform = grid_res["raster_transform"]
        raster_path = grid_res["raster_path"]
        stats = grid_res["stats"]
        gdf_out = alert_gdf
    else:
        # Legacy/fallback path for 232-cell sample or custom feature_df
        logger.info(f"[M2/predict] Running inference on provided/sample feature matrix")
        model = _load_model()
        calibrator = joblib.load(str(CALIBRATOR_P)) if CALIBRATOR_P.exists() else None

        if feature_df is None:
            if not Path(FEATURE_MATRIX_PATH).exists():
                from modules.M1_data_ingestion.feature_engineer import run_feature_pipeline
                feature_df = run_feature_pipeline(synthetic=synthetic)
            else:
                feature_df = pd.read_parquet(FEATURE_MATRIX_PATH)

        if FEATURE_LIST_P.exists():
            with open(FEATURE_LIST_P) as f:
                expected_features = json.load(f)
            missing = set(expected_features) - set(feature_df.columns)
            if missing:
                raise ValueError(f"[M2/predict] Missing features in matrix: {missing}")
            X = feature_df[expected_features].values
        else:
            X = feature_df[FEATURE_COLS].values

        raw_proba = model.predict_proba(X)[:, 1]
        p_calibrated = np.clip(calibrator.predict(raw_proba), 0.0, 1.0) if calibrator else raw_proba
        risk_tiers = [assign_tier(p, tau_watch, tau_alert, tau_respond) for p in p_calibrated]

        from modules.M3_uncertainty_engine.composite_confidence import compute_confidence_layer, save_confidence_layer
        result = feature_df.copy()
        result["p"] = p_calibrated.round(4)
        result["p_raw"] = raw_proba.round(4)
        result["risk_tier"] = risk_tiers
        result["dem_valid"] = feature_df.get("dem_valid", pd.Series(np.ones(len(feature_df)))).values
        result["rain_valid"] = feature_df.get("rain_valid", pd.Series(np.ones(len(feature_df)))).values
        result = compute_confidence_layer(result, tau_alert=tau_alert)

        if "geometry_wkt" in result.columns and "geometry" not in result.columns:
            from shapely import wkt as wkt_loader
            result["geometry"] = result["geometry_wkt"].apply(lambda g: wkt_loader.loads(g) if isinstance(g, str) and g else None)

        gdf_out = gpd.GeoDataFrame(result, geometry="geometry" if "geometry" in result.columns else None, crs=CRS_PROJECTED)
        save_confidence_layer(result, run_dir)
        p_2d, conf_2d, raster_transform, raster_path = None, None, None, None
        stats = {
            "n_total_cells": len(result),
            "n_none": int((result["risk_tier"] == "none").sum()),
            "n_watch": int((result["risk_tier"] == "watch").sum()),
            "n_alert": int((result["risk_tier"] == "alert").sum()),
            "n_respond": int((result["risk_tier"] == "respond").sum()),
            "p_min": float(p_calibrated.min()),
            "p_mean": float(p_calibrated.mean()),
            "p_max": float(p_calibrated.max()),
            "conf_mean": float(result["confidence"].mean()),
            "conf_max": float(result["confidence"].max()),
            "scenario_date": scenario_date,
        }

    # ── M4: Road Exposure & Graph ──────────────────────────────────────────────
    logger.info("[M2/predict] Wiring M4 road exposure analysis")
    from modules.M4_road_exposure.road_network_loader import (
        load_roads_gpkg, load_graph, _build_synthetic_network, save_roads
    )
    from modules.M4_road_exposure.spatial_intersect import run_spatial_intersect
    try:
        roads_gdf = load_roads_gpkg()
        G = load_graph()
    except FileNotFoundError:
        logger.info("[M2/predict] Road network not found; building network")
        roads_gdf, G = _build_synthetic_network()
        save_roads(roads_gdf, G)

    m4_layers = run_spatial_intersect(
        cells_gdf=gdf_out,
        G=G,
        roads_gdf=roads_gdf,
        raster_path=raster_path,
        p_2d=p_2d,
        conf_2d=conf_2d,
        raster_transform=raster_transform,
        run_dir=run_dir,
    )
    segments_risk = m4_layers["segments_risk"]

    # ── M5: Connectivity Failure Simulation ───────────────────────────────────
    logger.info("[M2/predict] Wiring M5 connectivity failure simulation")
    from modules.M5_connectivity_simulation.graph_builder import (
        get_village_and_hospital_nodes, compute_baseline_paths
    )
    from modules.M5_connectivity_simulation.failure_simulator import (
        simulate_deterministic, identify_critical_edges
    )
    village_nodes, hospital_nodes = get_village_and_hospital_nodes(G)
    baseline = compute_baseline_paths(G, village_nodes, hospital_nodes)
    m5_sim = simulate_deterministic(
        G=G,
        segments_risk_gdf=segments_risk,
        baseline=baseline,
        hospital_nodes=hospital_nodes,
        tau_alert=tau_alert,
    )
    critical_edges = identify_critical_edges(G, baseline, hospital_nodes)
    with open(run_dir / "impact_summary.json", "w") as f:
        json.dump(m5_sim["summary"], f, indent=2)
    with open(run_dir / "critical_edges.json", "w") as f:
        json.dump(critical_edges, f, indent=2)

    # ── M6: Criticality Scorer ────────────────────────────────────────────────
    logger.info("[M2/predict] Wiring M6 criticality scoring")
    from modules.M6_criticality_scorer.criticality_formula import compute_criticality
    crit_gdf = compute_criticality(
        segments_gdf=segments_risk,
        village_impacts=m5_sim["village_impacts"],
        baseline=baseline,
        G=G,
    )
    crit_out = Path(DATA_PROCESSED) / "criticality.geojson"
    crit_wgs84 = crit_gdf.to_crs(CRS_GEOGRAPHIC) if str(crit_gdf.crs) != CRS_GEOGRAPHIC else crit_gdf
    crit_wgs84.to_file(str(crit_out), driver="GeoJSON")
    crit_wgs84.to_file(str(run_dir / "criticality.geojson"), driver="GeoJSON")
    with open(Path(DATA_PROCESSED) / "criticality_weights.json", "w") as f:
        json.dump({"weights": CRITICALITY_WEIGHTS}, f, indent=2)

    # ── M7: Action Recommender ────────────────────────────────────────────────
    logger.info("[M2/predict] Wiring M7 action recommender")
    from modules.M7_action_recommender.action_tier_engine import run_action_engine
    actions = run_action_engine(
        cells_df=gdf_out,
        segments_criticality=crit_gdf,
        village_impacts=m5_sim["village_impacts"],
        run_id=f"run_{ts}",
        run_dir=run_dir,
    )

    # Save run metadata
    run_meta = {
        "run_id":          f"run_{ts}",
        "timestamp":       ts,
        "scenario_date":   scenario_date,
        "is_synthetic_data": bool(model_meta.get("is_synthetic_data", synthetic)),
        "training_dataset":  model_meta.get("training_dataset", "unknown"),
        "probability_interpretation": model_meta.get(
            "probability_interpretation", "case_control_ranking_score"
        ),
        "aoi_prevalence_correction": model_meta.get("aoi_prevalence_correction", "not_applied"),
        "inference_dataset": "full_aoi_588952",
        "full_grid_stats": stats,
        "n_road_segments": len(segments_risk),
        "n_exposed_roads": int((segments_risk["risk_max"] >= tau_alert).sum()),
        "n_respond_roads": int((segments_risk["risk_max"] >= tau_respond).sum()),
        "n_villages_isolated": m5_sim["summary"]["n_villages_isolated"],
        "n_poorly_connected":  m5_sim["summary"]["n_poorly_connected"],
        "n_critical_edges":    len(critical_edges),
        "thresholds":          thresholds,
        "model_meta":          str(META_PATH),
        "n_actions":           len(actions),
        "artifacts": {
            "risk_surface_tif": str(raster_path) if raster_path else None,
            "cells_geojson":    str(run_dir / "cells.geojson"),
            "segments_risk":    str(run_dir / "segments_risk.geojson"),
            "criticality":      str(run_dir / "criticality.geojson"),
            "impact_summary":   str(run_dir / "impact_summary.json"),
            "critical_edges":   str(run_dir / "critical_edges.json"),
            "actions":          str(run_dir / "actions.json"),
        }
    }
    with open(run_dir / "run_meta.json", "w") as f:
        json.dump(run_meta, f, indent=2)

    # Update "latest" pointer
    latest_ptr = Path(DATA_RUNS) / "latest_run.json"
    with open(latest_ptr, "w") as f:
        json.dump({"run_id": f"run_{ts}", "run_dir": str(run_dir)}, f)

    logger.info(
        f"[M2/predict] ✓ Full-grid end-to-end pipeline complete! Run saved → {run_dir}\n"
        f"  Total cells: {stats['n_total_cells']:,} (Alert: {stats['n_alert']:,}, Respond: {stats['n_respond']:,})\n"
        f"  Road segments: {len(segments_risk):,} (Exposed: {run_meta['n_exposed_roads']:,})\n"
        f"  Villages: {run_meta['n_villages_isolated']} isolated, {run_meta['n_poorly_connected']} poorly connected\n"
        f"  Critical edges: {len(critical_edges)}, Actions: {len(actions)}"
    )
    return gdf_out


if __name__ == "__main__":
    synthetic = "--synthetic" in sys.argv
    gdf = run_inference(synthetic=synthetic)
    print(f"Inference completed. Returned {len(gdf)} alert/respond cells.")
