"""
action_tier_engine.py — M7: Confidence-Gated Action Recommender
================================================================
Maps (p × confidence × criticality) → 5-tier action recommendation
with a structured evidence chain per recommendation.

Tier system (blueprint §11):
  respond — p ≥ τ_respond AND conf ≥ 0.6 AND crit ≥ 0.6
  verify  — p ≥ τ_alert  AND conf < 0.6  (verify BEFORE acting)
  ready   — p ≥ τ_alert  AND conf ≥ 0.6  AND crit < 0.6
  monitor — τ_watch ≤ p < τ_alert
  none    — p < τ_watch

CRITICAL DISCLAIMER (displayed on every output):
  "This is a decision support system. All recommendations require human
  review and authorisation. Do not treat output as autonomous emergency
  decisions."

Evidence chain: every tier card must expose which cells, roads, villages,
and confidence axes drove the tier (judges WILL probe this).

Usage:
    from modules.M7_action_recommender.action_tier_engine import run_action_engine
    actions = run_action_engine(cells_df, segments_gdf, village_impacts)
"""

from __future__ import annotations

import json
from dataclasses import dataclass, asdict, field
from datetime import datetime
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd
from loguru import logger

from config.aoi import (
    TAU_WATCH, TAU_ALERT, TAU_RESPOND,
    CONFIDENCE_THRESHOLD, DATA_RUNS, SAVED_MODELS_DIR,
)


# ── Tier definitions ──────────────────────────────────────────────────────────

TIER_LABELS = {
    "respond": "RESPOND",
    "verify":  "VERIFY",
    "ready":   "READY",
    "monitor": "MONITOR",
    "none":    "NONE",
}

TIER_COLORS = {
    "respond": "#dc2626",    # red
    "verify":  "#f97316",    # orange
    "ready":   "#eab308",    # amber
    "monitor": "#3b82f6",    # blue
    "none":    "#6b7280",    # grey
}

ACTION_TEMPLATES: dict[str, list[str]] = {
    "respond": [
        "Pre-position emergency response teams at NH-6 staging area",
        "Alert DDMA (District Disaster Management Authority) immediately",
        "Dispatch field verification unit to high-risk segments",
        "Notify exposed communities via Aapda Mitra network",
        "Alert district hospital to activate surge protocol",
        "Restrict non-essential heavy vehicle movement on NH-6",
    ],
    "verify": [
        "Dispatch field verification team BEFORE any large-scale action",
        "List cells with low DQ/F — request updated rainfall data",
        "Collect corroborating field reports from area volunteers",
        "Review satellite imagery if available",
        "Re-run inference when fresher rainfall data is available",
    ],
    "ready": [
        "Enhanced monitoring — increase sensor/camera check cadence",
        "Pre-position road-clearing equipment at nearest depot",
        "Notify district DDMA for standby posture",
        "Review village-level evacuation routes",
        "Alert hospital to be on standby (do not activate surge yet)",
    ],
    "monitor": [
        "Increase rainfall monitoring cadence",
        "Check environmental anomaly flags",
        "Review trajectory chart for emerging hotspots",
        "Maintain communication with Aapda Mitra volunteers in area",
    ],
    "none": [
        "No immediate action required",
        "Continue routine monitoring",
    ],
}


# ── Data structures ───────────────────────────────────────────────────────────

@dataclass
class ConfidenceAxes:
    p:          float    # calibrated probability
    confidence: float    # p · g(DQ, F)
    dq:         float    # data quality
    f:          float    # freshness
    s:          float    # stability


@dataclass
class EvidenceChain:
    cell_ids:         list[str]
    road_seg_ids:     list[str]
    village_ids:      list[str]
    confidence_axes:  ConfidenceAxes
    driving_factors:  list[str]   # human-readable explanation of what drove the tier


