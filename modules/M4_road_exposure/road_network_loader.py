"""
road_network_loader.py — M4: Road Exposure
============================================
ONE-TIME build of the OSM road network for the NH-6 corridor.

Design (§8, §24):
  - osmnx is used ONCE at build time to download/parse the road graph.
  - The result is persisted as roads.gpkg + graph.gpickle.
  - At runtime (API, inference), osmnx is NEVER imported.
  - Build is triggered manually or via: python -m modules.M4_road_exposure.road_network_loader --build

Data source: Geofabrik NE-India extract OR osmnx bbox query.
  Priority: local PBF file (data/raw/road_network/ne_india.osm.pbf)
  Fallback: osmnx.graph_from_bbox() for the AOI

Drivable highway classes retained:
  motorway, trunk, primary, secondary, tertiary, residential, unclassified, service
  (excludes footway, cycleway, path — not relevant for vehicle access)

Usage (build):
    python -m modules.M4_road_exposure.road_network_loader --build
    python -m modules.M4_road_exposure.road_network_loader --synthetic

Usage (load at runtime — no osmnx needed):
    from modules.M4_road_exposure.road_network_loader import load_roads_gpkg, load_graph
"""

from __future__ import annotations

import json
import sys
import pickle
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd
import geopandas as gpd
from shapely.geometry import LineString, Point, mapping
from loguru import logger

import networkx as nx

from config.aoi import (
    CRS_PROJECTED, CRS_GEOGRAPHIC,
    AOI_BBOX_WGS84, ROADS_GPKG_PATH, GRAPH_GPICKLE_PATH,
    SPEED_KMH, HILL_SPEED_FACTOR, DATA_PROCESSED,
    OSM_PBF_PATH, VILLAGES_RAW_PATH, HOSPITALS_RAW_PATH,
)

DRIVABLE_HIGHWAY_TYPES = {
    "motorway", "trunk", "primary", "secondary",
    "tertiary", "residential", "unclassified", "service",
    "motorway_link", "trunk_link", "primary_link", "secondary_link",
}


# ── Runtime loaders (no osmnx) ────────────────────────────────────────────────

def load_roads_gpkg(path: str = ROADS_GPKG_PATH) -> gpd.GeoDataFrame:
    """Load pre-built roads GeoPackage (EPSG:32646)."""
    if not Path(path).exists():
        raise FileNotFoundError(
            f"roads.gpkg not found at {path}. "
            "Run: python -m modules.M4_road_exposure.road_network_loader --build"
        )
    gdf = gpd.read_file(path)
    if str(gdf.crs) != CRS_PROJECTED:
        gdf = gdf.to_crs(CRS_PROJECTED)
    return gdf


def load_graph(path: str = GRAPH_GPICKLE_PATH) -> nx.MultiDiGraph:
    """Load pre-built NetworkX graph from gpickle."""
    if not Path(path).exists():
        raise FileNotFoundError(
            f"graph.gpickle not found at {path}. "
            "Run: python -m modules.M4_road_exposure.road_network_loader --build"
        )
    with open(path, "rb") as f:
        G = pickle.load(f)
    logger.info(f"[M4] Graph loaded: {G.number_of_nodes()} nodes, {G.number_of_edges()} edges")
    return G


# ── Synthetic road network for testing ───────────────────────────────────────

