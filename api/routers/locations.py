"""
locations.py — Multi-AOI Location Selection and Local Risk Query Router
========================================================================
Supports:
  - Hierarchy query (State -> District -> Place)
  - Autocomplete place search
  - Local vicinity risk summary for any selected coordinate
"""

import json
from pathlib import Path
from typing import Optional
from fastapi import APIRouter, Query, HTTPException
from config.locations import (
    LOCATION_CATALOG, SUPPORTED_AOIS,
    search_locations, check_coords_in_aoi,
)
from api.run_resolver import resolve_run

router = APIRouter(prefix="/locations", tags=["Locations"])


@router.get("/hierarchy")
async def get_location_hierarchy():
    """
    Returns the hierarchical list of States, Districts, and Places
    with explicit 'supported' flags.
    """
    return {
        "catalog": LOCATION_CATALOG,
        "active_aois": list(SUPPORTED_AOIS.values()),
        "current_default_aoi": "guwahati_shillong_nh6",
    }


@router.get("/search")
async def search_place(q: str = Query(..., min_length=1, description="Search term")):
    """
    Search places, districts, states by name.
    Returns matched items with lat, lon, display_name, and supported flag.
    """
    results = search_locations(q)
    return {"query": q, "results": results, "count": len(results)}


@router.get("/summary")
async def get_location_summary(
    lat: float = Query(..., description="Latitude"),
    lon: float = Query(..., description="Longitude"),
    name: Optional[str] = Query(None, description="Location name"),
    radius_km: float = Query(5.0, description="Vicinity radius in km"),
):
    """
    Returns the real local landslide indicators for a location coordinate.
    If the coordinates are outside the active AOI, explicitly returns supported=False
    with no fabricated metrics.
    """
    is_in_aoi = check_coords_in_aoi(lon, lat)
    if not is_in_aoi:
        return {
            "name": name or "Selected Point",
            "lat": lat,
            "lon": lon,
            "supported": False,
            "status": "outside_aoi",
            "message": (
                "Location is outside the active analysis AOI (Guwahati–Shillong NH-6 corridor). "
                "Active coverage is currently Kamrup Metropolitan, Ri-Bhoi, and East Khasi Hills."
            ),
            "suggested_aoi": SUPPORTED_AOIS["guwahati_shillong_nh6"],
        }

    run_dir: Optional[Path] = None
    run_id = "none"
    run_timestamp = None
    try:
        run_dir = resolve_run("latest")
        run_id = run_dir.name
        # Extract timestamp from run_meta.json if present
        meta_path = run_dir / "run_meta.json"
        if meta_path.exists():
            with open(meta_path) as f:
                meta = json.load(f)
            run_timestamp = meta.get("timestamp")
    except HTTPException:
        pass

    if run_dir is None or not run_dir.exists():
        return {
            "name": name or "Selected Point",
            "lat": lat,
            "lon": lon,
            "supported": True,
            "status": "no_runs",
            "message": "AOI is supported, but no run outputs are currently loaded.",
        }

    # Measure distance approximately in km: 1 deg lat ~ 111 km, 1 deg lon ~ 100 km
    lat_km = 111.0
    lon_km = 100.0

    # 1. Check exposed communities in vicinity
    nearby_communities = []
    comm_path = run_dir / "exposed_communities.geojson"
    if comm_path.exists():
        try:
            with open(comm_path, encoding="utf-8") as f:
                comm_fc = json.load(f)
            for feat in comm_fc.get("features", []):
                coords = feat.get("geometry", {}).get("coordinates", [])
                if len(coords) == 2:
                    c_lon, c_lat = coords
                    d_km = (((c_lat - lat) * lat_km)**2 + ((c_lon - lon) * lon_km)**2)**0.5
                    if d_km <= radius_km:
                        props = dict(feat.get("properties", {}))
                        props["dist_km"] = round(d_km, 2)
                        nearby_communities.append(props)
        except Exception:
            pass

    # 2. Check exposed roads in vicinity
    nearby_roads = []
    roads_path = run_dir / "exposed_roads.geojson"
    if roads_path.exists():
        try:
            with open(roads_path) as f:
                roads_fc = json.load(f)
            for feat in roads_fc.get("features", []):
                coords = feat.get("geometry", {}).get("coordinates", [])
                if coords:
                    # Check first point of line
                    first_pt = coords[0] if isinstance(coords[0][0], (int, float)) else coords[0][0]
                    r_lon, r_lat = first_pt[0], first_pt[1]
                    d_km = (((r_lat - lat) * lat_km)**2 + ((r_lon - lon) * lon_km)**2)**0.5
                    if d_km <= radius_km:
                        props = dict(feat.get("properties", {}))
                        props["dist_km"] = round(d_km, 2)
                        nearby_roads.append(props)
        except Exception:
            pass

    # 3. Local risk summary
    max_risk = 0.0
    for r in nearby_roads:
        max_risk = max(max_risk, r.get("risk_max", 0.0))

    risk_tier = "none"
    if max_risk >= 0.8:
        risk_tier = "respond"
    elif max_risk >= 0.6:
        risk_tier = "alert"
    elif max_risk >= 0.05:
        risk_tier = "watch"

    return {
        "name": name or "Selected Location",
        "lat": lat,
        "lon": lon,
        "supported": True,
        "status": "active_monitoring",
        "aoi_id": "guwahati_shillong_nh6",
        "aoi_name": "Guwahati–Shillong NH-6 Corridor",
        "radius_km": radius_km,
        "max_risk_in_radius": round(max_risk, 3),
        "local_tier": risk_tier,
        "nearby_exposed_roads_count": len(nearby_roads),
        "nearby_communities_count": len(nearby_communities),
        "nearby_communities": sorted(nearby_communities, key=lambda x: x.get("dist_km", 999))[:5],
        "nearby_roads": sorted(nearby_roads, key=lambda x: -x.get("risk_max", 0))[:5],
        "run_id": run_id,
        "run_timestamp": run_timestamp,
        "monitoring_disclaimer": "Continuous monitoring of rainfall-conditioned landslide susceptibility/risk indicators — NOT an individual-event forecast.",
    }
