from __future__ import annotations

import asyncio
import logging

from app.modules.assemblers.db.connection import get_db_connection

from . import ensure_schema, process_detail_metrics_recalc_queue


logger = logging.getLogger(__name__)

_DETAIL_RECALC_WORKER_LOCK_KEY = 764321987650001


async def _ensure_schema_with_retry(stop_event: asyncio.Event, max_attempts: int = 5) -> None:
    for attempt in range(1, max_attempts + 1):
        if stop_event.is_set():
            return
        try:
            await asyncio.to_thread(ensure_schema)
            return
        except Exception:
            if attempt >= max_attempts:
                logger.exception(
                    "ensure_schema failed after %d attempts; worker continues without schema init.",
                    max_attempts,
                )
                return
            delay = min(2 ** attempt, 30)
            logger.warning("ensure_schema attempt %d failed, retrying in %ss.", attempt, delay)
            try:
                await asyncio.wait_for(stop_event.wait(), timeout=float(delay))
                return
            except TimeoutError:
                pass


def _process_queue_with_lock(batch_size: int) -> dict:
    """Run one queue pass under a cross-process advisory lock.

    Multiple gunicorn workers start this background loop. Without a shared lock,
    they can process the same recalculation flow concurrently and deadlock.
    """
    with get_db_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute("SELECT pg_try_advisory_lock(%s)", (_DETAIL_RECALC_WORKER_LOCK_KEY,))
            acquired = bool(cursor.fetchone()[0])
            if not acquired:
                return {"queued_orders": 0, "updated_rows": 0}
            try:
                return process_detail_metrics_recalc_queue(batch_size)
            finally:
                cursor.execute("SELECT pg_advisory_unlock(%s)", (_DETAIL_RECALC_WORKER_LOCK_KEY,))


async def run_detail_metrics_recalc_worker(
    stop_event: asyncio.Event,
    *,
    poll_interval_seconds: float = 1.0,
    batch_size: int = 30,
) -> None:
    await _ensure_schema_with_retry(stop_event)

    while not stop_event.is_set():
        try:
            result = await asyncio.to_thread(
                _process_queue_with_lock,
                batch_size,
            )
        except Exception:
            logger.exception("Detail metrics queue worker failed.")
            result = {"queued_orders": 0, "updated_rows": 0}

        if result.get("queued_orders", 0) > 0:
            await asyncio.sleep(0)
            continue

        try:
            await asyncio.wait_for(stop_event.wait(), timeout=max(0.1, float(poll_interval_seconds)))
        except TimeoutError:
            continue
