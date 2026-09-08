"""
full_grid_inference.py — M2: Wall-to-Wall Spatial Risk Inference
================================================================
Generates calibrated landslide risk and composite confidence predictions
for ALL 588,952 valid 100m cells across the entire Guwahati-Shillong AOI.

Distinct Datasets:
  1. training_sample.parquet (232 cells: 58 pos + 174 neg) — strictly for training/CV
  2. full_grid_inference (588,952 cells) — strictly for wall-to-wall spatial prediction

Outputs:
  - GeoTIFF: risk_surface_100m.tif (EPSG:32646, 4 bands: p, confidence, risk_tier, dq)
  - Parquet: cells_full.parquet (tabular lookup for all 588,952 cells)
  - GeoJSON: cells.geojson (alert and respond cells in EPSG:4326 for lean vector UI rendering)
"""

from __future__ import annotations

import json
import time
from datetime import datetime
from pathlib import Path
from typing import Optional

import joblib
import numpy as np
import pandas as pd
import geopandas as gpd
from shapely.geometry import box
from pyproj import Transformer
import rasterio
from rasterio.transform import from_bounds, rowcol
from loguru import logger

from config.aoi import (
    AOI_BBOX_WGS84, CRS_PROJECTED, CRS_GEOGRAPHIC,
    SAVED_MODELS_DIR, DEM_RAW_PATH, DATA_RUNS, DATA_PROCESSED,
    FULL_GRID_RASTER_PATH,
)
from modules.M1_data_ingestion.dem_processor import clip_and_reproject_dem, compute_terrain_vars
from modules.M1_data_ingestion.rainfall_fetcher import RainfallLoader
from modules.M2_risk_model.predict import _load_model, _load_thresholds, assign_tier
from modules.M3_uncertainty_engine.composite_confidence import compute_dq, compute_f, compute_confidence


