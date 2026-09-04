"""
isolation_detector.py — M5: Connectivity Failure Simulation
============================================================
After edge removal, detect villages with no viable hospital route.
Also compute: number of remaining routes, travel time increase (%).
"""
import networkx as nx
from typing import List
from loguru import logger

def find_isolated_villages(G: nx.Graph, hospital_ids: List[str]) -> List[dict]:
    """Return list of villages with no path to any hospital."""
    logger.info("[M5] Detecting isolated villages")
    raise NotImplementedError("Isolation detector not yet implemented")

