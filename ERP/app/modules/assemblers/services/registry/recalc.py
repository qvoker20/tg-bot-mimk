from __future__ import annotations

from collections import defaultdict
from decimal import Decimal

from app.modules.assemblers.db.connection import get_db_connection
from app.modules.assemblers.services.settings.core import load_calculation_settings

from .constants import (
    DATA_METAL_TABLE,
    DETAIL_RECALC_QUEUE_TABLE,
    DETAILS_TABLE_NAME,
    MAIN_TABLE_NAME,
    TASK_STATUS_COMPLETED,
    TASK_STATUS_IN_PROGRESS,
    TASK_STATUS_QUEUED,
)
from .context import _build_schedule_execution_context, _build_metal_status, _part_matches_spec
from .schema import ensure_schema
from .status import _build_stage_status_distribution
from .utils import (
    _safe_text,
    _parse_decimal,
    _parse_part_number,
    _calculate_stage_metrics,
    _calculate_planned_hours,
    _parse_duration_minutes,
    _format_duration,
)


def recalculate_detail_metrics(order_numbers: list[str] | None = None) -> int:
    ensure_schema()
    normalized_orders = [_safe_text(value) for value in (order_numbers or []) if _safe_text(value)]

    with get_db_connection() as conn:
        with conn.cursor() as cursor:
            filter_sql = ""
            params: list[object] = []
            if normalized_orders:
                filter_sql = "WHERE TRIM(COALESCE(order_number, '')) = ANY(%s)"
                params.append(normalized_orders)

            cursor.execute(
                f"""
                SELECT
                    id,
                    order_number,
                    part_number,
                    product_name,
                    assembly_worker,
                    assembly_started_at,
                    assembly_completed_at,
                    assembly_status,
                    install_worker,
                    install_started_at,
                    install_completed_at,
                    install_status,
                    item_value,
                    requires_assembly,
                    requires_install
                FROM {DETAILS_TABLE_NAME}
                {filter_sql}
                ORDER BY id
                """,
                tuple(params),
            )
            detail_rows = cursor.fetchall()

            if not detail_rows:
                if normalized_orders:
                    cursor.execute(
                        f"""
                        UPDATE {MAIN_TABLE_NAME}
                        SET total_planned_hours = 0,
                            updated_at = NOW()
                        WHERE TRIM(COALESCE(order_number, '')) = ANY(%s)
                        """,
                        (normalized_orders,),
                    )
                    conn.commit()
                return 0

            metal_by_order: dict[str, list[dict]] = defaultdict(list)
            cursor.execute("SELECT to_regclass(%s)", (DATA_METAL_TABLE,))
            if cursor.fetchone()[0]:
                affected_orders = list({_safe_text(r[1]) for r in detail_rows if _safe_text(r[1])})
                cursor.execute(
                    f"""
                    SELECT
                        TRIM(COALESCE(column_1, '')),
                        TRIM(COALESCE(column_2, '')),
                        TRIM(COALESCE(column_3, '')),
                        TRIM(COALESCE(column_4, '')),
                        TRIM(COALESCE(column_5, ''))
                    FROM {DATA_METAL_TABLE}
                    WHERE TRIM(COALESCE(column_1, '')) = ANY(%s)
                    ORDER BY column_1, id
                    """,
                    (affected_orders,),
                )
                for row in cursor.fetchall():
                    order_num = row[0]
                    if order_num:
                        metal_by_order[order_num].append(
                            {
                                "part_spec": row[1],
                                "col3": row[2],
                                "col4": row[3],
                                "col5": row[4],
                            }
                        )

            schedule_context = _build_schedule_execution_context(
                [
                    (_safe_text(record[1]), _safe_text(record[2]), _safe_text(record[3]))
                    for record in detail_rows
                ]
            )
            calculation_settings = load_calculation_settings()
            day_cost = calculation_settings.get("assembly_day_cost", Decimal("35000"))
            workday_hours = calculation_settings.get("assembly_workday_hours", Decimal("8"))

            update_values = []
            order_totals: dict[str, Decimal] = defaultdict(lambda: Decimal("0"))
            order_stage_details: dict[str, list[dict[str, object]]] = defaultdict(list)

            for record in detail_rows:
                detail_id = int(record[0])
                order_number = _safe_text(record[1])
                part_number = _safe_text(record[2])
                product_name = _safe_text(record[3])
                schedule_info = schedule_context.get((order_number, part_number, product_name), {})

                assembly_worker = _safe_text(schedule_info.get("assembly_worker"))
                assembly_started_at = schedule_info.get("assembly_started_at")
                schedule_assembly_completed_at = schedule_info.get("assembly_completed_at")
                assembly_status = _safe_text(schedule_info.get("assembly_status"))
                install_worker = _safe_text(schedule_info.get("install_worker"))
                install_started_at = schedule_info.get("install_started_at")
                schedule_install_completed_at = schedule_info.get("install_completed_at")
                install_status = _safe_text(schedule_info.get("install_status"))
                requires_assembly = bool(record[13])
                requires_install = bool(record[14])

                persisted_assembly_completed_at = record[6]
                persisted_assembly_status = _safe_text(record[7])
                persisted_install_completed_at = record[10]
                persisted_install_status = _safe_text(record[11])

                # Completed status is valid only with explicit detail completion timestamp.
                if (
                    persisted_assembly_completed_at is None
                    and persisted_assembly_status.casefold() == TASK_STATUS_COMPLETED.casefold()
                ):
                    persisted_assembly_status = ""
                if (
                    persisted_install_completed_at is None
                    and persisted_install_status.casefold() == TASK_STATUS_COMPLETED.casefold()
                ):
                    persisted_install_status = ""

                if (
                    schedule_assembly_completed_at is None
                    and assembly_status.casefold() == TASK_STATUS_COMPLETED.casefold()
                ):
                    assembly_status = TASK_STATUS_IN_PROGRESS if assembly_started_at else TASK_STATUS_QUEUED
                if (
                    schedule_install_completed_at is None
                    and install_status.casefold() == TASK_STATUS_COMPLETED.casefold()
                ):
                    install_status = TASK_STATUS_IN_PROGRESS if install_started_at else TASK_STATUS_QUEUED

                # Only explicit detail completion should mark the detail as completed.
                final_assembly_completed_at = persisted_assembly_completed_at
                final_install_completed_at = persisted_install_completed_at
                final_assembly_status = (
                    persisted_assembly_status
                    if final_assembly_completed_at is not None
                    else (assembly_status or persisted_assembly_status)
                )
                final_install_status = (
                    persisted_install_status
                    if final_install_completed_at is not None
                    else (install_status or persisted_install_status)
                )

                if not schedule_info:
                    if final_assembly_completed_at is None and _safe_text(final_assembly_status).casefold() != TASK_STATUS_COMPLETED.casefold():
                        final_assembly_status = TASK_STATUS_QUEUED
                    if final_install_completed_at is None and _safe_text(final_install_status).casefold() != TASK_STATUS_COMPLETED.casefold():
                        final_install_status = TASK_STATUS_QUEUED

                # Explicit detail completion timestamp is the only source of truth for completed stage.
                if (
                    final_assembly_completed_at is None
                    and _safe_text(final_assembly_status).casefold() == TASK_STATUS_COMPLETED.casefold()
                ):
                    final_assembly_status = TASK_STATUS_IN_PROGRESS if assembly_started_at else TASK_STATUS_QUEUED
                if (
                    final_install_completed_at is None
                    and _safe_text(final_install_status).casefold() == TASK_STATUS_COMPLETED.casefold()
                ):
                    final_install_status = TASK_STATUS_IN_PROGRESS if install_started_at else TASK_STATUS_QUEUED

                assembly_days_count, assembly_hours = _calculate_stage_metrics(
                    started_at=assembly_started_at,
                    completed_at=final_assembly_completed_at,
                    fallback_days=int(schedule_info.get("assembly_days_count") or 0),
                    effective_minutes=int(schedule_info.get("assembly_effective_minutes") or 0),
                )
                install_days_count, install_hours = _calculate_stage_metrics(
                    started_at=install_started_at,
                    completed_at=final_install_completed_at,
                    fallback_days=int(schedule_info.get("install_days_count") or 0),
                    effective_minutes=int(schedule_info.get("install_effective_minutes") or 0),
                )
                planned_hours, _ = _calculate_planned_hours(
                    item_value=Decimal(record[12] or 0),
                    assembly_worker=assembly_worker or "-",
                    install_worker=install_worker or "-",
                    day_cost=day_cost,
                    workday_hours=workday_hours,
                )
                asm_mins = int(schedule_info.get("assembly_effective_minutes") or 0)
                inst_mins = int(schedule_info.get("install_effective_minutes") or 0)
                if asm_mins == 0 and assembly_hours:
                    asm_mins = _parse_duration_minutes(assembly_hours)
                if inst_mins == 0 and install_hours:
                    inst_mins = _parse_duration_minutes(install_hours)
                total_actual_minutes = asm_mins + inst_mins
                total_hours = _format_duration(total_actual_minutes) if total_actual_minutes > 0 else ""


                order_totals[order_number] += _parse_decimal(planned_hours)
                order_stage_details[order_number].append(
                    {
                        "assembly_status": final_assembly_status,
                        "assembly_completed_at": final_assembly_completed_at,
                        "install_status": final_install_status,
                        "install_completed_at": final_install_completed_at,
                        "requires_assembly": requires_assembly,
                        "requires_install": requires_install,
                    }
                )

                part_number_int = _parse_part_number(part_number)
                metal_status = "немає"
                for metal_row in metal_by_order.get(order_number, []):
                    if _part_matches_spec(part_number_int, metal_row["part_spec"]):
                        metal_status = _build_metal_status(
                            metal_row["col3"], metal_row["col4"], metal_row["col5"]
                        )
                        break

                update_values.append(
                    (
                        assembly_worker,
                        assembly_started_at,
                        final_assembly_completed_at,
                        final_assembly_status,
                        assembly_days_count,
                        assembly_hours,
                        install_worker,
                        install_started_at,
                        final_install_completed_at,
                        final_install_status,
                        install_days_count,
                        install_hours,
                        planned_hours,
                        total_hours,
                        metal_status,
                        detail_id,
                    )
                )

            cursor.executemany(
                f"""
                UPDATE {DETAILS_TABLE_NAME}
                SET
                    assembly_worker = %s,
                    assembly_started_at = %s,
                    assembly_completed_at = COALESCE(%s, assembly_completed_at),
                    assembly_status = %s,
                    assembly_days_count = %s,
                    assembly_hours = %s,
                    install_worker = %s,
                    install_started_at = %s,
                    install_completed_at = COALESCE(%s, install_completed_at),
                    install_status = %s,
                    install_days_count = %s,
                    install_hours = %s,
                    planned_hours = %s,
                    total_hours = %s,
                    metal = %s,
                    updated_at = NOW()
                WHERE id = %s
                """,
                update_values,
            )

            if order_totals:
                order_main_updates = [
                    (
                        total,
                        _build_stage_status_distribution(
                            order_stage_details.get(order_number, []),
                            status_key="assembly_status",
                            completed_at_key="assembly_completed_at",
                            required_key="requires_assembly",
                        ),
                        _build_stage_status_distribution(
                            order_stage_details.get(order_number, []),
                            status_key="install_status",
                            completed_at_key="install_completed_at",
                            required_key="requires_install",
                        ),
                        order_number,
                    )
                    for order_number, total in order_totals.items()
                ]
                cursor.executemany(
                    f"""
                    UPDATE {MAIN_TABLE_NAME}
                    SET total_planned_hours = %s,
                        assembly_status = %s,
                        install_status = %s,
                        updated_at = NOW()
                    WHERE order_number = %s
                    """,
                    order_main_updates,
                )

        conn.commit()

    return len(detail_rows)


