"""GET /risk-map — Serve M2 risk scores GeoJSON"""
import json
from fastapi import APIRouter
from loguru import logger

router = APIRouter(prefix="/risk-map", tags=["Risk Model"])

@router.get("/")
async def get_risk_map():
    """Return landslide risk scores GeoJSON for the target district."""
    logger.info("[API] GET /risk-map")
    # TODO: Load data/processed/risk_scores.geojson and return
    raise NotImplementedError("Risk map endpoint not yet implemented")
