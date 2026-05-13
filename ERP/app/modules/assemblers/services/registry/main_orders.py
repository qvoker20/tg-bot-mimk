from __future__ import annotations

from collections import defaultdict
from decimal import Decimal
import re

from app.modules.assemblers.db.connection import get_db_connection

from .constants import (
    ACTIVE_STATUS,
    CLOSED_STATUS,
    DETAILS_TABLE_NAME,
    MAIN_TABLE_NAME,
    SCHEDULE_TASKS_TABLE,
    TASK_STATUS_COMPLETED,
    TASK_STATUS_IN_PROGRESS,
    TASK_STATUS_PAUSED,
    TASK_STATUS_QUEUED,
)
from .context import _load_live_order_context
from .recalc import enqueue_detail_metrics_recalculation
from .schema import ensure_schema
from .status import (
    _build_status_distribution,
    _build_stage_status_distribution,
    _build_workers_list,
    _calc_plan_percent,
    _derive_order_status,
    _filter_required_stage_details,
    _has_worker_assignment,
)
from .utils import (
    _clean_free_text,
    _days_until,
    _format_date,
    _format_datetime,
    _format_duration,
    _format_hours,
    _format_money,
    _normalize_datetime,
    _normalize_limit,
    _normalize_offset,
    _build_products_text,
    _count_workers,
    _parse_decimal,
    _parse_uk_date,
    _safe_text,
)


_HEX_COLOR_RE = re.compile(r"^#(?:[0-9a-fA-F]{3}|[0-9a-fA-F]{6})$")
_DEFAULT_NOTE_TEXT_COLOR = "#0f172a"


def _normalize_note_color(value) -> str:
    color = _safe_text(value)
    if not color or not _HEX_COLOR_RE.fullmatch(color):
        return ""
    if len(color) == 4:
        return "#" + "".join(ch * 2 for ch in color[1:]).lower()
    return color.lower()


def _normalize_note_text_color(value) -> str:
    color = _normalize_note_color(value)
    return color or _DEFAULT_NOTE_TEXT_COLOR


def _resolve_detail_stage_status(
    *,
    raw_status,
    completed_at,
    started_at,
    is_required: bool,
    skipped_label: str,
) -> str:
    if not is_required:
        return skipped_label

    if _normalize_datetime(completed_at):
        return TASK_STATUS_COMPLETED

    normalized_status = _safe_text(raw_status)
    if normalized_status and normalized_status != "—":
        return normalized_status

    if _normalize_datetime(started_at):
        return TASK_STATUS_IN_PROGRESS

    return TASK_STATUS_QUEUED


