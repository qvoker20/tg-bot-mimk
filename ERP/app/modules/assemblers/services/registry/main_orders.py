from __future__ import annotations

from collections import defaultdict
from decimal import Decimal
import re

from app.modules.assemblers.db.connection import get_db_connection
from app.modules.assemblers.services.activity_log import record_activity_event

from .constants import (
    ACTIVE_STATUS,
    ASSEMBLY_TASK_TYPE,
    CLOSED_STATUS,
    DETAILS_TABLE_NAME,
    MAIN_TABLE_NAME,
    INSTALL_TASK_TYPE,
    RECLAMATION_STATUS,
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
_CLOSED_LIKE_STATUSES = (CLOSED_STATUS, RECLAMATION_STATUS)
_CLOSED_LIKE_STATUS_CASEFOLDS = {status.casefold() for status in _CLOSED_LIKE_STATUSES}


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


def _normalize_percent(value, *, field_label: str) -> float:
    try:
        normalized = float(value)
    except (TypeError, ValueError):
        normalized = 0.0

    if normalized < 0 or normalized > 100:
        raise ValueError(f"{field_label} повинен бути у діапазоні 0..100.")
    return normalized


def _is_constructor_completed(value) -> bool:
    text = _safe_text(value).casefold()
    if not text:
        return False
    if any(marker in text for marker in ("заверш", "викон", "готов", "done", "complete")):
        return True

    match = re.search(r"(\d+(?:[\.,]\d+)?)", text)
    if not match:
        return False
    try:
        percent = float(match.group(1).replace(",", "."))
    except ValueError:
        return False
    return percent >= 100


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


def _calculate_schedule_effective_minutes(
    schedule_tasks: list[dict],
    *,
    task_type: str | None = None,
) -> int:
    daily_minutes: dict[object, int] = {}

    for task in schedule_tasks:
        normalized_task_type = _safe_text(task.get("task_type")).casefold()
        if task_type and normalized_task_type != task_type.casefold():
            continue

        started_at = _normalize_datetime(task.get("started_at"))
        completed_at = _normalize_datetime(task.get("completed_at"))
        if not started_at or not completed_at or completed_at < started_at:
            continue

        day_key = started_at.date()
        total_seconds = int((completed_at - started_at).total_seconds())
        effective_seconds = max(0, total_seconds - int(task.get("pause_seconds") or 0))
        effective_minutes = effective_seconds // 60
        if effective_minutes <= 0:
            continue

        current_minutes = int(daily_minutes.get(day_key) or 0)
        if effective_minutes > current_minutes:
            daily_minutes[day_key] = effective_minutes

    return sum(daily_minutes.values())


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

    status_filter_values = tuple(_CLOSED_LIKE_STATUSES) if closed_only else (CLOSED_STATUS,)
    filter_clauses = [
        "TRIM(COALESCE(status, '')) IN %s"
        if closed_only
        else "TRIM(COALESCE(status, '')) NOT IN %s"
    ]
    filter_params: list[object] = [status_filter_values]

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
                    vat,
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
                            TRIM(COALESCE(status, '')),
                            started_at,
                            completed_at,
                            COALESCE(pause_seconds, 0),
                            paused_at,
                            TRIM(COALESCE(pause_reason, '')),
                            updated_at
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
                                "started_at": schedule_row[4],
                                "completed_at": schedule_row[5],
                                "pause_seconds": schedule_row[6],
                                "paused_at": schedule_row[7],
                                "pause_reason": schedule_row[8],
                                "updated_at": schedule_row[9],
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
                            "planned_assembly_due_at": record[9],
                            "planned_install_due_at": record[10],
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
        paused_tasks = [
            task
            for task in schedule_tasks
            if _safe_text(task.get("status")).casefold() == TASK_STATUS_PAUSED.casefold()
        ]

        latest_paused_task = None
        if paused_tasks:
            latest_paused_task = max(
                paused_tasks,
                key=lambda task: (
                    _normalize_datetime(task.get("paused_at"))
                    or _normalize_datetime(task.get("updated_at"))
                    or _normalize_datetime(task.get("scheduled_for"))
                    or _normalize_datetime(record[15])
                ),
            )

        latest_pause_at = (
            _normalize_datetime(latest_paused_task.get("paused_at"))
            if latest_paused_task
            else None
        ) or (
            _normalize_datetime(latest_paused_task.get("updated_at"))
            if latest_paused_task
            else None
        ) or _normalize_datetime(record[15])

        latest_pause_reason = (
            _safe_text(latest_paused_task.get("pause_reason"))
            if latest_paused_task
            else ""
        )

        live = live_context.get(order_number, {})
        total_value = sum(
            (Decimal(detail.get("item_value") or 0) for detail in details), start=Decimal("0")
        )
        contract_due_at = record[5]
        actual_minutes = _calculate_schedule_effective_minutes(schedule_tasks)
        if not schedule_tasks:
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
        if not closed_only and order_status.casefold() not in _CLOSED_LIKE_STATUS_CASEFOLDS:
            order_status = _derive_order_status(
                details=details,
                schedule_tasks=schedule_tasks,
                has_assignment=has_assignment,
            )

        first_install_started = min(install_started_values) if install_started_values else None
        all_install_completed = bool(install_details) and len(install_completed_values) == len(install_details)
        last_install_completed = max(install_completed_values) if all_install_completed else None

        assembly_hours_minutes = _calculate_schedule_effective_minutes(
            schedule_tasks,
            task_type=ASSEMBLY_TASK_TYPE,
        )
        install_hours_minutes = _calculate_schedule_effective_minutes(
            schedule_tasks,
            task_type=INSTALL_TASK_TYPE,
        )
        if not schedule_tasks:
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
                "vat": bool(record[24]),
                "note_color": _normalize_note_color(record[25]),
                "note_text_color": _normalize_note_text_color(record[26]),
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
                "paint_status": "немає",
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
                "glass_status": "немає",
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
                "vat": bool(record[24]),
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
                "assembler_stop_note": latest_pause_reason or "-",
                "completion_percent": "-",
                "warehouse_status": "-",
                "warehouse_note": "-",
                "materials": live.get("materials") or _safe_text(record[13]) or "-",
                "constructor_name": live.get("constructor_name") or _safe_text(record[14]) or "-",
                "assembler_pause_at": _format_datetime(latest_pause_at),
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

    status_filter_values = tuple(_CLOSED_LIKE_STATUSES) if closed_only else (CLOSED_STATUS,)
    filter_clauses = [
        "TRIM(COALESCE(status, '')) IN %s"
        if closed_only
        else "TRIM(COALESCE(status, '')) NOT IN %s"
    ]
    filter_params: list[object] = [status_filter_values]

    if normalized_order_query:
        filter_clauses.append("TRIM(COALESCE(order_number, '')) ILIKE %s")
        filter_params.append(f"%{normalized_order_query}%")

    if normalized_customer_query:
        filter_clauses.append("TRIM(COALESCE(customer, '')) ILIKE %s")
        filter_params.append(f"%{normalized_customer_query}%")

    filter_sql = f"WHERE {' AND '.join(filter_clauses)}"

    statuses: list[str] = (
        [CLOSED_STATUS, RECLAMATION_STATUS]
        if closed_only
        else [
            ACTIVE_STATUS,
            "Простой",
            "Збірка",
            "Монтаж",
            "Запланована збірка",
            "Заплановано монтаж",
            TASK_STATUS_PAUSED,
            TASK_STATUS_COMPLETED,
            RECLAMATION_STATUS,
        ]
    )
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
                lowered = status_text.casefold()
                if not status_text:
                    continue
                if not closed_only and lowered in _CLOSED_LIKE_STATUS_CASEFOLDS:
                    continue
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
                    constructor_status,
                    assembly_percent,
                    install_percent,
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
                        TRIM(COALESCE(status, '')),
                        started_at,
                        completed_at,
                        COALESCE(pause_seconds, 0),
                        TRIM(COALESCE(assembler_name, ''))
                    FROM {SCHEDULE_TASKS_TABLE}
                    WHERE TRIM(COALESCE(order_number, '')) = %s
                    ORDER BY scheduled_for, assembler_name
                    """,
                    (normalized_order,),
                )
                schedule_tasks = [
                    {
                        "scheduled_for": row[0],
                        "task_type": row[1],
                        "status": row[2],
                        "started_at": row[3],
                        "completed_at": row[4],
                        "pause_seconds": row[5],
                        "assembler_name": row[6],
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
            "planned_assembly_due_at": record[4],
            "planned_install_due_at": record[5],
            "planned_assembly_due_at_display": _format_date(record[4]),
            "planned_install_due_at_display": _format_date(record[5]),
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
            "constructor_status": _safe_text(record[16]) or "",
            "assembly_percent": float(record[17] or 0),
            "install_percent": float(record[18] or 0),
            "item_percent": float(record[19] or 0),
            "requires_assembly": bool(record[20]),
            "requires_install": bool(record[21]),
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

    assembly_hours_minutes = _calculate_schedule_effective_minutes(
        schedule_tasks,
        task_type=ASSEMBLY_TASK_TYPE,
    )
    install_hours_minutes = _calculate_schedule_effective_minutes(
        schedule_tasks,
        task_type=INSTALL_TASK_TYPE,
    )
    if not schedule_tasks:
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
    if derived_status.casefold() not in _CLOSED_LIKE_STATUS_CASEFOLDS:
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
        "paint_shop": live.get("paint_shop", "-"),
        "paint_status": "немає",
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
        "glass_status": "немає",
        "frame_facades": live.get("frame_facades", "-"),
        "ceramic_granite": live.get("ceramic_granite", "-"),
        "schedule_tasks": schedule_tasks,
        "details": [
            {
                "detail_id": d["detail_id"],
                "part_number": d["part_number"],
                "product_name": d["product_name"],
                "item_value": d["item_value"],
                "planned_assembly_due_at": d.get("planned_assembly_due_at_display") or "-",
                "planned_install_due_at": d.get("planned_install_due_at_display") or "-",
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
                "constructor_status": _safe_text(d.get("constructor_status")) or "",
                "assembly_percent": d.get("assembly_percent", 0),
                "install_percent": d.get("install_percent", 0),
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
    actor=None,
) -> dict | None:
    ensure_schema()
    normalized_order = _safe_text(order_number)
    if not normalized_order:
        return None

    with get_db_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                f"""
                SELECT TRIM(COALESCE(status, ''))
                FROM {MAIN_TABLE_NAME}
                WHERE order_number = %s
                LIMIT 1
                FOR UPDATE
                """,
                (normalized_order,),
            )
            status_row = cursor.fetchone()
            if not status_row:
                return None
            current_status_key = _safe_text(status_row[0]).casefold()
            if current_status_key == CLOSED_STATUS.casefold():
                raise ValueError("Закрите замовлення не можна редагувати.")

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
                cursor.execute(
                    f"""
                    SELECT
                        id,
                        requires_assembly,
                        requires_install,
                        constructor_status,
                        assembly_percent,
                        install_percent,
                        TRIM(COALESCE(assembly_status, '')),
                        assembly_completed_at,
                        TRIM(COALESCE(install_status, '')),
                        install_completed_at,
                        planned_assembly_due_at,
                        planned_install_due_at
                    FROM {DETAILS_TABLE_NAME}
                    WHERE TRIM(COALESCE(order_number, '')) = TRIM(COALESCE(%s, ''))
                    """,
                    (normalized_order,),
                )
                detail_state_by_id = {
                    int(row[0]): {
                        "requires_assembly": bool(row[1]),
                        "requires_install": bool(row[2]),
                        "constructor_status": _safe_text(row[3]),
                        "assembly_percent": float(row[4] or 0),
                        "install_percent": float(row[5] or 0),
                        "assembly_status": _safe_text(row[6]),
                        "assembly_completed_at": row[7],
                        "install_status": _safe_text(row[8]),
                        "install_completed_at": row[9],
                        "planned_assembly_due_at": row[10],
                        "planned_install_due_at": row[11],
                    }
                    for row in cursor.fetchall()
                }

                detail_updates = []
                requested_stage_actions: dict[int, dict[str, bool]] = {}
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
                    if complete_assembly_now and reset_assembly_completed:
                        raise ValueError("Некоректна дія для збірки: одночасно завершити і скасувати неможливо.")
                    if complete_install_now and reset_install_completed:
                        raise ValueError("Некоректна дія для монтажу: одночасно завершити і скасувати неможливо.")

                    if (
                        complete_assembly_now
                        or reset_assembly_completed
                        or complete_install_now
                        or reset_install_completed
                    ):
                        requested_stage_actions[normalized_detail_id] = {
                            "complete_assembly_now": complete_assembly_now,
                            "reset_assembly_completed": reset_assembly_completed,
                            "complete_install_now": complete_install_now,
                            "reset_install_completed": reset_install_completed,
                        }

                    requires_assembly = bool(item.get("requires_assembly", True))
                    requires_install = bool(item.get("requires_install", True))
                    planned_assembly_due_at = _pud(_safe_text(item.get("planned_assembly_due_at")))
                    planned_install_due_at = _pud(_safe_text(item.get("planned_install_due_at")))
                    assembly_percent = _normalize_percent(
                        item.get("assembly_percent"),
                        field_label="Відсоток збірка",
                    )
                    install_percent = _normalize_percent(
                        item.get("install_percent", item.get("item_percent")),
                        field_label="Відсоток монтаж",
                    )

                    current_detail = detail_state_by_id.get(normalized_detail_id)
                    if not current_detail:
                        if normalized_detail_id in requested_stage_actions:
                            raise ValueError("Вибраний виріб не знайдено або вже неактуальний. Оновіть сторінку.")
                        continue

                    constructor_completed = _is_constructor_completed(current_detail.get("constructor_status"))
                    if not constructor_completed:
                        has_stage_actions = bool(requested_stage_actions.get(normalized_detail_id))
                        if (
                            planned_assembly_due_at != current_detail.get("planned_assembly_due_at")
                            or planned_install_due_at != current_detail.get("planned_install_due_at")
                            or requires_assembly != bool(current_detail.get("requires_assembly"))
                            or requires_install != bool(current_detail.get("requires_install"))
                            or assembly_percent != float(current_detail.get("assembly_percent") or 0)
                            or install_percent != float(current_detail.get("install_percent") or 0)
                            or has_stage_actions
                        ):
                            raise ValueError("Редагування дозволене лише коли статус КБ: 'Завершено'.")

                    if not requires_assembly and not requires_install:
                        raise ValueError("Не можна одночасно зняти позначки 'Збірка' і 'Монтаж'.")

                    current_requires_assembly = bool(current_detail.get("requires_assembly"))
                    current_requires_install = bool(current_detail.get("requires_install"))
                    assembly_completed = bool(current_detail.get("assembly_completed_at")) or (
                        _safe_text(current_detail.get("assembly_status")).casefold() == TASK_STATUS_COMPLETED.casefold()
                    )
                    install_completed = bool(current_detail.get("install_completed_at")) or (
                        _safe_text(current_detail.get("install_status")).casefold() == TASK_STATUS_COMPLETED.casefold()
                    )
                    product_completed = (
                        (not current_requires_assembly or assembly_completed)
                        and (not current_requires_install or install_completed)
                    )

                    if assembly_completed:
                        if planned_assembly_due_at != current_detail.get("planned_assembly_due_at"):
                            raise ValueError("Збірку вже завершено: дату планування збірки змінювати не можна.")
                        if requires_assembly != current_requires_assembly:
                            raise ValueError("Збірку вже завершено: змінювати позначку 'Збірка' не можна.")

                    if install_completed:
                        if planned_install_due_at != current_detail.get("planned_install_due_at"):
                            raise ValueError("Монтаж вже завершено: дату планування монтажу змінювати не можна.")
                        if requires_install != current_requires_install:
                            raise ValueError("Монтаж вже завершено: змінювати позначку 'Монтаж' не можна.")

                    if product_completed:
                        if (
                            requires_assembly != current_requires_assembly
                            or requires_install != current_requires_install
                        ):
                            raise ValueError("Завершений виріб: змінювати позначки 'Збірка'/'Монтаж' заборонено.")
                        if (
                            planned_assembly_due_at != current_detail.get("planned_assembly_due_at")
                            or planned_install_due_at != current_detail.get("planned_install_due_at")
                        ):
                            raise ValueError("Завершений виріб: змінювати дати планування заборонено.")

                    detail_updates.append(
                        (
                            TASK_STATUS_COMPLETED,
                            planned_assembly_due_at,
                            TASK_STATUS_COMPLETED,
                            planned_install_due_at,
                            assembly_percent,
                            install_percent,
                            install_percent,
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
                        SET planned_assembly_due_at = CASE
                                WHEN assembly_completed_at IS NOT NULL
                                     OR TRIM(COALESCE(assembly_status, '')) ILIKE %s
                                THEN planned_assembly_due_at
                                ELSE %s
                            END,
                            planned_install_due_at = CASE
                                WHEN install_completed_at IS NOT NULL
                                     OR TRIM(COALESCE(install_status, '')) ILIKE %s
                                THEN planned_install_due_at
                                ELSE %s
                            END,
                            assembly_percent = %s,
                            install_percent = %s,
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
                          AND TRIM(COALESCE(order_number, '')) = TRIM(COALESCE(%s, ''))
                        """,
                        detail_updates,
                    )

                if requested_stage_actions:
                    action_detail_ids = list(requested_stage_actions.keys())
                    cursor.execute(
                        f"""
                        SELECT
                            id,
                            TRIM(COALESCE(assembly_status, '')),
                            assembly_completed_at,
                            TRIM(COALESCE(install_status, '')),
                            install_completed_at
                        FROM {DETAILS_TABLE_NAME}
                        WHERE id = ANY(%s)
                          AND TRIM(COALESCE(order_number, '')) = TRIM(COALESCE(%s, ''))
                        """,
                        (action_detail_ids, normalized_order),
                    )
                    persisted_details = {
                        int(row[0]): {
                            "assembly_status": _safe_text(row[1]),
                            "assembly_completed_at": row[2],
                            "install_status": _safe_text(row[3]),
                            "install_completed_at": row[4],
                        }
                        for row in cursor.fetchall()
                    }

                    for detail_id, action_state in requested_stage_actions.items():
                        persisted = persisted_details.get(detail_id)
                        if not persisted:
                            raise ValueError("Сервер не підтвердив оновлення виробу. Оновіть сторінку і спробуйте ще раз.")

                        assembly_completed_now = bool(persisted.get("assembly_completed_at")) or (
                            _safe_text(persisted.get("assembly_status")).casefold() == TASK_STATUS_COMPLETED.casefold()
                        )
                        install_completed_now = bool(persisted.get("install_completed_at")) or (
                            _safe_text(persisted.get("install_status")).casefold() == TASK_STATUS_COMPLETED.casefold()
                        )

                        if action_state.get("complete_assembly_now") and not assembly_completed_now:
                            raise ValueError("Сервер не підтвердив завершення збірки. Оновіть сторінку і спробуйте ще раз.")
                        if action_state.get("reset_assembly_completed") and assembly_completed_now:
                            raise ValueError("Сервер не підтвердив скасування завершення збірки. Оновіть сторінку і спробуйте ще раз.")
                        if action_state.get("complete_install_now") and not install_completed_now:
                            raise ValueError("Сервер не підтвердив завершення монтажу. Оновіть сторінку і спробуйте ще раз.")
                        if action_state.get("reset_install_completed") and install_completed_now:
                            raise ValueError("Сервер не підтвердив скасування завершення монтажу. Оновіть сторінку і спробуйте ще раз.")

        detail_action_notes = []
        if isinstance(details, list):
            for item in details:
                if not isinstance(item, dict):
                    continue
                detail_label = _safe_text(item.get("part_number")) or f"ID {item.get('detail_id')}"
                action_notes = []
                if item.get("complete_assembly_now"):
                    action_notes.append("достроково завершено збірку")
                if item.get("reset_assembly_completed"):
                    action_notes.append("скасовано завершення збірки")
                if item.get("complete_install_now"):
                    action_notes.append("достроково завершено монтаж")
                if item.get("reset_install_completed"):
                    action_notes.append("скасовано завершення монтажу")
                if action_notes:
                    detail_action_notes.append(f"{detail_label}: {', '.join(action_notes)}")
        conn.commit()

    enqueue_detail_metrics_recalculation([normalized_order], source="update_main_order_card")

    if not updated:
        return None

    record_activity_event(
        action_key="main.order.update",
        action_label="Оновлено замовлення",
        description=(
            f"Оновлено картку замовлення {normalized_order}"
            + (f"; дії по деталях: {'; '.join(detail_action_notes)}" if detail_action_notes else "")
        ),
        actor=actor,
        entity_type="main_order",
        entity_id=normalized_order,
        order_number=normalized_order,
        source_table=MAIN_TABLE_NAME,
        source_op="UPDATE",
        details={
            "details_count": len(details or []) if isinstance(details, list) else 0,
            "detail_actions": detail_action_notes[:25],
            "vat": bool(vat),
        },
    )

    return load_main_order_card(normalized_order)


