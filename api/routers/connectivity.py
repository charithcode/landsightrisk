"""connectivity.py — Exposed roads + village impact router"""
import json
from pathlib import Path
from typing import Optional
from fastapi import APIRouter, Query, HTTPException
from config.aoi import DATA_RUNS, DATA_PROCESSED, SCENARIO_RAINFALL_REPLAY, SCENARIO_NH6_BLOCK
from api.run_resolver import resolve_run

router = APIRouter(prefix="/connectivity", tags=["Connectivity"])


@router.get("/exposed")
async def get_exposed(run: str = Query("latest")):
    """
    Exposed roads GeoJSON (segments with risk_max ≥ τ_alert) +
    exposed communities GeoJSON — merged into a single FeatureCollection.
    """
    run_dir = resolve_run(run)
    processed = Path(DATA_PROCESSED)
    out = {"type": "FeatureCollection", "features": []}

    roads_path = run_dir / "exposed_roads.geojson"
    if not roads_path.exists():
        roads_path = processed / "exposed_roads.geojson"
    if roads_path.exists():
        with open(roads_path) as f:
            roads_fc = json.load(f)
        for feat in roads_fc.get("features", []):
            feat.setdefault("properties", {})["layer"] = "road"
            out["features"].append(feat)

    comm_path = run_dir / "exposed_communities.geojson"
    if not comm_path.exists():
        comm_path = processed / "exposed_communities.geojson"
    if comm_path.exists():
        with open(comm_path, encoding="utf-8") as f:
            comm_fc = json.load(f)
        for feat in comm_fc.get("features", []):
            feat.setdefault("properties", {})["layer"] = "community"
            out["features"].append(feat)

    return out


@router.get("/impact")
async def get_impact(
    scenario: str = Query("baseline", description="Scenario key or 'baseline'"),
    threshold: float = Query(0.45, description="Risk threshold for edge blocking"),
    run: str = Query("latest"),
):
    """
    Village isolation impact for a given scenario and threshold.

    Scenarios:
      baseline — no edges blocked
      nh6_escarpment_block — block NH-6 escarpment segment manually
      rainfall_replay_june2022 — block edges with June 2022 risk

    Returns impact_summary + village impacts list.
    """
    run_dir = resolve_run(run)

    # Return precomputed impact if scenario is baseline
    if scenario == "baseline":
        impact_path = run_dir / "impact_summary.json"
        if impact_path.exists():
            with open(impact_path) as f:
                return json.load(f)
        return {"error": "No impact data. Run M5 pipeline.", "n_villages_isolated": 0}

    # Dynamic scenario: recompute on request
    import asyncio
    from modules.M5_connectivity_simulation.graph_builder import (
        load_graph, get_village_and_hospital_nodes, compute_baseline_paths,
    )
    from modules.M5_connectivity_simulation.failure_simulator import simulate_deterministic

    try:
        G = load_graph()
    except FileNotFoundError:
        raise HTTPException(503, "Road graph not built. Run M4 pipeline.")

    villages, hospitals = get_village_and_hospital_nodes(G)
    baseline = compute_baseline_paths(G, villages, hospitals)

    # Scenario overrides
    overrides = None
    if scenario == SCENARIO_NH6_BLOCK:
        # Block the most critical spine segment (seg_ids 0–4 in synthetic network)
        overrides = [1000, 1001, 1002]

    result = simulate_deterministic(
        G=G, segments_risk_gdf=None,
        baseline=baseline, hospital_nodes=hospitals,
        tau_alert=threshold,
        scenario_overrides=overrides,
    )
    return {
        "scenario": scenario,
        "threshold": threshold,
        **result["summary"],
        "village_impacts": result["village_impacts"][:50],  # cap for API response size
    }
