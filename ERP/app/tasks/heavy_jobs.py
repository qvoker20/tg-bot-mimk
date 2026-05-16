from __future__ import annotations

from app.modules.assemblers.services.schedule import run_schedule_daily_cutoff_catchup


def run_cutoff_job(days_back: int = 31) -> dict:
    """RQ job wrapper for schedule daily cutoff catchup."""
    summary = run_schedule_daily_cutoff_catchup(days_back=days_back)
    return {
        "ok": True,
        "job": "schedule_cutoff",
        "summary": summary,
    }
