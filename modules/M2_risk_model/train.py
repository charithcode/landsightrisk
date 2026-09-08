"""
train.py — M2: Landslide Risk Model
=====================================
Train a calibrated XGBoost classifier on the time-anchored feature matrix.

Scientific design (per blueprint §5):

FEATURES (no proximity leakage):
  elevation, slope, aspect_sin, aspect_cos, tpi, tri, hand,
  r03d, r07d, r15d, r30d, rain_anom
  → NO distance-to-nearest-landslide, NO landslide-density features

VALIDATION:
  Primary: Spatial block CV (5 folds by k-means spatial blocks)
           — nearby cells are autocorrelated; random CV is invalid.
  Secondary: Temporal split (events before vs. after median year)
  Report: per-fold PR-AUC mean ± std (headline), ROC-AUC, F1, Brier

TARGET: binary landslide_occurrence — rainfall-conditioned susceptibility.
        This is NOT event forecasting. Say this every time.

CALIBRATION:
  XGBoost raw probabilities are NOT calibrated.
  Isotonic regression on out-of-fold predictions → calibrated P(event).
  Brier score reported before/after calibration.

THRESHOLD SELECTION:
  Choose τ_alert and τ_respond from PR curve under operational constraint:
    τ_alert  = highest recall such that PPV ≥ 0.60 (alert tier)
    τ_respond = highest recall such that PPV ≥ 0.75 (respond tier)
  Both thresholds persisted in saved_models/thresholds.json.

ARTIFACTS (saved_models/):
  model.json          — XGBoost native format
  calibrator.pkl      — IsotonicRegression
  thresholds.json     — {tau_watch, tau_alert, tau_respond}
  feature_list.json   — ordered list of feature names
  meta.json           — train date, AOI, CRS, CV metrics, hyperparams, data hashes
  cv_report.json      — per-fold metrics table

Usage:
    python -m modules.M2_risk_model.train --synthetic
    python -m modules.M2_risk_model.train  # real data
"""

from __future__ import annotations

import hashlib
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional

import joblib
import numpy as np
import pandas as pd
from loguru import logger
from sklearn.calibration import CalibratedClassifierCV
from sklearn.isotonic import IsotonicRegression
from sklearn.metrics import (
    average_precision_score, roc_auc_score, f1_score,
    precision_recall_curve, brier_score_loss, classification_report,
)
from sklearn.ensemble import RandomForestClassifier
from sklearn.cluster import KMeans

try:
    import xgboost as xgb
    XGB_AVAILABLE = True
except ImportError:
    XGB_AVAILABLE = False
    logger.warning("[M2] XGBoost not installed; falling back to Random Forest")

from config.aoi import (
    SAVED_MODELS_DIR, FEATURE_MATRIX_PATH, CV_N_BLOCKS,
    TAU_WATCH, TAU_ALERT, TAU_RESPOND, CRS_PROJECTED, AOI_BBOX_WGS84,
)
from modules.M1_data_ingestion.feature_engineer import (
    FEATURE_COLS, LABEL_COL, ALL_COLS,
)


# ── Paths ─────────────────────────────────────────────────────────────────────
MODELS_DIR        = Path(SAVED_MODELS_DIR)
MODEL_PATH        = MODELS_DIR / "model.json"       # XGBoost native
RF_MODEL_PATH     = MODELS_DIR / "rf_model.pkl"     # sanity-check RF
CALIBRATOR_PATH   = MODELS_DIR / "calibrator.pkl"
THRESHOLDS_PATH   = MODELS_DIR / "thresholds.json"
FEATURE_LIST_PATH = MODELS_DIR / "feature_list.json"
META_PATH         = MODELS_DIR / "meta.json"
CV_REPORT_PATH    = MODELS_DIR / "cv_report.json"


# ── Data loading ──────────────────────────────────────────────────────────────

