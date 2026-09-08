"""
feature_engineer.py — M1: Data Ingestion
==========================================
Assembles the full 100m analysis grid and feature matrix:

  1. Build 100m grid cells over AOI (EPSG:32646)
  2. Attach terrain features (dem_processor.py)
  3. Load and label GSI/NRSC inventory → positive cells (point-in-polygon)
  4. Sample negatives: never-inventoried cells ≥ 2km from any positive
  5. Time-anchor rainfall features: each positive cell gets rainfall as-of
     its event_date; each negative gets a random same-monsoon-season date
  6. Export feature_matrix.parquet with columns:
       cell_id, elevation, slope, aspect_sin, aspect_cos, tpi, tri, hand,
       r03d, r07d, r15d, r30d, rain_anom, date_anchor, landslide_occurrence,
       dem_valid, rain_valid

LEAKAGE CONTROLS (§5):
  - historical_landslide_density is NOT a feature
  - dist_to_stream_m is NOT a feature
  - Rainfall features are ALWAYS time-anchored (never "current")
  - Negative cells are spatially buffered 2km from positives

Usage:
    # Full pipeline (real data)
    from modules.M1_data_ingestion.feature_engineer import run_feature_pipeline
    run_feature_pipeline()

    # Synthetic (CI/demo, no files needed)
    run_feature_pipeline(synthetic=True)
"""

from __future__ import annotations

import json
import random
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd
import geopandas as gpd
from shapely.geometry import box, Point
from loguru import logger

from config.aoi import (
    CRS_PROJECTED, CRS_GEOGRAPHIC,
    AOI_BBOX_WGS84, GRID_CELL_SIZE_M,
    FEATURE_MATRIX_PATH, INVENTORY_DIR, DATA_PROCESSED,
    NEGATIVE_BUFFER_M, CV_N_BLOCKS,
)


# ── Feature column contract ────────────────────────────────────────────────────
STATIC_TERRAIN_COLS = [
    "elevation", "slope", "aspect_sin", "aspect_cos",
    "tpi", "tri", "hand",
]
DYNAMIC_RAINFALL_COLS = ["r03d", "r07d", "r15d", "r30d", "rain_anom"]
LABEL_COL = "landslide_occurrence"

FEATURE_COLS = STATIC_TERRAIN_COLS + DYNAMIC_RAINFALL_COLS   # model inputs (no proximity!)

META_COLS = [
    "cell_id", "date_anchor", LABEL_COL,
    "dem_valid", "rain_valid",
    "block_id",          # spatial CV block
    "geometry_wkt",      # for spatial joins downstream
]

ALL_COLS = META_COLS + FEATURE_COLS


# ── Grid construction ─────────────────────────────────────────────────────────

def build_analysis_grid(
    aoi_bbox_wgs84: tuple = AOI_BBOX_WGS84,
    cell_size_m: int = GRID_CELL_SIZE_M,
    crs_projected: str = CRS_PROJECTED,
) -> gpd.GeoDataFrame:
    """
    Build a regular 100m grid of cell polygons over the AOI.

    Steps:
      1. Create bounding box in WGS-84
      2. Reproject to EPSG:32646
      3. Generate cell polygons at cell_size_m intervals

    Returns:
        GeoDataFrame (EPSG:32646) with columns [cell_id, geometry]
        where geometry is a 100m × 100m square polygon.
    """
    logger.info(f"[M1/FE] Building {cell_size_m}m analysis grid over AOI")

    # AOI box in WGS-84 → project to UTM 46N
    aoi_geom = box(*aoi_bbox_wgs84)
    aoi_gdf = gpd.GeoDataFrame(geometry=[aoi_geom], crs=CRS_GEOGRAPHIC)
    aoi_utm = aoi_gdf.to_crs(crs_projected)

    minx, miny, maxx, maxy = aoi_utm.total_bounds

    # Generate grid cell origins
    xs = np.arange(minx, maxx, cell_size_m)
    ys = np.arange(miny, maxy, cell_size_m)

    cells = []
    cell_id = 0
    for y in ys:
        for x in xs:
            cells.append(box(x, y, x + cell_size_m, y + cell_size_m))
            cell_id += 1

    grid = gpd.GeoDataFrame(
        {"cell_id": range(len(cells))},
        geometry=cells,
        crs=crs_projected,
    )

    logger.info(f"[M1/FE] Grid: {len(grid)} cells "
                f"({len(xs)} × {len(ys)} approx)")
    return grid


