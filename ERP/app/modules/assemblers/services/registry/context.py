from __future__ import annotations

import re
from collections import defaultdict

from app.modules.assemblers.db.connection import get_db_connection

from .constants import (
    DATA_DESIGNER_TABLE,
    DATA_METAL_TABLE,
    DATA_PRODUCTION_TABLE,
    DESIGNER_SHOP_COLUMNS,
    ASSEMBLY_TASK_TYPE,
    INSTALL_TASK_TYPE,
    SCHEDULE_TASKS_TABLE,
    TASK_STATUS_COMPLETED,
    TASK_STATUS_IN_PROGRESS,
    TASK_STATUS_PAUSED,
    TASK_STATUS_QUEUED,
)
from .utils import (
    _safe_text,
    _split_csv_text,
    _parse_uk_date,
    _format_date,
    _build_products_text,
    _build_ratio,
    _pick_first_value,
    _is_done_status,
    _parse_part_number,
)


def _stage_status_rank(value: str) -> int:
    normalized = _safe_text(value).casefold()
    if normalized == TASK_STATUS_COMPLETED.casefold():
        return 3
    if normalized in {TASK_STATUS_IN_PROGRESS.casefold(), TASK_STATUS_PAUSED.casefold()}:
        return 2
    if normalized == TASK_STATUS_QUEUED.casefold():
        return 1
    return 0


def _part_matches_spec(part_number: int | None, raw_spec: str) -> bool:
    if part_number is None:
        return False

    text = _safe_text(raw_spec)
    if not text:
        return False

    text = text.replace("\u2013", "-").replace("\u2014", "-")
    text = re.sub(r"\([^)]*\)", "", text)
    text = re.sub(r"[^0-9,\-]", "", text)
    if not text:
        return False

    for chunk in [item.strip() for item in text.split(",") if item.strip()]:
        if "-" in chunk:
            left, right = chunk.split("-", 1)
            try:
                start = int(left)
                end = int(right)
            except ValueError:
                continue
            if start <= part_number <= end:
                return True
            continue

        try:
            if int(chunk) == part_number:
                return True
        except ValueError:
            continue

    return False


def _build_metal_status(col3, col4, col5) -> str:
    if _safe_text(col5):
        return "Доставлено"
    if _safe_text(col4):
        return "Фарбування"
    if _safe_text(col3):
        return "Цех металу"
    return "Немає"


def _task_matches_detail(
    *,
    detail_part_number: str,
    detail_product_name: str,
    task_part_numbers: set[str],
    task_product_names: set[str],
) -> bool:
    normalized_part_number = _safe_text(detail_part_number).casefold()
    normalized_product_name = _safe_text(detail_product_name).casefold()
    if normalized_part_number and normalized_part_number in task_part_numbers:
        return True
    if normalized_product_name and normalized_product_name in task_product_names:
        return True
    return False