def run_full_grid_inference(
    scenario_date: str = "2020-07-15",
    run_dir: Optional[Path] = None,
) -> dict:
    """
    Execute wall-to-wall inference over all 588,952 cells.

    Args:
        scenario_date: ISO date string for rainfall conditioning (default: peak monsoon date)
        run_dir: Directory to save run artifacts. If None, creates a new timestamped directory.

    Returns:
        dict containing grid metadata, summary statistics, and artifact paths.
    """
    t_start = time.time()
    logger.info(f"[M2/FullGrid] Starting wall-to-wall inference for scenario date: {scenario_date}")

    # ── 1. Create 100m Analysis Grid Bounding Coordinates ──────────────────
    aoi_geom = box(*AOI_BBOX_WGS84)
    aoi_gdf = gpd.GeoDataFrame(geometry=[aoi_geom], crs=CRS_GEOGRAPHIC).to_crs(CRS_PROJECTED)
    minx, miny, maxx, maxy = aoi_gdf.total_bounds

    cell_size = 100.0
    xs = np.arange(minx, maxx, cell_size)
    ys = np.arange(miny, maxy, cell_size)
    nx_cells, ny_cells = len(xs), len(ys)
    n_total = nx_cells * ny_cells

    # Affine transform for 2D raster (north-up: row 0 is maxy)
    raster_transform = from_bounds(minx, miny, maxx, maxy, nx_cells, ny_cells)
    logger.info(f"[M2/FullGrid] Grid: {nx_cells} cols x {ny_cells} rows = {n_total:,} cells (100m resolution)")

    # ── 2. Sample 7 Static Terrain Features from DEM ───────────────────────
    t0 = time.time()
    elev, dem_transform, dem_crs = clip_and_reproject_dem()
    terrain_vars = compute_terrain_vars(elev)

    # Centroids in projected UTM coordinates (mesh ordered row 0 = maxy down to miny)
    ys_desc = ys[::-1] - cell_size / 2.0
    xs_asc = xs + cell_size / 2.0
    XX, YY = np.meshgrid(xs_asc, ys_desc)
    XX_flat = XX.ravel()
    YY_flat = YY.ravel()

    rows, cols = rowcol(dem_transform, XX_flat, YY_flat)
    h_dem, w_dem = terrain_vars["elevation"].shape
    rows = np.clip(rows, 0, h_dem - 1)
    cols = np.clip(cols, 0, w_dem - 1)

    terrain_features = {}
    for feat in ["elevation", "slope", "aspect_sin", "aspect_cos", "tpi", "tri", "hand"]:
        terrain_features[feat] = terrain_vars[feat][rows, cols].astype(np.float32)
    logger.info(f"[M2/FullGrid] Sampled 7 terrain features for {n_total:,} cells in {time.time()-t0:.2f}s")

    # ── 3. Compute 5 Dynamic Rainfall Features from ERA5-Land ─────────────
    t0 = time.time()
    tr_to_wgs84 = Transformer.from_crs(CRS_PROJECTED, CRS_GEOGRAPHIC, always_xy=True)
    pt_lons, pt_lats = tr_to_wgs84.transform(XX_flat, YY_flat)

    rf_loader = RainfallLoader()
    centroids_gdf = gpd.GeoDataFrame(
        {"cell_id": np.arange(n_total, dtype=np.int32)},
        geometry=gpd.points_from_xy(pt_lons, pt_lats),
        crs=CRS_GEOGRAPHIC,
    )
    rf_df = rf_loader.get_windows(scenario_date, centroids_gdf)
    logger.info(f"[M2/FullGrid] Interpolated 5 rainfall features for {n_total:,} cells in {time.time()-t0:.2f}s")

    # ── 4. Predict Calibrated Probabilities ────────────────────────────────
    t0 = time.time()
    model = _load_model()
    calibrator = joblib.load(f"{SAVED_MODELS_DIR}/calibrator.pkl")
    thresholds = _load_thresholds()

    X_matrix = np.column_stack([
        terrain_features["elevation"],
        terrain_features["slope"],
        terrain_features["aspect_sin"],
        terrain_features["aspect_cos"],
        terrain_features["tpi"],
        terrain_features["tri"],
        terrain_features["hand"],
        rf_df["r03d"].values.astype(np.float32),
        rf_df["r07d"].values.astype(np.float32),
        rf_df["r15d"].values.astype(np.float32),
        rf_df["r30d"].values.astype(np.float32),
        rf_df["rain_anom"].values.astype(np.float32),
    ])

    raw_proba = model.predict_proba(X_matrix)[:, 1]
    p_calibrated = np.clip(calibrator.predict(raw_proba), 0.0, 1.0)
    logger.info(f"[M2/FullGrid] Model inference + isotonic calibration finished in {time.time()-t0:.2f}s")

    # ── 5. M3 Composite Confidence ─────────────────────────────────────────
    dq = compute_dq(np.ones(n_total, dtype=np.float32), np.ones(n_total, dtype=np.float32))
    f_val = compute_f()
    confidence = np.minimum(compute_confidence(p_calibrated, dq, f_val), p_calibrated)

    # ── 6. Risk Tier Assignment ───────────────────────────────────────────
    tau_watch = thresholds["tau_watch"]
    tau_alert = thresholds["tau_alert"]
    tau_respond = thresholds["tau_respond"]

    # Numeric tier codes: 0=none, 1=watch, 2=alert, 3=respond
    tiers_code = np.where(p_calibrated >= tau_respond, 3,
                 np.where(p_calibrated >= tau_alert, 2,
                 np.where(p_calibrated >= tau_watch, 1, 0))).astype(np.uint8)

    tier_names = np.where(tiers_code == 3, "respond",
                 np.where(tiers_code == 2, "alert",
                 np.where(tiers_code == 1, "watch", "none")))

    stats = {
        "n_total_cells": int(n_total),
        "n_none": int(np.sum(tiers_code == 0)),
        "n_watch": int(np.sum(tiers_code == 1)),
        "n_alert": int(np.sum(tiers_code == 2)),
        "n_respond": int(np.sum(tiers_code == 3)),
        "p_min": float(p_calibrated.min()),
        "p_mean": float(p_calibrated.mean()),
        "p_max": float(p_calibrated.max()),
        "conf_mean": float(confidence.mean()),
        "conf_max": float(confidence.max()),
        "scenario_date": scenario_date,
    }
    logger.info(
        f"[M2/FullGrid] Distribution: None={stats['n_none']:,}, "
        f"Watch={stats['n_watch']:,}, Alert={stats['n_alert']:,}, Respond={stats['n_respond']:,}"
    )

    # ── 7. Export Outputs ──────────────────────────────────────────────────
    if run_dir is None:
        ts = datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")
        run_dir = Path(DATA_RUNS) / f"run_{ts}"
    run_dir = Path(run_dir)
    run_dir.mkdir(parents=True, exist_ok=True)

    # A. 4-Band 100m GeoTIFF Risk Surface
    raster_tif_path = run_dir / "risk_surface_100m.tif"
    p_2d = p_calibrated.reshape((ny_cells, nx_cells)).astype(np.float32)
    conf_2d = confidence.reshape((ny_cells, nx_cells)).astype(np.float32)
    tier_2d = tiers_code.reshape((ny_cells, nx_cells)).astype(np.uint8)
    dq_2d = dq.reshape((ny_cells, nx_cells)).astype(np.float32)

    with rasterio.open(
        str(raster_tif_path),
        "w",
        driver="GTiff",
        height=ny_cells,
        width=nx_cells,
        count=4,
        dtype="float32",
        crs=CRS_PROJECTED,
        transform=raster_transform,
        compress="lzw",
    ) as dst:
        dst.write(p_2d, 1)
        dst.write(conf_2d, 2)
        dst.write(tier_2d.astype(np.float32), 3)
        dst.write(dq_2d, 4)
        dst.set_band_description(1, "p_calibrated")
        dst.set_band_description(2, "confidence")
        dst.set_band_description(3, "risk_tier_code")
        dst.set_band_description(4, "data_quality")

    # Also maintain the main processed symlink/file for general lookup
    Path(DATA_PROCESSED).mkdir(parents=True, exist_ok=True)
    import shutil
    shutil.copyfile(str(raster_tif_path), FULL_GRID_RASTER_PATH)
    logger.info(f"[M2/FullGrid] Full GeoTIFF raster saved → {raster_tif_path} & {FULL_GRID_RASTER_PATH}")

    # B. Vector GeoJSON for alert & respond cells (lean, browser-safe)
    alert_mask = tiers_code >= 2
    alert_indices = np.where(alert_mask)[0]
    logger.info(f"[M2/FullGrid] Creating vector GeoJSON for {len(alert_indices):,} alert/respond cells")

    if len(alert_indices) > 0:
        alert_boxes = [
            box(XX_flat[i] - cell_size/2.0, YY_flat[i] - cell_size/2.0,
                XX_flat[i] + cell_size/2.0, YY_flat[i] + cell_size/2.0)
            for i in alert_indices
        ]
        alert_gdf = gpd.GeoDataFrame({
            "cell_id": alert_indices,
            "p": p_calibrated[alert_indices].round(4),
            "confidence": confidence[alert_indices].round(4),
            "risk_tier": tier_names[alert_indices],
            "dq": dq[alert_indices].round(4),
            "f": round(float(f_val), 4),
            "s": 0.5,
            "dem_valid": 1.0,
            "rain_valid": 1.0,
        }, geometry=alert_boxes, crs=CRS_PROJECTED)

        cells_wgs84 = alert_gdf.to_crs(CRS_GEOGRAPHIC)
        cells_geojson_path = run_dir / "cells.geojson"
        cells_wgs84.to_file(str(cells_geojson_path), driver="GeoJSON")
    else:
        alert_gdf = gpd.GeoDataFrame(columns=["cell_id", "p", "risk_tier", "geometry"], crs=CRS_PROJECTED)
        cells_geojson_path = run_dir / "cells.geojson"
        alert_gdf.to_crs(CRS_GEOGRAPHIC).to_file(str(cells_geojson_path), driver="GeoJSON")

    # C. Full tabular lookup Parquet (optional compact format)
    parquet_path = run_dir / "cells_full.parquet"
    summary_df = pd.DataFrame({
        "cell_id": np.arange(n_total, dtype=np.int32),
        "x": XX_flat.astype(np.float32),
        "y": YY_flat.astype(np.float32),
        "p": p_calibrated.round(4),
        "confidence": confidence.round(4),
        "risk_tier": tier_names,
    })
    summary_df.to_parquet(str(parquet_path), index=False)
    logger.info(f"[M2/FullGrid] Parquet lookup saved → {parquet_path}")

    elapsed = time.time() - t_start
    logger.info(f"[M2/FullGrid] ✓ Wall-to-wall inference completed in {elapsed:.2f}s")

    return {
        "stats": stats,
        "run_dir": str(run_dir),
        "raster_path": str(raster_tif_path),
        "geojson_path": str(cells_geojson_path),
        "parquet_path": str(parquet_path),
        "raster_transform": raster_transform,
        "p_2d": p_2d,
        "conf_2d": conf_2d,
        "tier_2d": tier_2d,
        "alert_gdf": alert_gdf,
        "elapsed_s": elapsed,
    }


if __name__ == "__main__":
    result = run_full_grid_inference()
    print("Full grid execution complete:")
    print(json.dumps(result["stats"], indent=2))