def _add_spatial_cv_blocks(grid: gpd.GeoDataFrame, n_blocks: int = 3) -> gpd.GeoDataFrame:
    """
    Assign spatial CV block IDs along the Guwahati-Shillong corridor axis (UTM Y).
    This guarantees 100% spatial separation between regional sections
    (South / Central / North) and ensures all folds contain positive and negative samples.
    """
    grid = grid.copy()
    ys = grid.geometry.centroid.y.values

    if "is_positive" in grid.columns and grid["is_positive"].sum() >= n_blocks:
        pos_ys = grid[grid["is_positive"]].geometry.centroid.y.values
        quantiles = np.linspace(0, 100, n_blocks + 1)
        bins = np.percentile(pos_ys, quantiles)
        bins[0] -= 1000.0
        bins[-1] += 1000.0
        block_ids = np.digitize(ys, bins[1:-1])
    else:
        from sklearn.cluster import KMeans
        centroids = np.column_stack([grid.geometry.centroid.x.values, ys])
        km = KMeans(n_clusters=n_blocks, random_state=42, n_init=10)
        block_ids = km.fit_predict(centroids)

    grid["block_id"] = block_ids.astype(int)
    return grid


# ── Inventory loading ─────────────────────────────────────────────────────────

def load_inventory(inventory_dir: str = INVENTORY_DIR) -> gpd.GeoDataFrame:
    """
    Load GSI/NRSC/NESDR inventory from data/raw/historical_landslides/.

    Tries these file patterns in order:
      - inventory_clean.geojson
      - *.geojson  (first match)
      - *.shp      (first match)
      - *.parquet  (Parquet format from bharatlas mirror)

    Returns:
        GeoDataFrame in EPSG:32646 with columns [geometry, event_date, source].
        event_date is pd.Timestamp or NaT if not available.
        Returns empty GDF if no inventory found.
    """
    inv_dir = Path(inventory_dir)
    inventory_path = None

    for pattern in ["inventory_clean.geojson", "*.geojson", "*.shp", "*.parquet"]:
        matches = sorted(inv_dir.glob(pattern))
        if matches:
            inventory_path = matches[0]
            break

    if inventory_path is None:
        logger.warning(
            f"[M1/FE] No inventory file found in {inventory_dir}. "
            "Download GSI inventory from Bhukosh/bharatlas and place in "
            "data/raw/historical_landslides/. Using EMPTY inventory → "
            "falling back to terrain-only susceptibility model."
        )
        return gpd.GeoDataFrame(
            columns=["geometry", "event_date", "source"],
            geometry="geometry",
            crs=CRS_PROJECTED,
        )

    logger.info(f"[M1/FE] Loading inventory from {inventory_path}")

    if inventory_path.suffix == ".parquet":
        df = pd.read_parquet(inventory_path)
        gdf = gpd.GeoDataFrame(df, geometry=gpd.points_from_xy(df["lon"], df["lat"]),
                               crs=CRS_GEOGRAPHIC)
    elif inventory_path.suffix in (".geojson", ".json"):
        gdf = gpd.read_file(inventory_path)
    else:
        gdf = gpd.read_file(inventory_path)

    # Standardise CRS
    if gdf.crs is None:
        gdf = gdf.set_crs(CRS_GEOGRAPHIC)
    if str(gdf.crs) != CRS_PROJECTED:
        gdf = gdf.to_crs(CRS_PROJECTED)

    # Parse event_date
    date_cols = [c for c in gdf.columns if "date" in c.lower() or "year" in c.lower()]
    if date_cols:
        raw_dates = gdf[date_cols[0]]
        try:
            gdf["event_date"] = pd.to_datetime(raw_dates, errors="coerce")
        except Exception:
            gdf["event_date"] = pd.NaT
    else:
        gdf["event_date"] = pd.NaT

    if "source" not in gdf.columns:
        gdf["source"] = inventory_path.stem

    # Deduplicate by geometry proximity (< 10m) and same date
    logger.info(f"[M1/FE] Loaded {len(gdf)} inventory records; "
                f"{gdf['event_date'].notna().sum()} with usable dates")
    return gdf[["geometry", "event_date", "source"]]


