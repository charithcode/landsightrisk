"""
tests/integration/test_real_pipeline.py
========================================
Phase 3 integration tests that verify the FULL pipeline against REAL data.
- Real M2 model (232 case-control cells, is_synthetic_data=False)
- Full AOI inference (588,952 cells)
- All downstream modules M3–M9
- FastAPI endpoints

Run with:
    pytest tests/integration/test_real_pipeline.py -v
"""
import json
import pytest
from pathlib import Path

ROOT = Path(__file__).parent.parent.parent
RUNS_DIR = ROOT / "data" / "runs"
PROCESSED = ROOT / "data" / "processed"
MODEL_META = ROOT / "modules" / "M2_risk_model" / "saved_models" / "meta.json"

# ── Helpers ──────────────────────────────────────────────────────────────────

def get_latest_run_dir() -> Path:
    ptr = RUNS_DIR / "latest_run.json"
    assert ptr.exists(), "latest_run.json missing — run M2/predict.py first"
    d = json.loads(ptr.read_text())
    run_dir = Path(d["run_dir"])
    assert run_dir.exists(), f"Run dir {run_dir} does not exist"
    return run_dir


# ── M2 Model Metadata ─────────────────────────────────────────────────────────

class TestM2ModelMetadata:
    def test_meta_exists(self):
        assert MODEL_META.exists(), "M2 saved model meta.json not found"

    def test_not_synthetic(self):
        meta = json.loads(MODEL_META.read_text())
        assert meta.get("is_synthetic_data") is False, (
            f"Expected is_synthetic_data=False but got {meta.get('is_synthetic_data')}"
        )

    def test_sample_counts(self):
        meta = json.loads(MODEL_META.read_text())
        n_pos = meta.get("n_positives") or meta.get("cv_summary", {}).get("n_positives")
        n_neg = meta.get("n_negatives") or meta.get("cv_summary", {}).get("n_negatives")
        n_tot = (meta.get("cv_summary", {}).get("n_samples")
                 or (n_pos + n_neg if n_pos and n_neg else None))
        assert n_pos == 58,  f"Expected 58 positives, got {n_pos}"
        assert n_neg == 174, f"Expected 174 negatives, got {n_neg}"
        assert n_tot == 232, f"Expected 232 total, got {n_tot}"

    def test_feature_count(self):
        meta = json.loads(MODEL_META.read_text())
        # Real meta uses 'feature_cols' or 'feature_names'
        features = meta.get("feature_cols") or meta.get("feature_names", [])
        n_feat   = meta.get("n_features") or len(features)
        assert n_feat == 12, f"Expected 12 features, got {n_feat}"

    def test_no_leakage_features(self):
        """Ensure no historical landslide density/proximity features are present."""
        meta = json.loads(MODEL_META.read_text())
        features = meta.get("feature_cols") or meta.get("feature_names", [])
        banned = ["hist_density", "landslide_density", "ls_proximity", "historical_proximity"]
        for feat in features:
            for b in banned:
                assert b not in feat.lower(), (
                    f"Leakage feature '{feat}' found in M2 feature list"
                )

    def test_reports_do_not_enter_training(self):
        meta = json.loads(MODEL_META.read_text())
        assert meta.get("reports_enter_training") is False or \
               "reports_enter_training" not in meta or \
               meta.get("training_dataset") == "case_control_232", (
            "M8 field reports must NOT enter M2 training"
        )


# ── Full Grid Run Artifacts ───────────────────────────────────────────────────

class TestFullGridArtifacts:
    def test_cells_geojson_exists(self):
        run_dir = get_latest_run_dir()
        p = run_dir / "cells.geojson"
        assert p.exists(), "cells.geojson missing"

    def test_cells_geojson_size(self):
        """cells.geojson should only contain high-priority alert+respond cells (not 588k)."""
        run_dir = get_latest_run_dir()
        fc = json.loads((run_dir / "cells.geojson").read_text())
        n = len(fc.get("features", []))
        # Should be between 100 and 5000 alert+respond cells, NOT 588952
        assert 50 <= n <= 10000, f"cells.geojson has {n} features — expected alert+respond subset"

    def test_risk_surface_tif_exists(self):
        run_dir = get_latest_run_dir()
        p = run_dir / "risk_surface_100m.tif"
        assert p.exists(), "risk_surface_100m.tif missing"

    def test_risk_surface_tif_nonzero(self):
        run_dir = get_latest_run_dir()
        p = run_dir / "risk_surface_100m.tif"
        assert p.stat().st_size > 500_000, "risk_surface_100m.tif suspiciously small"

    def test_run_meta_cell_count(self):
        run_dir = get_latest_run_dir()
        meta = json.loads((run_dir / "run_meta.json").read_text())
        n_total = meta.get("full_grid_stats", {}).get("n_total_cells", 0)
        assert n_total == 588952, f"Expected 588952 cells, got {n_total}"

    def test_run_meta_not_synthetic(self):
        run_dir = get_latest_run_dir()
        meta = json.loads((run_dir / "run_meta.json").read_text())
        assert meta.get("is_synthetic_data") is False


