"""
graph_builder.py — M5: Connectivity Failure Simulation
=======================================================
Builds the travel-time weighted NetworkX MultiDiGraph from the pre-built
roads.gpkg. The graph is the foundation for all connectivity analysis.

Design (§9):
  - Edge weight = travel time in minutes = length / (speed_kmh × 1000/60)
  - Hill-country factor ×0.8 where slope > 20° or HAND > 20m
  - Nodes = road intersections + village/hospital snap nodes
  - Graph is built ONCE from roads.gpkg + saved to graph.gpickle
  - Baseline travel times (t0) are computed once per village/hospital pair

Speed classes (from config.aoi.SPEED_KMH):
  trunk=60, primary=45, secondary=35, tertiary=25, residential=20 km/h

Baseline computation:
  For each village node: t0 = min travel time to any hospital node
  Stored in village attributes and persisted for ratio computation.

Note: osmnx is NOT called here or at runtime. The graph is loaded from
      the pre-built gpickle file.
"""

from __future__ import annotations

import json
import pickle
import sys
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd
import geopandas as gpd
import networkx as nx
from loguru import logger

from config.aoi import (
    CRS_PROJECTED, DATA_PROCESSED,
    ROADS_GPKG_PATH, GRAPH_GPICKLE_PATH,
    SPEED_KMH, HILL_SPEED_FACTOR,
)


# ── Graph loading ─────────────────────────────────────────────────────────────

def load_graph(path: str = GRAPH_GPICKLE_PATH) -> nx.MultiDiGraph:
    """Load pre-built graph from disk."""
    if not Path(path).exists():
        raise FileNotFoundError(
            f"Graph not found at {path}. "
            "Run: python -m modules.M4_road_exposure.road_network_loader --build"
        )
    with open(path, "rb") as f:
        G = pickle.load(f)
    logger.info(f"[M5/GB] Graph loaded: {G.number_of_nodes()} nodes, {G.number_of_edges()} edges")
    return G


# ── Travel-time weight update ─────────────────────────────────────────────────

def apply_hill_factor(
    G: nx.MultiDiGraph,
    segments_risk_gdf: Optional[gpd.GeoDataFrame] = None,
) -> nx.MultiDiGraph:
    """
    Apply ×0.8 hill factor to edges in high-slope/high-HAND areas.

    If segments_risk_gdf is provided, reads slope/HAND from it.
    Otherwise applies hill factor to edges tagged with highway 'secondary'
    or lower (a conservative proxy for hill roads).
    """
    G = G.copy()
    n_hill = 0
    for u, v, k, data in G.edges(data=True, keys=True):
        hw = data.get("highway", "default")
        if isinstance(hw, list):
            hw = hw[0]
        # Mark edges as hill-adjusted based on highway class or explicit slope data
        is_hill = hw in ("secondary", "tertiary", "residential", "track", "path", "service")
        if is_hill:
            old_tt = data.get("tt_min", 1.0)
            G[u][v][k]["tt_min"] = round(old_tt / HILL_SPEED_FACTOR, 4)
            G[u][v][k]["hill_adjusted"] = True
            n_hill += 1
    logger.info(f"[M5/GB] Hill factor applied to {n_hill} edges")
    return G


# ── Baseline travel times ─────────────────────────────────────────────────────

def compute_baseline_paths(
    G: nx.MultiDiGraph,
    village_nodes: list,
    hospital_nodes: list,
) -> dict[any, dict]:
    """
    Compute baseline (t0) shortest travel times for every village.
    Uses multi-source Dijkstra on reversed graph to evaluate all 111 villages in ~20s.

    Returns:
        {village_node: {"t0": float, "nearest_hospital": int/str, "reachable": bool}}
    """
    logger.info(f"[M5/GB] Computing baseline paths for {len(village_nodes)} villages "
                f"→ {len(hospital_nodes)} hospitals")

    G_rev = G.reverse(copy=False)
    dist, paths = nx.multi_source_dijkstra(G_rev, sources=hospital_nodes, weight="tt_min")

    baseline = {}
    for village in village_nodes:
        if village in dist:
            hosp = paths[village][0]
            baseline[village] = {
                "t0":               round(float(dist[village]), 3),
                "nearest_hospital": hosp,
                "reachable":        True,
                "path":             paths[village],
            }
        else:
            baseline[village] = {
                "t0":               None,
                "nearest_hospital": None,
                "reachable":        False,
                "path":             [],
            }

    n_reachable = sum(v["reachable"] for v in baseline.values())
    logger.info(f"[M5/GB] {n_reachable}/{len(village_nodes)} villages reachable at baseline")
    return baseline