def load_main_rows(
    offset: int = 0,
    limit: int = 30,
    *,
    closed_only: bool = False,
    order_number_query: str = "",
    customer_query: str = "",
    status_query: str = "",
    order_type_query: str = "",
    deadline_bucket: str = "",
) -> dict:
    ensure_schema()
    offset = _normalize_offset(offset)
    limit = _normalize_limit(limit)
    normalized_order_query = _safe_text(order_number_query)
    normalized_customer_query = _safe_text(customer_query)
    normalized_status_query = _safe_text(status_query).casefold()
    normalized_order_type_query = _safe_text(order_type_query).casefold()
    normalized_deadline_bucket = _safe_text(deadline_bucket).casefold()

    filter_clauses = [
        "TRIM(COALESCE(status, '')) = %s"
        if closed_only
        else "TRIM(COALESCE(status, '')) <> %s"
    ]
    filter_params: list[object] = [CLOSED_STATUS]

    if normalized_order_query:
        filter_clauses.append("TRIM(COALESCE(order_number, '')) ILIKE %s")
        filter_params.append(f"%{normalized_order_query}%")

    if normalized_customer_query:
        filter_clauses.append("TRIM(COALESCE(customer, '')) ILIKE %s")
        filter_params.append(f"%{normalized_customer_query}%")

    filter_sql = f"WHERE {' AND '.join(filter_clauses)}"

    with get_db_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                f"""
                SELECT
                    order_number,
                    customer,
                    order_type,
                    status,
                    note,
                    contract_due_at,
                    assembly_status,
                    install_status,
                    assembly_workers,
                    install_workers,
                    recorded_at,
                    address,
                    address_note,
                    materials,
                    constructor_name,
                    assembler_pause_at,
                    manager_name,
                    signed_at,
                    planned_install_at,
                    install_completed_at,
                    closed_at,
                    closed_by_name,
                    closed_by_role,
                    total_planned_hours,
                    note_color,
                    note_text_color
                FROM {MAIN_TABLE_NAME}
                {filter_sql}
                ORDER BY recorded_at DESC, order_number DESC
                """,
                tuple(filter_params),
            )
            order_rows = cursor.fetchall()

            order_numbers = [row[0] for row in order_rows]
            live_context = _load_live_order_context(order_numbers)
            details_by_order: dict[str, list[dict]] = defaultdict(list)
            schedule_tasks_by_order: dict[str, list[dict]] = defaultdict(list)

            if order_numbers:
                cursor.execute("SELECT to_regclass(%s)", (SCHEDULE_TASKS_TABLE,))
                schedule_table_exists = cursor.fetchone()[0] is not None
                if schedule_table_exists:
                    cursor.execute(
                        f"""
                        SELECT
                            TRIM(COALESCE(order_number, '')),
                            scheduled_for,
                            TRIM(COALESCE(task_type, '')),
                            TRIM(COALESCE(status, ''))
                        FROM {SCHEDULE_TASKS_TABLE}
                        WHERE TRIM(COALESCE(order_number, '')) = ANY(%s)
                        """,
                        (order_numbers,),
                    )
                    for schedule_row in cursor.fetchall():
                        schedule_order_number = _safe_text(schedule_row[0])
                        if not schedule_order_number:
                            continue
                        schedule_tasks_by_order[schedule_order_number].append(
                            {
                                "scheduled_for": schedule_row[1],
                                "task_type": schedule_row[2],
                                "status": schedule_row[3],
                            }
                        )

                cursor.execute(
                    f"""
                    SELECT
                        order_number,
                        product_name,
                        item_value,
                        part_number,
                        production_launches,
                        production_completed,
                        constructor_status,
                        assembly_hours,
                        install_hours,
                        planned_assembly_due_at,
                        planned_install_due_at,
                        assembly_status,
                        install_status,
                        assembly_worker,
                        install_worker,
                        assembly_started_at,
                        assembly_completed_at,
                        install_started_at,
                        install_completed_at,
                        requires_assembly,
                        requires_install
                    FROM {DETAILS_TABLE_NAME}
                    WHERE order_number = ANY(%s)
                    ORDER BY order_number, id
                    """,
                    (order_numbers,),
                )
                for record in cursor.fetchall():
                    details_by_order[_safe_text(record[0])].append(
                        {
                            "product_name": record[1],
                            "item_value": record[2],
                            "part_number": record[3],
                            "production_launches": record[4],
                            "production_completed": record[5],
                            "constructor_status": record[6],
                            "assembly_hours": record[7],
                            "install_hours": record[8],
                            "has_assembly_plan": record[9] is not None,
                            "has_install_plan": record[10] is not None,
                            "assembly_status": record[11],
                            "install_status": record[12],
                            "assembly_worker": record[13],
                            "install_worker": record[14],
                            "assembly_started_at": record[15],
                            "assembly_completed_at": record[16],
                            "install_started_at": record[17],
                            "install_completed_at": record[18],
                            "requires_assembly": bool(record[19]),
                            "requires_install": bool(record[20]),
                        }
                    )

    rows = []
    from .utils import _parse_duration_minutes

    def _parse_deadline_days(value) -> int | None:
        text = _safe_text(value)
        if not text or text in {"-", "—"}:
            return None
        try:
            return int(text)
        except (TypeError, ValueError):
            return None

    def _matches_deadline_bucket(days: int | None, bucket: str) -> bool:
        if not bucket:
            return True
        if bucket == "overdue":
            return days is not None and days < 0
        if bucket == "critical":
            return days is not None and 0 <= days <= 9
        if bucket == "upcoming":
            return days is not None and 10 <= days <= 30
        if bucket == "far":
            return days is not None and days > 30
        if bucket == "no_deadline":
            return days is None
        return True

    for record in order_rows:
        order_number = _safe_text(record[0])
        details = details_by_order.get(order_number, [])
        assembly_details = _filter_required_stage_details(details, required_key="requires_assembly")
        install_details = _filter_required_stage_details(details, required_key="requires_install")
        schedule_tasks = schedule_tasks_by_order.get(order_number, [])
        live = live_context.get(order_number, {})
        total_value = sum(
            (Decimal(detail.get("item_value") or 0) for detail in details), start=Decimal("0")
        )
        contract_due_at = record[5]
        actual_minutes = sum(
            _parse_duration_minutes(d.get("assembly_hours") or "")
            + _parse_duration_minutes(d.get("install_hours") or "")
            for d in details
        )

        assembly_started_values = [
            _normalize_datetime(d.get("assembly_started_at"))
            for d in assembly_details
            if _normalize_datetime(d.get("assembly_started_at"))
        ]
        assembly_completed_values = [
            _normalize_datetime(d.get("assembly_completed_at"))
            for d in assembly_details
            if _normalize_datetime(d.get("assembly_completed_at"))
        ]
        first_assembly_started = min(assembly_started_values) if assembly_started_values else None
        all_assembly_completed = bool(assembly_details) and len(assembly_completed_values) == len(assembly_details)
        last_assembly_completed = max(assembly_completed_values) if all_assembly_completed else None

        install_started_values = [
            _normalize_datetime(d.get("install_started_at"))
            for d in install_details
            if _normalize_datetime(d.get("install_started_at"))
        ]
        install_completed_values = [
            _normalize_datetime(d.get("install_completed_at"))
            for d in install_details
            if _normalize_datetime(d.get("install_completed_at"))
        ]

        install_workers_value = _build_workers_list(details, "install_worker")
        if install_workers_value == "-":
            install_workers_value = _safe_text(record[9]) or "-"

        has_assignment = (
            _has_worker_assignment(_safe_text(record[8]))
            or _has_worker_assignment(_safe_text(record[9]))
            or any(
                _has_worker_assignment(detail.get("assembly_worker") or "")
                or _has_worker_assignment(detail.get("install_worker") or "")
                for detail in details
            )
        )

        order_status = _safe_text(record[3]) or ACTIVE_STATUS
        if not closed_only:
            order_status = _derive_order_status(
                details=details,
                schedule_tasks=schedule_tasks,
                has_assignment=has_assignment,
            )

        first_install_started = min(install_started_values) if install_started_values else None
        all_install_completed = bool(install_details) and len(install_completed_values) == len(install_details)
        last_install_completed = max(install_completed_values) if all_install_completed else None

        assembly_hours_minutes = sum(
            _parse_duration_minutes(d.get("assembly_hours") or "") for d in details
        )
        install_hours_minutes = sum(
            _parse_duration_minutes(d.get("install_hours") or "") for d in details
        )

        assembly_workers_list = _build_workers_list(details, "assembly_worker")
        assembly_workers_count = _count_workers(assembly_workers_list)
        install_workers_count = _count_workers(install_workers_value)

        rows.append(
            {
                "order_number": order_number,
                "customer": live.get("customer") or _safe_text(record[1]) or "-",
                "order_type": live.get("order_type") or _safe_text(record[2]) or "-",
                "status": order_status,
                "note": _clean_free_text(record[4]) or "-",
                "note_color": _normalize_note_color(record[24]),
                "note_text_color": _normalize_note_text_color(record[25]),
                "products": live.get("products") or _build_products_text(
                    [detail.get("product_name") for detail in details]
                ),
                "contract_due_at": _format_date(contract_due_at),
                "deadline": _days_until(contract_due_at),
                "planned_hours": _format_hours(Decimal(record[23] or 0)),
                "actual_hours": _format_duration(actual_minutes) if actual_minutes else "-",
                "remaining_hours": "-",
                "planned_assembly_parts": _calc_plan_percent(
                    details,
                    "has_assembly_plan",
                    required_key="requires_assembly",
                ),
                "planned_install_parts": _calc_plan_percent(
                    details,
                    "has_install_plan",
                    required_key="requires_install",
                ),
                "assembly_status": _build_stage_status_distribution(
                    details,
                    status_key="assembly_status",
                    completed_at_key="assembly_completed_at",
                    required_key="requires_assembly",
                ),
                "assembly_started_at": _format_datetime(first_assembly_started),
                "assembly_completed_at": _format_datetime(last_assembly_completed),
                "assembly_hours": _format_duration(assembly_hours_minutes)
                if assembly_hours_minutes
                else "-",
                "assembly_workers_count": assembly_workers_count,
                "install_status": _build_stage_status_distribution(
                    details,
                    status_key="install_status",
                    completed_at_key="install_completed_at",
                    required_key="requires_install",
                ),
                "install_started_at": _format_datetime(first_install_started),
                "install_completed_at": _format_datetime(last_install_completed),
                "install_hours": _format_duration(install_hours_minutes)
                if install_hours_minutes
                else "-",
                "install_workers_count": install_workers_count,
                "assembly_workers": assembly_workers_list,
                "install_workers": install_workers_value,
                "paint_shop": live.get("paint_shop", "-"),
                "paint_status": "-",
                "metal": live.get("metal", "-"),
                "metal_status": live.get("metal_status", "0/0"),
                "veneer": live.get("veneer", "-"),
                "plastic_hpl": live.get("plastic_hpl", "-"),
                "joinery_shop": live.get("joinery_shop", "-"),
                "soft_shop": live.get("soft_shop", "-"),
                "artificial_stone": live.get("artificial_stone", "-"),
                "compact_plate": live.get("compact_plate", "-"),
                "dsp_countertop": live.get("dsp_countertop", "-"),
                "sliding_systems": live.get("sliding_systems", "-"),
                "glass_mirror": live.get("glass_mirror", "-"),
                "glass_status": "-",
                "frame_facades": live.get("frame_facades", "-"),
                "ceramic_granite": live.get("ceramic_granite", "-"),
                "constructor_status": live.get("constructor_status")
                or (details[0].get("constructor_status") if details else "-"),
                "production_status": live.get("production_status")
                or (
                    f"{details[0].get('production_completed', 0)}/{details[0].get('production_launches', 0)}"
                    if details
                    else "-"
                ),
                "order_value": _format_money(total_value),
                "vat": "-",
                "install_percent": "-",
                "assembly_percent": "-",
                "parts_count": live.get("parts_count", len(details)),
                "launches_count": live.get(
                    "launches_count",
                    details[0].get("production_launches", 0) if details else 0,
                ),
                "recorded_at": _format_datetime(record[10]),
                "address": _safe_text(record[11]) or "-",
                "address_note": _safe_text(record[12]) or "-",
                "assembler_stop_note": "-",
                "completion_percent": "-",
                "warehouse_status": "-",
                "warehouse_note": "-",
                "materials": live.get("materials") or _safe_text(record[13]) or "-",
                "constructor_name": live.get("constructor_name") or _safe_text(record[14]) or "-",
                "assembler_pause_at": _format_datetime(record[15]),
                "manager_name": live.get("manager_name") or _safe_text(record[16]) or "-",
                "signed_at": live.get("signed_at") or _format_date(record[17]),
                "planned_install_at": live.get("planned_install_at") or _format_date(record[18]),
                "closed_at": _format_datetime(record[20]),
                "closed_by_name": _safe_text(record[21]) or "-",
                "closed_by_role": _safe_text(record[22]) or "-",
            }
        )

    if normalized_status_query:
        rows = [
            row for row in rows
            if _safe_text(row.get("status")).casefold() == normalized_status_query
        ]

    if normalized_order_type_query:
        rows = [
            row for row in rows
            if _safe_text(row.get("order_type")).casefold() == normalized_order_type_query
        ]

    if normalized_deadline_bucket:
        rows = [
            row for row in rows
            if _matches_deadline_bucket(
                _parse_deadline_days(row.get("deadline")),
                normalized_deadline_bucket,
            )
        ]

    total = len(rows)
    rows = rows[offset: offset + limit]

    return {
        "rows": rows,
        "total": total,
        "offset": offset,
        "limit": limit,
        "has_more": offset + limit < total,
    }