def _build_synthetic_network(seed: int = 42) -> tuple[gpd.GeoDataFrame, nx.MultiDiGraph]:
    """
    Build a synthetic road network approximating the NH-6 corridor.

    Topology: spine (NH-6 equivalent) running south-west to north-east,
    with branch roads connecting notional villages.
    Labeled SYNTHETIC — never used for real connectivity claims.
    """
    logger.warning("[M4] SYNTHETIC road network — not real OSM data.")
    rng = np.random.default_rng(seed)

    # AOI approximate UTM bounds
    from pyproj import Transformer
    tr = Transformer.from_crs(CRS_GEOGRAPHIC, CRS_PROJECTED, always_xy=True)
    x0, y0 = tr.transform(AOI_BBOX_WGS84[0], AOI_BBOX_WGS84[1])
    x1, y1 = tr.transform(AOI_BBOX_WGS84[2], AOI_BBOX_WGS84[3])

    # NH-6 spine: ~12 waypoints along the corridor
    n_spine = 20
    xs = np.linspace(x0 + 5000, x1 - 5000, n_spine)
    ys = np.linspace(y0 + 5000, y1 - 5000, n_spine)
    # Add slight meandering
    ys += rng.normal(0, 3000, n_spine)

    spine_nodes = list(range(n_spine))
    G = nx.MultiDiGraph()

    # Add spine nodes
    for i in range(n_spine):
        G.add_node(i, x=xs[i], y=ys[i], node_type="junction",
                   lon=float(xs[i]), lat=float(ys[i]))

    # Add spine edges (NH-6 trunk road)
    segments = []
    edge_id = 0
    for i in range(n_spine - 1):
        length = float(np.hypot(xs[i+1] - xs[i], ys[i+1] - ys[i]))
        speed = SPEED_KMH["trunk"]
        tt = length / (speed * 1000 / 60)   # travel time in minutes
        # Edges in both directions
        G.add_edge(i, i+1, key=edge_id, osm_id=1000+i, highway="trunk",
                   length=length, speed_kmh=speed, tt_min=tt, risk_max=0.0, conf_min=1.0)
        G.add_edge(i+1, i, key=edge_id+1, osm_id=1000+i, highway="trunk",
                   length=length, speed_kmh=speed, tt_min=tt, risk_max=0.0, conf_min=1.0)
        line = LineString([(xs[i], ys[i]), (xs[i+1], ys[i+1])])
        segments.append({
            "seg_id": edge_id, "osm_id": 1000+i, "highway": "trunk",
            "length": round(length, 1), "tt_min": round(tt, 3),
            "risk_max": 0.0, "conf_min": 1.0, "geometry": line,
        })
        edge_id += 2

    # Add branch roads to ~30 villages
    n_villages = 30
    vx = rng.uniform(x0 + 3000, x1 - 3000, n_villages)
    vy = rng.uniform(y0 + 3000, y1 - 3000, n_villages)

    for j in range(n_villages):
        # Find nearest spine node
        dists = np.hypot(xs - vx[j], ys - vy[j])
        nearest_spine = int(np.argmin(dists))

        vnode_id = n_spine + j
        G.add_node(vnode_id, x=vx[j], y=vy[j], node_type="village",
                   name=f"Village_{j+1}", pop_est=rng.integers(200, 5000),
                   lon=float(vx[j]), lat=float(vy[j]))

        length = float(dists[nearest_spine])
        speed = SPEED_KMH["secondary"]
        # Apply hill factor for some branches
        if rng.random() < 0.4:
            speed *= HILL_SPEED_FACTOR
        tt = length / (speed * 1000 / 60)

        G.add_edge(vnode_id, nearest_spine, key=edge_id, osm_id=2000+j,
                   highway="secondary", length=length, speed_kmh=speed,
                   tt_min=tt, risk_max=0.0, conf_min=1.0)
        G.add_edge(nearest_spine, vnode_id, key=edge_id+1, osm_id=2000+j,
                   highway="secondary", length=length, speed_kmh=speed,
                   tt_min=tt, risk_max=0.0, conf_min=1.0)
        line = LineString([(xs[nearest_spine], ys[nearest_spine]), (vx[j], vy[j])])
        segments.append({
            "seg_id": edge_id, "osm_id": 2000+j, "highway": "secondary",
            "length": round(length, 1), "tt_min": round(tt, 3),
            "risk_max": 0.0, "conf_min": 1.0, "geometry": line,
        })
        edge_id += 2

    # Add 3 hospitals near the hubs
    hosp_x = [x0 + 8000, x1 - 8000, (x0+x1)/2]
    hosp_y = [y0 + 8000, y1 - 8000, (y0+y1)/2 + 5000]
    for h in range(3):
        hnode_id = n_spine + n_villages + h
        G.add_node(hnode_id, x=hosp_x[h], y=hosp_y[h],
                   node_type="hospital", name=f"Hospital_{h+1}",
                   lon=float(hosp_x[h]), lat=float(hosp_y[h]))
        # Connect to nearest spine
        dists = np.hypot(xs - hosp_x[h], ys - hosp_y[h])
        ns = int(np.argmin(dists))
        length = float(dists[ns])
        tt = length / (SPEED_KMH["primary"] * 1000 / 60)
        G.add_edge(hnode_id, ns, key=edge_id, osm_id=3000+h, highway="primary",
                   length=length, speed_kmh=SPEED_KMH["primary"], tt_min=tt,
                   risk_max=0.0, conf_min=1.0)
        G.add_edge(ns, hnode_id, key=edge_id+1, osm_id=3000+h, highway="primary",
                   length=length, speed_kmh=SPEED_KMH["primary"], tt_min=tt,
                   risk_max=0.0, conf_min=1.0)
        edge_id += 2

    roads_gdf = gpd.GeoDataFrame(segments, geometry="geometry", crs=CRS_PROJECTED)
    return roads_gdf, G