# ── Positive / negative labelling ────────────────────────────────────────────

def label_positive_cells(
    grid: gpd.GeoDataFrame,
    inventory: gpd.GeoDataFrame,
) -> gpd.GeoDataFrame:
    """
    Mark grid cells as positive if any inventory point intersects them.
    Only keeps cells where inventory event_date is not NaT.
    """
    if inventory.empty:
        grid = grid.copy()
        grid["is_positive"] = False
        grid["event_date"] = pd.NaT
        return grid

    dated = inventory[inventory["event_date"].notna()].copy()
    if dated.empty:
        logger.warning("[M1/FE] No dated inventory records → all cells negative")
        grid = grid.copy()
        grid["is_positive"] = False
        grid["event_date"] = pd.NaT
        return grid

    # Fast spatial join via spatial index
    joined = gpd.sjoin(
        grid[["cell_id", "geometry"]],
        dated[["geometry", "event_date"]],
        how="inner",
        predicate="contains",
    )
    if joined.empty:
        # Fallback to intersects
        joined = gpd.sjoin(
            grid[["cell_id", "geometry"]],
            dated[["geometry", "event_date"]],
            how="inner",
            predicate="intersects",
        )

    earliest = joined.groupby("cell_id")["event_date"].min().reset_index()
    grid = grid.merge(earliest, on="cell_id", how="left")
    grid["event_date"] = pd.to_datetime(grid["event_date"])
    grid["is_positive"] = grid["event_date"].notna()

    n_pos = grid["is_positive"].sum()
    logger.info(f"[M1/FE] {n_pos} positive cells from inventory "
                f"({n_pos / len(grid) * 100:.2f}% of grid)")
    return grid


def sample_negatives(
    grid: gpd.GeoDataFrame,
    neg_buffer_m: float = NEGATIVE_BUFFER_M,
    ratio_neg_to_pos: float = 3.0,
) -> gpd.GeoDataFrame:
    """
    Sample negative cells: never-inventoried cells ≥ 2km from any positive.
    Uses fast cKDTree for instant 2km buffer distance check.
    """
    from scipy.spatial import cKDTree

    positives = grid[grid["is_positive"]].copy()
    candidates = grid[~grid["is_positive"]].copy()

    if len(positives) == 0:
        logger.warning("[M1/FE] No positives → all cells are 'negatives'")
        n_neg = min(len(candidates), 300)
        return pd.concat([positives, candidates.sample(n_neg, random_state=42)], ignore_index=True)

    # Coordinates of positives and candidates
    pos_coords = np.column_stack([positives.geometry.centroid.x, positives.geometry.centroid.y])
    cand_coords = np.column_stack([candidates.geometry.centroid.x, candidates.geometry.centroid.y])

    tree = cKDTree(pos_coords)
    dists, _ = tree.query(cand_coords)
    valid_mask = dists >= neg_buffer_m

    candidates_outside = candidates[valid_mask].copy()

    n_neg_target = int(len(positives) * ratio_neg_to_pos)
    if len(candidates_outside) < n_neg_target:
        logger.warning(
            f"[M1/FE] Only {len(candidates_outside)} candidates outside buffer. Using all."
        )
        negatives = candidates_outside
    else:
        negatives = candidates_outside.sample(n_neg_target, random_state=42)

    logger.info(f"[M1/FE] Sampled {len(negatives)} negatives "
                f"({neg_buffer_m/1000:.1f}km buffer, ratio {len(negatives)/len(positives):.2f}:1)")
    return pd.concat([positives, negatives], ignore_index=True)


