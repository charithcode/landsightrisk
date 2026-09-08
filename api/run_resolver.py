"""
api/run_resolver.py — Safe, validated run resolver for LANDSIGHT
================================================================
Single source of truth for resolving "latest valid run".

Rules:
  1. Read latest_run.json → validate the pointed directory has all required artifacts.
  2. If invalid, scan data/runs/ for the newest valid run by ISO timestamp in dir name.
  3. Never return an invalid/incomplete run.
  4. Thread-safe: uses a file-read lock pattern (no mutable global).

All API routers import resolve_run() from here instead of duplicating the logic.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Optional

from fastapi import HTTPException

REQUIRED_ARTIFACTS = [
    "cells.geojson",
    "criticality.geojson",
    "actions.json",
    "run_meta.json",
]

_RUNS_DIR = Path("data/runs")
_PTR_FILE = _RUNS_DIR / "latest_run.json"
_RUN_TS_PATTERN = re.compile(r"run_(\d{8}T\d{6}Z)$")


def _is_valid_run(run_dir: Path) -> bool:
    """Return True if run_dir exists and contains all required artifacts."""
    if not run_dir.is_dir():
        return False
    return all((run_dir / a).exists() for a in REQUIRED_ARTIFACTS)


def _newest_valid_run() -> Optional[Path]:
    """Scan runs/ and return the newest valid run dir by ISO timestamp in name."""
    candidates = []
    for d in _RUNS_DIR.iterdir():
        if d.is_dir() and _RUN_TS_PATTERN.match(d.name) and _is_valid_run(d):
            candidates.append(d)
    if not candidates:
        return None
    return sorted(candidates, key=lambda d: d.name)[-1]


def resolve_run(run: str = "latest") -> Path:
    """
    Resolve a run identifier to a valid run directory.

    Args:
        run: "latest" | specific run ID like "run_20260908T150000Z"

    Returns:
        Path to a validated run directory.

    Raises:
        HTTPException 503 if no valid run exists.
        HTTPException 404 if a specific run ID was requested and not found.
    """
    if run != "latest":
        run_dir = _RUNS_DIR / run
        if not run_dir.exists():
            raise HTTPException(404, f"Run not found: {run}")
        if not _is_valid_run(run_dir):
            raise HTTPException(422, f"Run {run} is incomplete (missing required artifacts).")
        return run_dir

    # "latest" path — read pointer, then validate
    run_dir: Optional[Path] = None

    if _PTR_FILE.exists():
        try:
            with open(_PTR_FILE, encoding="utf-8") as f:
                ptr = json.load(f)
            # Normalise: some older writes double-escaped the backslash
            raw_dir = ptr.get("run_dir", "")
            candidate = Path(raw_dir.replace("\\\\", "\\"))
            if _is_valid_run(candidate):
                run_dir = candidate
        except Exception:
            pass  # fall through to scan

    if run_dir is None:
        # Pointer missing, invalid, or broken — scan for newest valid run
        run_dir = _newest_valid_run()

    if run_dir is None:
        raise HTTPException(503, "No valid runs available. Run the pipeline first.")

    return run_dir


def get_latest_run_id() -> str:
    """Return the run_id string for the current best run (for health/status endpoints)."""
    try:
        d = resolve_run("latest")
        return d.name
    except HTTPException:
        return "none"


def update_latest_pointer(run_dir: Path) -> None:
    """
    Atomically update latest_run.json to point to run_dir.
    Only called AFTER a new run has been validated.
    """
    if not _is_valid_run(run_dir):
        raise ValueError(f"Cannot publish incomplete run: {run_dir}")
    _PTR_FILE.parent.mkdir(parents=True, exist_ok=True)
    tmp = _PTR_FILE.with_suffix(".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump({"run_id": run_dir.name, "run_dir": str(run_dir)}, f, indent=2)
    tmp.replace(_PTR_FILE)
