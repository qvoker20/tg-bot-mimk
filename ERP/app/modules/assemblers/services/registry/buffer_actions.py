from __future__ import annotations

from collections import defaultdict

from app.modules.assemblers.db.connection import get_db_connection
from app.modules.assemblers.services.activity_log import record_activity_event

from .constants import (
    ACTIVE_STATUS,
    CLOSED_STATUS,
    DATA_DESIGNER_TABLE,
    DATA_PRODUCTION_TABLE,
    DETAILS_TABLE_NAME,
    MAIN_TABLE_NAME,
    RECLAMATION_STATUS,
)
from .recalc import enqueue_detail_metrics_recalculation
from .recalc import recalculate_detail_metrics
from .schema import ensure_schema
from .utils import (
    _is_done_status,
    _parse_decimal,
    _parse_uk_date,
    _safe_text,
)


def load_transferred_order_numbers() -> set[str]:
    ensure_schema()
    with get_db_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute(f"SELECT order_number FROM {MAIN_TABLE_NAME}")
            return {_safe_text(row[0]) for row in cursor.fetchall() if _safe_text(row[0])}


def backfill_active_distribution_status() -> int:
    ensure_schema()
    with get_db_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                f"""
                UPDATE {MAIN_TABLE_NAME}
                SET status = %s,
                    updated_at = NOW()
                WHERE TRIM(COALESCE(status, '')) <> %s
                  AND TRIM(COALESCE(status, '')) <> %s
                  AND TRIM(COALESCE(status, '')) <> %s
                """,
                (ACTIVE_STATUS, CLOSED_STATUS, RECLAMATION_STATUS, ACTIVE_STATUS),
            )
            updated_rows = cursor.rowcount
        conn.commit()
    return updated_rows


