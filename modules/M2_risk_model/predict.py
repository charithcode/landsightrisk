"""
predict.py — M2: Landslide Risk Model
=======================================
Load a trained model and run inference on a live feature matrix.

Output:
  - GeoJSON: data/processed/risk_scores.geojson
    Each feature has: cell_id, geometry, risk_score (0.0–1.0),
    risk_class (LOW / MEDIUM / HIGH)
"""

import os
import joblib
import pandas as pd
import geopandas as gpd
from loguru import logger
from dotenv import load_dotenv

load_dotenv()

MODEL_PATH = os.getenv("RISK_MODEL_PATH", "modules/M2_risk_model/saved_models/rf_model.joblib")
THRESHOLD_HIGH = float(os.getenv("RISK_THRESHOLD_HIGH", 0.75))
THRESHOLD_MED = float(os.getenv("RISK_THRESHOLD_MEDIUM", 0.45))

FEATURE_COLS = [
    "rainfall_72h_mm", "soil_moisture_pct", "slope_deg", "aspect_deg",
    "twi", "curvature", "elevation_m", "lulc_class",
    "dist_to_stream_m", "historical_landslide_density",
]


def load_model(path: str = MODEL_PATH):
    """Load trained model from disk."""
    logger.info(f"[M2] Loading model from {path}")
    return joblib.load(path)


def classify_risk(score: float) -> str:
    """Convert continuous risk score to categorical class."""
    if score >= THRESHOLD_HIGH:
        return "HIGH"
    elif score >= THRESHOLD_MED:
        return "MEDIUM"
    return "LOW"


def run_inference(feature_gdf: gpd.GeoDataFrame, model=None) -> gpd.GeoDataFrame:
    """
    Run landslide risk prediction on a feature GeoDataFrame.

    Args:
        feature_gdf: GeoDataFrame from M1 feature engineering
        model: Loaded sklearn model (loads from disk if None)

    Returns:
        GeoDataFrame with added columns: risk_score, risk_class
    """
    if model is None:
        model = load_model()

    logger.info(f"[M2] Running inference on {len(feature_gdf)} grid cells")
    X = feature_gdf[FEATURE_COLS]
    probas = model.predict_proba(X)[:, 1]  # Probability of class=1 (landslide)

    result = feature_gdf.copy()
    result["risk_score"] = probas
    result["risk_class"] = result["risk_score"].apply(classify_risk)

    # Save to geojson
    output_path = "data/processed/risk_scores.geojson"
    result.to_file(output_path, driver="GeoJSON")
    logger.info(f"[M2] Risk scores saved to {output_path}")

    return result


if __name__ == "__main__":
    # Quick test with dummy data
    logger.warning("[M2] Running in test mode — no real feature matrix loaded")