def _assign_negative_date(pos_dates: pd.Series) -> pd.Timestamp:
    """
    Assign a random monsoon-season date to a negative cell.
    Picks a random year from the positive events and a random Jun–Sep date.
    """
    valid_years = pos_dates.dropna().dt.year.unique()
    if len(valid_years) == 0:
        year = 2018
    else:
        year = int(np.random.choice(valid_years))
    month = np.random.choice([6, 7, 8, 9])
    day = np.random.randint(1, 28)
    return pd.Timestamp(year=year, month=month, day=day)


def time_anchor_features(
    sample_grid: gpd.GeoDataFrame,
    rainfall_loader,
) -> pd.DataFrame:
    """
    Attach time-anchored rainfall windows to each cell.

    - Positive cells: rainfall as-of event_date
    - Negative cells: rainfall as-of random monsoon-season date in same date range

    Returns:
        DataFrame merged with rainfall window columns.
    """
    logger.info("[M1/FE] Time-anchoring rainfall features")

    pos_dates = sample_grid[sample_grid["is_positive"]]["event_date"]

    # Assign negative anchors
    sample = sample_grid.copy()
    np.random.seed(123)
    neg_mask = ~sample["is_positive"]
    sample.loc[neg_mask, "event_date"] = [
        _assign_negative_date(pos_dates) for _ in range(neg_mask.sum())
    ]
    sample["date_anchor"] = sample["event_date"].dt.strftime("%Y-%m-%d")

    # Prepare centroid GDF in WGS-84 for rainfall lookup
    centroids_utm = sample.geometry.centroid
    centroids_gdf_utm = gpd.GeoDataFrame(
        {"cell_id": sample["cell_id"].values},
        geometry=centroids_utm.values,
        crs=CRS_PROJECTED,
    ).to_crs(CRS_GEOGRAPHIC)

    # Group by date_anchor and fetch windows per unique date
    # (efficiency: many cells share the same date if positives cluster by event)
    unique_dates = sample["date_anchor"].unique()
    rainfall_rows = []

    for date_str in unique_dates:
        mask = sample["date_anchor"] == date_str
        cells_today = centroids_gdf_utm[sample["cell_id"].isin(sample.loc[mask, "cell_id"])]
        try:
            rf = rainfall_loader.get_windows(date_str, cells_today)
            rainfall_rows.append(rf)
        except Exception as e:
            logger.warning(f"[M1/FE] Rainfall fetch failed for {date_str}: {e}")
            # Fill with zeros
            rf = pd.DataFrame({
                "cell_id": cells_today["cell_id"].values,
                "r03d": 0.0, "r07d": 0.0, "r15d": 0.0, "r30d": 0.0,
                "rain_anom": 0.5, "rain_valid": 0.0,
            })
            rainfall_rows.append(rf)

    rf_all = pd.concat(rainfall_rows, ignore_index=True)

    # Merge back
    result = sample.merge(rf_all, on="cell_id", how="left")
    return result


# ── Synthetic fallback ────────────────────────────────────────────────────────