def load_main_filter_options(
    *,
    closed_only: bool = False,
    order_number_query: str = "",
    customer_query: str = "",
) -> dict:
    ensure_schema()
    normalized_order_query = _safe_text(order_number_query)
    normalized_customer_query = _safe_text(customer_query)

    filter_clauses = [
        "TRIM(COALESCE(status, '')) = %s"
        if closed_only
        else "TRIM(COALESCE(status, '')) <> %s"
    ]
    filter_params: list[object] = [CLOSED_STATUS]

    if normalized_order_query:
        filter_clauses.append("TRIM(COALESCE(order_number, '')) ILIKE %s")
        filter_params.append(f"%{normalized_order_query}%")

    if normalized_customer_query:
        filter_clauses.append("TRIM(COALESCE(customer, '')) ILIKE %s")
        filter_params.append(f"%{normalized_customer_query}%")

    filter_sql = f"WHERE {' AND '.join(filter_clauses)}"

    statuses: list[str] = [
        ACTIVE_STATUS,
        "Простой",
        "Збірка",
        "Монтаж",
        "Запланована збірка",
        "Заплановано монтаж",
        TASK_STATUS_PAUSED,
        TASK_STATUS_COMPLETED,
    ]
    status_seen = {s.casefold() for s in statuses}
    order_types: list[str] = []
    type_seen: set[str] = set()

    with get_db_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                f"""
                SELECT DISTINCT TRIM(COALESCE(status, ''))
                FROM {MAIN_TABLE_NAME}
                {filter_sql}
                """,
                tuple(filter_params),
            )
            for (raw_status,) in cursor.fetchall():
                status_text = _safe_text(raw_status)
                if not status_text or status_text.casefold() == CLOSED_STATUS.casefold():
                    continue
                lowered = status_text.casefold()
                if lowered in status_seen:
                    continue
                status_seen.add(lowered)
                statuses.append(status_text)

            cursor.execute(
                f"""
                SELECT DISTINCT TRIM(COALESCE(order_type, ''))
                FROM {MAIN_TABLE_NAME}
                {filter_sql}
                ORDER BY 1
                """,
                tuple(filter_params),
            )
            for (raw_type,) in cursor.fetchall():
                type_text = _safe_text(raw_type)
                if not type_text:
                    continue
                lowered = type_text.casefold()
                if lowered in type_seen:
                    continue
                type_seen.add(lowered)
                order_types.append(type_text)

    return {
        "statuses": statuses,
        "order_types": order_types,
    }


