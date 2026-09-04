"""
train.py — M2: Landslide Risk Model
=====================================
Train a Random Forest classifier on historical landslide inventory
matched to environmental feature vectors.

Features used:
  rainfall_72h_mm, soil_moisture_pct, slope_deg, aspect_deg,
  twi, curvature, elevation_m, lulc_class,
  dist_to_stream_m, historical_landslide_density

Label:
  landslide_occurred (0/1) — from Bhukosh / NGDR inventory

Evaluation:
  - Spatial cross-validation (block CV, not random split — avoids spatial autocorrelation)
  - Metrics: ROC-AUC, PR-AUC, F1
"""

import joblib
import pandas as pd
from sklearn.ensemble import RandomForestClassifier
from sklearn.model_selection import cross_val_score
from sklearn.metrics import classification_report, roc_auc_score
from loguru import logger

FEATURE_COLS = [
    "rainfall_72h_mm",
    "soil_moisture_pct",
    "slope_deg",
    "aspect_deg",
    "twi",
    "curvature",
    "elevation_m",
    "lulc_class",
    "dist_to_stream_m",
    "historical_landslide_density",
]
LABEL_COL = "landslide_occurred"
MODEL_PATH = "modules/M2_risk_model/saved_models/rf_model.joblib"


def load_training_data(feature_matrix_path: str) -> tuple:
    """
    Load and prepare training data.

    Returns:
        (X: DataFrame, y: Series)
    """
    logger.info(f"[M2] Loading training data from {feature_matrix_path}")
    df = pd.read_csv(feature_matrix_path)
    # TODO: Handle class imbalance (landslides are rare events)
    # TODO: Add spatial block CV splits
    X = df[FEATURE_COLS]
    y = df[LABEL_COL]
    return X, y


def train_random_forest(X: pd.DataFrame, y: pd.Series) -> RandomForestClassifier:
    """
    Train the primary Random Forest classifier.

    Returns:
        Trained RandomForestClassifier
    """
    logger.info("[M2] Training Random Forest model")
    model = RandomForestClassifier(
        n_estimators=200,
        max_depth=12,
        class_weight="balanced",    # Handle class imbalance
        random_state=42,
        n_jobs=-1,
    )
    # TODO: Replace with spatial block cross-validation
    model.fit(X, y)
    return model


def evaluate_model(model, X: pd.DataFrame, y: pd.Series) -> dict:
    """
    Evaluate model performance.

    Returns:
        Dict with auc_roc, classification_report
    """
    logger.info("[M2] Evaluating model")
    y_pred_proba = model.predict_proba(X)[:, 1]
    y_pred = model.predict(X)
    auc = roc_auc_score(y, y_pred_proba)
    report = classification_report(y, y_pred, output_dict=True)
    logger.info(f"[M2] ROC-AUC: {auc:.4f}")
    return {"auc_roc": auc, "report": report}


def save_model(model, path: str = MODEL_PATH) -> None:
    """Save trained model to disk."""
    joblib.dump(model, path)
    logger.info(f"[M2] Model saved to {path}")


def run_training_pipeline(feature_matrix_path: str = "data/processed/feature_matrix.csv"):
    """End-to-end training pipeline."""
    X, y = load_training_data(feature_matrix_path)
    model = train_random_forest(X, y)
    metrics = evaluate_model(model, X, y)
    save_model(model)
    return model, metrics


if __name__ == "__main__":
    model, metrics = run_training_pipeline()
    print(metrics)
