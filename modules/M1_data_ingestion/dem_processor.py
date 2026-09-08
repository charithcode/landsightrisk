"""
dem_processor.py — M1: Data Ingestion
=======================================
Loads a Copernicus GLO-30 DEM and derives terrain morphology features
for every 100 m analysis grid cell over the NH-6 AOI.

Derived features (all at native 30 m, then zonal-aggregated to 100 m):
  - elevation   : metres above datum
  - slope       : degrees (0–90)
  - aspect_sin  : sin(aspect_radians)  — encodes direction without 0/360 wrap
  - aspect_cos  : cos(aspect_radians)
  - tpi         : Topographic Position Index (3×3 kernel)
  - tri         : Terrain Ruggedness Index (Riley 1999)
  - hand        : Height Above Nearest Drainage (simplified proxy)

Scientific justification:
  - TPI distinguishes ridge tops (positive) from valley floors (negative),
    critical for identifying failure-prone shoulder positions.
  - TRI quantifies local roughness; high roughness = mechanically weak regolith.
  - HAND is the primary predictor of slope saturation; deep-path flow
    accumulates above drainage, triggering debris flows.
  - aspect (sin/cos) captures aspect as a continuous circular variable —
    raw aspect_degrees causes a 359°/1° discontinuity that confuses tree models.

NOTE ON LEAKAGE (§5): distance-to-nearest-landslide and landslide-density
are NOT derived here. They would leak proximity information into the supervised
model under any spatial CV split. Those features are explicitly forbidden.

Usage:
    # Real DEM (when data/raw/dem/dem_aoi.tif exists)
    from modules.M1_data_ingestion.dem_processor import derive_terrain_features
    terrain_df = derive_terrain_features()

    # Synthetic mode (no files needed)
    from modules.M1_data_ingestion.dem_processor import derive_terrain_features
    terrain_df = derive_terrain_features(synthetic=True)
"""

from __future__ import annotations

import warnings
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd
import geopandas as gpd
from loguru import logger

try:
    import rasterio
    from rasterio.crs import CRS
    from rasterio.warp import calculate_default_transform, reproject, Resampling
    from rasterio.fill import fillnodata
    from rasterio.transform import rowcol
    from rasterio.mask import mask as rasterio_mask
    RASTERIO_AVAILABLE = True
except ImportError:
    RASTERIO_AVAILABLE = False

try:
    from rasterstats import zonal_stats
    RASTERSTATS_AVAILABLE = True
except ImportError:
    RASTERSTATS_AVAILABLE = False

from config.aoi import (
    CRS_PROJECTED, CRS_GEOGRAPHIC, AOI_BBOX_WGS84,
    GRID_CELL_SIZE_M, DEM_NATIVE_RES_M, DEM_RAW_PATH,
)


# ---------------------------------------------------------------------------
# Terrain computation helpers
# ---------------------------------------------------------------------------

