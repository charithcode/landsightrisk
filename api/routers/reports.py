"""reports.py — Field report ingest + overlay router"""
import json
from pathlib import Path
from datetime import datetime
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from typing import Optional
from config.aoi import REPORTS_GEOJSON

router = APIRouter(prefix="/reports", tags=["Reports"])


class ReportIn(BaseModel):
    lon:           float
    lat:           float
    reporter_type: str = Field(..., description="official_agency|trained_volunteer|anonymous_citizen")
    report_type:   str = Field(..., description="road_blocked|bridge_damaged|landslide_active|etc.")
    description:   Optional[str] = None
    gps_accuracy_m: Optional[float] = None
    timestamp_utc:  str = Field(default_factory=lambda: datetime.utcnow().isoformat())
    report_id:      Optional[str] = None


@router.post("")
async def ingest_report(report: ReportIn):
    """
    Ingest a field report. Validates GPS against AOI, trust-scores,
    checks corroboration, and persists to SQLite.
    Trust score does NOT modify p — only updates stability overlay S.
    """
    from modules.M8_trust_weighted_reports.report_ingestion_api import validate_and_ingest
    result = validate_and_ingest(report.model_dump())
    if not result.get("ingested"):
        raise HTTPException(400, result.get("error", "Ingestion failed"))
    return result


@router.get("")
async def get_reports():
    """GeoJSON overlay of recent field reports (latest 500, color-coded by trust)."""
    rp = Path(REPORTS_GEOJSON)
    if rp.exists():
        with open(rp) as f:
            return json.load(f)

    # Return demo reports if no real reports yet
    from modules.M8_trust_weighted_reports.report_ingestion_api import load_demo_reports, validate_and_ingest
    demos = load_demo_reports()
    features = []
    for demo in demos:
        r = validate_and_ingest(demo)
        features.append({
            "type": "Feature",
            "geometry": {"type": "Point", "coordinates": [demo["lon"], demo["lat"]]},
            "properties": {
                "report_id":    demo["report_id"],
                "report_type":  demo["report_type"],
                "reporter_type":demo["reporter_type"],
                "description":  demo.get("description"),
                "trust":        r.get("trust", 0),
                "corroborated": r.get("corroborated", False),
            },
        })
    return {"type": "FeatureCollection", "features": features,
            "meta": {"source": "demo", "n": len(features)}}
