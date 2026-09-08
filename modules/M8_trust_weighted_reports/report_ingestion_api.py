"""
report_ingestion_api.py — M8: Trust-Weighted Field Reports
===========================================================
Report ingestion logic (NOT a FastAPI router — that is in api/routers/reports.py).
This module handles validation, trust scoring, persistence, and corroboration.

Functions:
  validate_and_ingest(report_dict) → ingested report with trust score
  check_corroboration(lon, lat, timestamp, db_path) → n_corroborating
  rebuild_reports_geojson() → updates data/reports/reports.geojson

Storage: SQLite (data/reports/reports.db) — simple, zero-config, no server.
PostGIS is P2. SQLite handles < 50k reports easily.
"""

from __future__ import annotations

import json
import math
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Optional

import geopandas as gpd
import pandas as pd
from shapely.geometry import Point
from loguru import logger

from config.aoi import (
    AOI_BBOX_WGS84, REPORTS_DB_PATH, REPORTS_GEOJSON,
    CORROBORATION_RADIUS_M, CORROBORATION_WINDOW_H, CORROBORATION_MIN_COUNT,
    DATA_REPORTS,
)
from modules.M8_trust_weighted_reports.trust_scorer import compute_trust, apply_corroboration_bonus


# ── DB setup ──────────────────────────────────────────────────────────────────

CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS reports (
    report_id     TEXT PRIMARY KEY,
    timestamp_utc TEXT NOT NULL,
    lon           REAL NOT NULL,
    lat           REAL NOT NULL,
    reporter_type TEXT NOT NULL,
    report_type   TEXT NOT NULL,
    description   TEXT,
    gps_accuracy_m REAL,
    trust         REAL,
    pedigree      REAL,
    accuracy_score REAL,
    freshness     REAL,
    sanity        REAL,
    corroborated  INTEGER DEFAULT 0,
    aoi_valid     INTEGER DEFAULT 1,
    created_at    TEXT DEFAULT CURRENT_TIMESTAMP
);
"""

def _get_db(db_path: str = REPORTS_DB_PATH) -> sqlite3.Connection:
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.execute(CREATE_TABLE_SQL)
    conn.commit()
    return conn


# ── Corroboration check ───────────────────────────────────────────────────────

def _haversine_m(lon1: float, lat1: float, lon2: float, lat2: float) -> float:
    """Fast Haversine distance in metres."""
    R = 6_371_000.0
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi  = math.radians(lat2 - lat1)
    dlam  = math.radians(lon2 - lon1)
    a = math.sin(dphi/2)**2 + math.cos(phi1)*math.cos(phi2)*math.sin(dlam/2)**2
    return 2 * R * math.asin(math.sqrt(a))


def check_corroboration(
    lon: float,
    lat: float,
    timestamp: datetime,
    db_path: str = REPORTS_DB_PATH,
    radius_m: float = CORROBORATION_RADIUS_M,
    window_h: float = CORROBORATION_WINDOW_H,
) -> int:
    """
    Count independent reports within radius_m and window_h of the given point/time.

    Returns:
        Integer count of nearby independent reports (excludes exact duplicates).
    """
    if not Path(db_path).exists():
        return 0

    cutoff = (timestamp - pd.Timedelta(hours=window_h)).isoformat()
    conn = _get_db(db_path)
    cursor = conn.execute(
        "SELECT lon, lat FROM reports WHERE timestamp_utc >= ? AND aoi_valid = 1",
        (cutoff,)
    )
    rows = cursor.fetchall()
    conn.close()

    count = 0
    for row_lon, row_lat in rows:
        if _haversine_m(lon, lat, row_lon, row_lat) <= radius_m:
            count += 1
    return count


# ── Validation ────────────────────────────────────────────────────────────────

REQUIRED_FIELDS = {"lon", "lat", "reporter_type", "report_type", "timestamp_utc"}

def validate_report(report: dict) -> tuple[bool, str]:
    """
    Validate incoming report dict.

    Returns (is_valid, error_message).
    """
    missing = REQUIRED_FIELDS - set(report.keys())
    if missing:
        return False, f"Missing required fields: {missing}"

    try:
        lon = float(report["lon"])
        lat = float(report["lat"])
    except (ValueError, TypeError):
        return False, "lon/lat must be numeric"

    if not (-180 <= lon <= 180 and -90 <= lat <= 90):
        return False, f"lon/lat out of range: ({lon}, {lat})"

    buf = 0.014   # ~1.5km in degrees
    if not (AOI_BBOX_WGS84[0]-buf <= lon <= AOI_BBOX_WGS84[2]+buf and
            AOI_BBOX_WGS84[1]-buf <= lat <= AOI_BBOX_WGS84[3]+buf):
        return False, f"Coordinates outside AOI ± 1.5km: ({lon:.4f}, {lat:.4f})"

    try:
        datetime.fromisoformat(report["timestamp_utc"].replace("Z", "+00:00"))
    except (ValueError, AttributeError):
        return False, f"Invalid timestamp_utc format: {report.get('timestamp_utc')}"

    return True, ""


# ── Ingest ────────────────────────────────────────────────────────────────────

def validate_and_ingest(
    report: dict,
    db_path: str = REPORTS_DB_PATH,
) -> dict:
    """
    Validate, trust-score, corroboration-check, and persist a field report.

    Args:
        report: dict with keys:
            report_id, lon, lat, reporter_type, report_type,
            timestamp_utc, description (opt), gps_accuracy_m (opt)
        db_path: SQLite database path

    Returns:
        Ingested report dict with trust scores added, or error dict.
    """
    is_valid, error = validate_report(report)
    if not is_valid:
        logger.warning(f"[M8] Report validation failed: {error}")
        return {"error": error, "ingested": False}

    lon = float(report["lon"])
    lat = float(report["lat"])
    ts_str = report["timestamp_utc"].replace("Z", "+00:00")
    timestamp = datetime.fromisoformat(ts_str).replace(tzinfo=None)
    gps_acc = float(report["gps_accuracy_m"]) if report.get("gps_accuracy_m") is not None else None

    # Trust scoring
    trust_result = compute_trust(
        reporter_type=report["reporter_type"],
        gps_accuracy_m=gps_acc,
        report_timestamp=timestamp,
        report_type=report["report_type"],
        lon=lon,
        lat=lat,
    )

    if not trust_result["aoi_valid"]:
        return {"error": "Coordinates outside AOI", "ingested": False}

    # Corroboration check
    n_corr = check_corroboration(lon, lat, timestamp, db_path)
    trust_final = apply_corroboration_bonus(trust_result, n_corroborating=n_corr)

    report_id = report.get("report_id") or f"rpt_{int(datetime.utcnow().timestamp())}"

    # Persist to SQLite
    conn = _get_db(db_path)
    try:
        conn.execute("""
            INSERT OR REPLACE INTO reports
              (report_id, timestamp_utc, lon, lat, reporter_type, report_type,
               description, gps_accuracy_m, trust, pedigree, accuracy_score,
               freshness, sanity, corroborated, aoi_valid)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        """, (
            report_id, ts_str, lon, lat,
            report["reporter_type"], report["report_type"],
            report.get("description", ""),
            gps_acc,
            trust_final["trust"],
            trust_final["pedigree"],
            trust_final["accuracy"],
            trust_final["freshness"],
            trust_final["sanity"],
            int(trust_final["corroborated"]),
            1,
        ))
        conn.commit()
        logger.info(f"[M8] Ingested report {report_id}: trust={trust_final['trust']:.3f}, "
                    f"corroborated={trust_final['corroborated']}")
    finally:
        conn.close()

    # Rebuild GeoJSON overlay
    try:
        rebuild_reports_geojson(db_path)
    except Exception as e:
        logger.warning(f"[M8] GeoJSON rebuild failed: {e}")

    return {
        "ingested":     True,
        "report_id":    report_id,
        "trust":        trust_final["trust"],
        "pedigree":     trust_final["pedigree"],
        "accuracy":     trust_final["accuracy"],
        "freshness":    trust_final["freshness"],
        "sanity":       trust_final["sanity"],
        "corroborated": trust_final["corroborated"],
        "n_corroborating": n_corr,
    }


# ── GeoJSON overlay rebuild ───────────────────────────────────────────────────

def rebuild_reports_geojson(db_path: str = REPORTS_DB_PATH) -> None:
    """
    Rebuild data/reports/reports.geojson from SQLite.
    Called on every ingest.
    """
    if not Path(db_path).exists():
        logger.warning("[M8] No reports DB — skipping GeoJSON rebuild")
        return

    conn = _get_db(db_path)
    df = pd.read_sql_query("""
        SELECT report_id, timestamp_utc, lon, lat, reporter_type, report_type,
               description, trust, corroborated
        FROM reports
        WHERE aoi_valid = 1
        ORDER BY timestamp_utc DESC
        LIMIT 500
    """, conn)
    conn.close()

    if df.empty:
        return

    gdf = gpd.GeoDataFrame(
        df,
        geometry=[Point(r.lon, r.lat) for _, r in df.iterrows()],
        crs="EPSG:4326",
    )
    out = Path(REPORTS_GEOJSON)
    out.parent.mkdir(parents=True, exist_ok=True)
    gdf.to_file(str(out), driver="GeoJSON")
    logger.info(f"[M8] Reports GeoJSON rebuilt: {len(gdf)} records → {out}")


# ── Demo helper ───────────────────────────────────────────────────────────────

def load_demo_reports() -> list[dict]:
    """Return 5 synthetic demo reports for the NH-6 corridor."""
    return [
        {
            "report_id":     "demo_001",
            "lon":           91.85, "lat": 25.88,
            "reporter_type": "trained_volunteer",
            "report_type":   "road_blocked",
            "description":   "Debris flow across NH-6 near Byrnihat",
            "gps_accuracy_m": 15.0,
            "timestamp_utc": "2022-06-17T09:30:00",
        },
        {
            "report_id":     "demo_002",
            "lon":           91.87, "lat": 25.86,
            "reporter_type": "anonymous_citizen",
            "report_type":   "landslide_active",
            "description":   "Large slide visible from road",
            "gps_accuracy_m": 85.0,
            "timestamp_utc": "2022-06-17T10:15:00",
        },
        {
            "report_id":     "demo_003",
            "lon":           91.96, "lat": 25.77,
            "reporter_type": "official_agency",
            "report_type":   "bridge_damaged",
            "description":   "SDRF: bridge abutment cracked, single lane only",
            "gps_accuracy_m": 5.0,
            "timestamp_utc": "2022-06-17T11:00:00",
        },
        {
            "report_id":     "demo_004",
            "lon":           91.75, "lat": 25.99,
            "reporter_type": "trained_volunteer",
            "report_type":   "debris_flow_observed",
            "description":   "Aapda Mitra volunteer: active debris flow on hillslope",
            "gps_accuracy_m": 25.0,
            "timestamp_utc": "2022-06-17T08:45:00",
        },
        {
            "report_id":     "demo_005",
            "lon":           92.02, "lat": 25.68,
            "reporter_type": "anonymous_citizen",
            "report_type":   "generic_landslide",
            "description":   "Rocks falling near village",
            "gps_accuracy_m": 350.0,
            "timestamp_utc": "2022-06-17T07:30:00",
        },
    ]


if __name__ == "__main__":
    logger.info("[M8] Ingesting demo reports")
    for demo in load_demo_reports():
        result = validate_and_ingest(demo)
        print(f"  {demo['report_id']}: trust={result.get('trust', 0):.3f}, "
              f"corroborated={result.get('corroborated', False)}")
