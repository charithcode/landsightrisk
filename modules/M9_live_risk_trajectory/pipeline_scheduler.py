"""
pipeline_scheduler.py — M9: Live-Updating Risk Trajectory
==========================================================
⭐ Innovation Module E (MVP Priority)

Schedules the full LANDSIGHT pipeline to re-run on a rolling basis
as new rainfall / field data arrives during a monsoon event.

Key behaviors:
  - Re-run every N hours (configurable via .env PIPELINE_RERUN_INTERVAL_HOURS)
  - Use a rolling 72-hour rainfall window (slide forward each run)
  - Compare current run vs previous → highlight escalating zones
  - Auto-escalate/de-escalate action tiers as risk shifts

Risk trajectory data is stored per-run for time-series visualization
in the dashboard.
"""

import os
import json
from datetime import datetime
from apscheduler.schedulers.background import BackgroundScheduler
from loguru import logger
from dotenv import load_dotenv

load_dotenv()

RERUN_INTERVAL_HOURS = int(os.getenv("PIPELINE_RERUN_INTERVAL_HOURS", 3))
TRAJECTORY_LOG_PATH = "data/processed/risk_trajectory.json"


def run_full_pipeline() -> dict:
    """
    Execute the complete LANDSIGHT pipeline for the current time window.
    Called by the scheduler on each interval.

    Returns:
        Dict with run metadata and summary risk statistics.
    """
    run_time = datetime.utcnow().isoformat()
    logger.info(f"[M9] Pipeline re-run triggered at {run_time}")

    # TODO: Step 1 — M1: Refresh data (new rainfall, field reports)
    # TODO: Step 2 — M2: Re-run risk prediction
    # TODO: Step 3 — M3: Re-compute confidence (with latest M8 reports)
    # TODO: Step 4 — M5: Re-run connectivity simulation
    # TODO: Step 5 — M6: Re-score criticality
    # TODO: Step 6 — M7: Re-generate action recommendations
    # TODO: Step 7 — Append run result to trajectory log

    run_result = {
        "run_timestamp": run_time,
        "high_risk_cell_count": None,    # TODO: fill
        "tier3_village_count": None,     # TODO: fill
        "max_risk_score": None,          # TODO: fill
        "mean_confidence": None,         # TODO: fill
    }

    append_to_trajectory(run_result)
    return run_result


def append_to_trajectory(run_result: dict) -> None:
    """Append a pipeline run result to the time-series trajectory log."""
    trajectory = load_trajectory()
    trajectory.append(run_result)

    with open(TRAJECTORY_LOG_PATH, "w") as f:
        json.dump(trajectory, f, indent=2)
    logger.info(f"[M9] Trajectory updated — {len(trajectory)} total runs logged")


def load_trajectory() -> list:
    """Load existing trajectory log (empty list if file doesn't exist)."""
    if not os.path.exists(TRAJECTORY_LOG_PATH):
        return []
    with open(TRAJECTORY_LOG_PATH) as f:
        return json.load(f)


def compute_risk_diff(run1: dict, run2: dict) -> dict:
    """
    Compare two consecutive pipeline runs to identify:
    - Zones that escalated in risk
    - Zones that de-escalated
    - New Tier 3 villages

    Args:
        run1: Previous run result
        run2: Current run result

    Returns:
        Dict summarizing changes
    """
    # TODO: Implement grid-level diff between run1 and run2
    raise NotImplementedError("Risk diff tracker not yet implemented")


def start_scheduler() -> BackgroundScheduler:
    """
    Start the APScheduler background scheduler.
    Call this on API startup.

    Returns:
        Running BackgroundScheduler instance
    """
    scheduler = BackgroundScheduler()
    scheduler.add_job(
        run_full_pipeline,
        trigger="interval",
        hours=RERUN_INTERVAL_HOURS,
        id="landsight_pipeline",
        name="LANDSIGHT Pipeline Re-run",
        replace_existing=True,
    )
    scheduler.start()
    logger.info(f"[M9] Scheduler started — pipeline runs every {RERUN_INTERVAL_HOURS} hours")
    return scheduler


if __name__ == "__main__":
    # Manual one-shot run
    result = run_full_pipeline()
    print(json.dumps(result, indent=2))