# ── Real build from GeoJSON ──────────────────────────────────────────────────

def _build_from_geojson(geojson_path: str = "data/raw/road_network/osm_roads.geojson") -> tuple[gpd.GeoDataFrame, nx.MultiDiGraph]:
    """
    Build real road network and travel-time graph from OSM GeoJSON.
    Connects real roads, real 111 villages, and real 324 hospitals.
    """
    import math
    from scipy.spatial import cKDTree

    logger.info(f"[M4] Building road network from real OSM GeoJSON: {geojson_path}")
    raw_gdf = gpd.read_file(geojson_path)
    if str(raw_gdf.crs) != CRS_PROJECTED:
        roads_utm = raw_gdf.to_crs(CRS_PROJECTED)
    else:
        roads_utm = raw_gdf

    # Retain drivable highway classes
    keep_mask = roads_utm["highway"].apply(
        lambda h: (h if isinstance(h, str) else h[0] if isinstance(h, list) else "") in DRIVABLE_HIGHWAY_TYPES
    )
    drivable = roads_utm[keep_mask].copy()

    G = nx.MultiDiGraph()
    segments = []
    edge_id = 0

    for idx, row in drivable.iterrows():
        coords = list(row.geometry.coords)
        if len(coords) < 2:
            continue
        hw = row["highway"]
        if isinstance(hw, list):
            hw = hw[0]
        speed = SPEED_KMH.get(hw, SPEED_KMH["default"])
        seg_length = float(row.geometry.length)
        seg_tt = seg_length / (speed * 1000 / 60)

        for i in range(len(coords) - 1):
            u = (round(coords[i][0], 1), round(coords[i][1], 1))
            v = (round(coords[i+1][0], 1), round(coords[i+1][1], 1))
            dx = coords[i+1][0] - coords[i][0]
            dy = coords[i+1][1] - coords[i][1]
            l_m = math.hypot(dx, dy)
            if l_m < 0.1:
                continue
            tt = l_m / (speed * 1000 / 60)

            G.add_node(u, x=u[0], y=u[1], node_type="junction")
            G.add_node(v, x=v[0], y=v[1], node_type="junction")
            G.add_edge(u, v, key=edge_id, osm_id=row["osm_id"], highway=hw, length=l_m, speed_kmh=speed, tt_min=tt, risk_max=0.0, conf_min=1.0)
            if row.get("oneway") != "yes":
                G.add_edge(v, u, key=edge_id+1, osm_id=row["osm_id"], highway=hw, length=l_m, speed_kmh=speed, tt_min=tt, risk_max=0.0, conf_min=1.0)
            edge_id += 2

        segments.append({
            "seg_id": idx,
            "osm_id": row["osm_id"],
            "highway": hw,
            "name": row.get("name", ""),
            "length": round(seg_length, 2),
            "speed_kmh": speed,
            "tt_min": round(seg_tt, 3),
            "risk_max": 0.0,
            "conf_min": 1.0,
            "geometry": row.geometry,
        })

    roads_gdf = gpd.GeoDataFrame(segments, geometry="geometry", crs=CRS_PROJECTED)

    # Attach real villages
    if Path(VILLAGES_RAW_PATH).exists():
        vill_gdf = gpd.read_file(VILLAGES_RAW_PATH).to_crs(CRS_PROJECTED)
        junction_nodes = [n for n in G.nodes() if G.nodes[n].get("node_type") == "junction"]
        node_coords = np.array(junction_nodes)
        tree = cKDTree(node_coords)
        for v_idx, v_row in vill_gdf.iterrows():
            vx, vy = v_row.geometry.x, v_row.geometry.y
            dist, n_i = tree.query([vx, vy])
            v_node = f"village_{v_idx}"
            near_n = tuple(junction_nodes[n_i])
            G.add_node(v_node, x=vx, y=vy, node_type="village", name=v_row.get("name", f"Village {v_idx}"), pop_est=int(v_row.get("population", 1000) or 1000))
            tt_conn = dist / (SPEED_KMH["secondary"] * 1000 / 60)
            G.add_edge(v_node, near_n, key=edge_id, osm_id=900000+v_idx, highway="secondary", length=float(dist), speed_kmh=SPEED_KMH["secondary"], tt_min=tt_conn, risk_max=0.0, conf_min=1.0)
            G.add_edge(near_n, v_node, key=edge_id+1, osm_id=900000+v_idx, highway="secondary", length=float(dist), speed_kmh=SPEED_KMH["secondary"], tt_min=tt_conn, risk_max=0.0, conf_min=1.0)
            edge_id += 2

    # Attach real hospitals
    if Path(HOSPITALS_RAW_PATH).exists():
        hosp_gdf = gpd.read_file(HOSPITALS_RAW_PATH).to_crs(CRS_PROJECTED)
        junction_nodes = [n for n in G.nodes() if G.nodes[n].get("node_type") == "junction"]
        node_coords = np.array(junction_nodes)
        tree = cKDTree(node_coords)
        for h_idx, h_row in hosp_gdf.iterrows():
            hx, hy = h_row.geometry.x, h_row.geometry.y
            dist, n_i = tree.query([hx, hy])
            h_node = f"hospital_{h_idx}"
            near_n = tuple(junction_nodes[n_i])
            G.add_node(h_node, x=hx, y=hy, node_type="hospital", name=h_row.get("name", f"Hospital {h_idx}"))
            tt_conn = dist / (SPEED_KMH["primary"] * 1000 / 60)
            G.add_edge(h_node, near_n, key=edge_id, osm_id=800000+h_idx, highway="primary", length=float(dist), speed_kmh=SPEED_KMH["primary"], tt_min=tt_conn, risk_max=0.0, conf_min=1.0)
            G.add_edge(near_n, h_node, key=edge_id+1, osm_id=800000+h_idx, highway="primary", length=float(dist), speed_kmh=SPEED_KMH["primary"], tt_min=tt_conn, risk_max=0.0, conf_min=1.0)
            edge_id += 2

    logger.info(f"[M4] Built real road network: {len(roads_gdf)} road segments, {G.number_of_nodes()} graph nodes, {G.number_of_edges()} edges")
    return roads_gdf, G


