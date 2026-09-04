"""
composite_confidence.py — M3: Uncertainty & Confidence Estimation Engine
=========================================================================
Combines three confidence signals into a single "Decision Confidence"
score (0.0–1.0) per grid cell.

Three signals:
  1. model_confidence  — RF probability spread / prediction entropy
  2. data_quality      — Missing/null feature ratio per cell
  3. data_freshness    — How stale is the rainfall/soil data?
  + (M8 hook) field_report_trust — citizen report trust injection

High Decision Confidence + High Risk → Tier 3 (emergency)
Low Decision Confidence + High Risk  → Tier 1 (monitor; do not over-react)

Output:
  data/processed/confidence_layer.geojson
"""

import numpy as np
import geopandas as gpd
from loguru import logger


# Weights for composite score (must sum to 1.0)
W_MODEL = 0.45
W_DATA_QUALITY = 0.30
W_FRESHNESS = 0.25


def compute_model_confidence(risk_proba: np.ndarray) -> np.ndarray:
    """
    Derive model confidence from RF probability.
    High confidence = prediction is far from 0.5 (decisive).
    
    confidence = |p - 0.5| * 2   →  maps [0.5, 1.0] to [0.0, 1.0]
    """
    return np.abs(risk_proba - 0.5) * 2.0


def compute_data_quality_score(feature_gdf: gpd.GeoDataFrame) -> np.ndarray:
    """
    Score data quality per cell: fraction of features that are present and valid.
    
    Returns:
        Array of scores in [0.0, 1.0]. 1.0 = all features present.
    """
    # TODO: Check null/missing values per row across feature columns
    # completeness = 1 - (null_count / total_features)
    raise NotImplementedError("Data quality scorer not yet implemented")


def compute_freshness_score(freshness_hours: np.ndarray,
                            max_stale_hours: float = 48.0) -> np.ndarray:
    """
    Penalize stale data. Score = 1.0 if data is fresh, decays linearly.
    
    Args:
        freshness_hours: Hours since last data update per cell
        max_stale_hours: Beyond this, score → 0.0
    """
    scores = 1.0 - np.clip(freshness_hours / max_stale_hours, 0.0, 1.0)
    return scores


def compute_composite_confidence(
    risk_proba: np.ndarray,
    feature_gdf: gpd.GeoDataFrame,
    freshness_hours: np.ndarray,
    report_trust_boost: np.ndarray = None,
) -> np.ndarray:
    """
    Compute final composite Decision Confidence per grid cell.

    Args:
        risk_proba:        Risk probabilities from M2
        feature_gdf:       Feature matrix from M1
        freshness_hours:   Hours since data last updated, per cell
        report_trust_boost: Optional array from M8 (trust-weighted reports)

    Returns:
        confidence_scores: np.ndarray in [0.0, 1.0]
    """
    logger.info("[M3] Computing composite confidence scores")

    model_conf = compute_model_confidence(risk_proba)
    # data_qual = compute_data_quality_score(feature_gdf)   # TODO: enable
    freshness = compute_freshness_score(freshness_hours)

    # Placeholder until data quality is implemented
    data_qual = np.ones(len(risk_proba))

    composite = (
        W_MODEL * model_conf
        + W_DATA_QUALITY * data_qual
        + W_FRESHNESS * freshness
    )

    # M8 injection: corroborated field reports raise confidence
    if report_trust_boost is not None:
        logger.info("[M3] Injecting field report trust boost from M8")
        composite = np.clip(composite + report_trust_boost, 0.0, 1.0)

    return composite


def build_confidence_layer(
    risk_gdf: gpd.GeoDataFrame,
    confidence_scores: np.ndarray,
) -> gpd.GeoDataFrame:
    """
    Attach confidence scores to the risk GeoDataFrame and save.

    Returns:
        GeoDataFrame with added 'decision_confidence' column.
    """
    result = risk_gdf.copy()
    result["decision_confidence"] = confidence_scores
    output_path = "data/processed/confidence_layer.geojson"
    result.to_file(output_path, driver="GeoJSON")
    logger.info(f"[M3] Confidence layer saved to {output_path}")
    return result
