"""GET /connectivity-impact — Serve M5 isolation analysis"""
from fastapi import APIRouter
from loguru import logger

router = APIRouter(prefix="/connectivity-impact", tags=["Connectivity"])

@router.get("/")
async def get_connectivity_impact():
    """Return village isolation analysis from M5."""
    logger.info("[API] GET /connectivity-impact")
    raise NotImplementedError("Connectivity impact endpoint not yet implemented")
