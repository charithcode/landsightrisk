"""GET /road-exposure — Serve M4 road vulnerability GeoJSON"""
from fastapi import APIRouter
from loguru import logger

router = APIRouter(prefix="/road-exposure", tags=["Road Exposure"])

@router.get("/")
async def get_road_exposure():
    """Return road vulnerability GeoJSON."""
    logger.info("[API] GET /road-exposure")
    raise NotImplementedError("Road exposure endpoint not yet implemented")
