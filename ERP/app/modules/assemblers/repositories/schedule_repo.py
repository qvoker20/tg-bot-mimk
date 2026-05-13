from __future__ import annotations

from datetime import date

from app.modules.assemblers.db.connection import get_db_connection
from app.modules.assemblers.db.tables import (
    ASSEMBLERS_STAFF_TABLE,
    DETAILS_TABLE_NAME,
    TELEGRAM_USERS_TABLE,
)
from app.modules.assemblers.services.registry.constants import MAIN_TABLE_NAME

from app.modules.assemblers.services.schedule.constants import (
    SCHEDULE_TASKS_TABLE,
    TASK_STATUS_COMPLETED,
    TASK_STATUS_IN_PROGRESS,
    TASK_STATUS_NO_EXECUTION,
    TASK_STATUS_PAUSED,
    TASK_STATUS_QUEUED,
)


def _safe_text(value) -> str:
    return " ".join(str(value or "").split()).strip()


def fetch_schedule_week_rows(*, subdivision: str, week_start: date, week_end: date) -> list[tuple]:
    with get_db_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                f"""
                SELECT
                    id,
                    source_user_id,
                    assembler_name,
                    scheduled_for,
                    task_type,
                    status,
                    order_number,
                    customer,
                    part_number,
                    product_name,
                    constructor_status,
                    description,
                    started_at,
                    paused_at,
                    completed_at,
                    pause_reason,
                    started_location_label,
                    started_latitude,
                    started_longitude,
                    started_accuracy,
                    completed_location_label,
                    completed_latitude,
                    completed_longitude,
                    completed_accuracy
                FROM {SCHEDULE_TASKS_TABLE}
                WHERE subdivision = %s
                  AND scheduled_for BETWEEN %s AND %s
                ORDER BY scheduled_for, source_user_id, id
                """,
                (subdivision, week_start, week_end),
            )
            return cursor.fetchall()


def fetch_user_day_task_rows(*, source_user_id: int, target_day: date) -> list[tuple]:
    with get_db_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                f"""
                SELECT
                    id,
                    source_user_id,
                    assembler_name,
                    scheduled_for,
                    task_type,
                    status,
                    order_number,
                    customer,
                    part_number,
                    product_name,
                    constructor_status,
                    description,
                    started_at,
                    paused_at,
                    completed_at,
                    pause_reason,
                    started_location_label,
                    started_latitude,
                    started_longitude,
                    started_accuracy,
                    completed_location_label,
                    completed_latitude,
                    completed_longitude,
                    completed_accuracy
                FROM {SCHEDULE_TASKS_TABLE}
                WHERE source_user_id = %s
                  AND scheduled_for = %s
                ORDER BY
                    CASE status
                        WHEN %s THEN 0
                        WHEN %s THEN 1
                        WHEN %s THEN 2
                        WHEN %s THEN 3
                        WHEN %s THEN 4
                        ELSE 5
                    END,
                    scheduled_for,
                    id
                """,
                (
                    source_user_id,
                    target_day,
                    TASK_STATUS_IN_PROGRESS,
                    TASK_STATUS_PAUSED,
                    TASK_STATUS_QUEUED,
                    TASK_STATUS_COMPLETED,
                    TASK_STATUS_NO_EXECUTION,
                ),
            )
            return cursor.fetchall()