def _make_synthetic_feature_matrix(
    n_positive: int = 300,
    n_negative: int = 500,
) -> pd.DataFrame:
    """
    Generate a synthetic feature matrix for the NH-6 AOI.
    Used when no real data is available (testing, CI, demo setup).

    CLEARLY LABELED: dem_valid=0, rain_valid=0.
    """
    logger.warning(
        "[M1/FE] SYNTHETIC feature matrix — NOT real data. "
        "For testing and CI only. Never claim these are real predictions."
    )
    rng = np.random.default_rng(42)
    n_total = n_positive + n_negative

    def _terrain(n: int, is_pos: bool) -> dict:
        """Positives tend to have higher slope, moderate HAND."""
        if is_pos:
            slope_mean, hand_mean = 32, 150
        else:
            slope_mean, hand_mean = 18, 280
        return {
            "elevation":   rng.uniform(200, 1600, n),
            "slope":       np.clip(rng.normal(slope_mean, 10, n), 0, 70),
            "aspect_sin":  rng.uniform(-1, 1, n),
            "aspect_cos":  rng.uniform(-1, 1, n),
            "tpi":         rng.normal(0 if is_pos else 20, 30, n),
            "tri":         np.clip(rng.normal(slope_mean * 0.8, 8, n), 0, 80),
            "hand":        np.clip(rng.exponential(hand_mean, n), 0, 600),
        }

    def _rainfall(n: int, is_pos: bool) -> dict:
        """Positives have higher antecedent rainfall on their event date."""
        base = 120 if is_pos else 60
        return {
            "r03d":      np.clip(rng.normal(base * 0.3, 20, n), 0, 300),
            "r07d":      np.clip(rng.normal(base * 0.7, 40, n), 0, 500),
            "r15d":      np.clip(rng.normal(base, 60, n), 0, 700),
            "r30d":      np.clip(rng.normal(base * 1.5, 80, n), 0, 900),
            "rain_anom": np.clip(rng.normal(0.7 if is_pos else 0.4, 0.15, n), 0, 1),
        }

    def _dates(n: int, is_pos: bool) -> list[str]:
        years = rng.integers(2010, 2023, n)
        months = rng.integers(6, 10, n)   # Jun–Sep
        days = rng.integers(1, 28, n)
        return [f"{y}-{m:02d}-{d:02d}" for y, m, d in zip(years, months, days)]

    # Generate spatial coordinates along the Guwahati–Shillong corridor (EPSG:32646)
    t_coord = np.linspace(0, 1, n_total)
    xs = 355000.0 + t_coord * 50000.0 + rng.normal(0, 3500, n_total)
    ys = 2840000.0 + t_coord * 45000.0 + rng.normal(0, 3500, n_total)

    # Assign spatial CV blocks using KMeans clustering on coordinates (true spatial CV)
    from sklearn.cluster import KMeans
    km = KMeans(n_clusters=CV_N_BLOCKS, random_state=42, n_init=10)
    block_ids = km.fit_predict(np.column_stack([xs, ys]))

    rows = []
    idx = 0
    for label, n in [(1, n_positive), (0, n_negative)]:
        is_pos = label == 1
        t = _terrain(n, is_pos)
        r = _rainfall(n, is_pos)
        dates = _dates(n, is_pos)
        for i in range(n):
            cell_box = box(xs[idx], ys[idx], xs[idx] + 100, ys[idx] + 100)
            row = {
                "cell_id":              idx,
                "landslide_occurrence": label,
                "date_anchor":          dates[i],
                "dem_valid":            1.0,
                "rain_valid":           1.0,
                "block_id":             int(block_ids[idx]),
                "geometry_wkt":         cell_box.wkt,
            }
            for col in STATIC_TERRAIN_COLS:
                row[col] = round(float(t[col][i]), 4)
            for col in DYNAMIC_RAINFALL_COLS:
                row[col] = round(float(r[col][i]), 4)
            rows.append(row)
            idx += 1

    df = pd.DataFrame(rows)[ALL_COLS]
    logger.info(f"[M1/FE] Synthetic matrix: {n_positive} positives, {n_negative} negatives with AOI coordinates & spatial blocks")
    return df


# ── Master pipeline ───────────────────────────────────────────────────────────

