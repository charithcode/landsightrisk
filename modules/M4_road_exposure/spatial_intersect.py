"""
spatial_intersect.py — M4: Road Exposure
==========================================
Performs buffered spatial join between risk cells and road segments.
Also snaps village/hospital points to the road graph.

Design (§8):
  - Each segment gets a 50m buffer; risk_max = max(p) of intersecting cells
  - confidence_min = min(confidence) among intersecting cells (conservative)
  - Village snap: nearest graph node ≤ 1.5km; farther → "unconnected" flag
  - No sliding-window rasters; plain buffered spatial joins — fast and correct.

Output:
  data/processed/segments_risk.geojson — roads with risk attributes
  data/processed/villages_snapped.gpkg — villages snapped to graph nodes
  data/processed/exposed_roads.geojson  — segments with risk ≥ τ_alert
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd
import geopandas as gpd
from shapely.geometry import Point
from loguru import logger

import networkx as nx

from config.aoi import (
    CRS_PROJECTED, CRS_GEOGRAPHIC, DATA_PROCESSED, SEGMENT_BUFFER_M,
    VILLAGE_SNAP_CAP_M, ROADS_GPKG_PATH, GRAPH_GPICKLE_PATH,
    VILLAGES_RAW_PATH, HOSPITALS_RAW_PATH,
    TAU_ALERT, FULL_GRID_RASTER_PATH,
)


# ── Segment risk assignment ────────────────────────────────────────────────────

def assign_risk_to_segments(
    segments_gdf: gpd.GeoDataFrame,
    cells_gdf: Optional[gpd.GeoDataFrame] = None,
    raster_path: Optional[str] = None,
    p_2d: Optional[np.ndarray] = None,
    conf_2d: Optional[np.ndarray] = None,
    raster_transform: Optional[object] = None,
    buffer_m: float = SEGMENT_BUFFER_M,
) -> gpd.GeoDataFrame:
    """
    For each road segment, compute:
      risk_max  = max(p) of risk cells along/within the segment
      conf_min  = min(confidence) of intersecting cells (conservative)

    Supports:
      1. Full-grid raster sampling (fastest, wall-to-wall exact across all 588,952 cells).
      2. Vector spatial join fallback (if only cells_gdf is provided).
    """
    if str(segments_gdf.crs) != CRS_PROJECTED:
        segments_gdf = segments_gdf.to_crs(CRS_PROJECTED)

    seg = segments_gdf.copy()

    # Determine whether raster sampling is available
    use_raster = False
    if p_2d is not None and conf_2d is not None and raster_transform is not None:
        use_raster = True
    else:
        target_tif = raster_path or FULL_GRID_RASTER_PATH
        if target_tif and Path(target_tif).exists():
            import rasterio
            with rasterio.open(str(target_tif)) as src:
                p_2d = src.read(1)
                conf_2d = src.read(2)
                raster_transform = src.transform
            use_raster = True

    if use_raster:
        logger.info(f"[M4/SI] Sampling wall-to-wall risk surface raster for {len(seg):,} road segments")
        from rasterio.transform import rowcol
        ny, nx = p_2d.shape

        seg_indices = []
        xs, ys = [], []
        for i, geom in enumerate(seg.geometry):
            if geom is not None and not geom.is_empty:
                c = geom.coords
                xs.extend([pt[0] for pt in c])
                ys.extend([pt[1] for pt in c])
                seg_indices.extend([i] * len(c))

        if len(xs) > 0:
            xs_arr = np.array(xs, dtype=np.float64)
            ys_arr = np.array(ys, dtype=np.float64)
            seg_idx_arr = np.array(seg_indices, dtype=np.int32)

            rows, cols = rowcol(raster_transform, xs_arr, ys_arr)
            rows = np.clip(rows, 0, ny - 1)
            cols = np.clip(cols, 0, nx - 1)

            sampled_p = p_2d[rows, cols]
            sampled_conf = conf_2d[rows, cols]

            df_pts = pd.DataFrame({
                "seg_idx": seg_idx_arr,
                "p": sampled_p,
                "conf": sampled_conf
            })
            agg = df_pts.groupby("seg_idx").agg(
                risk_max=("p", "max"),
                conf_min=("conf", "min"),
                cell_count=("p", "count"),
            ).reset_index()

            seg_clean = seg.drop(columns=["risk_max", "conf_min", "cell_count", "_buffer"], errors="ignore")
            seg_clean["_idx"] = np.arange(len(seg_clean))
            result = seg_clean.merge(agg, left_on="_idx", right_on="seg_idx", how="left")
            result = result.drop(columns=["_idx", "seg_idx"])
            result["risk_max"] = result["risk_max"].fillna(0.0).round(4)
            result["conf_min"] = result["conf_min"].fillna(1.0).round(4)
            result["cell_count"] = result["cell_count"].fillna(0).astype(int)
        else:
            result = seg
            result["risk_max"] = 0.0
            result["conf_min"] = 1.0
            result["cell_count"] = 0

        n_exposed = (result["risk_max"] >= TAU_ALERT).sum()
        logger.info(f"[M4/SI] Wall-to-wall raster sampling complete: {n_exposed} segments with risk_max ≥ τ_alert ({TAU_ALERT})")
        return result

    # Fallback to vector spatial join
    if cells_gdf is None or cells_gdf.empty:
        logger.warning("[M4/SI] Neither raster nor cells_gdf provided; assigning zero risk")
        seg["risk_max"] = 0.0
        seg["conf_min"] = 1.0
        seg["cell_count"] = 0
        return seg

    logger.info(f"[M4/SI] Assigning risk to {len(segments_gdf)} segments via vector spatial join (buffer={buffer_m}m)")
    if str(cells_gdf.crs) != CRS_PROJECTED:
        cells_gdf = cells_gdf.to_crs(CRS_PROJECTED)

    seg["_buffer"] = seg.geometry.buffer(buffer_m)
    seg_buf = seg.set_geometry("_buffer")[["seg_id", "_buffer"]]

    cells_join = cells_gdf[["cell_id", "p", "confidence", "geometry"]].copy()
    if "confidence" not in cells_join.columns:
        cells_join["confidence"] = cells_join["p"]

    joined = gpd.sjoin(
        seg_buf,
        cells_join,
        how="left",
        predicate="intersects",
    )

    agg = joined.groupby("seg_id").agg(
        risk_max=("p", "max"),
        conf_min=("confidence", "min"),
        cell_count=("cell_id", "count"),
    ).reset_index()

    seg_clean = seg.drop(columns=["risk_max", "conf_min", "cell_count", "_buffer"], errors="ignore")
    result = seg_clean.merge(agg, on="seg_id", how="left")
    result["risk_max"] = result["risk_max"].fillna(0.0).round(4)
    result["conf_min"] = result["conf_min"].fillna(1.0).round(4)
    result["cell_count"] = result["cell_count"].fillna(0).astype(int)

    n_exposed = (result["risk_max"] >= TAU_ALERT).sum()
    logger.info(f"[M4/SI] Vector spatial join complete: {n_exposed} segments with risk_max ≥ τ_alert ({TAU_ALERT})")
    return result


# ── Village / hospital snapping ───────────────────────────────────────────────

def load_places(
    villages_path: str = VILLAGES_RAW_PATH,
    hospitals_path: str = HOSPITALS_RAW_PATH,
    G: Optional[nx.MultiDiGraph] = None,
) -> tuple[gpd.GeoDataFrame, gpd.GeoDataFrame]:
    """
    Load village and hospital point GeoDataFrames.
    Falls back to graph nodes if files not found.
    """
    def _load(path: str, place_type: str) -> gpd.GeoDataFrame:
        if Path(path).exists():
            gdf = gpd.read_file(path)
            if str(gdf.crs) != CRS_PROJECTED:
                gdf = gdf.to_crs(CRS_PROJECTED)
            return gdf
        if G is not None:
            nodes_data = [
                {"name": d.get("name", f"{place_type}_{n}"),
                 "pop_est": d.get("pop_est", 1000),
                 "geometry": Point(d.get("x", 0), d.get("y", 0))}
                for n, d in G.nodes(data=True) if d.get("node_type") == place_type.lower()
            ]
            if nodes_data:
                logger.info(f"[M4/SI] Loaded {len(nodes_data)} {place_type}s directly from road graph")
                return gpd.GeoDataFrame(nodes_data, geometry="geometry", crs=CRS_PROJECTED)
        logger.warning(
            f"[M4/SI] {place_type} file not found at {path}. "
            "Using empty GDF — connectivity metrics will be incomplete."
        )
        return gpd.GeoDataFrame(
            columns=["name", "pop_est", "geometry"],
            geometry="geometry", crs=CRS_PROJECTED,
        )

    return _load(villages_path, "village"), _load(hospitals_path, "hospital")


def snap_places_to_graph(
    places_gdf: gpd.GeoDataFrame,
    G: nx.MultiDiGraph,
    snap_cap_m: float = VILLAGE_SNAP_CAP_M,
    place_type: str = "village",
) -> gpd.GeoDataFrame:
    """
    Snap each place point to the nearest graph node.
    Places farther than snap_cap_m are flagged as "unconnected".

    Returns:
        places_gdf with added columns [snap_node, snap_dist_m, unconnected]
    """
    if places_gdf.empty:
        return places_gdf

    logger.info(f"[M4/SI] Snapping {len(places_gdf)} {place_type}s to graph")

    # Build node lookup arrays
    node_ids = list(G.nodes())
    node_x   = np.array([G.nodes[n].get("x", 0) for n in node_ids])
    node_y   = np.array([G.nodes[n].get("y", 0) for n in node_ids])

    result = places_gdf.copy()
    snap_nodes = []
    snap_dists = []
    unconnected = []

    for _, row in result.iterrows():
        pt_x = row.geometry.x
        pt_y = row.geometry.y
        dists = np.hypot(node_x - pt_x, node_y - pt_y)
        nearest_i = int(np.argmin(dists))
        dist = float(dists[nearest_i])
        snap_nodes.append(node_ids[nearest_i])
        snap_dists.append(round(dist, 1))
        unconnected.append(dist > snap_cap_m)

    result["snap_node"]    = snap_nodes
    result["snap_dist_m"]  = snap_dists
    result["unconnected"]  = unconnected
    result["place_type"]   = place_type

    if not result.get("village_id", pd.Series()).any() if hasattr(result, "get") else True:
        result["village_id"] = [f"{place_type}_{i}" for i in range(len(result))]

    n_unconnected = sum(unconnected)
    logger.info(f"[M4/SI] {n_unconnected}/{len(result)} {place_type}s unconnected (>{snap_cap_m}m from road)")
    return result


# ── Exposed layers ────────────────────────────────────────────────────────────

def build_exposed_layers(
    segments_risk: gpd.GeoDataFrame,
    villages_snapped: gpd.GeoDataFrame,
    tau_alert: float = TAU_ALERT,
    exposure_buffer_m: float = 500.0,
) -> tuple[gpd.GeoDataFrame, gpd.GeoDataFrame]:
    """
    Build exposed_roads and exposed_communities layers.

    exposed_roads: segments with risk_max ≥ τ_alert
    exposed_communities: villages whose nearest exposed segment is ≤ 500m

    Returns:
        (exposed_roads_gdf, exposed_communities_gdf)
    """
    exposed_roads = segments_risk[segments_risk["risk_max"] >= tau_alert].copy()

    if exposed_roads.empty or villages_snapped.empty:
        return exposed_roads, villages_snapped.copy()

    # Fast spatial query using sindex instead of slow unary_union buffer
    tree = exposed_roads.sindex
    near_flags = []
    for geom in villages_snapped.geometry:
        candidates = tree.query(geom.buffer(exposure_buffer_m))
        is_near = False
        for c in candidates:
            if geom.distance(exposed_roads.geometry.iloc[c]) <= exposure_buffer_m:
                is_near = True
                break
        near_flags.append(is_near)
    vill_exp = villages_snapped.copy()
    vill_exp["near_exposed"] = near_flags
    exposed_communities = vill_exp[vill_exp["near_exposed"]].copy()

    logger.info(f"[M4/SI] Exposed roads: {len(exposed_roads)}, "
                f"exposed communities: {len(exposed_communities)}")
    return exposed_roads, exposed_communities


# ── Full pipeline ─────────────────────────────────────────────────────────────

def run_spatial_intersect(
    cells_gdf: Optional[gpd.GeoDataFrame] = None,
    G: Optional[nx.MultiDiGraph] = None,
    roads_gdf: Optional[gpd.GeoDataFrame] = None,
    raster_path: Optional[str] = None,
    p_2d: Optional[np.ndarray] = None,
    conf_2d: Optional[np.ndarray] = None,
    raster_transform: Optional[object] = None,
    run_dir: Optional[Path] = None,
) -> dict[str, gpd.GeoDataFrame]:
    """
    Full spatial intersection pipeline.

    Args:
        cells_gdf:        Risk cells with p, confidence columns (optional if raster provided)
        G:                Road graph (loaded from graph.gpickle if None)
        roads_gdf:        Road segments GDF (loaded from roads.gpkg if None)
        raster_path:      Path to 4-band 100m GeoTIFF risk surface
        p_2d, conf_2d:    In-memory 2D raster arrays
        raster_transform: Rasterio affine transform
        run_dir:          Optional directory for run-specific output copies

    Returns:
        Dict with keys: segments_risk, villages, hospitals,
                        exposed_roads, exposed_communities
    """
    out_dir = Path(DATA_PROCESSED)
    out_dir.mkdir(parents=True, exist_ok=True)

    # Load roads and graph if not provided
    if roads_gdf is None:
        from modules.M4_road_exposure.road_network_loader import load_roads_gpkg
        roads_gdf = load_roads_gpkg()
    if G is None:
        from modules.M4_road_exposure.road_network_loader import load_graph
        G = load_graph()

    # Assign risk to segments (uses raster if available, otherwise cells_gdf)
    segments_risk = assign_risk_to_segments(
        segments_gdf=roads_gdf,
        cells_gdf=cells_gdf,
        raster_path=raster_path,
        p_2d=p_2d,
        conf_2d=conf_2d,
        raster_transform=raster_transform,
    )

    # Synchronize graph G edge attributes so that downstream M5 simulations see exact values
    if G is not None:
        osm_to_risk = dict(zip(segments_risk["osm_id"], segments_risk["risk_max"]))
        osm_to_conf = dict(zip(segments_risk["osm_id"], segments_risk["conf_min"]))
        for u, v, k, data in G.edges(data=True, keys=True):
            osm = data.get("osm_id")
            if osm in osm_to_risk:
                data["risk_max"] = float(osm_to_risk[osm])
                data["conf_min"] = float(osm_to_conf[osm])

    seg_wgs84 = segments_risk.to_crs(CRS_GEOGRAPHIC) if str(segments_risk.crs) != CRS_GEOGRAPHIC else segments_risk
    seg_wgs84.to_file(str(out_dir / "segments_risk.geojson"), driver="GeoJSON")
    if run_dir is not None:
        seg_wgs84.to_file(str(run_dir / "segments_risk.geojson"), driver="GeoJSON")

    # Load and snap communities
    villages_raw, hospitals_raw = load_places(G=G)
    villages   = snap_places_to_graph(villages_raw,   G, place_type="village")
    hospitals  = snap_places_to_graph(hospitals_raw,  G, place_type="hospital")

    if not villages.empty:
        villages.to_file(str(out_dir / "villages_snapped.gpkg"), driver="GPKG")
        if run_dir is not None:
            villages.to_file(str(run_dir / "villages_snapped.gpkg"), driver="GPKG")
    if not hospitals.empty:
        hospitals.to_file(str(out_dir / "hospitals_snapped.gpkg"), driver="GPKG")
        if run_dir is not None:
            hospitals.to_file(str(run_dir / "hospitals_snapped.gpkg"), driver="GPKG")

    # Exposed layers
    exposed_roads, exposed_communities = build_exposed_layers(segments_risk, villages)
    if not exposed_roads.empty:
        exp_r_wgs84 = exposed_roads.to_crs(CRS_GEOGRAPHIC) if str(exposed_roads.crs) != CRS_GEOGRAPHIC else exposed_roads
        exp_r_wgs84.to_file(str(out_dir / "exposed_roads.geojson"), driver="GeoJSON")
        if run_dir is not None:
            exp_r_wgs84.to_file(str(run_dir / "exposed_roads.geojson"), driver="GeoJSON")
    if not exposed_communities.empty:
        exp_c_wgs84 = exposed_communities.to_crs(CRS_GEOGRAPHIC) if str(exposed_communities.crs) != CRS_GEOGRAPHIC else exposed_communities
        exp_c_wgs84.to_file(str(out_dir / "exposed_communities.geojson"), driver="GeoJSON")
        if run_dir is not None:
            exp_c_wgs84.to_file(str(run_dir / "exposed_communities.geojson"), driver="GeoJSON")

    return {
        "segments_risk":      segments_risk,
        "villages":           villages,
        "hospitals":          hospitals,
        "exposed_roads":      exposed_roads,
        "exposed_communities": exposed_communities,
    }