def load_main_order_card(order_number: str) -> dict | None:
    ensure_schema()
    normalized_order = _safe_text(order_number)
    if not normalized_order:
        return None

    with get_db_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                f"""
                SELECT
                    order_number,
                    customer,
                    order_type,
                    status,
                    note,
                    contract_due_at,
                    address,
                    address_note,
                    vat,
                    note_color,
                    note_text_color
                FROM {MAIN_TABLE_NAME}
                WHERE order_number = %s
                LIMIT 1
                """,
                (normalized_order,),
            )
            order_row = cursor.fetchone()
            if not order_row:
                return None

            cursor.execute(
                f"""
                SELECT
                    id,
                    part_number,
                    product_name,
                    item_value,
                    planned_assembly_due_at,
                    planned_install_due_at,
                    assembly_hours,
                    install_hours,
                    assembly_status,
                    install_status,
                    assembly_started_at,
                    assembly_completed_at,
                    install_started_at,
                    install_completed_at,
                    assembly_worker,
                    install_worker,
                    item_percent,
                    requires_assembly,
                    requires_install
                FROM {DETAILS_TABLE_NAME}
                WHERE order_number = %s
                ORDER BY id
                """,
                (normalized_order,),
            )
            detail_rows = cursor.fetchall()

            schedule_tasks: list[dict] = []
            cursor.execute("SELECT to_regclass(%s)", (SCHEDULE_TASKS_TABLE,))
            if cursor.fetchone()[0] is not None:
                cursor.execute(
                    f"""
                    SELECT
                        scheduled_for,
                        TRIM(COALESCE(task_type, '')),
                        TRIM(COALESCE(status, ''))
                    FROM {SCHEDULE_TASKS_TABLE}
                    WHERE TRIM(COALESCE(order_number, '')) = %s
                    """,
                    (normalized_order,),
                )
                schedule_tasks = [
                    {
                        "scheduled_for": row[0],
                        "task_type": row[1],
                        "status": row[2],
                    }
                    for row in cursor.fetchall()
                ]

    live = _load_live_order_context([normalized_order]).get(normalized_order, {})

    from .utils import (
        _format_date_input,
        _parse_duration_minutes,
    )

    details_list = [
        {
            "detail_id": int(record[0]),
            "part_number": _safe_text(record[1]) or "-",
            "product_name": _safe_text(record[2]) or "-",
            "item_value": _format_money(Decimal(record[3] or 0)),
            "planned_assembly_due_at": _format_date(record[4]),
            "planned_install_due_at": _format_date(record[5]),
            "planned_assembly_due_at_input": _format_date_input(record[4]),
            "planned_install_due_at_input": _format_date_input(record[5]),
            "assembly_hours": record[6],
            "install_hours": record[7],
            "assembly_status": record[8],
            "install_status": record[9],
            "assembly_started_at": record[10],
            "assembly_completed_at": record[11],
            "install_started_at": record[12],
            "install_completed_at": record[13],
            "assembly_worker": record[14],
            "install_worker": record[15],
            "item_percent": float(record[16] or 0),
            "requires_assembly": bool(record[17]),
            "requires_install": bool(record[18]),
        }
        for record in detail_rows
    ]

    assembly_details = _filter_required_stage_details(details_list, required_key="requires_assembly")
    install_details = _filter_required_stage_details(details_list, required_key="requires_install")

    assembly_started_values = [
        _normalize_datetime(d.get("assembly_started_at"))
        for d in assembly_details
        if _normalize_datetime(d.get("assembly_started_at"))
    ]
    assembly_completed_values = [
        _normalize_datetime(d.get("assembly_completed_at"))
        for d in assembly_details
        if _normalize_datetime(d.get("assembly_completed_at"))
    ]
    install_started_values = [
        _normalize_datetime(d.get("install_started_at"))
        for d in install_details
        if _normalize_datetime(d.get("install_started_at"))
    ]
    install_completed_values = [
        _normalize_datetime(d.get("install_completed_at"))
        for d in install_details
        if _normalize_datetime(d.get("install_completed_at"))
    ]

    first_assembly_started = min(assembly_started_values) if assembly_started_values else None
    all_assembly_completed = bool(assembly_details) and len(assembly_completed_values) == len(assembly_details)
    last_assembly_completed = max(assembly_completed_values) if all_assembly_completed else None

    first_install_started = min(install_started_values) if install_started_values else None
    all_install_completed = bool(install_details) and len(install_completed_values) == len(install_details)
    last_install_completed = max(install_completed_values) if all_install_completed else None

    assembly_hours_minutes = sum(
        _parse_duration_minutes(d.get("assembly_hours") or "") for d in details_list
    )
    install_hours_minutes = sum(
        _parse_duration_minutes(d.get("install_hours") or "") for d in details_list
    )

    assembly_workers_list = _build_workers_list(details_list, "assembly_worker")
    assembly_workers_count = _count_workers(assembly_workers_list)
    install_workers_list = _build_workers_list(details_list, "install_worker")
    install_workers_count = _count_workers(install_workers_list)

    has_assignment = any(
        _has_worker_assignment(detail.get("assembly_worker") or "")
        or _has_worker_assignment(detail.get("install_worker") or "")
        for detail in details_list
    )

    derived_status = _safe_text(order_row[3]) or ACTIVE_STATUS
    if derived_status != CLOSED_STATUS:
        derived_status = _derive_order_status(
            details=details_list,
            schedule_tasks=schedule_tasks,
            has_assignment=has_assignment,
        )

    return {
        "order_number": normalized_order,
        "customer": live.get("customer") or _safe_text(order_row[1]) or "-",
        "order_type": live.get("order_type") or _safe_text(order_row[2]) or "-",
        "status": derived_status,
        "note": _clean_free_text(order_row[4]),
        "deadline": _days_until(order_row[5]),
        "contract_due_at": _format_date(order_row[5]),
        "address": _clean_free_text(order_row[6]),
        "address_note": _clean_free_text(order_row[7]),
        "vat": bool(order_row[8]),
        "note_color": _normalize_note_color(order_row[9]),
        "note_text_color": _normalize_note_text_color(order_row[10]),
        "signed_at": live.get("signed_at") or "-",
        "planned_install_at": live.get("planned_install_at") or "-",
        "assembly_status": _build_stage_status_distribution(
            details_list,
            status_key="assembly_status",
            completed_at_key="assembly_completed_at",
            required_key="requires_assembly",
        ),
        "assembly_started_at": _format_datetime(first_assembly_started),
        "assembly_completed_at": _format_datetime(last_assembly_completed),
        "assembly_hours": _format_duration(assembly_hours_minutes) if assembly_hours_minutes else "-",
        "assembly_workers_count": assembly_workers_count,
        "install_status": _build_stage_status_distribution(
            details_list,
            status_key="install_status",
            completed_at_key="install_completed_at",
            required_key="requires_install",
        ),
        "install_started_at": _format_datetime(first_install_started),
        "install_completed_at": _format_datetime(last_install_completed),
        "install_hours": _format_duration(install_hours_minutes) if install_hours_minutes else "-",
        "install_workers_count": install_workers_count,
        "details": [
            {
                "detail_id": d["detail_id"],
                "part_number": d["part_number"],
                "product_name": d["product_name"],
                "item_value": d["item_value"],
                "planned_assembly_due_at": d["planned_assembly_due_at"],
                "planned_install_due_at": d["planned_install_due_at"],
                "planned_assembly_due_at_input": d["planned_assembly_due_at_input"],
                "planned_install_due_at_input": d["planned_install_due_at_input"],
                "assembly_status": _resolve_detail_stage_status(
                    raw_status=d.get("assembly_status"),
                    completed_at=d.get("assembly_completed_at"),
                    started_at=d.get("assembly_started_at"),
                    is_required=bool(d.get("requires_assembly", True)),
                    skipped_label="Без збірки",
                ),
                "install_status": _resolve_detail_stage_status(
                    raw_status=d.get("install_status"),
                    completed_at=d.get("install_completed_at"),
                    started_at=d.get("install_started_at"),
                    is_required=bool(d.get("requires_install", True)),
                    skipped_label="Без монтажу",
                ),
                "assembly_started_at": _format_datetime(
                    _normalize_datetime(d.get("assembly_started_at"))
                ),
                "assembly_completed_at": _format_datetime(
                    _normalize_datetime(d.get("assembly_completed_at"))
                ),
                "install_started_at": _format_datetime(
                    _normalize_datetime(d.get("install_started_at"))
                ),
                "install_completed_at": _format_datetime(
                    _normalize_datetime(d.get("install_completed_at"))
                ),
                "assembly_hours": _safe_text(d.get("assembly_hours")) or "-",
                "install_hours": _safe_text(d.get("install_hours")) or "-",
                "assembly_worker": _safe_text(d.get("assembly_worker")) or "-",
                "install_worker": _safe_text(d.get("install_worker")) or "-",
                "item_percent": d.get("item_percent", 0),
                "requires_assembly": bool(d.get("requires_assembly", True)),
                "requires_install": bool(d.get("requires_install", True)),
            }
            for d in details_list
        ],
    }