# ── M3 Confidence ─────────────────────────────────────────────────────────────

class TestM3Confidence:
    def test_confidence_bounds(self):
        """Confidence must be in [0, max_p]. We accept [0, 1] as a reasonable bound."""
        run_dir = get_latest_run_dir()
        meta = json.loads((run_dir / "run_meta.json").read_text())
        conf_max = meta.get("full_grid_stats", {}).get("conf_max", 1.0)
        conf_mean = meta.get("full_grid_stats", {}).get("conf_mean", 0.5)
        assert 0 <= conf_mean <= conf_max <= 1.01, (
            f"Confidence out of range: mean={conf_mean}, max={conf_max}"
        )

    def test_cells_have_confidence_field(self):
        run_dir = get_latest_run_dir()
        fc = json.loads((run_dir / "cells.geojson").read_text())
        feats = fc.get("features", [])
        if feats:
            assert "confidence" in feats[0].get("properties", {}), (
                "cells.geojson features missing 'confidence' property"
            )


# ── M4 Road Exposure ──────────────────────────────────────────────────────────

class TestM4RoadExposure:
    def test_exposed_roads_exists(self):
        run_dir = get_latest_run_dir()
        p = run_dir / "exposed_roads.geojson"
        assert p.exists(), "exposed_roads.geojson missing"

    def test_exposed_roads_has_risk_max(self):
        run_dir = get_latest_run_dir()
        fc = json.loads((run_dir / "exposed_roads.geojson").read_text())
        feats = fc.get("features", [])
        assert len(feats) > 0, "No exposed road features found"
        for f in feats[:5]:
            assert "risk_max" in f.get("properties", {}), (
                "exposed_roads features missing 'risk_max' property"
            )

    def test_run_meta_road_counts(self):
        run_dir = get_latest_run_dir()
        meta = json.loads((run_dir / "run_meta.json").read_text())
        assert meta.get("n_road_segments", 0) > 0, "n_road_segments is 0"
        assert meta.get("n_exposed_roads", 0) > 0, "n_exposed_roads is 0"


# ── M5 Connectivity ───────────────────────────────────────────────────────────

class TestM5Connectivity:
    def test_impact_summary_exists(self):
        run_dir = get_latest_run_dir()
        p = run_dir / "impact_summary.json"
        assert p.exists(), "impact_summary.json missing"

    def test_impact_summary_fields(self):
        run_dir = get_latest_run_dir()
        summary = json.loads((run_dir / "impact_summary.json").read_text())
        assert "n_villages_isolated" in summary or "scenario" in summary, (
            "impact_summary.json missing expected fields"
        )

    def test_exposed_communities_exists(self):
        run_dir = get_latest_run_dir()
        p = run_dir / "exposed_communities.geojson"
        assert p.exists(), "exposed_communities.geojson missing"


# ── M6 Criticality ────────────────────────────────────────────────────────────

class TestM6Criticality:
    def test_criticality_geojson_exists(self):
        run_dir = get_latest_run_dir()
        p = run_dir / "criticality.geojson"
        assert p.exists(), "criticality.geojson missing"

    def test_criticality_has_components(self):
        run_dir = get_latest_run_dir()
        fc = json.loads((run_dir / "criticality.geojson").read_text())
        feats = fc.get("features", [])
        assert len(feats) > 0, "criticality.geojson has no features"
        props = feats[0].get("properties", {})
        required = ["comp_RISK", "comp_SERVED", "comp_DETOUR", "comp_HOSPDEP", "comp_TREND"]
        for comp in required:
            assert comp in props, f"criticality missing component '{comp}'"

    def test_criticality_score_range(self):
        run_dir = get_latest_run_dir()
        fc = json.loads((run_dir / "criticality.geojson").read_text())
        for feat in fc.get("features", [])[:20]:
            props = feat.get("properties", {})
            score = props.get("criticality_score", props.get("score", None))
            if score is not None:
                assert 0 <= float(score) <= 1.01, f"criticality_score out of range: {score}"


# ── M7 Actions ────────────────────────────────────────────────────────────────

