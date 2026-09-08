"""
config/aoi.py — LANDSIGHT Single Source of Truth
==================================================
All AOI bounds, CRS, grid parameters, speed classes, criticality weights,
and decision thresholds are defined HERE and imported everywhere else.
Wrong CRS handling is the #1 silent killer of GIS pipelines.

AOI: Guwahati–Shillong NH-6 corridor
      Kamrup Metropolitan ∪ Ri-Bhoi ∪ East Khasi Hills
      ~70 × 80 km  ·  100 m grid  ·  EPSG:32646 (UTM 46N)
"""

from __future__ import annotations
import os

# ── CRS ──────────────────────────────────────────────────────────────────────
CRS_GEOGRAPHIC = "EPSG:4326"   # WGS-84 lat/lon — input data, API output
CRS_PROJECTED  = "EPSG:32646"  # UTM Zone 46N — all analysis, distances in metres

# ── AOI bounding box (WGS-84 for data downloads) ─────────────────────────────
AOI_BOUNDS_WGS84 = {
    "lon_min": 91.40,
    "lat_min": 25.55,
    "lon_max": 92.20,
    "lat_max": 26.20,
}

# AOI as (west, south, east, north) tuple for rasterio / osmnx
AOI_BBOX_WGS84 = (
    AOI_BOUNDS_WGS84["lon_min"],
    AOI_BOUNDS_WGS84["lat_min"],
    AOI_BOUNDS_WGS84["lon_max"],
    AOI_BOUNDS_WGS84["lat_max"],
)

# Hub cities used for connectivity reference points
AOI_HUBS = {
    "guwahati": {"lat": 26.1445, "lon": 91.7362, "name": "Guwahati"},
    "shillong": {"lat": 25.5788, "lon": 91.8933, "name": "Shillong"},
}

# ── Grid ─────────────────────────────────────────────────────────────────────
GRID_CELL_SIZE_M = 100          # 100-metre analysis grid
DEM_NATIVE_RES_M = 30           # Copernicus GLO-30

# ── File paths (relative to project root) ─────────────────────────────────────
DATA_RAW         = "data/raw"
DATA_PROCESSED   = "data/processed"
DATA_RUNS        = "data/runs"
DATA_REPORTS     = "data/reports"
SAVED_MODELS_DIR = "modules/M2_risk_model/saved_models"

# Key input files
DEM_RAW_PATH       = os.path.join(DATA_RAW, "dem", "dem_aoi.tif")
RAINFALL_DIR       = os.path.join(DATA_RAW, "rainfall")
INVENTORY_DIR      = os.path.join(DATA_RAW, "historical_landslides")
OSM_PBF_PATH       = os.path.join(DATA_RAW, "road_network", "ne_india.osm.pbf")
VILLAGES_RAW_PATH  = os.path.join(DATA_RAW, "village_hospitals", "villages.geojson")
HOSPITALS_RAW_PATH = os.path.join(DATA_RAW, "village_hospitals", "hospitals.geojson")

# Key processed artefacts
TRAINING_SAMPLE_PATH = os.path.join(DATA_PROCESSED, "training_sample.parquet")
FEATURE_MATRIX_PATH  = TRAINING_SAMPLE_PATH   # backwards-compatible alias
FULL_GRID_RASTER_PATH = os.path.join(DATA_PROCESSED, "risk_surface_100m.tif")
ROADS_GPKG_PATH      = os.path.join(DATA_PROCESSED, "roads.gpkg")
GRAPH_GPICKLE_PATH   = os.path.join(DATA_PROCESSED, "graph.gpickle")
VILLAGES_SNAPPED     = os.path.join(DATA_PROCESSED, "villages_snapped.gpkg")
HOTSPOTS_GEOJSON     = os.path.join(DATA_PROCESSED, "hotspots.geojson")
REPORTS_GEOJSON      = os.path.join(DATA_REPORTS, "reports.geojson")
REPORTS_DB_PATH      = os.path.join(DATA_REPORTS, "reports.db")

