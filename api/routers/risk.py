"""risk.py — Risk map router (includes confidence inline)"""
import json
from pathlib import Path
from typing import Optional
from fastapi import APIRouter, Query, HTTPException
from config.aoi import DATA_RUNS, DATA_PROCESSED
from api.run_resolver import resolve_run

router = APIRouter(prefix="/risk", tags=["Risk"])


@router.get("/map")
async def get_risk_map(
    run: str = Query("latest", description="Run ID or 'latest'"),
    tier: Optional[str] = Query(None, description="Filter tier: watch|alert|respond"),
    include_confidence: bool = Query(True, description="Include DQ/F/S confidence axes"),
):
    """
    GeoJSON risk cell layer with calibrated p, tier, and confidence axes.
    confidence = p · (DQ · F).  All fields are precomputed — no runtime ML.
    """
    run_dir = resolve_run(run)

    # Try confidence-enriched parquet first
    cells_path = run_dir / "cells.geojson"
    if cells_path.exists():
        with open(cells_path) as f:
            fc = json.load(f)
        if tier:
            fc["features"] = [
                feat for feat in fc.get("features", [])
                if feat.get("properties", {}).get("risk_tier") == tier
            ]
        return fc

    raise HTTPException(404, f"No risk data for run {run}. Run M2/predict.py.")


@router.get("/cells/{cell_id}")
async def get_cell_detail(cell_id: str, run: str = Query("latest")):
    """Full feature + prediction + confidence detail for a single cell."""
    run_dir = resolve_run(run)
    full_path = run_dir / "cells_full.parquet"
    if not full_path.exists():
        raise HTTPException(404, "Full cell data not available for this run.")
    import pandas as pd
    df = pd.read_parquet(str(full_path))
    row = df[df["cell_id"].astype(str) == str(cell_id)]
    if row.empty:
        raise HTTPException(404, f"Cell {cell_id} not found in run {run}")
    return row.iloc[0].to_dict()


@router.get("/bounds")
async def get_risk_bounds():
    """
    Return AOI raster corner coordinates in WGS84 for MapLibre image source.
    Format: [top-left, top-right, bottom-right, bottom-left]
    """
    from config.aoi import AOI_BBOX_WGS84
    minx, miny, maxx, maxy = AOI_BBOX_WGS84
    return {
        "bbox": [minx, miny, maxx, maxy],
        "coordinates": [
            [minx, maxy],  # top-left
            [maxx, maxy],  # top-right
            [maxx, miny],  # bottom-right
            [minx, miny],  # bottom-left
        ],
    }


@router.get("/raster")
async def get_risk_raster(
    layer: str = Query("risk", description="'risk' or 'confidence'"),
    run: str = Query("latest"),
):
    """
    Serve a wall-to-wall colorized RGBA PNG representing all 588,952 cells.
    Allows high-performance map rendering without browser GeoJSON overhead.
    """
    import io
    from fastapi.responses import Response
    import numpy as np
    from PIL import Image

    run_dir = resolve_run(run)
    tif_path = run_dir / "risk_surface_100m.tif"
    if not tif_path.exists():
        tif_path = Path(DATA_PROCESSED) / "risk_surface_100m.tif"
    if not tif_path.exists():
        raise HTTPException(404, "Risk surface raster not found for run")

    import rasterio
    with rasterio.open(str(tif_path)) as src:
        band_idx = 1 if layer == "risk" else 2
        arr = src.read(band_idx)

    # arr is ny x nx float32
    ny, nx = arr.shape
    rgba = np.zeros((ny, nx, 4), dtype=np.uint8)

    arr = np.nan_to_num(arr, nan=0.0)

    if layer == "risk":
        # Colors:
        # < 0.05: transparent
        # 0.05 - 0.6: blue/slate (watch)
        # 0.6 - 0.8: orange (alert)
        # >= 0.8: red (respond)
        mask_watch = (arr >= 0.05) & (arr < 0.6)
        rgba[mask_watch, 0] = 59    # R
        rgba[mask_watch, 1] = 130   # G
        rgba[mask_watch, 2] = 246   # B
        rgba[mask_watch, 3] = 90    # A

        mask_alert = (arr >= 0.6) & (arr < 0.8)
        rgba[mask_alert, 0] = 249
        rgba[mask_alert, 1] = 115
        rgba[mask_alert, 2] = 22
        rgba[mask_alert, 3] = 180

        mask_respond = (arr >= 0.8)
        rgba[mask_respond, 0] = 239
        rgba[mask_respond, 1] = 68
        rgba[mask_respond, 2] = 68
        rgba[mask_respond, 3] = 220
    else:
        # Confidence colormap (teal/emerald)
        mask_low = (arr >= 0.05) & (arr < 0.3)
        rgba[mask_low, 0] = 30
        rgba[mask_low, 1] = 64
        rgba[mask_low, 2] = 175
        rgba[mask_low, 3] = 80

        mask_med = (arr >= 0.3) & (arr < 0.6)
        rgba[mask_med, 0] = 20
        rgba[mask_med, 1] = 184
        rgba[mask_med, 2] = 166
        rgba[mask_med, 3] = 150

        mask_high = (arr >= 0.6)
        rgba[mask_high, 0] = 16
        rgba[mask_high, 1] = 185
        rgba[mask_high, 2] = 129
        rgba[mask_high, 3] = 200

    img = Image.fromarray(rgba, mode="RGBA")
    buf = io.BytesIO()
    img.save(buf, format="PNG", optimize=True)
    return Response(content=buf.getvalue(), media_type="image/png")

