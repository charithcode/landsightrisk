"""
spatial_intersect.py — M4: Road Exposure Mapping
=================================================
Intersect risk grid cells with road segments to compute exposure score.
Each road segment gets: max_risk_along_segment, mean_risk_along_segment.
TODO: Implement GeoPandas spatial join + overlay.
"""
import geopandas as gpd
from loguru import logger

def intersect_risk_with_roads(risk_gdf: gpd.GeoDataFrame,
                               roads_gdf: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    """Spatial join to attach risk scores to road segments."""
    logger.info("[M4] Intersecting risk layer with road network")
    raise NotImplementedError("Spatial intersect not yet implemented")