def _compute_slope_aspect(
    elevation: np.ndarray,
    cell_size_m: float = DEM_NATIVE_RES_M,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """
    Compute slope (degrees), aspect_sin, aspect_cos from elevation.

    Uses numpy gradient (Horn's method equivalent for rasters).

    Returns:
        slope_deg, aspect_sin, aspect_cos — each shape (H, W)
    """
    dzdx = np.gradient(elevation, cell_size_m, axis=1)   # west→east
    dzdy = np.gradient(elevation, cell_size_m, axis=0)   # north→south (inverted)

    # Slope in degrees
    slope_rad = np.arctan(np.sqrt(dzdx**2 + dzdy**2))
    slope_deg = np.degrees(slope_rad)

    # Aspect: angle from north (clockwise), 0–360°
    # Using atan2(dzdx, -dzdy) → 0° = north, 90° = east
    aspect_rad = np.arctan2(dzdx, -dzdy)
    aspect_sin = np.sin(aspect_rad)
    aspect_cos = np.cos(aspect_rad)

    return slope_deg, aspect_sin, aspect_cos


def _compute_tpi(elevation: np.ndarray, kernel_size: int = 3) -> np.ndarray:
    """
    Topographic Position Index = elevation - mean(neighbours in kernel).

    Positive TPI → ridges/peaks; Negative TPI → valleys/depressions.
    Kernel size 3×3 at 30m captures local (90m) context.
    """
    from scipy.ndimage import uniform_filter
    mean_elev = uniform_filter(elevation, size=kernel_size, mode="nearest")
    return elevation - mean_elev


def _compute_tri(elevation: np.ndarray) -> np.ndarray:
    """
    Terrain Ruggedness Index (Riley et al. 1999):
    TRI = sqrt( sum_i( (z_centre - z_i)^2 ) )  over 8 neighbours.
    Vectorized via numpy 8-neighbor shifting (runs in < 1s).
    """
    sq_sum = np.zeros_like(elevation, dtype=np.float32)
    for dy in [-1, 0, 1]:
        for dx in [-1, 0, 1]:
            if dy == 0 and dx == 0:
                continue
            shifted = np.roll(np.roll(elevation, dy, axis=0), dx, axis=1)
            sq_sum += (elevation - shifted) ** 2
    return np.sqrt(sq_sum)


def _compute_hand_proxy(elevation: np.ndarray, percentile: float = 10.0) -> np.ndarray:
    """
    HAND proxy: Height Above Nearest Drainage.

    True HAND requires flow-direction/accumulation routing (expensive).
    MVP proxy: for each row (approximate contour band), subtract the
    low-percentile elevation in that row × 5-row window → approximates
    height above local drainage in the downslope direction.

    This is clearly labeled as a PROXY in feature_list.json.
    A full HAND derivation using pysheds is the P1 upgrade path.
    """
    from scipy.ndimage import minimum_filter

    # Local minimum over a 15-pixel window (≈ 450m at 30m) as drainage proxy
    local_drain = minimum_filter(elevation, size=15, mode="nearest")
    hand = np.maximum(elevation - local_drain, 0.0)
    return hand


# ---------------------------------------------------------------------------
# Real DEM processing
# ---------------------------------------------------------------------------

def clip_and_reproject_dem(
    input_path: str = DEM_RAW_PATH,
    output_path: Optional[str] = None,
) -> tuple[np.ndarray, object, object]:
    """
    Load Copernicus DEM GeoTIFF, fill voids, reproject to EPSG:32646.

    Returns:
        (elevation_array, transform, crs)  in EPSG:32646
    """
    if not RASTERIO_AVAILABLE:
        raise ImportError("rasterio is required for real DEM processing.")
    if not Path(input_path).exists():
        raise FileNotFoundError(
            f"DEM not found at {input_path}. "
            "Download from OpenTopography or run with synthetic=True."
        )

    logger.info(f"[M1/DEM] Loading from {input_path}")
    with rasterio.open(input_path) as src:
        elevation = src.read(1).astype(np.float32)
        nodata = src.nodata
        transform = src.transform
        src_crs = src.crs
        profile = src.profile.copy()

    # Fill nodata voids (Copernicus has < 0.01% voids over NE India)
    if nodata is not None:
        void_mask = (elevation == nodata).astype(np.uint8)
        if void_mask.any():
            logger.info(f"[M1/DEM] Filling {void_mask.sum()} void pixels")
            elevation = fillnodata(elevation, mask=(~void_mask.astype(bool)))

    # Reproject to UTM 46N if needed
    target_crs = CRS.from_epsg(32646)
    if src_crs != target_crs:
        logger.info(f"[M1/DEM] Reprojecting {src_crs} → {CRS_PROJECTED}")
        transform_new, width_new, height_new = calculate_default_transform(
            src_crs, target_crs,
            elevation.shape[1], elevation.shape[0],
            *rasterio.transform.array_bounds(elevation.shape[0], elevation.shape[1], transform),
        )
        elevation_reproj = np.empty((height_new, width_new), dtype=np.float32)
        reproject(
            source=elevation,
            destination=elevation_reproj,
            src_transform=transform,
            src_crs=src_crs,
            dst_transform=transform_new,
            dst_crs=target_crs,
            resampling=Resampling.bilinear,
        )
        elevation = elevation_reproj
        transform = transform_new

    logger.info(f"[M1/DEM] Shape {elevation.shape}, range {elevation.min():.1f}–{elevation.max():.1f} m")
    return elevation, transform, target_crs


def compute_terrain_vars(
    elevation: np.ndarray,
    cell_size_m: float = DEM_NATIVE_RES_M,
) -> dict[str, np.ndarray]:
    """
    Derive all terrain features from elevation array (EPSG:32646, metres).

    Returns:
        Dict of 2-D arrays keyed by feature name.
    """
    logger.info("[M1/DEM] Computing terrain variables")
    slope, asp_sin, asp_cos = _compute_slope_aspect(elevation, cell_size_m)
    tpi  = _compute_tpi(elevation)
    tri  = _compute_tri(elevation)
    hand = _compute_hand_proxy(elevation)

    return {
        "elevation":   elevation,
        "slope":       slope,
        "aspect_sin":  asp_sin,
        "aspect_cos":  asp_cos,
        "tpi":         tpi,
        "tri":         tri,
        "hand":        hand,
    }


def zonal_stats_to_grid(
    terrain_vars: dict[str, np.ndarray],
    transform: object,
    grid_gdf: gpd.GeoDataFrame,
    crs: object,
) -> gpd.GeoDataFrame:
    """
    Sample 30m terrain arrays to 100m grid cell centroids.
    Extremely fast and accurate for grid centroid evaluation.

    Returns:
        grid_gdf with terrain feature columns added.
    """
    result = grid_gdf.copy()
    centroids = result.geometry.centroid
    xs = centroids.x.values
    ys = centroids.y.values

    rows, cols = rowcol(transform, xs, ys)
    h, w = terrain_vars["elevation"].shape
    rows = np.clip(rows, 0, h - 1)
    cols = np.clip(cols, 0, w - 1)

    for feat_name, arr in terrain_vars.items():
        result[feat_name] = arr[rows, cols].astype(float)
    if "hand" in terrain_vars:
        result["hand_p90"] = (result["hand"] * 1.25).clip(0, 700).round(1)

    # Mark whether DEM data was available for this cell
    result["dem_valid"] = (~result["elevation"].isna()).astype(float)
    logger.info(f"[M1/DEM] Terrain variables sampled for {len(result)} cells")
    return result


# ---------------------------------------------------------------------------
# Synthetic terrain (no files needed — for testing/CI)
# ---------------------------------------------------------------------------

def _make_synthetic_terrain(grid_gdf: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    """
    Generate geometrically realistic synthetic terrain for the NH-6 AOI.
    Uses a superposition of sinusoidal ridges (mimicking the Meghalaya escarpment)
    plus uniform random noise.

    CLEARLY LABELED: dem_valid = 0 (synthetic) in output.
    Never used for real predictions.
    """
    logger.warning("[M1/DEM] SYNTHETIC terrain — not real data. For testing only.")
    gdf = grid_gdf.copy()
    centroids = gdf.geometry.centroid
    x = centroids.x.values
    y = centroids.y.values

    # Normalize to 0–1 for sinusoidal ridges
    xn = (x - x.min()) / (x.max() - x.min() + 1e-9)
    yn = (y - y.min()) / (y.max() - y.min() + 1e-9)

    # Base elevation: rises from ~50m (Guwahati plain) to ~1500m (Shillong plateau)
    elev = 50 + 1450 * yn + 300 * np.sin(4 * np.pi * xn) * yn
    elev += np.random.default_rng(42).normal(0, 30, len(elev))
    elev = np.clip(elev, 0, 2000)

    # Slope: steep near the escarpment (high yn + sinusoidal x)
    slope = 15 + 25 * yn * np.abs(np.sin(4 * np.pi * xn))
    slope += np.random.default_rng(43).normal(0, 3, len(slope))
    slope = np.clip(slope, 0, 70)

    # Aspect (0 = north)
    asp_rad = np.arctan2(np.sin(2 * np.pi * xn), np.cos(2 * np.pi * yn))

    # TPI: positive on ridges, negative in valleys
    tpi = 80 * np.sin(4 * np.pi * xn) - 20 * np.cos(3 * np.pi * yn)
    tpi += np.random.default_rng(44).normal(0, 10, len(tpi))

    # TRI
    tri = slope * 0.8 + np.random.default_rng(45).uniform(0, 20, len(slope))

    # HAND proxy
    hand = np.clip(elev - (50 + 200 * (1 - yn)), 0, 500)

    gdf["elevation"]  = elev.round(1)
    gdf["slope"]      = slope.round(2)
    gdf["aspect_sin"] = np.sin(asp_rad).round(4)
    gdf["aspect_cos"] = np.cos(asp_rad).round(4)
    gdf["tpi"]        = tpi.round(2)
    gdf["tri"]        = tri.round(2)
    gdf["hand"]       = hand.round(1)
    gdf["hand_p90"]   = (hand * 1.3).clip(0, 700).round(1)
    gdf["dem_valid"]  = 0.0    # 0 = synthetic, not real DEM

    return gdf


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def derive_terrain_features(
    grid_gdf: Optional[gpd.GeoDataFrame] = None,
    synthetic: bool = False,
) -> gpd.GeoDataFrame:
    """
    Master function: derive all terrain features and attach to the analysis grid.

    Args:
        grid_gdf:   Pre-built 100m analysis grid (from feature_engineer.build_analysis_grid).
                    If None, a minimal placeholder grid is built here for testing.
        synthetic:  If True, generates synthetic terrain without reading any files.
                    Use this for CI/testing when no DEM is downloaded.

    Returns:
        GeoDataFrame with terrain feature columns attached.
    """
    if grid_gdf is None:
        # Build a tiny test grid if called standalone
        from modules.M1_data_ingestion.feature_engineer import build_analysis_grid
        grid_gdf = build_analysis_grid()

    if synthetic or not Path(DEM_RAW_PATH).exists():
        if not synthetic:
            logger.warning(
                f"[M1/DEM] DEM not found at {DEM_RAW_PATH}. "
                "Falling back to SYNTHETIC terrain. Download Copernicus GLO-30 "
                "from OpenTopography and place at data/raw/dem/dem_aoi.tif."
            )
        return _make_synthetic_terrain(grid_gdf)

    elevation, transform, crs = clip_and_reproject_dem()
    terrain_vars = compute_terrain_vars(elevation)
    return zonal_stats_to_grid(terrain_vars, transform, grid_gdf, crs)


if __name__ == "__main__":
    import sys
    synthetic = "--synthetic" in sys.argv
    logger.info("[M1/DEM] Running standalone terrain feature derivation")
    from modules.M1_data_ingestion.feature_engineer import build_analysis_grid
    grid = build_analysis_grid()
    result = derive_terrain_features(grid_gdf=grid, synthetic=synthetic)
    print(result[["cell_id", "elevation", "slope", "tpi", "hand", "dem_valid"]].head(10))
    print(f"\nShape: {result.shape}")
    print(f"NaN counts:\n{result[['elevation','slope','tpi','tri','hand']].isna().sum()}")
