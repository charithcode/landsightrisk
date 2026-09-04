"""POST /report — Accept M8 field reports"""
from fastapi import APIRouter
from pydantic import BaseModel
from datetime import datetime
from loguru import logger

router = APIRouter(prefix="/report", tags=["Field Reports"])

class ReportPayload(BaseModel):
    reporter_id: str
    lat: float
    lon: float
    description: str
    is_aapda_mitra: bool = False

@router.post("/")
async def submit_report(payload: ReportPayload):
    """Accept, store, and trust-score a citizen/field report."""
    logger.info(f"[API] POST /report from {payload.reporter_id}")
    raise NotImplementedError("Report submission not yet implemented")
