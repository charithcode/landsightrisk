"""
criticality_formula.py — M6: Dynamic Criticality Scorer
=========================================================
Computes a composite Criticality Score for each at-risk village/corridor.

Formula:
  criticality = w1*hazard_risk + w2*population_dependency
              + w3*alt_route_scarcity + w4*hospital_access_loss

All sub-scores normalized to [0,1] before weighting.

Higher criticality → higher priority for emergency response.

Output: data/processed/criticality_scores.json
"""

import json
import numpy as np
import pandas as pd
from loguru import logger

# Weights (must sum to 1.0)
W_HAZARD = 0.30
W_POPULATION = 0.25
W_ALT_ROUTE = 0.25
W_HOSPITAL = 0.20


def score_hazard_risk(risk_scores: np.ndarray) -> np.ndarray:
    """Sub-score 1: Raw landslide risk from M2. Already in [0,1]."""
    return np.clip(risk_scores, 0.0, 1.0)


def score_population_dependency(populations: np.ndarray) -> np.ndarray:
    """
    Sub-score 2: Normalize population served by a corridor.
    Larger population → higher score.
    """
    max_pop = populations.max() if populations.max() > 0 else 1
    return populations / max_pop


def score_alt_route_scarcity(alt_route_counts: np.ndarray) -> np.ndarray:
    """
    Sub-score 3: Penalize corridors with few/no alternative routes.
    0 alt routes → score 1.0 (most critical)
    1 alt route  → score 0.6
    2+ alt routes → score 0.0 (least critical)
    """
    scores = np.where(alt_route_counts == 0, 1.0,
             np.where(alt_route_counts == 1, 0.6, 0.0))
    return scores


def score_hospital_access_loss(hospital_access_lost: np.ndarray) -> np.ndarray:
    """
    Sub-score 4: Binary/graded hospital access loss.
    1.0 = complete loss of hospital access
    0.0 = hospital still reachable
    """
    return np.clip(hospital_access_lost, 0.0, 1.0)


def compute_criticality(
    risk_scores: np.ndarray,
    populations: np.ndarray,
    alt_route_counts: np.ndarray,
    hospital_access_lost: np.ndarray,
) -> np.ndarray:
    """
    Compute composite criticality scores for a set of villages/corridors.

    Returns:
        criticality_scores: np.ndarray in [0.0, 1.0]
    """
    logger.info("[M6] Computing criticality scores")

    s1 = score_hazard_risk(risk_scores)
    s2 = score_population_dependency(populations)
    s3 = score_alt_route_scarcity(alt_route_counts)
    s4 = score_hospital_access_loss(hospital_access_lost)

    composite = W_HAZARD * s1 + W_POPULATION * s2 + W_ALT_ROUTE * s3 + W_HOSPITAL * s4
    return composite


def rank_and_export(village_ids: list,
                    criticality_scores: np.ndarray,
                    extra_attrs: dict = None) -> list:
    """
    Rank villages by criticality and export as JSON.

    Args:
        village_ids: List of village identifiers
        criticality_scores: Corresponding scores
        extra_attrs: Dict of extra attribute arrays (optional)

    Returns:
        Sorted list of dicts, highest criticality first
    """
    records = []
    for i, (vid, score) in enumerate(zip(village_ids, criticality_scores)):
        record = {"village_id": vid, "criticality_score": round(float(score), 4)}
        if extra_attrs:
            for key, arr in extra_attrs.items():
                record[key] = arr[i]
        records.append(record)

    records.sort(key=lambda x: x["criticality_score"], reverse=True)

    with open("data/processed/criticality_scores.json", "w") as f:
        json.dump(records, f, indent=2)
    logger.info("[M6] Criticality scores saved to data/processed/criticality_scores.json")

    return records