def enqueue_detail_metrics_recalculation(
    order_numbers: list[str] | None = None, *, source: str = "manual"
) -> int:
    ensure_schema()
    normalized_source = _safe_text(source) or "manual"
    normalized_orders = sorted(
        {_safe_text(value) for value in (order_numbers or []) if _safe_text(value)}
    )

    with get_db_connection() as conn:
        with conn.cursor() as cursor:
            if not normalized_orders:
                cursor.execute(
                    f"""
                    SELECT order_number
                    FROM {MAIN_TABLE_NAME}
                    WHERE TRIM(COALESCE(order_number, '')) <> ''
                    """
                )
                normalized_orders = sorted(
                    {_safe_text(row[0]) for row in cursor.fetchall() if _safe_text(row[0])}
                )

            if not normalized_orders:
                return 0

            cursor.executemany(
                "SELECT assemblers_enqueue_detail_recalc(%s, %s)",
                [(order_number, normalized_source) for order_number in normalized_orders],
            )
        conn.commit()

    return len(normalized_orders)


def pull_detail_metrics_recalc_orders(batch_size: int = 30) -> list[str]:
    ensure_schema()
    normalized_batch_size = max(1, min(int(batch_size or 30), 500))

    with get_db_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                f"""
                WITH picked AS (
                    SELECT order_number
                    FROM {DETAIL_RECALC_QUEUE_TABLE}
                    ORDER BY requested_at
                    LIMIT %s
                    FOR UPDATE SKIP LOCKED
                )
                DELETE FROM {DETAIL_RECALC_QUEUE_TABLE} queue
                USING picked
                WHERE queue.order_number = picked.order_number
                RETURNING queue.order_number
                """,
                (normalized_batch_size,),
            )
            rows = cursor.fetchall()
        conn.commit()

    return [_safe_text(row[0]) for row in rows if _safe_text(row[0])]


def process_detail_metrics_recalc_queue(batch_size: int = 30) -> dict[str, int]:
    order_numbers = pull_detail_metrics_recalc_orders(batch_size=batch_size)
    if not order_numbers:
        return {"queued_orders": 0, "updated_rows": 0}

    updated_rows = recalculate_detail_metrics(order_numbers)
    return {"queued_orders": len(order_numbers), "updated_rows": updated_rows}
