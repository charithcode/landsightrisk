"""GET /criticality — Serve M6 ranked corridors"""
from fastapi import APIRouter
from loguru import logger

router = APIRouter(prefix="/criticality", tags=["Criticality"])

@router.get("/")
async def get_criticality():
    """Return ranked village/corridor criticality scores from M6."""
    logger.info("[API] GET /criticality")
    raise NotImplementedError("Criticality endpoint not yet implemented")
