from __future__ import annotations

from app.modules.assemblers.db.connection import get_db_connection

from .constants import CLOSED_STATUS, DETAILS_TABLE_NAME, MAIN_TABLE_NAME, SCHEDULE_TASKS_TABLE
from .context import _load_detail_production_context, _split_csv_text, _task_matches_detail
from .schema import ensure_schema
from .status import _build_detail_status_value, _normalize_execution_status
from .utils import (
    _format_date,
    _format_datetime,
    _format_money,
    _normalize_limit,
    _normalize_offset,
    _safe_text,
)
from decimal import Decimal


def load_detail_rows(
    offset: int = 0,
    limit: int = 30,
    order_number: str = "",
    customer: str = "",
    product: str = "",
    requires_assembly: str = "",
    requires_install: str = "",
) -> dict:
    ensure_schema()
    normalized_order_number = _safe_text(order_number)
    normalized_customer = _safe_text(customer)
    normalized_product = _safe_text(product)
    normalized_requires_assembly = _safe_text(requires_assembly).lower()
    normalized_requires_install = _safe_text(requires_install).lower()

    offset = _normalize_offset(offset)
    limit = _normalize_limit(limit)

    where_parts = []
    where_params: list[object] = []
    if normalized_order_number:
        where_parts.append("TRIM(COALESCE(d.order_number, '')) ILIKE %s")
        where_params.append(f"%{normalized_order_number}%")
    if normalized_customer:
        where_parts.append("TRIM(COALESCE(d.customer, '')) ILIKE %s")
        where_params.append(f"%{normalized_customer}%")
    if normalized_product:
        where_parts.append("TRIM(COALESCE(d.product_name, '')) ILIKE %s")
        where_params.append(f"%{normalized_product}%")
    if normalized_requires_assembly == "yes":
        where_parts.append("d.requires_assembly = TRUE")
    elif normalized_requires_assembly == "no":
        where_parts.append("d.requires_assembly = FALSE")
    if normalized_requires_install == "yes":
        where_parts.append("d.requires_install = TRUE")
    elif normalized_requires_install == "no":
        where_parts.append("d.requires_install = FALSE")
    where_parts.append("TRIM(COALESCE(m.status, '')) <> %s")
    where_params.append(CLOSED_STATUS)
    where_sql = f"WHERE {' AND '.join(where_parts)}" if where_parts else ""

    with get_db_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                f"""
                SELECT COUNT(*)
                FROM {DETAILS_TABLE_NAME} d
                LEFT JOIN {MAIN_TABLE_NAME} m ON m.order_number = d.order_number
                {where_sql}
                """,
                tuple(where_params),
            )
            total = int(cursor.fetchone()[0] or 0)

            cursor.execute("SELECT to_regclass(%s)", (SCHEDULE_TASKS_TABLE,))
            schedule_table_exists = cursor.fetchone()[0] is not None

            cursor.execute(
                f"""
                SELECT
                    d.order_number,
                    d.part_number,
                    d.customer,
                    d.product_name,
                    d.planned_assembly_due_at,
                    d.assembly_worker,
                    d.assembly_started_at,
                    d.assembly_completed_at,
                    d.assembly_days_count,
                    d.assembly_hours,
                    d.assembly_status,
                    d.planned_install_due_at,
                    d.install_worker,
                    d.install_started_at,
                    d.install_completed_at,
                    d.install_days_count,
                    d.install_hours,
                    d.install_status,
                    COALESCE(m.order_type, d.item_type),
                    d.constructor_status,
                    d.production_launches,
                    d.production_completed,
                    d.metal,
                    d.glass_eta,
                    d.glass_delivered,
                    d.planned_hours,
                    d.item_value,
                    d.requires_assembly,
                    d.requires_install,
                    d.total_hours,
                    d.assembly_percent,
                    d.install_percent,
                    d.item_percent,
                    COALESCE((SELECT pause_reason FROM {SCHEDULE_TASKS_TABLE} WHERE order_number = d.order_number AND task_type = 'assembly' AND status = 'Пауза' ORDER BY updated_at DESC LIMIT 1), ''),
                    COALESCE((SELECT pause_reason FROM {SCHEDULE_TASKS_TABLE} WHERE order_number = d.order_number AND task_type = 'install' AND status = 'Пауза' ORDER BY updated_at DESC LIMIT 1), '')
                FROM {DETAILS_TABLE_NAME} d
                LEFT JOIN {MAIN_TABLE_NAME} m ON m.order_number = d.order_number
                {where_sql}
                ORDER BY d.created_at DESC, d.id DESC
                LIMIT %s OFFSET %s
                """,
                tuple(where_params + [limit, offset]),
            )
            detail_rows = cursor.fetchall()

            today_schedule_flags: dict[tuple[str, str, str], dict[str, bool]] = {}
            if schedule_table_exists and detail_rows:
                order_numbers = sorted({_safe_text(row[0]) for row in detail_rows if _safe_text(row[0])})
                if order_numbers:
                    cursor.execute(
                        f"""
                        SELECT
                            TRIM(COALESCE(order_number, '')),
                            TRIM(COALESCE(task_type, '')),
                            TRIM(COALESCE(part_number, '')),
                            TRIM(COALESCE(product_name, ''))
                        FROM {SCHEDULE_TASKS_TABLE}
                        WHERE TRIM(COALESCE(order_number, '')) = ANY(%s)
                          AND scheduled_for = CURRENT_DATE
                        """,
                        (order_numbers,),
                    )
                    schedule_rows = cursor.fetchall()

                    schedule_by_order: dict[str, list[tuple[str, set[str], set[str]]]] = {}
                    for order_number, task_type, task_part_number, task_product_name in schedule_rows:
                        task_part_numbers = {value.casefold() for value in _split_csv_text(task_part_number)}
                        task_product_names = {value.casefold() for value in _split_csv_text(task_product_name)}
                        schedule_by_order.setdefault(order_number, []).append(
                            (task_type, task_part_numbers, task_product_names)
                        )

                    for row in detail_rows:
                        order_value = _safe_text(row[0])
                        part_value = _safe_text(row[1])
                        product_value = _safe_text(row[3])
                        detail_key = (order_value, part_value, product_value)
                        detail_flags = {"assembly": False, "install": False}
                        for task_type, task_part_numbers, task_product_names in schedule_by_order.get(order_value, []):
                            if _task_matches_detail(
                                detail_part_number=part_value,
                                detail_product_name=product_value,
                                task_part_numbers=task_part_numbers,
                                task_product_names=task_product_names,
                            ):
                                if task_type == 'assembly':
                                    detail_flags['assembly'] = True
                                elif task_type == 'install':
                                    detail_flags['install'] = True
                        today_schedule_flags[detail_key] = detail_flags

    production_context = _load_detail_production_context(
        [(_safe_text(record[0]), _safe_text(record[1])) for record in detail_rows]
    )

    rows = []
    for record in detail_rows:
        order_num = _safe_text(record[0]) or "-"
        part_number = _safe_text(record[1]) or "-"
        product_name = _safe_text(record[3])
        production_info = production_context.get((order_num, part_number), {})
        assembly_days_count = int(record[8] or 0)
        install_days_count = int(record[15] or 0)
        today_schedule = today_schedule_flags.get((order_num, part_number, product_name), {})
        rows.append(
            {
                "order_number": order_num,
                "part_number": part_number,
                "customer": _safe_text(record[2]) or "-",
                "product_name": product_name or "-",
                "planned_assembly_due_at": _format_date(record[4]),
                "assembly_worker": _safe_text(record[5]) or "-",
                "assembly_started_at": _format_datetime(record[6]),
                "assembly_completed_at": _format_datetime(record[7]),
                "assembly_days": str(assembly_days_count),
                "assembly_hours": _safe_text(record[9]) or "—",
                "assembly_status": _normalize_execution_status(
                    _safe_text(record[10]),
                    record[7],
                    assembly_days_count,
                    is_required=bool(record[27]),
                    skipped_label="Без збірки",
                    has_today_schedule=bool(today_schedule.get("assembly")),
                ),
                "planned_install_due_at": _format_date(record[11]),
                "install_worker": _safe_text(record[12]) or "—",
                "install_started_at": _format_datetime(record[13]),
                "install_completed_at": _format_datetime(record[14]),
                "install_days": str(install_days_count),
                "install_hours": _safe_text(record[16]) or "—",
                "install_status": _normalize_execution_status(
                    _safe_text(record[17]),
                    record[14],
                    install_days_count,
                    is_required=bool(record[28]),
                    skipped_label="Без монтажу",
                    has_today_schedule=bool(today_schedule.get("install")),
                ),
                "assembly_paused": bool(_safe_text(record[33])),
                "assembly_pause_reason": _safe_text(record[33]) or "",
                "install_paused": bool(_safe_text(record[34])),
                "install_pause_reason": _safe_text(record[34]) or "",
                "detail_status": _build_detail_status_value(
                    assembly_status=_normalize_execution_status(
                        _safe_text(record[10]),
                        record[7],
                        assembly_days_count,
                        is_required=bool(record[27]),
                        skipped_label="Без збірки",
                        has_today_schedule=bool(today_schedule.get("assembly")),
                    ),
                    install_status=_normalize_execution_status(
                        _safe_text(record[17]),
                        record[14],
                        install_days_count,
                        is_required=bool(record[28]),
                        skipped_label="Без монтажу",
                        has_today_schedule=bool(today_schedule.get("install")),
                    ),
                    assembly_completed_at=record[7],
                    install_completed_at=record[14],
                ),
                "item_type": _safe_text(record[18]) or "—",
                "constructor_status": _safe_text(record[19]) or "—",
                "production_launches": production_info.get(
                    "production_launches_display", record[20] or "не запущено"
                ),
                "production_completed": production_info.get("production_completed", record[21] or 0),
                "metal": _safe_text(record[22]) or "—",
                "glass_eta": _safe_text(record[23]) or "—",
                "glass_delivered": _safe_text(record[24]) or "—",
                "planned_hours": _safe_text(record[25]) or "0",
                "item_value": _format_money(Decimal(record[26] or 0)),
                "requires_assembly": bool(record[27]),
                "requires_install": bool(record[28]),
                "total_hours": _safe_text(record[29]) or "0",
                "assembly_percent": float(record[30] or 0),
                "install_percent": float(record[31] or 0),
                "item_percent": float(record[32] or 0),
            }
        )

    return {
        "rows": rows,
        "total": total,
        "offset": offset,
        "limit": limit,
        "has_more": offset + limit < total,
    }