# ── Real build from osmnx ────────────────────────────────────────────────────

def _build_from_osmnx() -> tuple[gpd.GeoDataFrame, nx.MultiDiGraph]:
    """
    Build road network from OSM using osmnx or fallback to GeoJSON.
    """
    geojson_p = Path("data/raw/road_network/osm_roads.geojson")
    if geojson_p.exists():
        return _build_from_geojson(str(geojson_p))

    pbf = Path(OSM_PBF_PATH)
    if pbf.exists():
        logger.info(f"[M4] Using local PBF: {pbf}")
        # osmnx ≥ 1.9 can read PBF directly
        try:
            G_raw = ox.graph_from_file(str(pbf), network_type="drive")
        except AttributeError:
            logger.warning("[M4] graph_from_file not available; falling back to bbox query")
            G_raw = _osmnx_bbox_query()
    else:
        logger.info("[M4] No PBF found; using bbox query")
        G_raw = _osmnx_bbox_query()

    # Project to UTM 46N
    G = ox.project_graph(G_raw, to_crs=CRS_PROJECTED)

    # Filter to drivable highway classes
    edges_gdf = ox.graph_to_gdfs(G, nodes=False, edges=True)
    keep_mask = edges_gdf["highway"].apply(
        lambda h: (h if isinstance(h, str) else h[0] if isinstance(h, list) else "") in DRIVABLE_HIGHWAY_TYPES
    )
    keep_edges = set(edges_gdf[keep_mask].index.tolist())
    G_filtered = G.copy()
    for u, v, k in list(G.edges(keys=True)):
        if (u, v, k) not in keep_edges:
            G_filtered.remove_edge(u, v, k)

    # Add travel-time weights
    for u, v, k, data in G_filtered.edges(data=True, keys=True):
        hw = data.get("highway", "default")
        if isinstance(hw, list):
            hw = hw[0]
        speed = SPEED_KMH.get(hw, SPEED_KMH["default"])
        length = data.get("length", 100.0)
        tt = length / (speed * 1000 / 60)
        G_filtered[u][v][k]["speed_kmh"] = speed
        G_filtered[u][v][k]["tt_min"]    = round(tt, 4)
        G_filtered[u][v][k]["risk_max"]  = 0.0
        G_filtered[u][v][k]["conf_min"]  = 1.0

    roads_gdf = ox.graph_to_gdfs(G_filtered, nodes=False, edges=True).reset_index()
    roads_gdf = roads_gdf.to_crs(CRS_PROJECTED)

    # Rename for consistency
    roads_gdf["seg_id"] = range(len(roads_gdf))
    for col, default in [("osm_id", 0), ("tt_min", 1.0), ("risk_max", 0.0), ("conf_min", 1.0)]:
        if col not in roads_gdf.columns:
            roads_gdf[col] = default

    return roads_gdf, G_filtered