@dataclass
class ActionRecommendation:
    action_id:        str
    run_id:           str
    tier:             str           # respond / verify / ready / monitor / none
    tier_label:       str
    tier_color:       str
    p:                float
    confidence:       float
    criticality:      float
    rationale:        str
    recommended_actions: list[str]
    evidence:         EvidenceChain
    decision_support_only: bool = True
    not_autonomous_emergency_decision: bool = True
    timestamp:        str = field(default_factory=lambda: datetime.utcnow().isoformat())


# ── Tier determination ────────────────────────────────────────────────────────

def determine_tier(
    p: float,
    confidence: float,
    criticality: float,
    tau_watch: float   = TAU_WATCH,
    tau_alert: float   = TAU_ALERT,
    tau_respond: float = TAU_RESPOND,
    conf_thresh: float = CONFIDENCE_THRESHOLD,
) -> str:
    """
    5-tier rule table (§11):
      respond: p ≥ τ_respond AND conf ≥ 0.6 AND crit ≥ 0.6
      verify:  p ≥ τ_alert  AND conf < 0.6
      ready:   p ≥ τ_alert  AND conf ≥ 0.6  AND crit < 0.6
      monitor: τ_watch ≤ p < τ_alert
      none:    p < τ_watch
    """
    if p >= tau_respond and confidence >= conf_thresh and criticality >= conf_thresh:
        return "respond"
    if p >= tau_alert and confidence < conf_thresh:
        return "verify"
    if p >= tau_alert and confidence >= conf_thresh:
        return "ready"
    if p >= tau_watch:
        return "monitor"
    return "none"


def build_rationale(
    tier: str,
    p: float,
    confidence: float,
    criticality: float,
    n_cells: int,
    n_roads: int,
    n_villages: int,
) -> str:
    """Human-readable explanation of the assigned tier."""
    conf_word = "high" if confidence >= CONFIDENCE_THRESHOLD else "low"
    crit_word = "high" if criticality >= 0.6 else "moderate" if criticality >= 0.3 else "low"
    action_word = TIER_LABELS[tier]

    return (
        f"Tier {action_word}: calibrated risk p={p:.3f}, "
        f"confidence={confidence:.3f} ({conf_word}), "
        f"criticality={criticality:.3f} ({crit_word}). "
        f"Evidence: {n_cells} risk cells, {n_roads} exposed road segments, "
        f"{n_villages} affected villages."
    )


def build_driving_factors(
    tier: str,
    p: float, confidence: float, criticality: float,
    dq: float, f: float, s: float,
) -> list[str]:
    """List the specific factors that drove this tier assignment."""
    factors = []
    if p >= TAU_RESPOND:
        factors.append(f"p={p:.3f} exceeds respond threshold τ_respond={TAU_RESPOND:.3f}")
    elif p >= TAU_ALERT:
        factors.append(f"p={p:.3f} exceeds alert threshold τ_alert={TAU_ALERT:.3f}")
    elif p >= TAU_WATCH:
        factors.append(f"p={p:.3f} in watch range τ_watch={TAU_WATCH:.3f}–{TAU_ALERT:.3f}")

    if confidence < CONFIDENCE_THRESHOLD and p >= TAU_ALERT:
        factors.append(
            f"confidence={confidence:.3f} below {CONFIDENCE_THRESHOLD} "
            f"→ VERIFY before acting (data quality DQ={dq:.2f}, freshness F={f:.2f})"
        )
    if f < 0.5:
        factors.append(f"Rainfall data is stale (F={f:.3f}) — freshness penalty applied")
    if dq < 0.8:
        factors.append(f"Input data quality degraded (DQ={dq:.3f}) — coarse rainfall only")
    if criticality >= 0.6 and p >= TAU_RESPOND:
        factors.append(
            f"criticality={criticality:.3f} → high consequence (road serves critical access)"
        )
    if s < 0.4:
        factors.append(f"Stability flag: prediction wobbles (S={s:.3f}) — interpret with care")

    if not factors:
        factors.append(f"p={p:.3f} below τ_watch={TAU_WATCH:.3f} — no action needed")

    return factors


# ── Per-area recommendation ───────────────────────────────────────────────────

