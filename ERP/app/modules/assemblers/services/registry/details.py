from __future__ import annotations

from app.modules.assemblers.db.connection import get_db_connection

from .constants import CLOSED_STATUS, DETAILS_TABLE_NAME, MAIN_TABLE_NAME
from .context import _load_detail_production_context
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
) -> dict:
    ensure_schema()
    normalized_order_number = _safe_text(order_number)
    normalized_customer = _safe_text(customer)
    normalized_product = _safe_text(product)

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
                    d.item_percent
                FROM {DETAILS_TABLE_NAME} d
                LEFT JOIN {MAIN_TABLE_NAME} m ON m.order_number = d.order_number
                {where_sql}
                ORDER BY d.created_at DESC, d.id DESC
                LIMIT %s OFFSET %s
                """,
                tuple(where_params + [limit, offset]),
            )
            detail_rows = cursor.fetchall()

    production_context = _load_detail_production_context(
        [(_safe_text(record[0]), _safe_text(record[1])) for record in detail_rows]
    )

    rows = []
    for record in detail_rows:
        order_num = _safe_text(record[0]) or "-"
        part_number = _safe_text(record[1]) or "-"
        production_info = production_context.get((order_num, part_number), {})
        assembly_days_count = int(record[8] or 0)
        install_days_count = int(record[15] or 0)
        rows.append(
            {
                "order_number": order_num,
                "part_number": part_number,
                "customer": _safe_text(record[2]) or "-",
                "product_name": _safe_text(record[3]) or "-",
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
                ),
                "detail_status": _build_detail_status_value(
                    assembly_status=_normalize_execution_status(
                        _safe_text(record[10]),
                        record[7],
                        assembly_days_count,
                        is_required=bool(record[27]),
                        skipped_label="Без збірки",
                    ),
                    install_status=_normalize_execution_status(
                        _safe_text(record[17]),
                        record[14],
                        install_days_count,
                        is_required=bool(record[28]),
                        skipped_label="Без монтажу",
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
                "item_percent": float(record[30] or 0),
            }
        )

    return {
        "rows": rows,
        "total": total,
        "offset": offset,
        "limit": limit,
        "has_more": offset + limit < total,
    }


def search_detail_rows_by_order(order_number: str) -> list[dict]:
    ensure_schema()
    normalized_order = _safe_text(order_number)
    if not normalized_order:
        return []

    with get_db_connection() as conn:
        with conn.cursor() as cursor:
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
                    d.requires_install
                FROM {DETAILS_TABLE_NAME} d
                LEFT JOIN {MAIN_TABLE_NAME} m ON m.order_number = d.order_number
                WHERE TRIM(COALESCE(d.order_number, '')) = %s
                  AND TRIM(COALESCE(m.status, '')) <> %s
                ORDER BY d.id
                """,
                (normalized_order, CLOSED_STATUS),
            )
            rows = cursor.fetchall()

    return [
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
    ]