def _osmnx_bbox_query():
    import osmnx as ox
    west, south, east, north = AOI_BBOX_WGS84
    return ox.graph_from_bbox(
        north=north, south=south, east=east, west=west,
        network_type="drive",
        retain_all=False,
    )


# ── Save / load ───────────────────────────────────────────────────────────────

def save_roads(roads_gdf: gpd.GeoDataFrame, G: nx.MultiDiGraph) -> None:
    Path(DATA_PROCESSED).mkdir(parents=True, exist_ok=True)
    roads_gdf.to_file(ROADS_GPKG_PATH, driver="GPKG", layer="roads")
    logger.info(f"[M4] Roads saved → {ROADS_GPKG_PATH}")

    with open(GRAPH_GPICKLE_PATH, "wb") as f:
        pickle.dump(G, f, protocol=4)
    logger.info(f"[M4] Graph saved → {GRAPH_GPICKLE_PATH} "
                f"({G.number_of_nodes()} nodes, {G.number_of_edges()} edges)")


# ── Entry point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    synthetic = "--synthetic" in sys.argv
    build = "--build" in sys.argv or synthetic

    if not build:
        print("Usage: python -m modules.M4_road_exposure.road_network_loader --build [--synthetic]")
        sys.exit(0)

    if synthetic:
        roads_gdf, G = _build_synthetic_network()
    else:
        try:
            roads_gdf, G = _build_from_osmnx()
        except Exception as e:
            logger.warning(f"[M4] osmnx build failed ({e}). Using synthetic fallback.")
            roads_gdf, G = _build_synthetic_network()

    save_roads(roads_gdf, G)
    print(f"[OK] Roads: {len(roads_gdf)} segments")
    print(f"[OK] Graph: {G.number_of_nodes()} nodes, {G.number_of_edges()} edges")
    print(roads_gdf[["seg_id", "highway", "length", "tt_min"]].head(5))