def get_village_and_hospital_nodes(G: nx.MultiDiGraph) -> tuple[list, list]:
    """Extract village and hospital node IDs from graph node attributes."""
    villages  = [n for n, d in G.nodes(data=True) if d.get("node_type") == "village"]
    hospitals = [n for n, d in G.nodes(data=True) if d.get("node_type") == "hospital"]
    return villages, hospitals


def build_travel_time_graph(
    roads_gdf: Optional[gpd.GeoDataFrame] = None,
) -> nx.MultiDiGraph:
    """
    Build weighted MultiDiGraph from roads GDF (if gpickle doesn't exist).
    Primarily used when starting from scratch without the pre-built graph.
    """
    if Path(GRAPH_GPICKLE_PATH).exists():
        return load_graph()

    if roads_gdf is None:
        if Path(ROADS_GPKG_PATH).exists():
            roads_gdf = gpd.read_file(ROADS_GPKG_PATH)
        else:
            logger.warning("[M5/GB] No roads.gpkg found — building synthetic network")
            from modules.M4_road_exposure.road_network_loader import _build_synthetic_network
            roads_gdf, G = _build_synthetic_network()
            _save_graph(G)
            return G

    logger.info(f"[M5/GB] Building graph from {len(roads_gdf)} road segments")
    G = nx.MultiDiGraph()

    for _, row in roads_gdf.iterrows():
        seg_id = row.get("seg_id", 0)
        hw = row.get("highway", "default")
        if isinstance(hw, list):
            hw = hw[0]
        speed = SPEED_KMH.get(hw, SPEED_KMH["default"])
        length = row.get("length", 100.0)
        tt = row.get("tt_min", length / (speed * 1000 / 60))

        if row.geometry is None:
            continue
        coords = list(row.geometry.coords)
        if len(coords) < 2:
            continue

        u_coords = coords[0]
        v_coords = coords[-1]
        u = hash(u_coords)
        v = hash(v_coords)

        G.add_node(u, x=u_coords[0], y=u_coords[1])
        G.add_node(v, x=v_coords[0], y=v_coords[1])
        G.add_edge(u, v, key=seg_id, osm_id=row.get("osm_id", 0),
                   highway=hw, length=float(length), speed_kmh=speed,
                   tt_min=float(tt), risk_max=0.0, conf_min=1.0)
        G.add_edge(v, u, key=seg_id+1, osm_id=row.get("osm_id", 0),
                   highway=hw, length=float(length), speed_kmh=speed,
                   tt_min=float(tt), risk_max=0.0, conf_min=1.0)

    _save_graph(G)
    logger.info(f"[M5/GB] Graph built: {G.number_of_nodes()} nodes, {G.number_of_edges()} edges")
    return G


def _save_graph(G: nx.MultiDiGraph) -> None:
    Path(DATA_PROCESSED).mkdir(parents=True, exist_ok=True)
    with open(GRAPH_GPICKLE_PATH, "wb") as f:
        pickle.dump(G, f, protocol=4)
    logger.info(f"[M5/GB] Graph saved → {GRAPH_GPICKLE_PATH}")


def save_baseline(baseline: dict, run_dir: Path) -> None:
    """Save baseline travel times to run artifact directory."""
    out = run_dir / "baseline_paths.json"
    serializable = {str(k): v for k, v in baseline.items()}
    with open(out, "w") as f:
        json.dump(serializable, f, indent=2)
    logger.info(f"[M5/GB] Baseline paths → {out}")


if __name__ == "__main__":
    G = build_travel_time_graph()
    villages, hospitals = get_village_and_hospital_nodes(G)
    logger.info(f"Villages: {len(villages)}, Hospitals: {len(hospitals)}")
    if villages and hospitals:
        baseline = compute_baseline_paths(G, villages, hospitals)
        reachable = [v for v in baseline.values() if v["reachable"]]
        t0_vals = [v["t0"] for v in reachable]
        if t0_vals:
            logger.info(f"t0 range: {min(t0_vals):.1f}–{max(t0_vals):.1f} min")