def fetch_order_customer_map(order_numbers: list[str]) -> dict[str, str]:
    normalized_orders = [_safe_text(order_number) for order_number in order_numbers if _safe_text(order_number)]
    if not normalized_orders:
        return {}

    with get_db_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                f"""
                SELECT
                    order_number,
                    MAX(customer)
                FROM (
                    SELECT
                        TRIM(COALESCE(order_number, '')) AS order_number,
                        NULLIF(TRIM(COALESCE(customer, '')), '') AS customer,
                        1 AS priority
                    FROM {MAIN_TABLE_NAME}
                    WHERE TRIM(COALESCE(order_number, '')) = ANY(%s)

                    UNION ALL

                    SELECT
                        TRIM(COALESCE(order_number, '')) AS order_number,
                        NULLIF(TRIM(COALESCE(customer, '')), '') AS customer,
                        2 AS priority
                    FROM {DETAILS_TABLE_NAME}
                    WHERE TRIM(COALESCE(order_number, '')) = ANY(%s)
                ) AS source_rows
                WHERE customer IS NOT NULL
                GROUP BY order_number
                """,
                (normalized_orders, normalized_orders),
            )
            rows = cursor.fetchall()

    return {
        _safe_text(row[0]): _safe_text(row[1])
        for row in rows
        if _safe_text(row[0]) and _safe_text(row[1])
    }


def fetch_allowed_workers(*, subdivision: str, source_user_ids: list[int]) -> dict[int, str]:
    if not source_user_ids:
        return {}

    with get_db_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                f"""
                SELECT s.source_user_id, COALESCE(u.name, '')
                FROM {ASSEMBLERS_STAFF_TABLE} s
                LEFT JOIN {TELEGRAM_USERS_TABLE} u ON u.id = s.source_user_id
                WHERE s.subdivision = %s
                  AND s.source_user_id = ANY(%s)
                """,
                (subdivision, source_user_ids),
            )
            rows = cursor.fetchall()

    return {int(row[0]): _safe_text(row[1]) for row in rows}


def fetch_detail_stage_rows_by_order(*, order_number: str) -> list[tuple]:
    normalized_order_number = _safe_text(order_number)
    if not normalized_order_number:
        return []

    with get_db_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                f"""
                SELECT
                    part_number,
                    product_name,
                    assembly_status,
                    assembly_completed_at,
                    install_status,
                    install_completed_at,
                    constructor_status,
                    requires_assembly,
                    requires_install
                FROM {DETAILS_TABLE_NAME}
                WHERE TRIM(COALESCE(order_number, '')) = %s
                """,
                (normalized_order_number,),
            )
            return cursor.fetchall()


def insert_schedule_tasks(insert_values: list[tuple]) -> int:
    if not insert_values:
        return 0

    with get_db_connection() as conn:
        with conn.cursor() as cursor:
            cursor.executemany(
                f"""
                INSERT INTO {SCHEDULE_TASKS_TABLE} (
                    source_user_id,
                    assembler_name,
                    subdivision,
                    scheduled_for,
                    task_type,
                    status,
                    order_number,
                    customer,
                    part_number,
                    product_name,
                    constructor_status,
                    description,
                    updated_at
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, NOW())
                """,
                insert_values,
            )
            return cursor.rowcount


def fetch_tasks_for_edit(*, subdivision: str, task_ids: list[int]) -> list[dict]:
    if not task_ids:
        return []

    with get_db_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                f"""
                SELECT
                    id,
                    source_user_id,
                    assembler_name,
                    scheduled_for,
                    task_type,
                    status,
                    order_number,
                    customer,
                    part_number,
                    product_name,
                    constructor_status,
                    description
                FROM {SCHEDULE_TASKS_TABLE}
                WHERE subdivision = %s
                  AND id = ANY(%s)
                ORDER BY scheduled_for, source_user_id, id
                """,
                (subdivision, task_ids),
            )
            rows = cursor.fetchall()

    return [
        {
            "id": int(row[0]),
            "source_user_id": int(row[1]),
            "assembler_name": _safe_text(row[2]),
            "scheduled_for": row[3],
            "task_type": _safe_text(row[4]),
            "status": _safe_text(row[5]) or TASK_STATUS_QUEUED,
            "order_number": _safe_text(row[6]),
            "customer": _safe_text(row[7]),
            "part_number": _safe_text(row[8]),
            "product_name": _safe_text(row[9]),
            "constructor_status": _safe_text(row[10]),
            "description": _safe_text(row[11]),
        }
        for row in rows
    ]


