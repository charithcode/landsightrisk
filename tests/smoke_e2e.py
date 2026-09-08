"""
smoke_e2e.py — End-to-end smoke test using synthetic data
==========================================================
Verifies the full pipeline runs without errors on synthetic data.
No internet access required. Takes ~60–120 seconds.

Run:
    python -m pytest tests/smoke_e2e.py -v
    python tests/smoke_e2e.py  (standalone)
"""

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))


# ── M1: Feature matrix ────────────────────────────────────────────

def test_feature_matrix_synthetic():
    """Feature matrix should be non-empty with correct columns."""
    from modules.M1_data_ingestion.feature_engineer import (
        run_feature_pipeline, FEATURE_COLS, LABEL_COL, ALL_COLS,
    )
    df = run_feature_pipeline(synthetic=True)
    assert len(df) > 0, "Feature matrix is empty"
    assert LABEL_COL in df.columns, f"Missing {LABEL_COL}"
    assert "date_anchor" in df.columns, "Missing date_anchor — time anchoring failed"
    assert df["date_anchor"].notna().all(), "Some cells missing date_anchor"

    # Positive cells must have date_anchor
    pos = df[df[LABEL_COL] == 1]
    assert len(pos) > 0, "No positive samples"
    assert pos["date_anchor"].notna().all(), "Positive cells missing date_anchor"

    # No leaking proximity features
    forbidden = {"historical_landslide_density", "dist_to_stream_m"}
    assert not (set(df.columns) & forbidden), f"Leaking features found: {set(df.columns) & forbidden}"

    # Feature cols present
    for col in FEATURE_COLS:
        assert col in df.columns, f"Missing feature column: {col}"

    print(f"[OK] Feature matrix: {len(df)} rows, {len(pos)} positives")


# ── M2: Training ──────────────────────────────────────────────────

def test_model_trains_synthetic():
    """Model should train and save all artefacts."""
    import tempfile
    from modules.M2_risk_model.train import run_training_pipeline

    tmp_dir = Path(tempfile.mkdtemp())
    meta = run_training_pipeline(synthetic=True, models_dir=tmp_dir)
    assert "cv_summary" in meta, "No CV summary in meta"
    assert meta["cv_summary"]["n_positives"] > 0

    meta_path = tmp_dir / "meta.json"
    cv_path = tmp_dir / "cv_report.json"
    feat_path = tmp_dir / "feature_list.json"

    assert meta_path.exists(), "meta.json not saved"
    assert cv_path.exists(), "cv_report.json not saved"

    with open(cv_path) as f:
        cv = json.load(f)
    assert "summary" in cv
    pr_auc = cv["summary"].get("pr_auc_mean", 0)
    assert pr_auc >= 0, "PR-AUC must be non-negative"

    # No proximity features in feature list
    if feat_path.exists():
        with open(feat_path) as f:
            features = json.load(f)
        assert "historical_landslide_density" not in features, "Leaking feature in model!"

    print(f"[OK] Model trained: PR-AUC={pr_auc:.4f}")


# ── M2: Inference ─────────────────────────────────────────────────

def test_inference_runs():
    """Inference should produce p in [0,1] for all cells."""
    from modules.M2_risk_model.predict import run_inference
    # Fast test on sample feature matrix (full-grid verified in integration tests)
    gdf = run_inference(synthetic=True, use_full_grid=False)
    assert len(gdf) > 0, "No cells in inference output"
    assert "p" in gdf.columns, "Missing p column"
    p = gdf["p"].values
    assert (p >= 0).all() and (p <= 1).all(), "p values out of [0,1]"
    assert "risk_tier" in gdf.columns
    valid_tiers = {"respond", "alert", "watch", "none"}
    assert set(gdf["risk_tier"].unique()).issubset(valid_tiers | {""}), "Invalid tier values"
    print(f"[OK] Inference: {len(gdf)} cells, mean_p={p.mean():.4f}")


# ── M3: Confidence ────────────────────────────────────────────────

