"""
failure_simulator.py — M5: Connectivity Failure Simulation
============================================================
Deterministic failure simulation: block high-risk road edges, recompute
travel times, measure isolation and connectivity degradation.

Design (§9):
  DETERMINISTIC ONLY for MVP (Monte Carlo is P2).
  
  Failure scenario:
    1. Find all edges where risk_max ≥ τ_alert → "failed edges"
    2. Remove them from a copy of the graph
    3. Recompute t1 = shortest path to nearest hospital per village
    4. Compute ratio r = t1/t0
    5. Apply isolation thresholds:
       - isolated:        unreachable (r = ∞) OR r ≥ 1.5
       - poorly_connected: 1.25 ≤ r < 1.5
       - accessible:       r < 1.25

  Critical edges:
    An edge is "critical" if ≥ N_MIN villages become isolated/poorly-connected
    when that single edge is removed (single-edge sensitivity).

Scenario registry:
  - "baseline"                       — current conditions
  - "rainfall_replay_june2022"       — replay June 2022 rainfall scenario
  - "nh6_escarpment_block"           — manually block the NH-6 escarpment segment
  - "reset"                          — restore baseline

Output (per run):
  run_{ts}/impact.geojson      — village impact layer with flags
  run_{ts}/impact_summary.json — aggregate stats
  run_{ts}/critical_edges.json — ranked critical edges
"""

from __future__ import annotations

import json
import pickle
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd
import geopandas as gpd
import networkx as nx
from loguru import logger

from config.aoi import (
    ISOLATION_RATIO, POOR_CONNECT_RATIO, MIN_VILLAGES_CRITICAL,
    TAU_ALERT, GRAPH_GPICKLE_PATH, DATA_PROCESSED, DATA_RUNS,
)


# ── Isolation classification ──────────────────────────────────────────────────

def classify_isolation(t0: Optional[float], t1: Optional[float]) -> str:
    """
    Classify village connectivity given baseline (t0) and post-failure (t1).

    Returns one of: 'isolated', 'poorly_connected', 'accessible', 'was_unreachable'
    """
    if t0 is None:
        return "was_unreachable"    # not reachable even at baseline
    if t1 is None:
        return "isolated"           # was reachable, now not
    r = t1 / max(t0, 0.01)
    if r >= ISOLATION_RATIO:
        return "isolated"
    if r >= POOR_CONNECT_RATIO:
        return "poorly_connected"
    return "accessible"


# ── Main simulation ───────────────────────────────────────────────────────────

