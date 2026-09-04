"""
graph_builder.py — M5: Connectivity Failure Simulation
=======================================================
Builds a NetworkX graph representing the road connectivity network
for the target district.

Nodes:
  - Villages (with population attribute)
  - Hospitals / health centres
  - District headquarters
  - Key road junctions

Edges:
  - Road segments connecting nodes
  - Weight = travel time (base) adjusted by road condition + risk exposure

This graph is the input to the failure simulator and shortest-path recomputer.
"""

import json
import networkx as nx
import geopandas as gpd
import pandas as pd
from loguru import logger


def load_road_network(road_shapefile: str) -> gpd.GeoDataFrame:
    """
    Load road network from shapefile (OSM or NRSC).

    Returns:
        GeoDataFrame of road segments with geometry and attributes
    """
    logger.info(f"[M5] Loading road network from {road_shapefile}")
    # TODO: Load and clip to BBOX
    raise NotImplementedError("Road network loader not yet implemented")


def load_node_locations(village_path: str, hospital_path: str) -> gpd.GeoDataFrame:
    """
    Load village and hospital locations.

    Returns:
        GeoDataFrame of all nodes (villages + hospitals + HQ)
    """
    logger.info("[M5] Loading village and hospital node locations")
    # TODO: Load census village points + facility locations
    raise NotImplementedError("Node locations loader not yet implemented")


def build_graph(nodes_gdf: gpd.GeoDataFrame,
                roads_gdf: gpd.GeoDataFrame,
                risk_gdf: gpd.GeoDataFrame) -> nx.Graph:
    """
    Build a weighted graph from nodes and roads.

    Edge weight = travel_time_minutes * (1 + risk_score)
    This increases effective travel time through high-risk segments.

    Args:
        nodes_gdf:  Village + hospital nodes
        roads_gdf:  Road segments
        risk_gdf:   Risk scores per cell from M2

    Returns:
        NetworkX Graph
    """
    logger.info("[M5] Building connectivity graph")
    G = nx.Graph()

    # TODO: Step 1 — add nodes with attributes (node_type, population, lat, lon)
    # TODO: Step 2 — add edges from road network, snap endpoints to nearest nodes
    # TODO: Step 3 — spatially join risk scores to edges
    # TODO: Step 4 — compute edge weights

    raise NotImplementedError("Graph construction not yet implemented")


def save_graph(G: nx.Graph, path: str = "data/processed/graph.gpickle") -> None:
    """Save graph to disk."""
    nx.write_gpickle(G, path)
    logger.info(f"[M5] Graph saved to {path}")

    # Also export nodes/edges as JSON for API serving
    nodes_data = [{"id": n, **d} for n, d in G.nodes(data=True)]
    edges_data = [{"from": u, "to": v, **d} for u, v, d in G.edges(data=True)]

    with open("data/processed/graph_nodes.json", "w") as f:
        json.dump(nodes_data, f, indent=2, default=str)
    with open("data/processed/graph_edges.json", "w") as f:
        json.dump(edges_data, f, indent=2, default=str)

    logger.info("[M5] Graph nodes/edges exported as JSON")