def test_confidence_bounds():
    """Confidence must be in [0, p] for all cells."""
    from modules.M3_uncertainty_engine.composite_confidence import compute_confidence_layer
    rng = np.random.default_rng(42)
    n = 200
    df = pd.DataFrame({
        "cell_id":    range(n),
        "p":          rng.uniform(0.1, 0.9, n),
        "dem_valid":  rng.choice([0.0, 1.0], n, p=[0.2, 0.8]),
        "rain_valid": rng.choice([0.0, 1.0], n, p=[0.3, 0.7]),
        "risk_tier":  ["watch"] * n,
    })
    result = compute_confidence_layer(df)
    assert "confidence" in result.columns
    conf = result["confidence"].values
    p    = result["p"].values
    assert (conf >= 0).all(), "Negative confidence"
    assert (conf <= 1).all(), "Confidence > 1"
    assert (conf <= p + 1e-6).all(), "confidence > p (should always be <= p)"
    print(f"[OK] Confidence: mean={conf.mean():.4f}, all <= p: {(conf <= p + 1e-6).all()}")


# ── M7: Action tiers ──────────────────────────────────────────────

def test_action_tiers():
    """RESPOND requires p>=tau_respond AND conf>=0.6 AND crit>=0.6."""
    from modules.M7_action_recommender.action_tier_engine import determine_tier
    from config.aoi import TAU_RESPOND, TAU_ALERT, TAU_WATCH

    assert determine_tier(TAU_RESPOND, 0.8, 0.8) == "respond"
    assert determine_tier(TAU_RESPOND, 0.3, 0.8) == "verify"   # conf too low
    assert determine_tier(TAU_ALERT,   0.8, 0.8) == "ready"    # p not >= tau_respond
    assert determine_tier(TAU_ALERT,   0.3, 0.8) == "verify"   # conf < 0.6
    assert determine_tier(TAU_WATCH,   0.8, 0.8) == "monitor"
    assert determine_tier(0.0,         0.8, 0.8) == "none"
    print("[OK] Action tier rule table correct")


# ── M8: Trust scorer ──────────────────────────────────────────────

def test_trust_scorer():
    """Trust scores must be in [0,1] and honor the reports_enter_training=False rule."""
    from modules.M8_trust_weighted_reports.trust_scorer import (
        compute_trust, reports_enter_training,
    )
    from datetime import datetime

    assert reports_enter_training is False, "INVARIANT: reports must not enter training!"

    r = compute_trust(
        reporter_type="official_agency",
        gps_accuracy_m=10.0,
        report_timestamp=datetime.utcnow(),
        report_type="road_blocked",
        lon=91.85, lat=25.88,
    )
    assert 0 <= r["trust"] <= 1
    assert r["aoi_valid"] is True
    assert r["pedigree"] == 1.0

    r_anon = compute_trust(
        reporter_type="anonymous_citizen",
        gps_accuracy_m=500.0,
        report_timestamp=datetime.utcnow(),
        report_type="generic_landslide",
        lon=91.85, lat=25.88,
    )
    assert r_anon["trust"] <= r["trust"], "Official should score >= anonymous"
    print(f"[OK] Trust: official={r['trust']:.3f}, anonymous={r_anon['trust']:.3f}")


# ── Standalone runner ─────────────────────────────────────────────

if __name__ == "__main__":
    tests = [
        test_feature_matrix_synthetic,
        test_model_trains_synthetic,
        test_inference_runs,
        test_confidence_bounds,
        test_action_tiers,
        test_trust_scorer,
    ]
    failed = 0
    for t in tests:
        try:
            print(f"\n{'-'*50}\nRunning: {t.__name__}")
            t()
        except Exception as e:
            print(f"[FAIL] FAILED: {e}")
            failed += 1
    print(f"\n{'='*50}")
    print(f"Results: {len(tests)-failed}/{len(tests)} passed")
    if failed:
        sys.exit(1)
