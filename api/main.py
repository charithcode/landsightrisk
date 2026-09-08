"""
api/main.py — LANDSIGHT FastAPI Application
============================================
6 routers (blueprint §14 — consolidated from original 8):
  /risk          — risk map + cell detail (includes confidence inline)
  /connectivity  — exposed roads + village impact (includes road layer)
  /criticality   — ranked segments with component bars
  /actions       — tiered recommendations with evidence chains
  /reports       — POST ingest + GET overlay
  /trajectory    — run comparison + emerging hotspots

REMOVED:
  /confidence — merged into /risk response
  /roads      — merged into /connectivity response

All endpoints are READ-ONLY artifact servers (no runtime ML computation).
The ML pipeline is run offline via:
  python -m modules.M2_risk_model.train --synthetic
  python -m modules.M2_risk_model.predict --synthetic

CORS: allows all origins in dev (configure for production).
"""

import asyncio
import json
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from loguru import logger

from api.routers import risk, connectivity, criticality, actions, reports, trajectory, locations
from api.run_resolver import get_latest_run_id, resolve_run
from config.aoi import DATA_RUNS, SAVED_MODELS_DIR


# ── App state ─────────────────────────────────────────────────────────────────

class AppState:
    model_meta: dict = {}
    latest_run_id: str = "none"
    last_run_ts: str = "never"
    is_synthetic: bool = True
    monitoring_status: str = "SOURCE_UNAVAILABLE"  # machine-readable state
    last_status_check: str = "never"


state = AppState()

_HOT_RELOAD_INTERVAL_S = 60   # seconds between latest-run pointer re-checks


def _compute_monitoring_status(rf_meta: dict | None) -> str:
    """
    Derive machine-readable monitoring status from rainfall metadata.

    CURRENT          — rainfall data ≤ 3h old
    DATA_AGING       — 3h – 24h
    SOURCE_UNAVAILABLE — > 24h or no meta
    UPDATE_FAILED    — a monitoring update attempt failed (set externally)
    """
    if not rf_meta:
        return "SOURCE_UNAVAILABLE"
    last_ts_str = rf_meta.get("last_ingest_ts")
    if not last_ts_str:
        return "SOURCE_UNAVAILABLE"
    if rf_meta.get("synthetic", True):
        return "SOURCE_UNAVAILABLE"   # synthetic data ≠ live monitoring
    try:
        last_ts = datetime.fromisoformat(last_ts_str.replace("Z", "+00:00"))
        age_h = (datetime.now(timezone.utc) - last_ts).total_seconds() / 3600
        if age_h <= 3:
            return "CURRENT"
        if age_h <= 24:
            return "DATA_AGING"
        return "SOURCE_UNAVAILABLE"
    except Exception:
        return "SOURCE_UNAVAILABLE"