def load_feature_matrix(path: str = FEATURE_MATRIX_PATH) -> pd.DataFrame:
    logger.info(f"[M2] Loading feature matrix from {path}")
    df = pd.read_parquet(path)
    # Safety: confirm no leaking features
    forbidden = {"historical_landslide_density", "dist_to_stream_m",
                 "dist_to_nearest_landslide", "landslide_density"}
    present_forbidden = set(df.columns) & forbidden
    if present_forbidden:
        raise ValueError(
            f"[M2] LEAKAGE DETECTED: forbidden features in matrix: {present_forbidden}. "
            "These proximity features leak under spatial CV. Remove from feature_engineer.py."
        )
    return df


# ── Spatial block CV ──────────────────────────────────────────────────────────

def get_spatial_block_splits(df: pd.DataFrame) -> list[tuple[np.ndarray, np.ndarray]]:
    """
    Leave-one-block-out spatial CV using pre-assigned block_id values.
    Iterates unique block IDs (does not assume they are 0..n-1).
    """
    if "block_id" not in df.columns:
        raise ValueError("[M2] training_sample.parquet is missing block_id — cannot run spatial CV.")
    block_ids = df["block_id"].values
    splits = []
    for bid in sorted(np.unique(block_ids)):
        val_mask = block_ids == bid
        train_mask = ~val_mask
        splits.append((np.where(train_mask)[0], np.where(val_mask)[0]))
    return splits


# ── XGBoost model ────────────────────────────────────────────────────────────

def make_xgb_model(scale_pos_weight: float = 2.0):
    """
    XGBoost binary classifier with conservative hyperparameters.
    scale_pos_weight handles class imbalance (neg:pos ratio).
    Tuning: max ~50 trials (blueprint §5 — more is negative ROI here).
    """
    if not XGB_AVAILABLE:
        return make_rf_model()
    return xgb.XGBClassifier(
        n_estimators=300,
        max_depth=5,
        learning_rate=0.05,
        subsample=0.8,
        colsample_bytree=0.8,
        scale_pos_weight=scale_pos_weight,
        eval_metric="aucpr",
        random_state=42,
        n_jobs=-1,
        verbosity=0,
    )


def make_rf_model():
    return RandomForestClassifier(
        n_estimators=300,
        max_depth=10,
        class_weight="balanced",
        random_state=42,
        n_jobs=-1,
    )


# ── Calibration ───────────────────────────────────────────────────────────────

def calibrate_isotonic(
    y_true: np.ndarray,
    y_proba_oof: np.ndarray,
) -> IsotonicRegression:
    """
    Fit isotonic regression calibrator on out-of-fold (OOF) predictions.
    OOF predictions are unbiased: each cell's score was made by a model
    that never saw that cell.

    Returns fitted IsotonicRegression.
    """
    iso = IsotonicRegression(out_of_bounds="clip")
    iso.fit(y_proba_oof, y_true)
    return iso


def brier_score(y: np.ndarray, p: np.ndarray) -> float:
    return float(brier_score_loss(y, p))


# ── Threshold selection ───────────────────────────────────────────────────────