def simulate_deterministic(
    G: nx.MultiDiGraph,
    segments_risk_gdf: gpd.GeoDataFrame,
    baseline: dict[int, dict],
    hospital_nodes: list[int],
    tau_alert: float = TAU_ALERT,
    scenario_overrides: Optional[list[int]] = None,
) -> dict:
    """
    Block edges with risk_max ≥ τ_alert; recompute connectivity.

    Args:
        G:                  Full road graph (not modified; copy is used)
        segments_risk_gdf:  Road segments with risk_max, seg_id
        baseline:           {village_node: {"t0", "nearest_hospital", "reachable"}}
        hospital_nodes:     Hospital node IDs
        tau_alert:          Risk threshold for edge blocking
        scenario_overrides: If provided, block these specific seg_ids
                            (used for manual NH-6 escarpment scenario)

    Returns:
        Dict with failed_edges, village_impacts, summary, critical_edges
    """
    logger.info(f"[M5/FS] Deterministic simulation (τ_alert={tau_alert})")

    G_failed = G.copy()
    failed_edge_keys = []

    # Identify edges to block
    if scenario_overrides is not None:
        # Manual scenario: block specific segments
        blocked_osm_ids = set(scenario_overrides)
        for u, v, k, data in G.edges(data=True, keys=True):
            if data.get("osm_id") in blocked_osm_ids or data.get("seg_id") in blocked_osm_ids:
                failed_edge_keys.append((u, v, k))
    else:
        # Risk-based: block edges exceeding threshold
        high_risk_osm = set()
        if segments_risk_gdf is not None and not segments_risk_gdf.empty:
            high_risk = segments_risk_gdf[segments_risk_gdf["risk_max"] >= tau_alert]
            high_risk_osm = set(high_risk["osm_id"].tolist())

        for u, v, k, data in G.edges(data=True, keys=True):
            if data.get("risk_max", 0) >= tau_alert:
                failed_edge_keys.append((u, v, k))
            elif data.get("osm_id") in high_risk_osm:
                failed_edge_keys.append((u, v, k))

    # Remove failed edges
    for u, v, k in failed_edge_keys:
        if G_failed.has_edge(u, v, k):
            G_failed.remove_edge(u, v, k)

    logger.info(f"[M5/FS] Blocked {len(failed_edge_keys)} edges")

    # Recompute village travel times using multi-source Dijkstra on reversed failed graph
    village_impacts = []
    village_nodes = list(baseline.keys())

    G_failed_rev = G_failed.reverse(copy=False)
    dist_failed, _ = nx.multi_source_dijkstra(G_failed_rev, sources=hospital_nodes, weight="tt_min")

    for village in village_nodes:
        b = baseline[village]
        t0 = b["t0"]
        t1 = round(float(dist_failed[village]), 2) if village in dist_failed else None
        reachable_after = village in dist_failed

        ratio = (t1 / max(t0, 0.01)) if (t0 and t1) else (None if not t0 else float("inf"))
        status = classify_isolation(t0, t1 if reachable_after else None)

        village_impacts.append({
            "village_node":   village,
            "t0":             round(t0, 2) if t0 else None,
            "t1":             t1,
            "ratio":          round(ratio, 3) if isinstance(ratio, float) and np.isfinite(ratio) else None,
            "isolation_flag": status,
            "delta_min":      round(t1 - t0, 2) if (t0 and t1) else None,
        })

    n_isolated       = sum(1 for v in village_impacts if v["isolation_flag"] == "isolated")
    n_poor           = sum(1 for v in village_impacts if v["isolation_flag"] == "poorly_connected")
    n_accessible     = sum(1 for v in village_impacts if v["isolation_flag"] == "accessible")

    summary = {
        "n_failed_edges":       len(failed_edge_keys),
        "n_villages_isolated":  n_isolated,
        "n_poorly_connected":   n_poor,
        "n_accessible":         n_accessible,
        "n_was_unreachable":    sum(1 for v in village_impacts if v["isolation_flag"] == "was_unreachable"),
        "tau_alert":            tau_alert,
        "isolation_threshold":  ISOLATION_RATIO,
        "poor_connect_threshold": POOR_CONNECT_RATIO,
        "isolation_definition": (
            "isolated = unreachable OR t1/t0 ≥ 1.5; "
            "poorly_connected = 1.25 ≤ t1/t0 < 1.5"
        ),
    }

    logger.info(f"[M5/FS] Impact: {n_isolated} isolated, {n_poor} poorly connected, "
                f"{n_accessible} accessible")

    return {
        "failed_edge_keys": failed_edge_keys,
        "village_impacts":  village_impacts,
        "summary":          summary,
    }


# ── Critical edge identification ──────────────────────────────────────────────

