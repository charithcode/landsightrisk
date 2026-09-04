"""
feature_engineer.py — M1: Data Ingestion
==========================================
Merges all data source layers into a single unified feature matrix.
Each row = one slope unit / grid cell.

Output columns:
  cell_id, lat, lon, geometry,
  rainfall_72h_mm, soil_moisture_pct,
  elevation_m, slope_deg, aspect_deg, twi, curvature,
  lulc_class, dist_to_road_m, dist_to_stream_m,
  historical_landslide_density,
  data_freshness_hours, data_completeness_score
"""

import pandas as pd
import geopandas as gpd
from loguru import logger

from modules.M1_data_ingestion.rainfall_fetcher import get_rolling_rainfall
from modules.M1_data_ingestion.dem_processor import derive_all_terrain_features


def merge_all_sources() -> gpd.GeoDataFrame:
    """
    Merge all environmental data layers into one feature matrix.

    Returns:
        GeoDataFrame — one row per grid cell with all features populated.
        Saves to data/processed/feature_matrix.csv
    """
    logger.info("[M1] Starting full feature engineering pipeline")

    # TODO: Step 1 — load terrain features
    # terrain_gdf = derive_all_terrain_features()

    # TODO: Step 2 — load rainfall layer and spatial join
    # rainfall_gdf = get_rolling_rainfall()

    # TODO: Step 3 — join soil moisture

    # TODO: Step 4 — join land cover

    # TODO: Step 5 — join historical landslide density

    # TODO: Step 6 — compute data_freshness and data_completeness scores
    #   (feeds into M3 Uncertainty Engine)

    # TODO: Step 7 — export
    # feature_matrix.to_csv("data/processed/feature_matrix.csv", index=False)

    raise NotImplementedError("Feature engineering pipeline not yet implemented")


if __name__ == "__main__":
    gdf = merge_all_sources()
    print(gdf.head())