def search_detail_rows_by_order(order_number: str) -> dict:
    ensure_schema()
    normalized_order = _safe_text(order_number)
    if not normalized_order:
        return {
            "rows": [],
            "order_found": False,
            "is_closed": False,
        }

    with get_db_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                f"""
                SELECT TRIM(COALESCE(status, ''))
                FROM {MAIN_TABLE_NAME}
                WHERE TRIM(COALESCE(order_number, '')) = %s
                LIMIT 1
                """,
                (normalized_order,),
            )
            order_row = cursor.fetchone()
            if not order_row:
                return {
                    "rows": [],
                    "order_found": False,
                    "is_closed": False,
                }

            order_status = _safe_text(order_row[0])
            if order_status.casefold() == CLOSED_STATUS.casefold():
                return {
                    "rows": [],
                    "order_found": True,
                    "is_closed": True,
                }

            cursor.execute(
                f"""
                SELECT
                    d.part_number,
                    d.customer,
                    d.product_name,
                    d.constructor_status,
                    d.assembly_status,
                    d.assembly_completed_at,
                    d.install_status,
                    d.install_completed_at,
                    d.requires_assembly,
                    d.requires_install,
                    d.planned_assembly_due_at,
                    d.planned_install_due_at
                FROM {DETAILS_TABLE_NAME} d
                LEFT JOIN {MAIN_TABLE_NAME} m ON m.order_number = d.order_number
                WHERE TRIM(COALESCE(d.order_number, '')) = %s
                  AND TRIM(COALESCE(m.status, '')) <> %s
                ORDER BY d.id
                """,
                (normalized_order, CLOSED_STATUS),
            )
            rows = cursor.fetchall()

    return {
        "rows": [
            {
                "part_number": _safe_text(row[0]) or "—",
                "customer": _safe_text(row[1]) or "—",
                "product_name": _safe_text(row[2]) or "—",
                "constructor_status": _safe_text(row[3]) or "—",
                "assembly_status": _safe_text(row[4]) or "",
                "assembly_completed_at": row[5],
                "install_status": _safe_text(row[6]) or "",
                "install_completed_at": row[7],
                "requires_assembly": bool(row[8]),
                "requires_install": bool(row[9]),
                "planned_assembly_due_at": _format_date(row[10]),
                "planned_install_due_at": _format_date(row[11]),
                "product_status": (
                    "Завершено"
                    if (
                        (not bool(row[8]) or bool(row[5]) or _safe_text(row[4]).casefold() == "завершено")
                        and (not bool(row[9]) or bool(row[7]) or _safe_text(row[6]).casefold() == "завершено")
                    )
                    else "Не завершено"
                ),
            }
            for row in rows
        ],
        "order_found": True,
        "is_closed": False,
    }
