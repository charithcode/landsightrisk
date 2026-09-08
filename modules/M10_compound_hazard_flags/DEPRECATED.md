# DEPRECATED — Module Cut per Blueprint §19

This module (M10: Compound Hazard Flags) is **future-scope (P2)**.

It was cut from the MVP to focus resources on:
- M2: Calibrated XGBoost susceptibility model (spatial block CV, isotonic calibration)
- M5: Deterministic connectivity failure simulation
- M6: Criticality formula with DETOUR/HOSPDEP weighting

## Planned scope (P2)
- Multi-hazard overlay: flood hazard (CWC) × landslide susceptibility
- Compound event detection: simultaneous rainfall + seismic + slope failure
- Integration with NDMA compound hazard database

## Why cut?
Adding a compound hazard layer before the single-hazard baseline is validated
would increase complexity without improving defensibility. Train the evaluators
to trust the susceptibility model first, then add compound analysis.

## Code status
No new code written here. Original skeleton preserved.