def update_main_order_card(
    order_number: str,
    *,
    address=None,
    address_note=None,
    note=None,
    note_color=None,
    note_text_color=None,
    vat=None,
    details=None,
) -> dict | None:
    ensure_schema()
    normalized_order = _safe_text(order_number)
    if not normalized_order:
        return None

    with get_db_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                f"""
                UPDATE {MAIN_TABLE_NAME}
                SET address = %s,
                    address_note = %s,
                    note = %s,
                    note_color = %s,
                    note_text_color = %s,
                    vat = %s,
                    updated_at = NOW()
                WHERE order_number = %s
                RETURNING order_number
                """,
                (
                    _clean_free_text(address),
                    _clean_free_text(address_note),
                    _clean_free_text(note),
                    _normalize_note_color(note_color),
                    _normalize_note_text_color(note_text_color),
                    bool(vat),
                    normalized_order,
                ),
            )
            updated = cursor.fetchone()

            if updated and isinstance(details, list):
                detail_updates = []
                for item in details:
                    if not isinstance(item, dict):
                        continue
                    detail_id = item.get("detail_id")
                    try:
                        normalized_detail_id = int(detail_id)
                    except (TypeError, ValueError):
                        continue

                    from .utils import _parse_uk_date as _pud
                    reset_assembly_completed = bool(item.get("reset_assembly_completed"))
                    complete_assembly_now = bool(item.get("complete_assembly_now"))
                    reset_install_completed = bool(item.get("reset_install_completed"))
                    complete_install_now = bool(item.get("complete_install_now"))
                    requires_assembly = bool(item.get("requires_assembly", True))
                    requires_install = bool(item.get("requires_install", True))
                    detail_updates.append(
                        (
                            _pud(_safe_text(item.get("planned_assembly_due_at"))),
                            _pud(_safe_text(item.get("planned_install_due_at"))),
                            float(item.get("item_percent") or 0),
                            requires_assembly,
                            requires_install,
                            complete_assembly_now,
                            reset_assembly_completed,
                            complete_assembly_now,
                            TASK_STATUS_COMPLETED,
                            reset_assembly_completed,
                            TASK_STATUS_COMPLETED,
                            TASK_STATUS_IN_PROGRESS,
                            TASK_STATUS_QUEUED,
                            complete_install_now,
                            reset_install_completed,
                            complete_install_now,
                            TASK_STATUS_COMPLETED,
                            reset_install_completed,
                            TASK_STATUS_COMPLETED,
                            TASK_STATUS_IN_PROGRESS,
                            TASK_STATUS_QUEUED,
                            normalized_detail_id,
                            normalized_order,
                        )
                    )

                if detail_updates:
                    cursor.executemany(
                        f"""
                        UPDATE {DETAILS_TABLE_NAME}
                        SET planned_assembly_due_at = %s,
                            planned_install_due_at = %s,
                            item_percent = %s,
                            requires_assembly = %s,
                            requires_install = %s,
                            assembly_completed_at = CASE
                                WHEN %s THEN NOW()
                                WHEN %s THEN NULL
                                ELSE assembly_completed_at
                            END,
                            assembly_status = CASE
                                WHEN %s THEN %s
                                WHEN %s AND TRIM(COALESCE(assembly_status, '')) ILIKE %s THEN
                                    CASE
                                        WHEN assembly_started_at IS NOT NULL THEN %s
                                        ELSE %s
                                    END
                                ELSE assembly_status
                            END,
                            install_completed_at = CASE
                                WHEN %s THEN NOW()
                                WHEN %s THEN NULL
                                ELSE install_completed_at
                            END,
                            install_status = CASE
                                WHEN %s THEN %s
                                WHEN %s AND TRIM(COALESCE(install_status, '')) ILIKE %s THEN
                                    CASE
                                        WHEN install_started_at IS NOT NULL THEN %s
                                        ELSE %s
                                    END
                                ELSE install_status
                            END,
                            updated_at = NOW()
                        WHERE id = %s
                          AND order_number = %s
                        """,
                        detail_updates,
                    )
        conn.commit()

    enqueue_detail_metrics_recalculation([normalized_order], source="update_main_order_card")

    if not updated:
        return None

    return load_main_order_card(normalized_order)
