from __future__ import annotations

import asyncio
import logging

from .schema import run_schedule_daily_cutoff_catchup


logger = logging.getLogger(__name__)


async def run_schedule_daily_cutoff_worker(
    stop_event: asyncio.Event,
    *,
    poll_interval_seconds: float = 60.0,
    days_back: int = 31,
) -> None:
    """Periodically runs DB-side 18:00 auto-close checks with downtime catch-up."""
    while not stop_event.is_set():
        try:
            await asyncio.to_thread(run_schedule_daily_cutoff_catchup, days_back=days_back)
        except Exception:
            logger.exception("Schedule daily cutoff worker failed.")

        try:
            await asyncio.wait_for(stop_event.wait(), timeout=max(5.0, float(poll_interval_seconds)))
        except TimeoutError:
            continue