def identify_critical_edges(
    G: nx.MultiDiGraph,
    baseline: dict[int, dict],
    hospital_nodes: list[int],
    n_min: int = MIN_VILLAGES_CRITICAL,
    max_edges_to_check: int = 100,
) -> list[dict]:
    """
    Single-edge sensitivity analysis: which edges isolate ≥ n_min villages?

    For MVP: checks candidate alert-tier edges (risk_max ≥ τ_alert).
    Uses in-place temporary edge removal and baseline path filtering for high performance.

    Returns:
        Sorted list of critical edge dicts (most critical first).
    """
    logger.info(f"[M5/FS] Identifying critical edges (n_min={n_min})")
    village_nodes = list(baseline.keys())

    # Map each village to the set of edges on its baseline hospital path
    village_edge_sets = {}
    for v, b in baseline.items():
        p = b.get("path", [])
        edges = set()
        for i in range(len(p) - 1):
            edges.add((p[i+1], p[i]))  # in G (p is hospital-to-village in G_rev)
            edges.add((p[i], p[i+1]))
        village_edge_sets[v] = edges

    # Get candidate alert-tier edges to check
    candidates = []
    seen_osm = set()
    for u, v, k, data in G.edges(data=True, keys=True):
        if data.get("risk_max", 0) >= TAU_ALERT:
            osm_id = data.get("osm_id", (u, v))
            if osm_id not in seen_osm:
                candidates.append((u, v, k, data))
                seen_osm.add(osm_id)

    # Sort candidates by risk_max descending
    candidates.sort(key=lambda x: x[3].get("risk_max", 0), reverse=True)
    edges_to_check = candidates[:max_edges_to_check]
    logger.info(f"[M5/FS] Checking {len(edges_to_check)} candidate alert-tier edges")

    critical = []
    for u, v, k, data in edges_to_check:
        # Check which villages actually use this edge
        relevant_villages = [
            vil for vil in village_nodes
            if (u, v) in village_edge_sets.get(vil, set())
        ]
        # If no villages use this edge, removing it cannot impact any village
        if len(relevant_villages) < n_min:
            continue

        # In-place removal
        G.remove_edge(u, v, k)
        rev_removed = False
        rev_data = None
        rev_k = None
        if G.has_edge(v, u):
            rev_keys = list(G[v][u].keys())
            if rev_keys:
                rev_k = rev_keys[0]
                rev_data = G.get_edge_data(v, u, rev_k)
                G.remove_edge(v, u, rev_k)
                rev_removed = True

        n_impacted = 0
        for village in relevant_villages:
            b = baseline[village]
            if not b.get("reachable"):
                continue
            t0 = b["t0"]
            h = b["nearest_hospital"]
            if h is None:
                continue
            try:
                t1 = nx.shortest_path_length(G, village, h, weight="tt_min")
                if t0 is None or t1 / max(t0, 0.01) >= POOR_CONNECT_RATIO:
                    n_impacted += 1
            except (nx.NetworkXNoPath, nx.NodeNotFound):
                n_impacted += 1

        # Restore edge in G
        G.add_edge(u, v, key=k, **data)
        if rev_removed and rev_data is not None and rev_k is not None:
            G.add_edge(v, u, key=rev_k, **rev_data)

        if n_impacted >= n_min:
            critical.append({
                "edge_u":     u,
                "edge_v":     v,
                "edge_key":   k,
                "osm_id":     data.get("osm_id"),
                "highway":    data.get("highway"),
                "risk_max":   round(data.get("risk_max", 0), 4),
                "length":     round(data.get("length", 0), 1),
                "n_villages_impacted": n_impacted,
            })

    critical.sort(key=lambda x: x["n_villages_impacted"], reverse=True)
    logger.info(f"[M5/FS] {len(critical)} critical edges found")
    return critical


# ── Save outputs ──────────────────────────────────────────────────────────────

def save_impact_outputs(
    village_impacts: list[dict],
    summary: dict,
    critical_edges: list[dict],
    villages_gdf: gpd.GeoDataFrame,
    run_dir: Path,
) -> gpd.GeoDataFrame:
    """
    Save impact outputs to run directory.
    Merges village_impacts with geometry from villages_gdf.
    """
    impacts_df = pd.DataFrame(village_impacts)

    if not villages_gdf.empty and "snap_node" in villages_gdf.columns:
        merged = villages_gdf.merge(
            impacts_df,
            left_on="snap_node",
            right_on="village_node",
            how="left",
        )
        impact_gdf = gpd.GeoDataFrame(merged, geometry="geometry", crs=CRS_PROJECTED if hasattr(villages_gdf, "crs") else None)
        impact_gdf.to_file(str(run_dir / "impact.geojson"), driver="GeoJSON")
    else:
        impact_gdf = gpd.GeoDataFrame(impacts_df)

    with open(run_dir / "impact_summary.json", "w") as f:
        json.dump(summary, f, indent=2)

    with open(run_dir / "critical_edges.json", "w") as f:
        json.dump(critical_edges, f, indent=2)

    logger.info(f"[M5/FS] Impact outputs saved → {run_dir}")
    return impact_gdf


try:
    from config.aoi import CRS_PROJECTED
except ImportError:
    CRS_PROJECTED = "EPSG:32646"


if __name__ == "__main__":
    from modules.M5_connectivity_simulation.graph_builder import (
        load_graph, get_village_and_hospital_nodes, compute_baseline_paths,
    )
    G = load_graph()
    villages, hospitals = get_village_and_hospital_nodes(G)
    baseline = compute_baseline_paths(G, villages, hospitals)

    result = simulate_deterministic(
        G=G,
        segments_risk_gdf=None,
        baseline=baseline,
        hospital_nodes=hospitals,
        tau_alert=TAU_ALERT,
    )
    print(json.dumps(result["summary"], indent=2))