def _build_schedule_execution_context(
    detail_specs: list[tuple[str, str, str]],
) -> dict[tuple[str, str, str], dict[str, object]]:
    normalized_specs = []
    seen_specs: set[tuple[str, str, str]] = set()
    order_to_specs: dict[str, list[tuple[str, str, str]]] = defaultdict(list)

    for order_number, part_number, product_name in detail_specs:
        normalized_spec = (
            _safe_text(order_number),
            _safe_text(part_number),
            _safe_text(product_name),
        )
        if not normalized_spec[0] or normalized_spec in seen_specs:
            continue
        seen_specs.add(normalized_spec)
        normalized_specs.append(normalized_spec)
        order_to_specs[normalized_spec[0]].append(normalized_spec)

    if not normalized_specs:
        return {}

    normalized_orders = list(order_to_specs.keys())

    with get_db_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute("SELECT to_regclass(%s)", (SCHEDULE_TASKS_TABLE,))
            if not cursor.fetchone()[0]:
                return {}

            cursor.execute(
                f"""
                SELECT
                    TRIM(COALESCE(order_number, '')),
                    TRIM(COALESCE(task_type, '')),
                    TRIM(COALESCE(assembler_name, '')),
                    TRIM(COALESCE(status, '')),
                    scheduled_for,
                    started_at,
                    completed_at,
                    COALESCE(pause_seconds, 0),
                    TRIM(COALESCE(part_number, '')),
                    TRIM(COALESCE(product_name, '')),
                    auto_closed_at
                FROM {SCHEDULE_TASKS_TABLE}
                WHERE TRIM(COALESCE(order_number, '')) = ANY(%s)
                  AND TRIM(COALESCE(task_type, '')) = ANY(%s)
                ORDER BY started_at NULLS LAST, id
                """,
                (normalized_orders, [ASSEMBLY_TASK_TYPE, INSTALL_TASK_TYPE]),
            )
            schedule_rows = cursor.fetchall()

    context: dict[tuple[str, str, str], dict[str, object]] = {}
    for order_number, task_type, assembler_name, status, scheduled_for, started_at, completed_at, pause_seconds, part_number, product_name, auto_closed_at in schedule_rows:
        normalized_order = _safe_text(order_number)
        normalized_type = _safe_text(task_type)
        normalized_name = _safe_text(assembler_name)
        normalized_status = _safe_text(status)
        raw_completed_at = completed_at
        if not normalized_order or normalized_type not in {ASSEMBLY_TASK_TYPE, INSTALL_TASK_TYPE}:
            continue
        if auto_closed_at is not None:
            # Auto-cutoff closes the schedule task, but details stage must stay non-completed.
            normalized_status = TASK_STATUS_QUEUED
            completed_at = None

        started_day = started_at.date() if hasattr(started_at, "date") else scheduled_for
        task_part_numbers = {value.casefold() for value in _split_csv_text(part_number)}
        task_product_names = {value.casefold() for value in _split_csv_text(product_name)}

        for detail_key in order_to_specs.get(normalized_order, []):
            _, detail_part_number, detail_product_name = detail_key
            if not _task_matches_detail(
                detail_part_number=detail_part_number,
                detail_product_name=detail_product_name,
                task_part_numbers=task_part_numbers,
                task_product_names=task_product_names,
            ):
                continue

            detail_context = context.setdefault(
                detail_key,
                {
                    "assembly_names": [],
                    "assembly_seen": set(),
                    "assembly_started_at": None,
                    "assembly_completed_at": None,
                    "assembly_status": "",
                    "assembly_days": set(),
                    "assembly_daily_minutes": {},
                    "install_names": [],
                    "install_seen": set(),
                    "install_started_at": None,
                    "install_completed_at": None,
                    "install_status": "",
                    "install_days": set(),
                    "install_daily_minutes": {},
                },
            )

            names_key = "assembly_names" if normalized_type == ASSEMBLY_TASK_TYPE else "install_names"
            seen_key = "assembly_seen" if normalized_type == ASSEMBLY_TASK_TYPE else "install_seen"
            started_key = "assembly_started_at" if normalized_type == ASSEMBLY_TASK_TYPE else "install_started_at"
            completed_key = "assembly_completed_at" if normalized_type == ASSEMBLY_TASK_TYPE else "install_completed_at"
            status_key = "assembly_status" if normalized_type == ASSEMBLY_TASK_TYPE else "install_status"
            days_key = "assembly_days" if normalized_type == ASSEMBLY_TASK_TYPE else "install_days"
            daily_minutes_key = (
                "assembly_daily_minutes" if normalized_type == ASSEMBLY_TASK_TYPE else "install_daily_minutes"
            )

            if normalized_name and normalized_name not in detail_context[seen_key]:
                detail_context[seen_key].add(normalized_name)
                detail_context[names_key].append(normalized_name)

            if _stage_status_rank(normalized_status) > _stage_status_rank(detail_context[status_key]):
                detail_context[status_key] = normalized_status

            if normalized_status == TASK_STATUS_QUEUED and started_at is None:
                continue

            if started_at and (detail_context[started_key] is None or started_at < detail_context[started_key]):
                detail_context[started_key] = started_at
            if completed_at and (
                detail_context[completed_key] is None or completed_at > detail_context[completed_key]
            ):
                detail_context[completed_key] = completed_at
            if started_day:
                detail_context[days_key].add(started_day)

            if started_at and raw_completed_at and raw_completed_at >= started_at:
                total_seconds = int((raw_completed_at - started_at).total_seconds())
                effective_seconds = max(0, total_seconds - int(pause_seconds or 0))
                effective_minutes = effective_seconds // 60
                if effective_minutes > 0 and started_day:
                    daily_minutes = detail_context[daily_minutes_key]
                    current_daily_minutes = int(daily_minutes.get(started_day) or 0)
                    if effective_minutes > current_daily_minutes:
                        daily_minutes[started_day] = effective_minutes

    for detail_context in context.values():
        assembly_daily_minutes = detail_context.pop("assembly_daily_minutes", {})
        install_daily_minutes = detail_context.pop("install_daily_minutes", {})
        detail_context["assembly_worker"] = ", ".join(detail_context.pop("assembly_names")) or ""
        detail_context["install_worker"] = ", ".join(detail_context.pop("install_names")) or ""
        assembly_days = detail_context.pop("assembly_days")
        install_days = detail_context.pop("install_days")
        detail_context["assembly_effective_minutes"] = sum(int(value or 0) for value in assembly_daily_minutes.values())
        detail_context["install_effective_minutes"] = sum(int(value or 0) for value in install_daily_minutes.values())
        detail_context["assembly_days_count"] = len(assembly_daily_minutes) or len(assembly_days)
        detail_context["install_days_count"] = len(install_daily_minutes) or len(install_days)
        detail_context.pop("assembly_seen", None)
        detail_context.pop("install_seen", None)

    return context


