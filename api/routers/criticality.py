"""criticality.py — Ranked criticality segments router"""
import json
from pathlib import Path
from fastapi import APIRouter, Query, HTTPException
from config.aoi import DATA_PROCESSED, DATA_RUNS, CRITICALITY_WEIGHTS
from api.run_resolver import resolve_run

router = APIRouter(prefix="/criticality", tags=["Criticality"])


@router.get("")
async def get_criticality(
    run: str = Query("latest"),
    top_n: int = Query(20, description="Return top N segments"),
):
    """
    Ranked road segments with 5-component criticality bars.
    Returns segments sorted by criticality descending.
    Each segment includes: criticality, comp_RISK, comp_SERVED,
    comp_DETOUR, comp_HOSPDEP, comp_TREND, weights, rationale.
    """
    run_dir = resolve_run(run)
    processed = Path(DATA_PROCESSED)
    crit_path = run_dir / "criticality.geojson"
    if not crit_path.exists():
        crit_path = processed / "criticality.geojson"
    weights_path = processed / "criticality_weights.json"

    if not crit_path.exists():
        raise HTTPException(503, "Criticality not computed. Run M6 pipeline.")

    with open(crit_path) as f:
        crit_fc = json.load(f)

    weights = CRITICALITY_WEIGHTS
    if weights_path.exists():
        with open(weights_path) as f:
            weights_meta = json.load(f)
        weights = weights_meta.get("weights", weights)

    features = crit_fc.get("features", [])
    # Sort by criticality
    features.sort(
        key=lambda x: x.get("properties", {}).get("criticality", 0),
        reverse=True
    )
    features = features[:top_n]

    return {
        "type": "FeatureCollection",
        "features": features,
        "weights": weights,
        "rationale": (
            "DETOUR/HOSPDEP weighted highest because NH-6 is a single-artery "
            "corridor — edge removal has outsized consequence. "
            "RISK anchors to measured hazard probability."
        ),
        "n_total": len(crit_fc.get("features", [])),
        "n_returned": len(features),
    }