def select_thresholds(
    y_true: np.ndarray,
    y_prob_calibrated: np.ndarray,
) -> dict[str, float]:
    """
    Select operational thresholds from the PR curve.
    Constraints:
      τ_alert  : highest recall s.t. PPV ≥ 0.60
      τ_respond: highest recall s.t. PPV ≥ 0.75

    Returns:
        {tau_watch, tau_alert, tau_respond}
    """
    precision, recall, thresholds = precision_recall_curve(y_true, y_prob_calibrated)
    # Note: precision_recall_curve returns len(thresholds) = len(precision)-1
    # We work with the inner values
    prec = precision[:-1]
    rec  = recall[:-1]

    def _best_threshold(ppv_min: float, default: float) -> float:
        mask = prec >= ppv_min
        if not mask.any():
            return default
        # Among thresholds with PPV ≥ ppv_min, pick the one with highest recall
        best_idx = np.argmax(rec[mask])
        return float(thresholds[mask][best_idx])

    tau_alert   = _best_threshold(0.60, TAU_ALERT)
    tau_respond = _best_threshold(0.75, TAU_RESPOND)
    tau_watch   = float(thresholds[np.argmax(rec >= 0.85)] if (rec >= 0.85).any() else TAU_WATCH)

    # Ranking cutoffs on the case-control score, not AOI event probabilities.
    tau_alert   = float(np.clip(tau_alert, 0.15, 0.80))
    tau_watch   = float(np.clip(min(tau_watch, tau_alert - 0.05), 0.05, tau_alert - 0.02))
    tau_respond = float(np.clip(max(tau_respond, tau_alert + 0.05), tau_alert + 0.02, 0.95))

    logger.info(f"[M2] Ranking cutoffs → watch={tau_watch:.3f}, "
                f"alert={tau_alert:.3f}, respond={tau_respond:.3f} "
                "(case-control scores; not AOI prevalence-calibrated probabilities)")
    return {
        "tau_watch":   round(tau_watch, 4),
        "tau_alert":   round(tau_alert, 4),
        "tau_respond": round(tau_respond, 4),
        "interpretation": "case_control_ranking_cutoffs",
        "aoi_prevalence_correction": "not_applied",
    }


# ── Evaluation ────────────────────────────────────────────────────────────────

def evaluate_fold(
    y_true: np.ndarray,
    y_prob: np.ndarray,
    tau: float,
) -> dict[str, float]:
    """Compute metrics for one CV fold."""
    y_pred = (y_prob >= tau).astype(int)
    pr_auc = average_precision_score(y_true, y_prob) if y_true.sum() > 0 else 0.0
    roc_auc = roc_auc_score(y_true, y_prob) if y_true.sum() > 0 and (1 - y_true).sum() > 0 else 0.5
    f1 = f1_score(y_true, y_pred, zero_division=0)

    tp = int(((y_pred == 1) & (y_true == 1)).sum())
    fp = int(((y_pred == 1) & (y_true == 0)).sum())
    fn = int(((y_pred == 0) & (y_true == 1)).sum())
    ppv = tp / (tp + fp) if (tp + fp) > 0 else 0.0
    tpr = tp / (tp + fn) if (tp + fn) > 0 else 0.0

    brier = brier_score(y_true, y_prob)

    # Hit-rate concentration: fraction of positives in top 10% of cells by risk
    n_top = max(1, int(0.10 * len(y_prob)))
    top_idx = np.argsort(y_prob)[::-1][:n_top]
    hit_rate_top10 = float(y_true[top_idx].sum() / max(y_true.sum(), 1))

    return {
        "pr_auc":         round(pr_auc, 4),
        "roc_auc":        round(roc_auc, 4),
        "f1":             round(f1, 4),
        "ppv":            round(ppv, 4),
        "tpr":            round(tpr, 4),
        "brier":          round(brier, 4),
        "hit_rate_top10": round(hit_rate_top10, 4),
    }


# ── Main training pipeline ────────────────────────────────────────────────────