# ── Road speed classes (km/h) — for travel-time weighting ─────────────────────
SPEED_KMH: dict[str, float] = {
    "motorway":       80.0,
    "trunk":          60.0,
    "primary":        45.0,
    "secondary":      35.0,
    "tertiary":       25.0,
    "residential":    20.0,
    "unclassified":   20.0,
    "service":        15.0,
    "track":          10.0,
    "path":            5.0,
    "default":        20.0,   # fallback
}

# Hill-country speed reduction factor (applies where slope > 20° or HAND > 20 m)
HILL_SPEED_FACTOR = 0.8

# Village snap cap: points farther than this from the road graph are flagged
VILLAGE_SNAP_CAP_M = 1500.0

# ── Risk / decision thresholds ─────────────────────────────────────────────────
# These are set by calibrated PR-curve analysis in M2/train.py and persisted
# in saved_models/thresholds.json; defaults here are conservative placeholders
# that will be OVERWRITTEN by train.py output.
TAU_WATCH   = 0.25   # p ≥ τ_watch  → monitor tier
TAU_ALERT   = 0.45   # p ≥ τ_alert  → ready/verify tier
TAU_RESPOND = 0.65   # p ≥ τ_respond → respond tier

CONFIDENCE_THRESHOLD = 0.60   # confidence ≥ this → act vs. verify

# Isolation thresholds (travel-time ratio t1/t0)
ISOLATION_RATIO      = 1.50   # r ≥ 1.5  → isolated
POOR_CONNECT_RATIO   = 1.25   # r ≥ 1.25 → poorly connected
MIN_VILLAGES_CRITICAL = 3      # edge is "critical" if it isolates ≥ N villages

# Road–risk intersection buffer
SEGMENT_BUFFER_M = 50          # 50m buffer for risk→road join (§8)

# ── Criticality weights (§10) ────────────────────────────────────────────────
# Stored here as the single source; also written to criticality_weights.json
# by the criticality formula module for dashboard transparency.
CRITICALITY_WEIGHTS: dict[str, float] = {
    "RISK":    0.35,
    "SERVED":  0.25,
    "DETOUR":  0.20,
    "HOSPDEP": 0.10,
    "TREND":   0.10,
}
assert abs(sum(CRITICALITY_WEIGHTS.values()) - 1.0) < 1e-9, "Weights must sum to 1.0"

TREND_DEFAULT = 0.5   # default TREND before M9 trajectory data exists

# ── Confidence freshness (§7) ─────────────────────────────────────────────────
FRESHNESS_TAU_DAYS = 3.0        # exponential decay time constant
FRESHNESS_FRESH_HOURS = 24.0    # ≤ this → F = 1.0

# ── Corroboration (§12) ──────────────────────────────────────────────────────
CORROBORATION_RADIUS_M = 500.0
CORROBORATION_WINDOW_H = 12.0
CORROBORATION_MIN_COUNT = 2

# ── Negative sample buffer (§5) ──────────────────────────────────────────────
NEGATIVE_BUFFER_M = 2000.0     # 2 km buffer around positive cells

# ── Spatial block CV ─────────────────────────────────────────────────────────
CV_N_BLOCKS = 5

# ── IMD rainfall grid resolution ──────────────────────────────────────────────
IMD_RESOLUTION_DEG = 0.25

# ── Rainfall anomaly climatology window (months) ─────────────────────────────
CLIMATOLOGY_START_YEAR = 1990
CLIMATOLOGY_END_YEAR   = 2020

# ── Scenario keys for the demo player ────────────────────────────────────────
SCENARIO_RAINFALL_REPLAY = "rainfall_replay_june2022"
SCENARIO_NH6_BLOCK       = "nh6_escarpment_block"
SCENARIO_RESET           = "reset"
