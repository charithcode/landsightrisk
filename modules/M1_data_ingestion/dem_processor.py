"""
dem_processor.py — M1: Data Ingestion
=======================================
Loads a Digital Elevation Model (DEM) raster (SRTM 30m or ASTER)
and derives terrain morphology features for each grid cell.

Derived features:
  - slope (degrees)
  - aspect (degrees from north)
  - curvature (plan + profile)
  - Topographic Wetness Index (TWI)
  - Relative Relief
"""

import numpy as np
import rasterio
from rasterio.warp import reproject, Resampling
import geopandas as gpd
from loguru import logger


DEM_PATH = "data/raw/dem/srtm_30m.tif"


def load_dem(dem_path: str = DEM_PATH) -> tuple:
    """
    Load DEM raster.

    Returns:
        (elevation_array, transform, crs)
    """
    logger.info(f"[M1] Loading DEM from {dem_path}")
    with rasterio.open(dem_path) as src:
        elevation = src.read(1).astype(np.float32)
        transform = src.transform
        crs = src.crs
    return elevation, transform, crs


def compute_slope(elevation: np.ndarray, cell_size: float = 30.0) -> np.ndarray:
    """
    Compute slope in degrees from elevation array.

    Args:
        elevation: 2D numpy array of elevation values (metres)
        cell_size: Pixel size in metres (default 30m for SRTM)

    Returns:
        2D numpy array of slope values in degrees
    """
    # TODO: Use numpy gradient or richdem for slope calculation
    raise NotImplementedError("Slope computation not yet implemented")


def compute_aspect(elevation: np.ndarray) -> np.ndarray:
    """Compute aspect (direction of steepest descent) in degrees."""
    # TODO: Implement
    raise NotImplementedError("Aspect computation not yet implemented")


def compute_twi(slope: np.ndarray, upslope_area: np.ndarray) -> np.ndarray:
    """
    Topographic Wetness Index = ln(upslope_area / tan(slope))
    Higher TWI → more water accumulation → higher landslide susceptibility.
    """
    # TODO: Implement
    raise NotImplementedError("TWI computation not yet implemented")


def derive_all_terrain_features(dem_path: str = DEM_PATH) -> gpd.GeoDataFrame:
    """
    Master function: load DEM and return all terrain features as GeoDataFrame.

    Returns:
        GeoDataFrame with columns [geometry, elevation, slope, aspect, twi, curvature]
    """
    logger.info("[M1] Deriving all terrain features from DEM")
    # TODO: Call load_dem → compute_slope → compute_aspect → compute_twi → convert to GDF
    raise NotImplementedError("Full terrain feature derivation not yet implemented")
