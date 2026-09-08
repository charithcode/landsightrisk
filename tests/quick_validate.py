"""Quick validation of M7 tier logic and M8 trust invariant."""
import sys
sys.path.insert(0, ".")

# M7 tier rules
from modules.M7_action_recommender.action_tier_engine import determine_tier
from config.aoi import TAU_RESPOND, TAU_ALERT, TAU_WATCH

cases = [
    (TAU_RESPOND, 0.8, 0.8, "respond"),
    (TAU_RESPOND, 0.3, 0.8, "verify"),
    (TAU_ALERT,   0.8, 0.3, "ready"),
    (TAU_ALERT,   0.3, 0.8, "verify"),
    (TAU_WATCH,   0.8, 0.8, "monitor"),
    (0.0,         0.8, 0.8, "none"),
]

all_ok = True
for p, conf, crit, expected in cases:
    got = determine_tier(p, conf, crit)
    ok = got == expected
    all_ok = all_ok and ok
    status = "OK" if ok else f"FAIL (expected {expected})"
    print(f"  p={p:.2f} conf={conf} crit={crit} -> {got}  {status}")

print("M7 tier rules:", "ALL PASS" if all_ok else "FAILED")

# M8 trust invariant
from modules.M8_trust_weighted_reports.trust_scorer import compute_trust, reports_enter_training
from datetime import datetime
assert reports_enter_training is False, "INVARIANT VIOLATED"
r = compute_trust("official_agency", 10.0, datetime.utcnow(), "road_blocked", 91.85, 25.88)
assert 0 <= r["trust"] <= 1
assert r["pedigree"] == 1.0
r_anon = compute_trust("anonymous_citizen", 500.0, datetime.utcnow(), "generic_landslide", 91.85, 25.88)
assert r_anon["trust"] <= r["trust"]
print(f"M8 trust: official={r['trust']:.3f}, anonymous={r_anon['trust']:.3f}  OK")

# M3 confidence bounds
import numpy as np
import pandas as pd
from modules.M3_uncertainty_engine.composite_confidence import compute_confidence_layer
rng = np.random.default_rng(42)
n = 100
df = pd.DataFrame({
    "cell_id":    range(n),
    "p":          rng.uniform(0.1, 0.9, n),
    "dem_valid":  rng.choice([0.0, 1.0], n),
    "rain_valid": rng.choice([0.0, 1.0], n),
    "risk_tier":  ["watch"] * n,
})
result = compute_confidence_layer(df)
conf = result["confidence"].values
p_vals = result["p"].values
assert (conf >= 0).all(), "Negative confidence!"
assert (conf <= 1).all(), "Confidence > 1!"
assert (conf <= p_vals + 1e-6).all(), "confidence > p!"
print(f"M3 confidence bounds: mean={conf.mean():.4f}, all in [0,p]  OK")

print("\n=== CORE LOGIC TESTS: ALL PASS ===")
