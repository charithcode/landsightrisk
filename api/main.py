"""
main.py — LANDSIGHT FastAPI Application
========================================
Entry point for the LANDSIGHT backend API.

Endpoints:
  GET  /risk-map              → M2 risk scores GeoJSON
  GET  /confidence-map        → M3 confidence layer GeoJSON
  GET  /road-exposure         → M4 road vulnerability GeoJSON
  GET  /connectivity-impact   → M5 isolation analysis
  GET  /criticality           → M6 ranked corridors
  GET  /action-recommendations → M7 tiered action plan
  POST /report                → M8 submit field report
  GET  /risk-trajectory       → M9 time-series risk evolution
  GET  /cascading-flags       → M10 compound hazard alerts

Run with:
  uvicorn api.main:app --reload --host 0.0.0.0 --port 8000
"""

import json
import os
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from loguru import logger

from api.routers import risk, confidence, roads, connectivity, criticality, actions, reports, trajectory


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup and shutdown events."""
    logger.info("🏔️ LANDSIGHT API starting up")
    # TODO: Start M9 scheduler on startup
    # from modules.M9_live_risk_trajectory.pipeline_scheduler import start_scheduler
    # scheduler = start_scheduler()
    yield
    logger.info("LANDSIGHT API shutting down")
    # TODO: scheduler.shutdown()


app = FastAPI(
    title="LANDSIGHT API",
    description="AI-Powered Landslide Connectivity & Response Intelligence — SIH 2026",
    version="0.1.0",
    lifespan=lifespan,
)

# Allow dashboard (React dev server) to call API
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register routers
app.include_router(risk.router)
app.include_router(confidence.router)
app.include_router(roads.router)
app.include_router(connectivity.router)
app.include_router(criticality.router)
app.include_router(actions.router)
app.include_router(reports.router)
app.include_router(trajectory.router)


@app.get("/", tags=["Health"])
async def root():
    return {
        "system": "LANDSIGHT",
        "status": "operational",
        "version": "0.1.0",
        "tagline": "PREDICT → VERIFY → ANTICIPATE → PRIORITIZE → ACT",
    }


@app.get("/health", tags=["Health"])
async def health():
    return {"status": "ok"}