def delete_schedule_tasks(*, subdivision: str, task_ids: list[int]) -> int:
    if not task_ids:
        return 0

    with get_db_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                f"DELETE FROM {SCHEDULE_TASKS_TABLE} WHERE subdivision = %s AND id = ANY(%s)",
                (subdivision, task_ids),
            )
            return cursor.rowcount


def update_schedule_tasks_parts(
    *,
    subdivision: str,
    task_ids: list[int],
    order_number: str,
    customer: str,
    part_number: str,
    product_name: str,
    constructor_status: str,
) -> int:
    if not task_ids:
        return 0

    with get_db_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                f"""
                UPDATE {SCHEDULE_TASKS_TABLE}
                SET
                    order_number = %s,
                    customer = %s,
                    part_number = %s,
                    product_name = %s,
                    constructor_status = %s,
                    updated_at = NOW()
                WHERE subdivision = %s
                  AND id = ANY(%s)
                """,
                (
                    order_number,
                    customer,
                    part_number,
                    product_name,
                    constructor_status,
                    subdivision,
                    task_ids,
                ),
            )
            return cursor.rowcount


def fetch_task_for_user(*, task_id: int, source_user_id: int) -> tuple | None:
    with get_db_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                f"""
                SELECT
                    id,
                    source_user_id,
                    assembler_name,
                    scheduled_for,
                    task_type,
                    status,
                    order_number,
                    customer,
                    part_number,
                    product_name,
                    constructor_status,
                    description,
                    started_at,
                    paused_at,
                    completed_at,
                    pause_reason,
                    started_location_label,
                    started_latitude,
                    started_longitude,
                    started_accuracy,
                    completed_location_label,
                    completed_latitude,
                    completed_longitude,
                    completed_accuracy,
                    auto_closed_at
                FROM {SCHEDULE_TASKS_TABLE}
                WHERE id = %s
                  AND source_user_id = %s
                LIMIT 1
                """,
                (task_id, source_user_id),
            )
            return cursor.fetchone()


def fetch_task_by_id(task_id: int) -> tuple | None:
    with get_db_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                f"""
                SELECT
                    id,
                    source_user_id,
                    assembler_name,
                    scheduled_for,
                    task_type,
                    status,
                    order_number,
                    customer,
                    part_number,
                    product_name,
                    constructor_status,
                    description,
                    started_at,
                    paused_at,
                    completed_at,
                    pause_reason,
                    started_location_label,
                    started_latitude,
                    started_longitude,
                    started_accuracy,
                    completed_location_label,
                    completed_latitude,
                    completed_longitude,
                    completed_accuracy,
                    auto_closed_at
                FROM {SCHEDULE_TASKS_TABLE}
                WHERE id = %s
                LIMIT 1
                """,
                (task_id,),
            )
            return cursor.fetchone()


def mark_task_started(*, task_id: int, location: dict) -> int:
    with get_db_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                f"""
                UPDATE {SCHEDULE_TASKS_TABLE}
                SET
                    status = %s,
                    started_at = NOW(),
                    paused_at = NULL,
                    completed_at = NULL,
                    pause_reason = '',
                    started_location_label = %s,
                    started_latitude = %s,
                    started_longitude = %s,
                    started_accuracy = %s,
                    updated_at = NOW()
                WHERE id = %s
                """,
                (
                    TASK_STATUS_IN_PROGRESS,
                    location["label"],
                    location["latitude"],
                    location["longitude"],
                    location["accuracy"],
                    task_id,
                ),
            )
            return cursor.rowcount


def mark_task_paused(*, task_id: int, pause_reason: str) -> int:
    with get_db_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                f"""
                UPDATE {SCHEDULE_TASKS_TABLE}
                SET
                    status = %s,
                    paused_at = NOW(),
                    pause_reason = %s,
                    updated_at = NOW()
                WHERE id = %s
                """,
                (TASK_STATUS_PAUSED, pause_reason, task_id),
            )
            return cursor.rowcount