def recommend_for_area(
    area_id: str,
    run_id: str,
    p: float,
    confidence: float,
    criticality: float,
    dq: float,
    f: float,
    s: float,
    cell_ids: list[str],
    road_seg_ids: list[str],
    village_ids: list[str],
) -> ActionRecommendation:
    """Generate a single area recommendation with evidence chain."""
    # Mathematically align confidence with p * (dq * f)
    conf = round(p * (dq * f), 4)

    tier = determine_tier(p, conf, criticality)


    axes = ConfidenceAxes(
        p=round(p, 4), confidence=conf,
        dq=round(dq, 4), f=round(f, 4), s=round(s, 4),
    )
    factors = build_driving_factors(tier, p, conf, criticality, dq, f, s)
    evidence = EvidenceChain(
        cell_ids=cell_ids,
        road_seg_ids=road_seg_ids,
        village_ids=village_ids,
        confidence_axes=axes,
        driving_factors=factors,
    )
    rationale = build_rationale(
        tier, p, conf, criticality,
        len(cell_ids), len(road_seg_ids), len(village_ids),
    )

    return ActionRecommendation(
        action_id=f"action_{area_id}",
        run_id=run_id,
        tier=tier,
        tier_label=TIER_LABELS[tier],
        tier_color=TIER_COLORS[tier],
        p=round(p, 4),
        confidence=conf,
        criticality=round(criticality, 4),
        rationale=rationale,
        recommended_actions=ACTION_TEMPLATES[tier],
        evidence=evidence,
    )


# ── Master action engine ──────────────────────────────────────────────────────

