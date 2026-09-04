# 🏔️ LANDSIGHT
### AI-Powered Landslide Connectivity & Response Intelligence
**SIH 2026 — Northeast India**

---

## What is LANDSIGHT?

LANDSIGHT is a **decision-support system** for landslide disaster management in Northeast India.

It doesn't just answer *"where might a landslide occur?"* — it answers:

> **If a high-risk slope fails, which connections collapse, which communities get isolated, how does risk evolve over the event, and what should authorities do — before and during it happens?**

---

## Pipeline Philosophy

```
PREDICT → VERIFY → ANTICIPATE → PRIORITIZE → ACT
```

Always distinguish ML predictions from scenario simulations.

---

## Module Overview

| Module | Name | MVP? |
|--------|------|------|
| M1 | Multi-Source Environmental Data Ingestion | ✅ Core |
| M2 | Landslide Risk Model (ML) | ✅ Core |
| M3 | Uncertainty & Confidence Estimation | ✅ Core |
| M4 | Road / Infrastructure Exposure Mapping | ✅ Core |
| M5 | Connectivity Failure Simulation | ✅ Core |
| M6 | Dynamic Criticality Scorer | ✅ Core |
| M7 | Confidence-Gated Action Recommender | ✅ Core |
| M8 | Trust-Weighted Citizen / Field Reports | ⭐ Innovation B |
| M9 | Live-Updating Risk Trajectory | ⭐ Innovation E |
| M10 | Compound / Cascading Hazard Flags | 📋 Roadmap |
| M11 | Resource Allocation Optimizer | 📋 Roadmap |
| M12 | Recovery-Time / Reopening Estimator | 📋 Roadmap |

---

## Tech Stack

| Layer | Technology |
|-------|-----------|
| ML Models | Python + scikit-learn + XGBoost |
| Geospatial | GeoPandas + Rasterio + Shapely |
| Graph Engine | NetworkX |
| API | FastAPI |
| Dashboard | React + Mapbox GL JS |
| Database | PostgreSQL + PostGIS |
| Scheduling | APScheduler |

---

## Quick Start

```bash
# 1. Install Python dependencies
pip install -r requirements.txt

# 2. Run the API
uvicorn api.main:app --reload

# 3. Run the dashboard
cd dashboard && npm install && npm run dev
```

---

## Honest Framing

LANDSIGHT is a **decision-support tool for authorities**, not a replacement for geologists, GSI, or official warning agencies.
We explicitly acknowledge GSI/LANDSLIP, NDMA, and published road-vulnerability research as prior art.

Our contribution: **uncertainty-aware hazard intelligence + predictive connectivity/isolation analysis + trust-weighted human input + evolving risk trajectory + confidence-gated action recommendation**, integrated into one pipeline for Northeast India.
