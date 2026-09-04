"""GET /confidence-map — Serve M3 decision confidence GeoJSON"""
from fastapi import APIRouter
from loguru import logger

router = APIRouter(prefix="/confidence-map", tags=["Confidence"])

@router.get("/")
async def get_confidence_map():
    """Return Decision Confidence scores GeoJSON."""
    logger.info("[API] GET /confidence-map")
    raise NotImplementedError("Confidence map endpoint not yet implemented")
