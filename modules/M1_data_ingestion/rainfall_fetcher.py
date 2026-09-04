"""
rainfall_fetcher.py — M1: Data Ingestion
=========================================
Fetches rainfall data from IMD gridded product and NASA GPM IMERG.
Returns a GeoDataFrame with rainfall values per grid cell for the
target bounding box and rolling time window.
"""

import os
import requests
import pandas as pd
import geopandas as gpd
from loguru import logger
from dotenv import load_dotenv

load_dotenv()

BBOX = {
    "lat_min": float(os.getenv("BBOX_LAT_MIN", 25.4)),
    "lat_max": float(os.getenv("BBOX_LAT_MAX", 26.2)),
    "lon_min": float(os.getenv("BBOX_LON_MIN", 93.8)),
    "lon_max": float(os.getenv("BBOX_LON_MAX", 94.6)),
}
WINDOW_HOURS = int(os.getenv("RAINFALL_WINDOW_HOURS", 72))


def fetch_imd_rainfall(date_str: str) -> pd.DataFrame:
    """
    Fetch IMD gridded daily rainfall for the target district.
    
    Args:
        date_str: Date in 'YYYY-MM-DD' format
    
    Returns:
        DataFrame with columns [lat, lon, rainfall_mm]
    
    TODO: Implement real IMD API call or file-based fallback.
    """
    logger.info(f"[M1] Fetching IMD rainfall for {date_str}")
    # TODO: Replace with actual IMD API / file reader
    raise NotImplementedError("IMD rainfall fetcher not yet implemented")


def fetch_gpm_imerg(start_dt: str, end_dt: str) -> pd.DataFrame:
    """
    Fetch NASA GPM IMERG half-hourly precipitation for the rolling window.
    
    Args:
        start_dt: Start datetime string
        end_dt:   End datetime string
    
    Returns:
        DataFrame with columns [lat, lon, rainfall_mm_per_hour, timestamp]
    
    TODO: Use NASA Earthdata API with auth token.
    """
    logger.info(f"[M1] Fetching GPM IMERG: {start_dt} → {end_dt}")
    # TODO: Implement NASA Earthdata GPM fetch
    raise NotImplementedError("GPM IMERG fetcher not yet implemented")


def get_rolling_rainfall(window_hours: int = WINDOW_HOURS) -> gpd.GeoDataFrame:
    """
    Aggregate rainfall over the rolling window for the target bbox.
    
    Returns:
        GeoDataFrame with total rainfall per grid cell over the window.
    """
    logger.info(f"[M1] Building {window_hours}h rolling rainfall layer")
    # TODO: Combine IMD + GPM, aggregate, clip to BBOX
    raise NotImplementedError("Rolling rainfall aggregator not yet implemented")