def _load_detail_production_context(
    order_parts: list[tuple[str, str]],
) -> dict[tuple[str, str], dict]:
    normalized_pairs = [
        (_safe_text(order_number), _safe_text(part_number))
        for order_number, part_number in order_parts
        if _safe_text(order_number)
    ]
    order_numbers = sorted({order_number for order_number, _ in normalized_pairs})
    if not order_numbers:
        return {}

    with get_db_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                f"""
                SELECT
                    column_1,
                    column_4,
                    column_9
                FROM {DATA_PRODUCTION_TABLE}
                WHERE TRIM(COALESCE(column_1, '')) = ANY(%s)
                ORDER BY column_1, id
                """,
                (order_numbers,),
            )
            production_rows = cursor.fetchall()

    grouped_production: dict[str, list[dict]] = defaultdict(list)
    for order_number, part_spec, status in production_rows:
        normalized_order = _safe_text(order_number)
        if not normalized_order:
            continue
        grouped_production[normalized_order].append(
            {
                "part_spec": _safe_text(part_spec),
                "status": _safe_text(status),
            }
        )

    result = {}
    for order_number, part_number_text in normalized_pairs:
        part_number = _parse_part_number(part_number_text)
        matching = [
            row
            for row in grouped_production.get(order_number, [])
            if _part_matches_spec(part_number, row.get("part_spec", ""))
        ]
        total = len(matching)
        completed = sum(1 for row in matching if _is_done_status(row.get("status", "")))
        result[(order_number, part_number_text)] = {
            "production_launches": total,
            "production_launches_display": total if total > 0 else "не запущено",
            "production_completed": completed,
        }

    return result