def update_main_order_status(
    order_number: str,
    *,
    action: str,
    actor=None,
) -> dict | None:
    ensure_schema()
    normalized_order = _safe_text(order_number)
    if not normalized_order:
        return None

    normalized_action = _safe_text(action).casefold()
    action_map = {
        "close": {
            "label": "Закрито замовлення",
            "log_key": "main.order.close",
            "next_status": CLOSED_STATUS,
        },
        "mark_reclamation": {
            "label": "Позначено рекламацію",
            "log_key": "main.order.mark_reclamation",
            "next_status": RECLAMATION_STATUS,
        },
        "cancel_reclamation": {
            "label": "Скасовано рекламацію",
            "log_key": "main.order.cancel_reclamation",
            "next_status": CLOSED_STATUS,
        },
    }
    if normalized_action not in action_map:
        raise ValueError("Некоректна дія для зміни статусу.")

    current_order = load_main_order_card(normalized_order)
    if not current_order:
        return None

    current_display_status = _safe_text(current_order.get("status"))
    current_display_key = current_display_status.casefold()
    reclamation_key = RECLAMATION_STATUS.casefold()
    completed_key = TASK_STATUS_COMPLETED.casefold()

    closer_name = _safe_text((actor or {}).get("name")) or "Корисувач"
    closer_role = _safe_text((actor or {}).get("role")) or "-"
    closer_telegram_id = (actor or {}).get("telegram_id")
    actual_status = action_map[normalized_action]["next_status"]

    with get_db_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                f"""
                SELECT TRIM(COALESCE(status, ''))
                FROM {MAIN_TABLE_NAME}
                WHERE order_number = %s
                LIMIT 1
                FOR UPDATE
                """,
                (normalized_order,),
            )
            raw_row = cursor.fetchone()
            if not raw_row:
                return None
            current_raw_status = _safe_text(raw_row[0])
            current_raw_key = current_raw_status.casefold()

            if normalized_action == "close":
                can_close = (
                    current_raw_key == reclamation_key
                    or current_display_key == completed_key
                )
                if not can_close:
                    raise ValueError("Закриття доступне лише для статусів 'Завершено' або 'Рекламація'.")

                cursor.execute(
                    f"""
                    UPDATE {MAIN_TABLE_NAME}
                    SET status = %s,
                        closed_at = NOW(),
                        closed_by_name = %s,
                        closed_by_role = %s,
                        closed_by_telegram_id = %s,
                        updated_at = NOW()
                    WHERE order_number = %s
                    """,
                    (
                        CLOSED_STATUS,
                        closer_name,
                        closer_role,
                        closer_telegram_id,
                        normalized_order,
                    ),
                )
            elif normalized_action == "mark_reclamation":
                can_mark_reclamation = (
                    current_display_key == completed_key
                    or current_raw_key == completed_key
                )
                if not can_mark_reclamation:
                    raise ValueError("Рекламацію можна поставити лише для завершеного замовлення.")

                cursor.execute(
                    f"""
                    UPDATE {MAIN_TABLE_NAME}
                    SET status = %s,
                        updated_at = NOW()
                    WHERE order_number = %s
                    """,
                    (RECLAMATION_STATUS, normalized_order),
                )
            else:
                if current_raw_key != reclamation_key:
                    raise ValueError("Скасувати рекламацію можна лише для статусу 'Рекламація'.")

                cursor.execute(
                    f"""
                    SELECT id, requires_assembly, requires_install,
                           assembly_status, assembly_completed_at,
                           install_status, install_completed_at
                    FROM {DETAILS_TABLE_NAME}
                    WHERE order_number = %s
                    ORDER BY id
                    """,
                    (normalized_order,),
                )
                detail_rows = cursor.fetchall()
                details_for_status = [
                    {
                        "detail_id": row[0],
                        "requires_assembly": bool(row[1]),
                        "requires_install": bool(row[2]),
                        "assembly_status": row[3],
                        "assembly_completed_at": row[4],
                        "install_status": row[5],
                        "install_completed_at": row[6],
                    }
                    for row in detail_rows
                ]

                cursor.execute("SELECT to_regclass(%s)", (SCHEDULE_TASKS_TABLE,))
                schedule_tasks = []
                if cursor.fetchone()[0] is not None:
                    cursor.execute(
                        f"""
                        SELECT scheduled_for, TRIM(COALESCE(task_type, '')),
                               TRIM(COALESCE(status, '')),
                               started_at, completed_at, COALESCE(pause_seconds, 0)
                        FROM {SCHEDULE_TASKS_TABLE}
                        WHERE TRIM(COALESCE(order_number, '')) = %s
                        ORDER BY scheduled_for
                        """,
                        (normalized_order,),
                    )
                    schedule_tasks = [
                        {
                            "scheduled_for": row[0],
                            "task_type": row[1],
                            "status": row[2],
                            "started_at": row[3],
                            "completed_at": row[4],
                            "pause_seconds": row[5],
                        }
                        for row in cursor.fetchall()
                    ]

                has_assignment = any(
                    _safe_text(detail.get("assembly_status")).strip() != ""
                    or _safe_text(detail.get("install_status")).strip() != ""
                    for detail in details_for_status
                )

                actual_status = _derive_order_status(
                    details=details_for_status,
                    schedule_tasks=schedule_tasks,
                    has_assignment=has_assignment,
                )

                cursor.execute(
                    f"""
                    UPDATE {MAIN_TABLE_NAME}
                    SET status = %s,
                        updated_at = NOW()
                    WHERE order_number = %s
                    """,
                    (actual_status, normalized_order),
                )

        conn.commit()

    enqueue_detail_metrics_recalculation([normalized_order], source="update_main_order_status")

    action_meta = action_map[normalized_action]
    record_activity_event(
        action_key=action_meta["log_key"],
        action_label=action_meta["label"],
        description=(
            f"{action_meta['label']}: {normalized_order}"
            f" (було: {current_display_status or '-'}, стало: {actual_status})"
        ),
        actor=actor,
        entity_type="main_order",
        entity_id=normalized_order,
        order_number=normalized_order,
        source_table=MAIN_TABLE_NAME,
        source_op="UPDATE",
        details={
            "action": normalized_action,
            "previous_status": current_display_status,
            "next_status": actual_status,
        },
    )

    return load_main_order_card(normalized_order)
