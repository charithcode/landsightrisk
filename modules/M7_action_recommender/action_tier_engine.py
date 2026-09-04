"""
action_tier_engine.py — M7: Confidence-Gated Action Recommender
================================================================
Determines the appropriate response tier for each at-risk corridor/village
based on the combination of:
  - risk_score (from M2)
  - decision_confidence (from M3)
  - criticality_score (from M6)

Tier System:
  TIER 1 — Monitor & Observe
    → Low confidence OR low risk. Don't over-commit resources on uncertainty.
    → Actions: Enhanced monitoring, pre-alert to local officials.

  TIER 2 — Pre-Position & Advisory
    → Medium risk + medium confidence.
    → Actions: Pre-position road-clearing crews, issue public advisory,
               notify district DDMA, alert hospitals.

  TIER 3 — Emergency Deploy
    → High risk + high confidence.
    → Actions: Evacuate vulnerable zones, deploy emergency response,
               activate NDRF/SDRF, full hospital surge preparation.

Output:
  data/processed/action_recommendations.json
"""

import json
from dataclasses import dataclass, asdict
from typing import List
from loguru import logger
import os
from dotenv import load_dotenv

load_dotenv()

RISK_HIGH = float(os.getenv("RISK_THRESHOLD_HIGH", 0.75))
RISK_MED = float(os.getenv("RISK_THRESHOLD_MEDIUM", 0.45))
CONF_HIGH = float(os.getenv("CONFIDENCE_THRESHOLD_HIGH", 0.70))
CONF_LOW = float(os.getenv("CONFIDENCE_THRESHOLD_LOW", 0.40))


@dataclass
class ActionRecommendation:
    village_id: str
    risk_score: float
    decision_confidence: float
    criticality_score: float
    action_tier: int                  # 1, 2, or 3
    tier_label: str                   # "MONITOR" / "ADVISORY" / "EMERGENCY"
    rationale: str                    # Human-readable explanation
    recommended_actions: List[str]


ACTION_TEMPLATES = {
    1: {
        "label": "MONITOR",
        "actions": [
            "Increase monitoring frequency at weather stations",
            "Pre-alert local village panchayat",
            "Review and test emergency communication channels",
        ]
    },
    2: {
        "label": "ADVISORY",
        "actions": [
            "Issue public advisory for the corridor",
            "Pre-position road-clearing crew at nearest NHAI depot",
            "Notify District Disaster Management Authority (DDMA)",
            "Alert nearest district hospital to standby",
            "Restrict non-essential heavy vehicle movement",
        ]
    },
    3: {
        "label": "EMERGENCY",
        "actions": [
            "Initiate evacuation of vulnerable slope-adjacent settlements",
            "Deploy NDRF / SDRF to the corridor",
            "Activate Emergency Operations Centre (EOC)",
            "Full hospital surge preparation at district hospital",
            "Dispatch road-clearing equipment immediately",
            "Broadcast emergency alert via Aapda Mitra network",
        ]
    }
}


def determine_tier(risk_score: float, confidence: float) -> int:
    """
    Map (risk, confidence) to action tier.

    Decision matrix:
      High risk + High conf → Tier 3
      High risk + Low conf  → Tier 2 (confidence gates escalation)
      Med risk + Any conf   → Tier 2
      Low risk OR Low conf  → Tier 1
    """
    if risk_score >= RISK_HIGH and confidence >= CONF_HIGH:
        return 3
    elif risk_score >= RISK_MED or (risk_score >= RISK_HIGH and confidence < CONF_HIGH):
        return 2
    else:
        return 1


def build_rationale(village_id: str, risk: float, confidence: float,
                    criticality: float, tier: int) -> str:
    """Generate a human-readable explanation for the assigned tier."""
    return (
        f"Village '{village_id}': Risk score={risk:.2f}, "
        f"Decision Confidence={confidence:.2f}, "
        f"Criticality={criticality:.2f}. "
        f"Assigned Tier {tier} ({ACTION_TEMPLATES[tier]['label']})."
    )


def recommend(village_id: str,
              risk_score: float,
              decision_confidence: float,
              criticality_score: float) -> ActionRecommendation:
    """
    Generate a full action recommendation for a single village/corridor.
    """
    tier = determine_tier(risk_score, decision_confidence)
    rationale = build_rationale(village_id, risk_score, decision_confidence,
                                criticality_score, tier)
    return ActionRecommendation(
        village_id=village_id,
        risk_score=round(risk_score, 4),
        decision_confidence=round(decision_confidence, 4),
        criticality_score=round(criticality_score, 4),
        action_tier=tier,
        tier_label=ACTION_TEMPLATES[tier]["label"],
        rationale=rationale,
        recommended_actions=ACTION_TEMPLATES[tier]["actions"],
    )


def run_recommendations(villages: List[dict]) -> List[dict]:
    """
    Generate recommendations for all villages.

    Args:
        villages: List of dicts with keys:
                  [village_id, risk_score, decision_confidence, criticality_score]

    Returns:
        List of ActionRecommendation dicts, sorted by criticality (desc)
    """
    logger.info(f"[M7] Generating action recommendations for {len(villages)} villages")
    results = []
    for v in villages:
        rec = recommend(
            village_id=v["village_id"],
            risk_score=v["risk_score"],
            decision_confidence=v["decision_confidence"],
            criticality_score=v["criticality_score"],
        )
        results.append(asdict(rec))

    results.sort(key=lambda x: x["criticality_score"], reverse=True)

    with open("data/processed/action_recommendations.json", "w") as f:
        json.dump(results, f, indent=2)
    logger.info("[M7] Action recommendations saved")
    return results