def _load_live_order_context(order_numbers: list[str]) -> dict[str, dict]:
    normalized_orders = [_safe_text(value) for value in order_numbers if _safe_text(value)]
    if not normalized_orders:
        return {}

    shop_select_sql = ",\n                    ".join(DESIGNER_SHOP_COLUMNS.values())

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
                    column_32,
                    {shop_select_sql}
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
                    column_8,
                    column_9,
                    column_12
                FROM {DATA_PRODUCTION_TABLE}
                WHERE TRIM(COALESCE(column_1, '')) = ANY(%s)
                ORDER BY column_1, id
                """,
                (normalized_orders,),
            )
            production_rows = cursor.fetchall()

            cursor.execute("SELECT to_regclass(%s)", (DATA_METAL_TABLE,))
            metal_table_exists = cursor.fetchone()[0] is not None
            metal_rows = []
            if metal_table_exists:
                cursor.execute(
                    f"""
                    SELECT
                        column_1,
                        column_5
                    FROM {DATA_METAL_TABLE}
                    WHERE TRIM(COALESCE(column_1, '')) = ANY(%s)
                    ORDER BY column_1, id
                    """,
                    (normalized_orders,),
                )
                metal_rows = cursor.fetchall()

    grouped_designer: dict[str, list[dict]] = defaultdict(list)
    for record in designer_rows:
        order_number = _safe_text(record[0])
        if not order_number:
            continue

        item: dict = {
            "order_number": order_number,
            "part_number": record[1],
            "customer": record[2],
            "product_name": record[3],
            "manager_name": record[4],
            "order_type": record[5],
            "order_value": record[6],
            "constructor_name": record[7],
            "constructor_completed_at": record[8],
            "signed_at": record[9],
            "planned_install_at": record[11] or record[10],
        }

        for offset, key in enumerate(DESIGNER_SHOP_COLUMNS.keys(), start=12):
            item[key] = record[offset]

        if not _safe_text(item.get("sliding_systems")):
            item["sliding_systems"] = item.get("frame_facades")
        if not _safe_text(item.get("glass_mirror")):
            item["glass_mirror"] = item.get("glass_status")
        if not _safe_text(item.get("frame_facades")):
            item["frame_facades"] = item.get("frame_facades_status")

        grouped_designer[order_number].append(item)

    grouped_production: dict[str, list[dict]] = defaultdict(list)
    for record in production_rows:
        order_number = _safe_text(record[0])
        if not order_number:
            continue
        grouped_production[order_number].append(
            {
                "material": record[1],
                "status": record[2],
                "completed_at": record[3],
            }
        )

    grouped_metal: dict[str, list[dict]] = defaultdict(list)
    for record in metal_rows:
        order_number = _safe_text(record[0])
        if not order_number:
            continue
        grouped_metal[order_number].append(
            {
                "warehouse_received_at": _safe_text(record[1]),
            }
        )

    context: dict[str, dict] = {}
    for order_number in normalized_orders:
        designer = grouped_designer.get(order_number, [])
        production = grouped_production.get(order_number, [])
        metal = grouped_metal.get(order_number, [])
        constructor_done = sum(
            1 for row in designer if _parse_uk_date(row.get("constructor_completed_at", ""))
        )
        constructor_total = len(designer)
        production_done = sum(1 for row in production if _is_done_status(row.get("status", "")))
        production_total = len(production)
        metal_done = sum(
            1 for row in metal if _parse_uk_date(row.get("warehouse_received_at", ""))
        )
        metal_total = len(metal)

        row_context: dict = {
            "customer": _pick_first_value([row.get("customer") for row in designer]),
            "order_type": _pick_first_value([row.get("order_type") for row in designer]),
            "manager_name": _pick_first_value([row.get("manager_name") for row in designer]),
            "constructor_name": _pick_first_value([row.get("constructor_name") for row in designer]),
            "products": _build_products_text([row.get("product_name") for row in designer]),
            "constructor_status": _build_ratio(constructor_done, constructor_total),
            "production_status": _build_ratio(production_done, production_total),
            "metal_status": _build_ratio(metal_done, metal_total) if metal_total > 0 else "-",
            "parts_count": constructor_total,
            "launches_count": production_total,
            "materials": _build_products_text([row.get("material") for row in production]),
            "signed_at": _format_date(
                _parse_uk_date(_pick_first_value([row.get("signed_at") for row in designer], default=""))
            ),
            "planned_install_at": _format_date(
                _parse_uk_date(
                    _pick_first_value([row.get("planned_install_at") for row in designer], default="")
                )
            ),
        }

        for key in DESIGNER_SHOP_COLUMNS.keys():
            row_context[key] = _build_products_text([row.get(key) for row in designer])

        context[order_number] = row_context

    return context