def transfer_buffer_orders(order_numbers: list[str], actor: dict | None = None) -> dict:
    ensure_schema()
    normalized_orders = [_safe_text(value) for value in order_numbers if _safe_text(value)]
    if not normalized_orders:
        return {"inserted_orders": 0, "inserted_details": 0}

    with get_db_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                f"""
                SELECT
                    column_1,
                    column_2,
                    column_3,
                    column_6,
                    column_7,
                    column_9,
                    column_10,
                    column_11,
                    column_12,
                    column_30,
                    column_31,
                    column_32
                FROM {DATA_DESIGNER_TABLE}
                WHERE TRIM(COALESCE(column_1, '')) = ANY(%s)
                ORDER BY column_1, id
                """,
                (normalized_orders,),
            )
            designer_rows = cursor.fetchall()

            cursor.execute(
                f"""
                SELECT
                    column_1,
                    column_9
                FROM {DATA_PRODUCTION_TABLE}
                WHERE TRIM(COALESCE(column_1, '')) = ANY(%s)
                ORDER BY column_1, id
                """,
                (normalized_orders,),
            )
            production_rows = cursor.fetchall()

            grouped_production: dict[str, list[str]] = defaultdict(list)
            for order_number, status in production_rows:
                grouped_production[_safe_text(order_number)].append(_safe_text(status))

            grouped_orders: dict[str, list[dict]] = defaultdict(list)
            for record in designer_rows:
                order_number = _safe_text(record[0])
                if not order_number:
                    continue
                grouped_orders[order_number].append(
                    {
                        "order_number": order_number,
                        "part_number": record[1],
                        "customer": record[2],
                        "product_name": record[3],
                        "manager_name": record[4],
                        "order_type": record[5],
                        "item_value": record[6],
                        "constructor_name": record[7],
                        "constructor_completed_at": record[8],
                        "signed_at": record[9],
                        "contract_due_at": record[11] or record[10],
                    }
                )

            inserted_orders = 0
            inserted_details = 0

            for order_number, rows in grouped_orders.items():
                first_row = rows[0]
                contract_due_at = _parse_uk_date(first_row.get("contract_due_at", ""))
                signed_at = _parse_uk_date(first_row.get("signed_at", ""))

                cursor.execute(
                    f"""
                    INSERT INTO {MAIN_TABLE_NAME} (
                        order_number,
                        customer,
                        order_type,
                        status,
                        signed_at,
                        contract_due_at,
                        manager_name,
                        constructor_name,
                        planned_install_at,
                        updated_at
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, NOW())
                    ON CONFLICT (order_number)
                    DO UPDATE SET
                        customer = EXCLUDED.customer,
                        order_type = EXCLUDED.order_type,
                        status = CASE
                            WHEN TRIM(COALESCE({MAIN_TABLE_NAME}.status, '')) IN %s THEN {MAIN_TABLE_NAME}.status
                            ELSE EXCLUDED.status
                        END,
                        signed_at = EXCLUDED.signed_at,
                        contract_due_at = EXCLUDED.contract_due_at,
                        manager_name = EXCLUDED.manager_name,
                        constructor_name = EXCLUDED.constructor_name,
                        planned_install_at = EXCLUDED.planned_install_at,
                        updated_at = NOW()
                    """,
                    (
                        order_number,
                        _safe_text(first_row.get("customer")),
                        _safe_text(first_row.get("order_type")),
                        ACTIVE_STATUS,
                        signed_at,
                        contract_due_at,
                        _safe_text(first_row.get("manager_name")),
                        _safe_text(first_row.get("constructor_name")),
                        contract_due_at,
                        (CLOSED_STATUS, RECLAMATION_STATUS),
                    ),
                )
                inserted_orders += 1

                cursor.execute(
                    f"DELETE FROM {DETAILS_TABLE_NAME} WHERE order_number = %s",
                    (order_number,),
                )

                production_statuses = grouped_production.get(order_number, [])
                production_total = len(production_statuses)
                production_done = sum(1 for value in production_statuses if _is_done_status(value))

                detail_values = []
                for row in rows:
                    detail_values.append(
                        (
                            order_number,
                            _safe_text(row.get("part_number")),
                            _safe_text(row.get("customer")),
                            _safe_text(row.get("product_name")),
                            None,
                            None,
                            _safe_text(row.get("order_type")),
                            "Завершено" if _parse_uk_date(row.get("constructor_completed_at", "")) else "",
                            production_total,
                            production_done,
                            _parse_decimal(row.get("item_value")),
                        )
                    )

                if detail_values:
                    cursor.executemany(
                        f"""
                        INSERT INTO {DETAILS_TABLE_NAME} (
                            order_number,
                            part_number,
                            customer,
                            product_name,
                            planned_assembly_due_at,
                            planned_install_due_at,
                            item_type,
                            constructor_status,
                            production_launches,
                            production_completed,
                            item_value
                        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                        """,
                        detail_values,
                    )
                    inserted_details += len(detail_values)

        conn.commit()

    # Force immediate consistency for UI right after transfer.
    # Queue is still used in other flows, but transfer should be visible instantly.
    recalculate_detail_metrics(normalized_orders)

    record_activity_event(
        action_key="buffer.transfer",
        action_label="Перенесено з буфера",
        description=f"Перенесено {inserted_orders} замовлень і {inserted_details} деталей з буфера в головну",
        actor=actor,
        entity_type="main_order_batch",
        entity_id=", ".join(normalized_orders[:10]),
        order_number=", ".join(normalized_orders[:10]),
        subdivision="",
        source_table=MAIN_TABLE_NAME,
        source_op="INSERT",
        details={
            "inserted_orders": inserted_orders,
            "inserted_details": inserted_details,
            "orders": normalized_orders[:25],
        },
    )

    return {"inserted_orders": inserted_orders, "inserted_details": inserted_details}