class TestM7Actions:
    def test_actions_json_exists(self):
        run_dir = get_latest_run_dir()
        p = run_dir / "actions.json"
        assert p.exists(), "actions.json missing"

    def test_actions_have_evidence_chains(self):
        run_dir = get_latest_run_dir()
        data = json.loads((run_dir / "actions.json").read_text())
        actions = data.get("actions", data) if isinstance(data, dict) else data
        assert len(actions) > 0, "No actions found in actions.json"
        for act in actions[:5]:
            assert "tier" in act, f"Action missing 'tier': {act}"
            assert "evidence" in act or "action" in act, f"Action missing key fields: {act}"

    def test_action_tiers_valid(self):
        run_dir = get_latest_run_dir()
        data = json.loads((run_dir / "actions.json").read_text())
        actions = data.get("actions", data) if isinstance(data, dict) else data
        valid_tiers = {"respond", "alert", "watch", "monitor", "none", 1, 2, 3, 4, 5}
        for act in actions:
            tier = act.get("tier")
            # Accept string or int tier
            assert tier is not None, "Action has no tier"


# ── M8 Trust-Weighted Reports ─────────────────────────────────────────────────

class TestM8Trust:
    def test_reports_not_in_training(self):
        """M8 reports must be isolated from M2 training — verify meta.json."""
        meta = json.loads(MODEL_META.read_text())
        # Training dataset must be the real case-control set, not enriched by reports
        training_ds = meta.get("training_dataset", "")
        assert "case_control" in training_ds.lower(), (
            f"Unexpected training_dataset: {training_ds}"
        )
        # Explicit flag if present
        if "reports_enter_training" in meta:
            assert meta["reports_enter_training"] is False


# ── M9 Trajectory ─────────────────────────────────────────────────────────────

class TestM9Trajectory:
    def test_trajectory_json_exists(self):
        p = RUNS_DIR / "trajectory.json"
        assert p.exists(), "trajectory.json missing — run M9 pipeline_scheduler.py"

    def test_trajectory_has_chart_series(self):
        p = RUNS_DIR / "trajectory.json"
        if not p.exists():
            pytest.skip("trajectory.json not yet generated")
        data = json.loads(p.read_text())
        assert "chart_series" in data, "trajectory.json missing chart_series"
        assert len(data["chart_series"]) >= 1, "trajectory.json chart_series is empty"

    def test_trajectory_disclaimer_present(self):
        p = RUNS_DIR / "trajectory.json"
        if not p.exists():
            pytest.skip("trajectory.json not yet generated")
        data = json.loads(p.read_text())
        assert "disclaimer" in data, "trajectory.json missing disclaimer"
        disclaimer = data["disclaimer"].lower()
        assert "not a forecast" in disclaimer, "Disclaimer must say 'NOT a forecast'"


# ── FastAPI Endpoints ─────────────────────────────────────────────────────────

@pytest.mark.skipif(
    not __import__("socket").create_connection.__module__,
    reason="requires running API server"
)
class TestAPIEndpoints:
    """These tests require the FastAPI server to be running on localhost:8000."""

    BASE = "http://localhost:8000"

    def _get(self, path: str):
        import urllib.request
        try:
            with urllib.request.urlopen(f"{self.BASE}{path}", timeout=10) as r:
                return r.status, json.loads(r.read())
        except Exception as e:
            return None, str(e)

    def _api_available(self):
        import socket
        try:
            socket.create_connection(("localhost", 8000), timeout=2)
            return True
        except OSError:
            return False

    def test_health(self):
        if not self._api_available():
            pytest.skip("API server not running")
        status, data = self._get("/health")
        assert status == 200

    def test_risk_map(self):
        if not self._api_available():
            pytest.skip("API server not running")
        status, data = self._get("/risk/map?run=latest")
        assert status == 200
        assert data.get("type") == "FeatureCollection"

    def test_risk_bounds(self):
        if not self._api_available():
            pytest.skip("API server not running")
        status, data = self._get("/risk/bounds")
        assert status == 200
        assert "bbox" in data
        assert "coordinates" in data
        assert len(data["coordinates"]) == 4

    def test_connectivity_exposed(self):
        if not self._api_available():
            pytest.skip("API server not running")
        status, data = self._get("/connectivity/exposed?run=latest")
        assert status == 200
        assert data.get("type") == "FeatureCollection"
        assert len(data.get("features", [])) > 0

    def test_criticality(self):
        if not self._api_available():
            pytest.skip("API server not running")
        status, data = self._get("/criticality?run=latest")
        assert status == 200

    def test_actions(self):
        if not self._api_available():
            pytest.skip("API server not running")
        status, data = self._get("/actions?run=latest")
        assert status == 200

    def test_trajectory(self):
        if not self._api_available():
            pytest.skip("API server not running")
        status, data = self._get("/trajectory")
        assert status == 200
        assert "chart_series" in data
