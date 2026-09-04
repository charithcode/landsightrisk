"""
MODULE M2 — Landslide Risk Model (ML)
======================================
Trains and serves a machine learning model to predict landslide
risk probability for each grid cell.

Model: Random Forest (primary) + XGBoost (baseline comparison)
Explainability: SHAP values

Input:
  - data/processed/feature_matrix.csv
  - data/raw/historical_landslides/ (labels)

Output:
  - modules/M2_risk_model/saved_models/rf_model.joblib
  - data/processed/risk_scores.geojson
"""
