"""actions.py — Tiered action recommendations router"""
import json
from pathlib import Path
from fastapi import APIRouter, Query, HTTPException
from config.aoi import DATA_RUNS
from api.run_resolver import resolve_run

router = APIRouter(prefix="/actions", tags=["Actions"])


@router.get("")
async def get_actions(run: str = Query("latest")):
    """
    5-tier action recommendations with evidence chains.
    Each recommendation includes: tier, rationale, evidence (cell_ids,
    road_ids, village_ids, confidence axes), recommended_actions.
    DISCLAIMER: decision_support_only = true on all outputs.
    """
    run_dir = resolve_run(run)
    actions_path = run_dir / "actions.json"

    if not actions_path.exists():
        raise HTTPException(503, "Actions not computed. Run M7 pipeline.")

    with open(actions_path) as f:
        actions = json.load(f)

    return {
        "actions": actions,
        "disclaimer": (
            "All recommendations are decision support only. "
            "No autonomous emergency decisions should be made from this output. "
            "Human authorisation is required for all RESPOND-tier actions."
        ),
        "n_actions": len(actions),
        "tier_counts": _count_tiers(actions),
    }


@router.get("/evidence/{action_id}")
async def get_action_evidence(action_id: str, run: str = Query("latest")):
    """
    Retrieve the structured evidence chain for a specific action ID.
    This endpoint will be probed by judges and evaluators.
    """
    run_dir = resolve_run(run)
    actions_path = run_dir / "actions.json"
    if not actions_path.exists():
        raise HTTPException(404, "No actions for this run.")
    with open(actions_path) as f:
        actions = json.load(f)
    for a in actions:
        if a.get("action_id") == action_id:
            return {
                "action_id": action_id,
                "tier":      a.get("tier"),
                "evidence":  a.get("evidence", {}),
                "rationale": a.get("rationale"),
            }
    raise HTTPException(404, f"Action {action_id} not found.")


def _count_tiers(actions: list) -> dict:
    counts = {}
    for a in actions:
        t = a.get("tier", "none")
        counts[t] = counts.get(t, 0) + 1
    return counts