def _temporal_holdout(df: pd.DataFrame, X: np.ndarray, y: np.ndarray,
                      scale_pos_weight: float) -> dict:
    """
    Temporal holdout is only reported when positive *event* dates support it.

    Negative date_anchor values are randomly assigned monsoon dates, so they
    are not used as a time axis. Train = earlier positives + all negatives;
    test = later positives + a random negative subset (non-events, not dates).
    """
    result: dict = {"performed": False}
    if "date_anchor" not in df.columns:
        result["reason"] = "No date_anchor column."
        return result

    pos_mask = y == 1
    pos_years = pd.to_datetime(df.loc[pos_mask, "date_anchor"], errors="coerce").dt.year
    if pos_years.dropna().nunique() < 2:
        result["reason"] = "Positive event dates do not span multiple years."
        return result

    split_year = int(pos_years.median())
    pos_train = pos_mask & (pd.to_datetime(df["date_anchor"], errors="coerce").dt.year <= split_year)
    pos_test  = pos_mask & (pd.to_datetime(df["date_anchor"], errors="coerce").dt.year > split_year)
    n_pos_tr, n_pos_te = int(pos_train.sum()), int(pos_test.sum())
    result.update({
        "split_year": split_year,
        "n_pos_train": n_pos_tr,
        "n_pos_test": n_pos_te,
        "date_min": str(pd.to_datetime(df.loc[pos_mask, "date_anchor"], errors="coerce").min().date())
                    if pos_mask.any() else None,
        "date_max": str(pd.to_datetime(df.loc[pos_mask, "date_anchor"], errors="coerce").max().date())
                    if pos_mask.any() else None,
    })

    # Need enough later positives and both classes in test for ROC/PR.
    if n_pos_tr < 15 or n_pos_te < 8:
        result["reason"] = (
            f"Too few positives around split_year={split_year} "
            f"(train={n_pos_tr}, test={n_pos_te}) for a meaningful temporal holdout."
        )
        return result

    rng = np.random.default_rng(42)
    neg_idx = np.where(y == 0)[0]
    n_neg_te = min(len(neg_idx) // 3, max(n_pos_te * 3, 20))
    if n_neg_te < 8:
        result["reason"] = "Too few negatives to form a mixed temporal test set."
        return result
    perm = rng.permutation(neg_idx)
    neg_te, neg_tr = perm[:n_neg_te], perm[n_neg_te:]
    train_idx = np.concatenate([np.where(pos_train)[0], neg_tr])
    test_idx  = np.concatenate([np.where(pos_test)[0], neg_te])
    y_te = y[test_idx]
    if y_te.sum() == 0 or (1 - y_te).sum() == 0:
        result["reason"] = "Temporal test fold would be single-class."
        return result

    m_t = make_xgb_model(scale_pos_weight)
    m_t.fit(X[train_idx], y[train_idx])
    p_te = m_t.predict_proba(X[test_idx])[:, 1]
    result["performed"] = True
    result["test_pr_auc"] = round(float(average_precision_score(y_te, p_te)), 4)
    result["test_roc_auc"] = round(float(roc_auc_score(y_te, p_te)), 4)
    result["test_brier"] = round(float(brier_score_loss(y_te, p_te)), 4)
    result["metric_scope"] = "case_control_sample"
    result["note"] = (
        "Holdout uses later positive event dates vs. sampled non-events. "
        "Not a full-AOI temporal forecast metric."
    )
    logger.info(f"[M2] Temporal holdout PR-AUC={result['test_pr_auc']:.4f} "
                f"ROC-AUC={result['test_roc_auc']:.4f} (case-control only)")
    return result


def run_training_pipeline(
    feature_matrix_path: str = FEATURE_MATRIX_PATH,
    synthetic: bool = False,
    models_dir: Optional[Path | str] = None,
) -> dict:
    """
    Full training pipeline.

    Real mode loads training_sample.parquet only. Synthetic data is generated
    solely when synthetic=True (--synthetic). Never trains on the full AOI grid.

    Returns:
        meta dict with CV metrics and model paths.
    """
    out_dir = Path(models_dir) if models_dir else MODELS_DIR
    out_dir.mkdir(parents=True, exist_ok=True)

    forbidden = {"historical_landslide_density", "dist_to_stream_m",
                 "dist_to_nearest_landslide", "landslide_density",
                 "trust", "report_id", "pedigree"}

    # ── Load data ─────────────────────────────────────────────────────────────
    if synthetic:
        logger.warning("[M2] EXPLICIT synthetic training — not real inventory.")
        from modules.M1_data_ingestion.feature_engineer import _make_synthetic_feature_matrix
        df = _make_synthetic_feature_matrix()
    else:
        path = Path(feature_matrix_path)
        if not path.exists():
            raise FileNotFoundError(
                f"[M2] Real training sample not found: {path}. "
                "Persist data/processed/training_sample.parquet (232 case-control cells) "
                "or pass --synthetic for CI-only synthetic data."
            )
        df = load_feature_matrix(str(path))

    present_forbidden = set(df.columns) & forbidden
    if present_forbidden:
        raise ValueError(f"[M2] LEAKAGE DETECTED: {present_forbidden}")

    if not synthetic and len(df) > 5000:
        raise ValueError(
            f"[M2] Refusing to train on {len(df)} rows — looks like the AOI grid, "
            "not the 232-cell case-control sample."
        )

    X = df[FEATURE_COLS].values
    y = df[LABEL_COL].values

    n_pos = y.sum()
    n_neg = len(y) - n_pos
    logger.info(f"[M2] Training set: {n_pos} positives, {n_neg} negatives")

    if n_pos < 10:
        raise ValueError(
            f"[M2] Only {n_pos} positive samples — too few to train. "
            "Download more inventory data or check data/raw/historical_landslides/."
        )

    scale_pos_weight = n_neg / max(n_pos, 1)

    # ── Spatial block CV ──────────────────────────────────────────────────────
    splits = get_spatial_block_splits(df)
    fold_metrics = []
    oof_proba = np.zeros(len(y))
    oof_mask  = np.zeros(len(y), dtype=bool)

    logger.info(f"[M2] Running {len(splits)}-fold spatial block CV")

    # Use τ_alert placeholder (0.45) for fold evaluation; will be overwritten
    tau_eval = TAU_ALERT

    for fold_i, (train_idx, val_idx) in enumerate(splits):
        X_tr, X_val = X[train_idx], X[val_idx]
        y_tr, y_val = y[train_idx], y[val_idx]

        n_val_pos = int(y_val.sum())
        n_val_neg = int(len(y_val) - n_val_pos)
        if n_val_pos == 0 or n_val_neg == 0:
            logger.warning(
                f"[M2] Fold {fold_i}: single-class validation "
                f"(pos={n_val_pos}, neg={n_val_neg}) — skipping"
            )
            continue

        model_fold = make_xgb_model(scale_pos_weight)
        model_fold.fit(X_tr, y_tr)
        p_val = model_fold.predict_proba(X_val)[:, 1]
        oof_proba[val_idx] = p_val
        oof_mask[val_idx]  = True

        metrics = evaluate_fold(y_val, p_val, tau_eval)
        metrics["fold"] = fold_i
        metrics["n_val"] = int(len(val_idx))
        metrics["n_val_pos"] = n_val_pos
        metrics["n_val_neg"] = n_val_neg
        fold_metrics.append(metrics)
        logger.info(f"[M2] Fold {fold_i}: PR-AUC={metrics['pr_auc']:.4f}, "
                    f"ROC-AUC={metrics['roc_auc']:.4f}, "
                    f"hit@10%={metrics['hit_rate_top10']:.3f}")

    if not fold_metrics:
        raise RuntimeError("[M2] No valid spatial CV folds (every block was single-class).")

    # Summary statistics — CASE-CONTROL sample only, not full-AOI performance
    pr_aucs   = [m["pr_auc"]  for m in fold_metrics]
    roc_aucs  = [m["roc_auc"] for m in fold_metrics]
    briers    = [m["brier"]   for m in fold_metrics]
    hits      = [m["hit_rate_top10"] for m in fold_metrics]

    cv_summary = {
        "metric_scope":       "case_control_sample",
        "not_full_aoi_performance": True,
        "pr_auc_mean":        round(float(np.mean(pr_aucs)), 4),
        "pr_auc_std":         round(float(np.std(pr_aucs)),  4),
        "roc_auc_mean":       round(float(np.mean(roc_aucs)), 4),
        "roc_auc_std":        round(float(np.std(roc_aucs)), 4),
        "brier_mean":         round(float(np.mean(briers)), 4),
        "brier_std":          round(float(np.std(briers)), 4),
        "hit_rate_top10_mean":round(float(np.mean(hits)),    4),
        "n_folds":            len(fold_metrics),
        "n_samples":          int(len(df)),
        "n_positives":        int(n_pos),
        "n_negatives":        int(n_neg),
        "prevalence_in_sample": round(float(n_pos / max(len(df), 1)), 4),
    }
    logger.info(f"[M2] CV Summary: PR-AUC={cv_summary['pr_auc_mean']:.4f}"
                f" ±{cv_summary['pr_auc_std']:.4f}, "
                f"hit@10%={cv_summary['hit_rate_top10_mean']:.3f}")

    # ── Train final model on all data ─────────────────────────────────────────
    logger.info("[M2] Training final model on full dataset")
    final_model = make_xgb_model(scale_pos_weight)
    final_model.fit(X, y)

    # ── Calibration ───────────────────────────────────────────────────────────
    valid_oof = oof_mask   # cells that were in a validation fold
    if valid_oof.sum() > 50:
        brier_before = brier_score(y[valid_oof], oof_proba[valid_oof])
        calibrator = calibrate_isotonic(y[valid_oof], oof_proba[valid_oof])
        oof_calibrated = np.clip(calibrator.predict(oof_proba[valid_oof]), 0, 1)
        brier_after = brier_score(y[valid_oof], oof_calibrated)
        logger.info(f"[M2] Calibration: Brier before={brier_before:.4f}, after={brier_after:.4f}")
    else:
        logger.warning("[M2] Too few OOF predictions for calibration — using identity")
        calibrator = IsotonicRegression(out_of_bounds="clip")
        calibrator.fit([0, 1], [0, 1])
        brier_before = brier_after = 0.0
        oof_calibrated = oof_proba[valid_oof] if valid_oof.any() else oof_proba

    # ── Threshold selection ───────────────────────────────────────────────────
    thresholds = select_thresholds(
        y[valid_oof] if valid_oof.any() else y,
        oof_calibrated if valid_oof.any() else oof_proba,
    )

    # ── RF sanity check ───────────────────────────────────────────────────────
    logger.info("[M2] Running RF sanity check")
    rf_splits = get_spatial_block_splits(df)
    rf_pr_aucs = []
    for train_idx, val_idx in rf_splits[:3]:   # just 3 folds for speed
        if y[val_idx].sum() == 0:
            continue
        rf = make_rf_model()
        rf.fit(X[train_idx], y[train_idx])
        p_rf = rf.predict_proba(X[val_idx])[:, 1]
        rf_pr_aucs.append(average_precision_score(y[val_idx], p_rf))
    rf_pr_mean = float(np.mean(rf_pr_aucs)) if rf_pr_aucs else 0.0
    logger.info(f"[M2] RF sanity PR-AUC: {rf_pr_mean:.4f} "
                f"(XGB: {cv_summary['pr_auc_mean']:.4f})")

    # ── Temporal split check (only if positive event dates support it) ────────
    temporal_check = _temporal_holdout(df, X, y, scale_pos_weight)

    # ── SHAP Explainability ───────────────────────────────────────────────────
    logger.info("[M2] Computing SHAP values for model explainability")
    shap_summary = {}
    try:
        import shap
        explainer = shap.TreeExplainer(final_model)
        shap_values = explainer.shap_values(X)
        if isinstance(shap_values, list) and len(shap_values) > 1:
            shap_matrix = shap_values[1]
        else:
            shap_matrix = shap_values
        mean_abs_shap = np.mean(np.abs(shap_matrix), axis=0)
        top_indices = np.argsort(mean_abs_shap)[::-1]
        shap_ranking = [
            {"feature": FEATURE_COLS[i], "mean_abs_shap": round(float(mean_abs_shap[i]), 4)}
            for i in top_indices
        ]
        shap_summary = {
            "ranking": shap_ranking,
            "top_features": [FEATURE_COLS[i] for i in top_indices[:5]],
        }
        with open(out_dir / "shap_summary.json", "w") as f:
            json.dump(shap_summary, f, indent=2)
        np.save(out_dir / "shap_values.npy", shap_matrix)
        logger.info(f"[M2] Top SHAP features: {shap_summary['top_features']}")
    except Exception as e:
        logger.warning(f"[M2] SHAP calculation failed: {e}")

    # ── Save artefacts ────────────────────────────────────────────────────────
    logger.info("[M2] Saving model artefacts")
    model_path = out_dir / "model.json"
    calibrator_path = out_dir / "calibrator.pkl"
    thresholds_path = out_dir / "thresholds.json"
    feature_list_path = out_dir / "feature_list.json"
    meta_path = out_dir / "meta.json"
    cv_report_path = out_dir / "cv_report.json"

    if XGB_AVAILABLE and hasattr(final_model, "save_model"):
        final_model.save_model(str(model_path))
    else:
        joblib.dump(final_model, str(model_path.with_suffix(".pkl")))

    joblib.dump(calibrator, str(calibrator_path))

    with open(thresholds_path, "w") as f:
        json.dump(thresholds, f, indent=2)

    with open(feature_list_path, "w") as f:
        json.dump(FEATURE_COLS, f, indent=2)

    # Compute data hash for reproducibility
    df_bytes = df[FEATURE_COLS + [LABEL_COL]].to_parquet()
    data_hash = hashlib.md5(df_bytes).hexdigest()

    meta = {
        "train_date":          datetime.utcnow().isoformat(),
        "aoi_bbox_wgs84":      list(AOI_BBOX_WGS84),
        "crs_projected":       CRS_PROJECTED,
        "model_type":          "XGBoost" if XGB_AVAILABLE else "RandomForest",
        "n_features":          len(FEATURE_COLS),
        "feature_cols":        FEATURE_COLS,
        "n_positives":         int(n_pos),
        "n_negatives":         int(n_neg),
        "cv_summary":          cv_summary,
        "thresholds":          thresholds,
        "brier_before_calib":  round(float(brier_before), 4),
        "brier_after_calib":   round(float(brier_after), 4),
        "rf_sanity_pr_auc":    round(float(rf_pr_mean), 4),
        "temporal_check":      temporal_check,
        "data_hash_md5":       data_hash,
        "shap_summary":        shap_summary,
        "is_synthetic_data":   bool(synthetic),
        "training_dataset":    "synthetic_800" if synthetic else "case_control_232",
        "probability_interpretation": "case_control_ranking_score",
        "aoi_prevalence_correction": "not_applied",
        "aoi_prevalence_correction_reason": (
            "Negatives are 2 km-buffered subsampled cells, not a random AOI sample; "
            "Elkan-style prior correction is not identified. Outputs are ranking scores, "
            "not calibrated P(event) at ~0.01% AOI prevalence."
        ),
        "metric_scope":        "case_control_sample",
    }

    class _NumpyEncoder(json.JSONEncoder):
        def default(self, obj):
            import numpy as np
            if isinstance(obj, (np.integer,)):  return int(obj)
            if isinstance(obj, (np.floating,)): return float(obj)
            if isinstance(obj, (np.bool_,)):    return bool(obj)
            if isinstance(obj, np.ndarray):     return obj.tolist()
            return super().default(obj)

    with open(meta_path, "w") as f:
        json.dump(meta, f, indent=2, cls=_NumpyEncoder)

    cv_report = {
        "metric_scope": "case_control_sample",
        "not_full_aoi_performance": True,
        "is_synthetic_data": bool(synthetic),
        "folds": fold_metrics,
        "summary": cv_summary,
        "temporal_check": temporal_check,
    }
    with open(cv_report_path, "w") as f:
        json.dump(cv_report, f, indent=2, cls=_NumpyEncoder)

    logger.info(f"[M2] ✓ Training complete. Artefacts in {out_dir}/")
    return meta


if __name__ == "__main__":
    synthetic = "--synthetic" in sys.argv
    meta = run_training_pipeline(synthetic=synthetic)
    print("\n=== TRAINING COMPLETE ===")
    print(json.dumps(meta["cv_summary"], indent=2))
    print(json.dumps(meta["thresholds"], indent=2))
