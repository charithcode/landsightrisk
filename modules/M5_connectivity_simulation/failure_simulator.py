"""
failure_simulator.py — M5: Connectivity Failure Simulation
============================================================
Simulates road blockage by removing high-risk edges from the graph
and recomputing connectivity / shortest paths.

Two simulation modes:
  1. Deterministic — remove edges above a fixed risk threshold
  2. Monte Carlo   — probabilistic edge removal based on risk score,
                     run N scenarios to get expected isolation probability

Key questions answered:
  - Which villages lose ALL hospital access?
  - Which villages see travel time increase > X%?
  - What is expected isolation probability per village?
"""

import numpy as np
import networkx as nx
from loguru import logger
from typing import List, Dict


RISK_THRESHOLD_BLOCK = 0.75   # Edges above this are treated as failed
N_MONTE_CARLO = 500           # Number of simulation scenarios


def simulate_deterministic_failure(G: nx.Graph,
                                   risk_threshold: float = RISK_THRESHOLD_BLOCK
                                   ) -> Dict:
    """
    Remove all edges with risk_score >= threshold and recompute connectivity.

    Args:
        G: Full connectivity graph from graph_builder.py
        risk_threshold: Edges above this are removed

    Returns:
        Dict with:
          - failed_edges: list of removed edge IDs
          - isolated_villages: list of village node IDs with no hospital path
          - travel_time_deltas: {village_id: delta_minutes}
    """
    logger.info(f"[M5] Running deterministic failure simulation (threshold={risk_threshold})")

    G_failed = G.copy()
    failed_edges = []

    for u, v, data in G.edges(data=True):
        if data.get("risk_score", 0) >= risk_threshold:
            G_failed.remove_edge(u, v)
            failed_edges.append((u, v))

    logger.info(f"[M5] Removed {len(failed_edges)} high-risk edges")

    # TODO: Identify isolated villages (no path to any hospital node)
    # TODO: Compute travel time delta vs baseline shortest paths

    return {
        "failed_edges": failed_edges,
        "isolated_villages": [],      # TODO
        "travel_time_deltas": {},     # TODO
    }


def simulate_monte_carlo(G: nx.Graph,
                         n_scenarios: int = N_MONTE_CARLO) -> Dict:
    """
    Run N probabilistic simulations where each edge is removed
    with probability = its risk_score.

    Returns:
        Dict with:
          - isolation_probability: {village_id: probability of isolation}
          - expected_travel_time_increase: {village_id: expected delta minutes}
    """
    logger.info(f"[M5] Running Monte Carlo simulation ({n_scenarios} scenarios)")

    isolation_counts = {}  # village_id → count of scenarios where isolated
    travel_time_totals = {}

    for scenario in range(n_scenarios):
        G_scenario = G.copy()

        # Probabilistic edge removal
        for u, v, data in G.edges(data=True):
            if np.random.random() < data.get("risk_score", 0):
                G_scenario.remove_edge(u, v)

        # TODO: For each village, check hospital reachability and travel time

    isolation_probability = {
        vid: count / n_scenarios
        for vid, count in isolation_counts.items()
    }

    logger.info("[M5] Monte Carlo simulation complete")
    return {
        "isolation_probability": isolation_probability,
        "expected_travel_time_increase": travel_time_totals,
    }


def identify_isolated_villages(G: nx.Graph, hospital_nodes: List[str]) -> List[str]:
    """
    Return list of village node IDs that have no path to any hospital.

    Args:
        G: Post-failure graph
        hospital_nodes: List of node IDs tagged as hospitals

    Returns:
        List of isolated village node IDs
    """
    isolated = []
    village_nodes = [n for n, d in G.nodes(data=True) if d.get("node_type") == "village"]

    for village in village_nodes:
        reachable = False
        for hospital in hospital_nodes:
            if nx.has_path(G, village, hospital):
                reachable = True
                break
        if not reachable:
            isolated.append(village)

    logger.info(f"[M5] {len(isolated)} villages isolated from hospital access")
    return isolated
