"""GET /risk-trajectory — Serve M9 time-series risk evolution"""
import json, os
from fastapi import APIRouter
from loguru import logger

router = APIRouter(prefix="/risk-trajectory", tags=["Risk Trajectory"])

@router.get("/")
async def get_risk_trajectory():
    """Return time-series of pipeline run summaries for chart rendering."""
    logger.info("[API] GET /risk-trajectory")
    path = "data/processed/risk_trajectory.json"
    if not os.path.exists(path):
        return []
    with open(path) as f:
        return json.load(f)
