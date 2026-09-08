"""
trust_scorer.py — M8: Trust-Weighted Field Reports
====================================================
Scores incoming field reports on four independent axes (blueprint §12).

AXES:
  pedigree   — reporter credential level
  accuracy   — GPS horizontal accuracy
  freshness  — exponential decay from report timestamp
  sanity     — report type specificity + AOI validation

FORMULA:
  trust = pedigree × accuracy × freshness × sanity
  corroboration bonus: ×1.3 if ≥2 independent reports within 500m/12h (cap 1.0)

HARD RULES (§12):
  1. reports_enter_training = False  — enforced by assertion; reports NEVER
     update the landslide inventory or retrain the model.
  2. confidence_boost changes S (stability) only — never changes p.
  3. Trust score is used ONLY for UI display and corroboration detection.

Reporter pedigree levels:
  official_agency      → 1.0  (NDRF, SDRF, DDMA, highway patrol)
  trained_volunteer    → 0.7  (Aapda Mitra, NCC, NSS volunteers)
  anonymous_citizen    → 0.4  (unauthenticated public submission)

GPS accuracy:
  ≤ 20m  → 1.0
  ≤ 200m → 0.7
  > 200m → 0.4

Freshness (exponential, τ=6h):
  ≤ 1h → 1.0
  6h   → ~0.37
  24h  → ~0.02

Report type sanity:
  road_blocked           → 1.0
  bridge_damaged         → 0.95
  debris_flow_observed   → 0.9
  landslide_active       → 0.85
  landslide_risk_seen    → 0.7
  generic_landslide      → 0.5
  other                  → 0.3
"""

from __future__ import annotations

import math
from datetime import datetime, timedelta
from typing import Literal, Optional

from loguru import logger

from config.aoi import (
    AOI_BBOX_WGS84, CORROBORATION_RADIUS_M,
    CORROBORATION_WINDOW_H, CORROBORATION_MIN_COUNT,
)

# ── HARD RULE: reports never enter training ────────────────────────────────────
reports_enter_training: bool = False
assert reports_enter_training is False, (
    "INVARIANT VIOLATION: field reports must never enter the ML training pipeline. "
    "Trust scores affect only S (stability overlay) in M3, never p."
)


# ── Pedigree levels ───────────────────────────────────────────────────────────

PEDIGREE_SCORES: dict[str, float] = {
    "official_agency":   1.00,   # NDRF/SDRF/DDMA/highway patrol
    "trained_volunteer": 0.70,   # Aapda Mitra, NCC, NSS
    "anonymous_citizen": 0.40,   # unauthenticated public
}

REPORT_TYPE_SCORES: dict[str, float] = {
    "road_blocked":         1.00,
    "bridge_damaged":       0.95,
    "debris_flow_observed": 0.90,
    "landslide_active":     0.85,
    "landslide_risk_seen":  0.70,
    "generic_landslide":    0.50,
    "other":                0.30,
}

PEDIGREE_FRESHNESS_TAU_HOURS = 6.0    # τ for freshness decay
PEDIGREE_FRESH_WINDOW_HOURS  = 1.0    # ≤ 1h → F = 1.0

# AOI ± buffer (degrees) for GPS validation
AOI_BUFFER_DEG = 0.014    # ~1.5 km


# ── Scoring functions ─────────────────────────────────────────────────────────

def score_pedigree(reporter_type: str) -> float:
    """Return pedigree score for a reporter type string."""
    return PEDIGREE_SCORES.get(reporter_type.lower(), PEDIGREE_SCORES["anonymous_citizen"])


def score_gps_accuracy(gps_accuracy_m: Optional[float]) -> float:
    """Return GPS accuracy score."""
    if gps_accuracy_m is None:
        return 0.4   # no accuracy info → weakest score
    if gps_accuracy_m <= 20:
        return 1.0
    if gps_accuracy_m <= 200:
        return 0.7
    return 0.4