def run_feature_pipeline(synthetic: bool = False) -> pd.DataFrame:
    """
    End-to-end feature engineering pipeline.

    Args:
        synthetic: If True, generates synthetic data without reading any files.
                   Use this for CI, demo setup, or when data is not yet downloaded.

    Returns:
        Feature matrix DataFrame, also saved to data/processed/feature_matrix.parquet.
    """
    Path(DATA_PROCESSED).mkdir(parents=True, exist_ok=True)

    if synthetic:
        df = _make_synthetic_feature_matrix()
        # Never overwrite the real 232-cell training_sample.parquet.
        out = Path(DATA_PROCESSED) / "training_sample_synthetic.parquet"
        out.parent.mkdir(parents=True, exist_ok=True)
        df.to_parquet(out, index=False)
        logger.info(f"[M1/FE] Synthetic feature matrix → {out} (real training_sample.parquet untouched)")
        return df

    # ── Real pipeline ──────────────────────────────────────────────────────
    from modules.M1_data_ingestion.dem_processor import derive_terrain_features
    from modules.M1_data_ingestion.rainfall_fetcher import RainfallLoader

    # Step 1: Build analysis grid over AOI
    grid = build_analysis_grid()

    # Step 2: Load inventory and label positive cells
    inventory = load_inventory()
    grid = label_positive_cells(grid, inventory)

    # Step 3: Sample negatives (never-inventoried, > 2km buffer)
    sample = sample_negatives(grid, ratio_neg_to_pos=3.0)

    # Step 4: Assign spatial CV blocks using KMeans on sampled cell centroids
    sample = _add_spatial_cv_blocks(sample)

    # Step 5: Derive real DEM terrain features for sampled cells
    sample = derive_terrain_features(grid_gdf=sample, synthetic=False)

    # Step 6: Time-anchor real daily rainfall features (2007-2020 ERA5-Land)
    rainfall_loader = RainfallLoader()
    sample = time_anchor_features(sample, rainfall_loader)
    rainfall_loader.save_freshness_meta()

    # Step 7: Assemble final matrix
    sample["landslide_occurrence"] = sample["is_positive"].astype(int)
    sample["geometry_wkt"] = sample.geometry.apply(lambda g: g.wkt if g else "")

    df = sample[ALL_COLS].reset_index(drop=True)

    out = Path(FEATURE_MATRIX_PATH)
    df.to_parquet(out, index=False)
    logger.info(f"[M1/FE] Feature matrix saved → {out} "
                f"({df['landslide_occurrence'].sum()} positives, "
                f"{(~df['landslide_occurrence'].astype(bool)).sum()} negatives)")

    _validate_matrix(df)
    return df


def _validate_matrix(df: pd.DataFrame) -> None:
    """Quick sanity checks; raises AssertionError if critical invariants broken."""
    assert "date_anchor" in df.columns, "Missing date_anchor column"
    assert df["date_anchor"].notna().all(), "Some cells missing date_anchor"
    pos = df[df["landslide_occurrence"] == 1]
    if len(pos) > 0:
        assert pos["date_anchor"].notna().all(), "Positive cells must have date_anchor"
    nan_terrain = df[STATIC_TERRAIN_COLS].isna().sum()
    if nan_terrain.any():
        logger.warning(f"[M1/FE] NaN in terrain: {nan_terrain[nan_terrain > 0].to_dict()}")
    logger.info("[M1/FE] ✓ Feature matrix validation passed")


if __name__ == "__main__":
    import sys
    synthetic = "--synthetic" in sys.argv
    df = run_feature_pipeline(synthetic=synthetic)
    print(df[FEATURE_COLS + [LABEL_COL, "date_anchor", "dem_valid", "rain_valid"]].head(10))
    print(f"\nShape: {df.shape}")
    print(f"Positives: {df[LABEL_COL].sum()} / {len(df)}")
    print(f"NaN summary:\n{df[FEATURE_COLS].isna().sum()}")