def close_buffer_orders(
    order_numbers: list[str], user: dict | None, analyze_only: bool = False
) -> dict:
    normalized_orders = []
    seen_orders: set[str] = set()
    for value in order_numbers:
        normalized = _safe_text(value)
        if not normalized or normalized in seen_orders:
            continue
        seen_orders.add(normalized)
        normalized_orders.append(normalized)

    if not normalized_orders:
        return {
            "requested_orders": 0,
            "already_closed_orders": 0,
            "orders_to_close": [],
            "inserted_orders": 0,
            "inserted_details": 0,
            "closed_orders": 0,
        }

    ensure_schema()
    already_closed: set[str] = set()
    with get_db_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                f"""
                SELECT order_number
                FROM {MAIN_TABLE_NAME}
                WHERE order_number = ANY(%s)
                  AND TRIM(COALESCE(status, '')) IN %s
                """,
                (normalized_orders, (CLOSED_STATUS, RECLAMATION_STATUS)),
            )
            already_closed = {_safe_text(row[0]) for row in cursor.fetchall() if _safe_text(row[0])}

    orders_to_close = [value for value in normalized_orders if value not in already_closed]

    if analyze_only:
        return {
            "requested_orders": len(normalized_orders),
            "already_closed_orders": len(already_closed),
            "orders_to_close": orders_to_close,
            "inserted_orders": 0,
            "inserted_details": 0,
            "closed_orders": 0,
        }

    if not orders_to_close:
        return {
            "requested_orders": len(normalized_orders),
            "already_closed_orders": len(already_closed),
            "orders_to_close": [],
            "inserted_orders": 0,
            "inserted_details": 0,
            "closed_orders": 0,
        }

    transfer_result = transfer_buffer_orders(orders_to_close, actor=user)
    closer_name = _safe_text((user or {}).get("name")) or "Корисувач"
    closer_role = _safe_text((user or {}).get("role")) or "-"
    closer_telegram_id = (user or {}).get("telegram_id")

    with get_db_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                f"""
                UPDATE {MAIN_TABLE_NAME}
                SET status = %s,
                    closed_at = NOW(),
                    closed_by_name = %s,
                    closed_by_role = %s,
                    closed_by_telegram_id = %s,
                    updated_at = NOW()
                WHERE order_number = ANY(%s)
                  AND TRIM(COALESCE(status, '')) NOT IN %s
                """,
                (
                    CLOSED_STATUS,
                    closer_name,
                    closer_role,
                    closer_telegram_id,
                    orders_to_close,
                    (CLOSED_STATUS, RECLAMATION_STATUS),
                ),
            )
            closed_orders = cursor.rowcount
        conn.commit()

    enqueue_detail_metrics_recalculation(orders_to_close, source="close_buffer_orders")

    record_activity_event(
        action_key="buffer.close",
        action_label="Закрито замовлення",
        description=f"Закрито {closed_orders} замовлень з буфера",
        actor=user,
        entity_type="main_order_batch",
        entity_id=", ".join(orders_to_close[:10]),
        order_number=", ".join(orders_to_close[:10]),
        subdivision="",
        source_table=MAIN_TABLE_NAME,
        source_op="UPDATE",
        details={
            "requested_orders": len(normalized_orders),
            "closed_orders": closed_orders,
            "orders_to_close": orders_to_close[:25],
        },
    )

    return {
        "requested_orders": len(normalized_orders),
        "already_closed_orders": len(already_closed),
        "orders_to_close": orders_to_close,
        **transfer_result,
        "closed_orders": closed_orders,
    }


def reopen_closed_orders(order_numbers: list[str], user: dict | None) -> dict:
    normalized_orders = [_safe_text(value) for value in order_numbers if _safe_text(value)]
    if not normalized_orders:
        return {"reopened_orders": 0}

    ensure_schema()
    with get_db_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                f"""
                UPDATE {MAIN_TABLE_NAME}
                SET status = %s,
                    closed_at = NULL,
                    closed_by_name = '',
                    closed_by_role = '',
                    closed_by_telegram_id = NULL,
                    updated_at = NOW()
                WHERE order_number = ANY(%s)
                  AND TRIM(COALESCE(status, '')) IN %s
                """,
                (ACTIVE_STATUS, normalized_orders, (CLOSED_STATUS, RECLAMATION_STATUS)),
            )
            reopened_orders = cursor.rowcount
        conn.commit()

    enqueue_detail_metrics_recalculation(normalized_orders, source="reopen_closed_orders")

    record_activity_event(
        action_key="buffer.reopen",
        action_label="Повернено замовлення в активні",
        description=f"Повернено {reopened_orders} замовлень з закритих в активні",
        actor=user,
        entity_type="main_order_batch",
        entity_id=", ".join(normalized_orders[:10]),
        order_number=", ".join(normalized_orders[:10]),
        subdivision="",
        source_table=MAIN_TABLE_NAME,
        source_op="UPDATE",
        details={
            "reopened_orders": reopened_orders,
            "orders": normalized_orders[:25],
        },
    )

    return {"reopened_orders": reopened_orders}