def mark_task_resumed(*, task_id: int) -> int:
    with get_db_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                f"""
                UPDATE {SCHEDULE_TASKS_TABLE}
                SET
                    status = %s,
                    paused_at = NULL,
                    updated_at = NOW()
                WHERE id = %s
                """,
                (TASK_STATUS_IN_PROGRESS, task_id),
            )
            return cursor.rowcount


def mark_task_completed(*, task_id: int, location: dict) -> int:
    with get_db_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                f"""
                UPDATE {SCHEDULE_TASKS_TABLE}
                SET
                    status = %s,
                    completed_at = NOW(),
                    paused_at = NULL,
                    auto_closed_at = NULL,
                    auto_close_note = NULL,
                    completed_location_label = %s,
                    completed_latitude = %s,
                    completed_longitude = %s,
                    completed_accuracy = %s,
                    updated_at = NOW()
                WHERE id = %s
                """,
                (
                    TASK_STATUS_COMPLETED,
                    location["label"],
                    location["latitude"],
                    location["longitude"],
                    location["accuracy"],
                    task_id,
                ),
            )
            return cursor.rowcount


def fetch_detail_rows_for_product_match(*, order_number: str) -> list[tuple]:
    normalized_order_number = _safe_text(order_number)
    if not normalized_order_number:
        return []

    with get_db_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                f"""
                SELECT
                    id,
                    part_number,
                    product_name
                FROM {DETAILS_TABLE_NAME}
                WHERE TRIM(COALESCE(order_number, '')) = %s
                ORDER BY id
                """,
                (normalized_order_number,),
            )
            return cursor.fetchall()


def mark_detail_rows_completed(
    *,
    detail_ids: list[int],
    task_type: str,
    assembler_name: str,
    started_at,
) -> int:
    if not detail_ids:
        return 0

    if task_type == "assembly":
        with get_db_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    f"""
                    UPDATE {DETAILS_TABLE_NAME}
                    SET
                        assembly_worker = CASE
                            WHEN TRIM(COALESCE(assembly_worker, '')) = '' THEN %s
                            ELSE assembly_worker
                        END,
                        assembly_started_at = COALESCE(assembly_started_at, %s),
                        assembly_completed_at = NOW(),
                        assembly_status = %s,
                        updated_at = NOW()
                    WHERE id = ANY(%s)
                    """,
                    (
                        _safe_text(assembler_name),
                        started_at,
                        TASK_STATUS_COMPLETED,
                        detail_ids,
                    ),
                )
                return cursor.rowcount

    if task_type == "install":
        with get_db_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    f"""
                    UPDATE {DETAILS_TABLE_NAME}
                    SET
                        install_worker = CASE
                            WHEN TRIM(COALESCE(install_worker, '')) = '' THEN %s
                            ELSE install_worker
                        END,
                        install_started_at = COALESCE(install_started_at, %s),
                        install_completed_at = NOW(),
                        install_status = %s,
                        updated_at = NOW()
                    WHERE id = ANY(%s)
                    """,
                    (
                        _safe_text(assembler_name),
                        started_at,
                        TASK_STATUS_COMPLETED,
                        detail_ids,
                    ),
                )
                return cursor.rowcount

    return 0


__all__ = [
    "fetch_allowed_workers",
    "fetch_detail_rows_for_product_match",
    "fetch_detail_stage_rows_by_order",
    "fetch_order_customer_map",
    "fetch_schedule_week_rows",
    "fetch_task_by_id",
    "fetch_task_for_user",
    "fetch_tasks_for_edit",
    "fetch_user_day_task_rows",
    "insert_schedule_tasks",
    "mark_detail_rows_completed",
    "mark_task_completed",
    "mark_task_paused",
    "mark_task_resumed",
    "mark_task_started",
    "delete_schedule_tasks",
    "update_schedule_tasks_parts",
]