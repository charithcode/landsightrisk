"""
trust_scorer.py — M8: Trust-Weighted Citizen / Field Reports
=============================================================
⭐ Innovation Module B (MVP Priority)

Scores incoming citizen and field reports by source trust.
High-trust, corroborated reports raise the Decision Confidence
in M3's output — making the system more responsive to ground truth.

Trust score formula:
  trust = w_history * source_history_score
        + w_corroboration * corroboration_score
        + w_aapda_mitra * aapda_mitra_bonus

Corroboration rule:
  If ≥ 2 reports within 5 km + 3 hours → corroboration_score = 1.0

Aapda Mitra:
  NDMA's trained volunteer network — highest-trust human source.
  aapda_mitra_bonus = 0.3 (additive boost)
"""

import math
from datetime import datetime, timedelta
from dataclasses import dataclass, field
from typing import List, Optional
from loguru import logger

# Weights
W_HISTORY = 0.40
W_CORROBORATION = 0.40
W_AAPDA_MITRA = 0.20

CORROBORATION_RADIUS_KM = 5.0
CORROBORATION_WINDOW_HOURS = 3.0
CORROBORATION_MIN_REPORTS = 2


@dataclass
class FieldReport:
    report_id: str
    reporter_id: str
    lat: float
    lon: float
    timestamp: datetime
    description: str
    is_aapda_mitra: bool = False
    reporter_accuracy_history: float = 0.5   # 0.0–1.0, default neutral


@dataclass
class TrustScoredReport:
    report: FieldReport
    source_history_score: float
    corroboration_score: float
    aapda_mitra_bonus: float
    trust_score: float          # Final composite [0.0, 1.0]
    confidence_boost: float     # How much to add to M3 Decision Confidence


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Calculate great-circle distance between two points in km."""
    R = 6371.0
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi/2)**2 + math.cos(phi1)*math.cos(phi2)*math.sin(dlambda/2)**2
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def compute_corroboration_score(report: FieldReport,
                                all_reports: List[FieldReport]) -> float:
    """
    Check if any other report is within the corroboration radius + time window.

    Returns:
        1.0 if corroborated, 0.0 if not
    """
    window = timedelta(hours=CORROBORATION_WINDOW_HOURS)
    nearby_count = 0

    for other in all_reports:
        if other.report_id == report.report_id:
            continue
        time_diff = abs(report.timestamp - other.timestamp)
        if time_diff > window:
            continue
        dist_km = haversine_km(report.lat, report.lon, other.lat, other.lon)
        if dist_km <= CORROBORATION_RADIUS_KM:
            nearby_count += 1

    return 1.0 if nearby_count >= CORROBORATION_MIN_REPORTS - 1 else 0.0


def score_report(report: FieldReport, all_reports: List[FieldReport]) -> TrustScoredReport:
    """
    Compute full trust score for a single report.

    Returns:
        TrustScoredReport with all sub-scores and final trust score
    """
    history_score = report.reporter_accuracy_history
    corroboration = compute_corroboration_score(report, all_reports)
    aapda_bonus = 0.3 if report.is_aapda_mitra else 0.0

    trust = (
        W_HISTORY * history_score
        + W_CORROBORATION * corroboration
        + W_AAPDA_MITRA * (1.0 if report.is_aapda_mitra else 0.0)
    )
    trust = min(trust + aapda_bonus, 1.0)

    # Confidence boost injected into M3 — scales with trust
    confidence_boost = trust * 0.15   # Max 15% boost to Decision Confidence

    return TrustScoredReport(
        report=report,
        source_history_score=history_score,
        corroboration_score=corroboration,
        aapda_mitra_bonus=aapda_bonus,
        trust_score=round(trust, 4),
        confidence_boost=round(confidence_boost, 4),
    )


def score_all_reports(reports: List[FieldReport]) -> List[TrustScoredReport]:
    """Score all incoming reports."""
    logger.info(f"[M8] Scoring {len(reports)} field reports")
    return [score_report(r, reports) for r in reports]