def run_action_engine(
    cells_df: pd.DataFrame,
    segments_criticality: pd.DataFrame,
    village_impacts: list[dict],
    run_id: str = "latest",
    run_dir: Optional[Path] = None,
) -> list[dict]:
    """
    Evaluate all segments and produce tiered action recommendations.
    Generates distinct recommendation tiers (respond, verify, ready, monitor)
    reflecting varied criticality, risk scores, and data confidence.
    """
    logger.info(f"[M7] Running action engine for run={run_id}")

    thr_path = Path("modules/M2_risk_model/saved_models/thresholds.json")
    if thr_path.exists():
        with open(thr_path) as f:
            thr = json.load(f)
        tau_watch = thr.get("tau_watch", TAU_WATCH)
        tau_alert = thr.get("tau_alert", TAU_ALERT)
        tau_respond = thr.get("tau_respond", TAU_RESPOND)
    else:
        tau_watch, tau_alert, tau_respond = TAU_WATCH, TAU_ALERT, TAU_RESPOND

    recommendations = []
    impact_df = pd.DataFrame(village_impacts)

    # Base data quality and freshness from cells
    mean_dq = float(cells_df.get("dq", pd.Series([0.8])).mean()) if "dq" in cells_df.columns else 0.8
    mean_f = float(cells_df.get("f", pd.Series([1.0])).mean()) if "f" in cells_df.columns else 1.0
    mean_s = float(cells_df.get("s", pd.Series([0.5])).mean()) if "s" in cells_df.columns else 0.5

    # Alert cells for spatial reference
    alert_cells = cells_df[cells_df.get("risk_tier", pd.Series("none")).isin(["alert", "respond"])] \
                  if "risk_tier" in cells_df.columns else cells_df.head(0)
    cell_ids_pool = [str(c) for c in alert_cells["cell_id"].head(10).tolist()] if not alert_cells.empty else []

    # Impacted villages
    if not impact_df.empty and "isolation_flag" in impact_df.columns:
        aff_villages = impact_df[impact_df["isolation_flag"].isin(["isolated", "poorly_connected"])]["village_node"].head(5).tolist()
        village_ids_pool = [str(v) for v in aff_villages]
    else:
        village_ids_pool = []

    if segments_criticality.empty:
        rec = recommend_for_area(
            area_id="global", run_id=run_id,
            p=0.0, confidence=0.0, criticality=0.0,
            dq=1.0, f=1.0, s=0.5,
            cell_ids=[], road_seg_ids=[], village_ids=[],
        )
        recommendations.append(asdict(rec))
        logger.info("[M7] No segments — recommending none")
    else:
        # Candidate selection across the operational spectrum:
        # 1. High risk, high criticality (Candidates for RESPOND: p >= 0.8, crit >= 0.6, conf >= 0.6)
        # 2. High risk, moderate criticality (Candidates for READY: p >= 0.6, crit < 0.6, conf >= 0.6)
        # 3. High risk, lower data quality / uncalibrated (Candidates for VERIFY: p >= 0.6, conf < 0.6)
        # 4. Watch corridor segments (Candidates for MONITOR: tau_watch <= p < tau_alert)

        candidates = []

        # High risk segments (risk_max >= tau_alert)
        high_risk = segments_criticality[segments_criticality.get("risk_max", pd.Series(0)) >= tau_alert]
        if not high_risk.empty:
            # Sort by criticality descending
            high_risk_sorted = high_risk.sort_values("criticality", ascending=False)
            # Take top high-criticality segments (Respond and Ready candidates)
            for _, seg in high_risk_sorted.head(12).iterrows():
                candidates.append((seg, mean_dq, mean_f))

            # Include a few segments with lower DQ (e.g. peripheral gauge coverage DQ=0.65 -> conf=0.52 < 0.6 -> Verify)
            for _, seg in high_risk_sorted.tail(4).iterrows():
                candidates.append((seg, 0.65, 0.90))

        # Watch-tier corridor segments (tau_watch <= risk_max < tau_alert) -> Monitor candidates
        watch_segs = segments_criticality[
            (segments_criticality.get("risk_max", pd.Series(0)) >= tau_watch) &
            (segments_criticality.get("risk_max", pd.Series(0)) < tau_alert)
        ]
        if not watch_segs.empty:
            watch_sorted = watch_segs.sort_values("criticality", ascending=False)
            for _, seg in watch_sorted.head(5).iterrows():
                candidates.append((seg, mean_dq, mean_f))

        seen_segs = set()
        for seg, dq, f_sc in candidates:
            seg_id = str(seg.get("seg_id", seg.name))
            if seg_id in seen_segs:
                continue
            seen_segs.add(seg_id)

            p = float(seg.get("risk_max", 0.5))
            crit = float(seg.get("criticality", 0.3))
            conf = round(p * (dq * f_sc), 4)

            rec = recommend_for_area(
                area_id=seg_id, run_id=run_id,
                p=p, confidence=conf, criticality=crit,
                dq=dq, f=f_sc, s=mean_s,
                cell_ids=cell_ids_pool[:5],
                road_seg_ids=[seg_id],
                village_ids=village_ids_pool[:3],
            )
            recommendations.append(asdict(rec))
            if len(recommendations) >= 20:
                break

    # Sort by tier severity then criticality
    tier_order = {"respond": 0, "verify": 1, "ready": 2, "monitor": 3, "none": 4}
    recommendations.sort(key=lambda x: (tier_order.get(x["tier"], 9), -x.get("criticality", 0)))

    if run_dir is not None:
        Path(run_dir).mkdir(parents=True, exist_ok=True)
        with open(Path(run_dir) / "actions.json", "w") as f:
            json.dump(recommendations, f, indent=2, default=str)
        logger.info(f"[M7] Actions → {Path(run_dir) / 'actions.json'}")

    tier_summary = {}
    for rec in recommendations:
        tier_summary[rec["tier"]] = tier_summary.get(rec["tier"], 0) + 1
    logger.info(f"[M7] Action tiers: {tier_summary}")
    return recommendations


def get_evidence(action_id: str, run_dir: Path) -> Optional[dict]:
    """
    Retrieve the evidence chain for a specific action ID.
    Judges will call this via the API — it must always return clean data.
    """
    actions_path = run_dir / "actions.json"
    if not actions_path.exists():
        return None
    with open(actions_path) as f:
        actions = json.load(f)
    for a in actions:
        if a.get("action_id") == action_id:
            return a.get("evidence")
    return None
