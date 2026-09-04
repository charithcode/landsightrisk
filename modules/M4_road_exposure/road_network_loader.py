"""
road_network_loader.py — M4: Road Exposure Mapping
====================================================
Load OSM + NRSC road shapefiles and clip to target district bbox.
Tag each segment with road_class (NH/SH/MDR/ODR) and surface type.
TODO: Implement shapefile loader + bbox clip + attribute enrichment.
"""
import geopandas as gpd
from loguru import logger

def load_roads(shapefile_path: str, bbox: dict) -> gpd.GeoDataFrame:
    """Load and clip road network to bounding box."""
    logger.info(f"[M4] Loading roads from {shapefile_path}")
    raise NotImplementedError("Road loader not yet implemented")