def score_freshness(report_timestamp: datetime) -> float:
    """
    Exponential freshness: F = 1.0 if ≤ 1h ago, then exp(-δh/τ).
    """
    delta_hours = (datetime.utcnow() - report_timestamp).total_seconds() / 3600.0
    if delta_hours <= PEDIGREE_FRESH_WINDOW_HOURS:
        return 1.0
    return round(math.exp(-delta_hours / PEDIGREE_FRESHNESS_TAU_HOURS), 4)


def score_type_sanity(report_type: str) -> float:
    """Return report type specificity score."""
    return REPORT_TYPE_SCORES.get(report_type.lower(), REPORT_TYPE_SCORES["other"])


def validate_aoi(lon: float, lat: float) -> bool:
    """
    Validate that GPS coordinates fall within AOI ± ~1.5 km buffer.
    Returns True if valid, False if outside.
    """
    buf = AOI_BUFFER_DEG
    lon_min = AOI_BBOX_WGS84[0] - buf
    lat_min = AOI_BBOX_WGS84[1] - buf
    lon_max = AOI_BBOX_WGS84[2] + buf
    lat_max = AOI_BBOX_WGS84[3] + buf
    return lon_min <= lon <= lon_max and lat_min <= lat <= lat_max


def compute_trust(
    reporter_type: str,
    gps_accuracy_m: Optional[float],
    report_timestamp: datetime,
    report_type: str,
    lon: float,
    lat: float,
) -> dict:
    """
    Compute the full trust score for a single field report.

    Returns:
        {
            trust: float [0, 1],
            pedigree: float,
            accuracy: float,
            freshness: float,
            sanity: float,
            aoi_valid: bool,
            corroborated: False (updated later by corroboration check)
        }
    """
    aoi_valid = validate_aoi(lon, lat)
    if not aoi_valid:
        logger.warning(f"[M8] Report outside AOI: lon={lon}, lat={lat}")
        return {
            "trust": 0.0,
            "pedigree": 0.0, "accuracy": 0.0, "freshness": 0.0, "sanity": 0.0,
            "aoi_valid": False, "corroborated": False,
        }

    pedigree  = score_pedigree(reporter_type)
    accuracy  = score_gps_accuracy(gps_accuracy_m)
    freshness = score_freshness(report_timestamp)
    sanity    = score_type_sanity(report_type)

    trust = round(pedigree * accuracy * freshness * sanity, 4)
    return {
        "trust":       trust,
        "pedigree":    pedigree,
        "accuracy":    accuracy,
        "freshness":   freshness,
        "sanity":      sanity,
        "aoi_valid":   True,
        "corroborated":False,    # updated by apply_corroboration_bonus
    }


def apply_corroboration_bonus(
    trust_result: dict,
    n_corroborating: int,
    bonus_factor: float = 1.3,
) -> dict:
    """
    Apply corroboration bonus if ≥ CORROBORATION_MIN_COUNT independent reports
    exist within CORROBORATION_RADIUS_M and CORROBORATION_WINDOW_H.

    trust final = min(trust × 1.3, 1.0)

    NOTE: corroboration boosts trust display only; it does NOT modify p.
    """
    result = trust_result.copy()
    if n_corroborating >= CORROBORATION_MIN_COUNT:
        boosted = min(trust_result["trust"] * bonus_factor, 1.0)
        result["trust"] = round(boosted, 4)
        result["corroborated"] = True
    return result


def confidence_stability_adjustment(
    trust_score: float,
    corroborated: bool,
    cells_near_report: list[str],
) -> dict:
    """
    Field reports adjust S (stability) only — NEVER p.

    Returns:
        {cell_id: s_adjustment} — small positive delta to S if trust is high.

    This is the ONLY feedback path from reports to model outputs.
    s_delta = 0.05 × trust × (1.5 if corroborated else 1.0)  (bounded to +0.1 max)
    """
    assert reports_enter_training is False, "Invariant: reports never enter training"

    s_delta = min(0.05 * trust_score * (1.5 if corroborated else 1.0), 0.10)
    return {cell_id: round(s_delta, 4) for cell_id in cells_near_report}