async def _hot_reload_state():
    """Background task: re-read latest_run.json every 60 s without restart."""
    while True:
        await asyncio.sleep(_HOT_RELOAD_INTERVAL_S)
        try:
            new_run_id = get_latest_run_id()
            if new_run_id != state.latest_run_id:
                logger.info(f"[API] Hot-reload: new run detected: {new_run_id}")
                state.latest_run_id = new_run_id

            # Refresh rainfall freshness
            rf_meta_path = Path("data/processed/rainfall_meta.json")
            rf_meta = None
            if rf_meta_path.exists():
                with open(rf_meta_path) as f:
                    rf_meta = json.load(f)
            state.monitoring_status = _compute_monitoring_status(rf_meta)
            state.last_status_check = datetime.utcnow().isoformat() + "Z"
        except Exception as e:
            logger.warning(f"[API] Hot-reload error: {e}")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Load model metadata and latest run pointer on startup; start hot-reload task."""
    logger.info("[API] LANDSIGHT API starting up")

    # Load model meta
    meta_path = Path(SAVED_MODELS_DIR) / "meta.json"
    if meta_path.exists():
        with open(meta_path) as f:
            state.model_meta = json.load(f)
        state.is_synthetic = state.model_meta.get("is_synthetic_data", True)
        logger.info(f"[API] Model meta loaded — synthetic={state.is_synthetic}")
    else:
        logger.warning("[API] No model meta found. Run M2/train.py first.")
        state.model_meta = {"model_type": "none", "train_date": "never"}

    # Load latest run pointer (using safe resolver)
    state.latest_run_id = get_latest_run_id()
    logger.info(f"[API] Latest run: {state.latest_run_id}")

    # Initial monitoring status from rainfall meta
    rf_meta_path = Path("data/processed/rainfall_meta.json")
    rf_meta = None
    if rf_meta_path.exists():
        with open(rf_meta_path) as f:
            rf_meta = json.load(f)
    state.monitoring_status = _compute_monitoring_status(rf_meta)
    state.last_status_check = datetime.utcnow().isoformat() + "Z"

    # Start background hot-reload task
    task = asyncio.create_task(_hot_reload_state())

    yield

    task.cancel()
    logger.info("[API] LANDSIGHT API shutdown")


# ── App definition ────────────────────────────────────────────────────────────

app = FastAPI(
    title="LANDSIGHT — Landslide Connectivity Intelligence",
    description=(
        "Decision-support API for the Guwahati–Shillong NH-6 corridor. "
        "Model estimates rainfall-conditioned landslide susceptibility; "
        "does NOT predict individual events. All outputs require human authorisation."
    ),
    version="1.0.0-mvp",
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
)

# CORS — allow dev origins; restrict in production
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)

# ── Routers ───────────────────────────────────────────────────────────────────
app.include_router(risk.router)
app.include_router(connectivity.router)
app.include_router(criticality.router)
app.include_router(actions.router)
app.include_router(reports.router)
app.include_router(trajectory.router)
app.include_router(locations.router)


# ── Health endpoint ───────────────────────────────────────────────────────────

@app.get("/health", tags=["System"])
async def health():
    """
    System health check.
    Returns model version, data staleness, run status, and machine-readable
    monitoring_status (CURRENT | DATA_AGING | SOURCE_UNAVAILABLE | UPDATE_FAILED).
    """
    # Always re-read freshness on /health so it doesn't stale between hot-reloads
    rf_meta_path = Path("data/processed/rainfall_meta.json")
    freshness_info = {}
    rf_meta = None
    if rf_meta_path.exists():
        with open(rf_meta_path) as f:
            rf_meta = json.load(f)
        last_ts = rf_meta.get("last_ingest_ts")
        freshness_info = {
            "last_rainfall_ingest": last_ts,
            "synthetic": rf_meta.get("synthetic", True),
        }

    # Also refresh latest run id live (not just from hot-reload cache)
    live_run_id = get_latest_run_id()
    if live_run_id != state.latest_run_id:
        state.latest_run_id = live_run_id

    live_monitoring_status = _compute_monitoring_status(rf_meta)

    return {
        "status":              "ok",
        "model_type":          state.model_meta.get("model_type", "none"),
        "model_trained":       state.model_meta.get("train_date", "never"),
        "latest_run_id":       live_run_id,
        "is_synthetic":        state.is_synthetic,
        "monitoring_status":   live_monitoring_status,
        "monitoring_label": (
            "Continuous monitoring: READY — awaiting live data feed"
            if live_monitoring_status == "SOURCE_UNAVAILABLE"
            else f"Monitoring: {live_monitoring_status}"
        ),
        "disclaimer": (
            "Model estimates rainfall-conditioned susceptibility — "
            "not individual event prediction. "
            "All recommendations require human authorisation."
        ),
        "rainfall":            freshness_info,
        "server_time_utc":     datetime.utcnow().isoformat() + "Z",
        "last_status_check":   state.last_status_check,
    }


@app.get("/", tags=["System"])
async def root():
    return {
        "app":     "LANDSIGHT",
        "version": "1.0.0-mvp",
        "docs":    "/docs",
        "health":  "/health",
    }
