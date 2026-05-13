from __future__ import annotations

from datetime import date, timedelta

from app.modules.assemblers.repositories.schedule_repo import (
    delete_schedule_tasks,
    fetch_allowed_workers,
    fetch_detail_stage_rows_by_order,
    fetch_order_customer_map,
    fetch_schedule_week_rows,
    fetch_tasks_for_edit,
    insert_schedule_tasks,
    update_schedule_tasks_parts,
)
from app.modules.assemblers.services.registry import enqueue_detail_metrics_recalculation
from app.modules.assemblers.services.staff import ALLOWED_SUBDIVISIONS

from .constants import ALLOWED_EDIT_ACTIONS, ALLOWED_TASK_TYPES, TASK_STATUS_QUEUED
from .helpers import (
    _find_blocked_selected_parts,
    _normalize_selected_parts,
    _normalize_task_ids,
    _normalize_task_type,
    _parse_iso_date,
    _safe_text,
    _start_of_week,
    _task_row_to_dict,
)
from .schema import ensure_schedule_schema


def load_schedule_tasks(subdivision: str, start_date: str) -> dict:
    """Load weekly schedule tasks for management grid by subdivision."""
    ensure_schedule_schema()
    normalized_subdivision = _safe_text(subdivision)
    if normalized_subdivision not in ALLOWED_SUBDIVISIONS:
        raise ValueError("Невірний підрозділ")

    parsed_start = _parse_iso_date(start_date) or _start_of_week(date.today())
    week_start = _start_of_week(parsed_start)
    week_end = week_start + timedelta(days=6)

    rows = fetch_schedule_week_rows(
        subdivision=normalized_subdivision,
        week_start=week_start,
        week_end=week_end,
    )
    customer_fallbacks = fetch_order_customer_map(
        [_safe_text(row[6]) for row in rows if _safe_text(row[6])]
    )

    tasks = [_task_row_to_dict(row, customer_fallbacks) for row in rows]

    return {
        "week_start": week_start.isoformat(),
        "week_end": week_end.isoformat(),
        "tasks": tasks,
    }


def create_schedule_tasks(*, subdivision: str, task_type: str, cells: list[dict], order_number=None, selected_parts=None, description=None) -> dict:
    """Create schedule tasks from selected grid cells for assembly/install/related workflows."""
    ensure_schedule_schema()
    normalized_subdivision = _safe_text(subdivision)
    if normalized_subdivision not in ALLOWED_SUBDIVISIONS:
        raise ValueError("Невірний підрозділ")

    normalized_task_type = _normalize_task_type(task_type)
    if normalized_task_type not in ALLOWED_TASK_TYPES:
        raise ValueError("Невірний тип задачі")

    normalized_order_number = _safe_text(order_number)
    normalized_description = _safe_text(description)
    normalized_cells: list[tuple[int, date]] = []
    seen_cells: set[tuple[int, date]] = set()

    for item in cells or []:
        if not isinstance(item, dict):
            continue
        try:
            source_user_id = int(item.get("source_user_id"))
        except (TypeError, ValueError):
            continue
        scheduled_for = _parse_iso_date(item.get("scheduled_for"))
        if not scheduled_for:
            continue
        key = (source_user_id, scheduled_for)
        if key in seen_cells:
            continue
        seen_cells.add(key)
        normalized_cells.append(key)

    if not normalized_cells:
        raise ValueError("Треба обрати хоча б одну комірку графіка")

    allowed_workers = fetch_allowed_workers(
        subdivision=normalized_subdivision,
        source_user_ids=[cell[0] for cell in normalized_cells],
    )

    normalized_cells = [cell for cell in normalized_cells if cell[0] in allowed_workers]
    if not normalized_cells:
        raise ValueError("Не вдалося знайти жодного збиральника для цього підрозділу")

    insert_values = []
    if normalized_task_type == "related":
        if not normalized_description:
            raise ValueError("Для супутньої задачі треба вказати опис")

        for source_user_id, scheduled_for in normalized_cells:
            insert_values.append(
                (
                    source_user_id,
                    allowed_workers.get(source_user_id, ""),
                    normalized_subdivision,
                    scheduled_for,
                    normalized_task_type,
                    TASK_STATUS_QUEUED,
                    "",
                    "",
                    "",
                    "",
                    "",
                    normalized_description,
                )
            )
    else:
        if not normalized_order_number:
            raise ValueError("Для збірки або монтажу треба вказати номер замовлення")

        aggregated_part_numbers, aggregated_customers, aggregated_product_names, aggregated_constructor_statuses = _normalize_selected_parts(selected_parts)
        canonical_customer = fetch_order_customer_map([normalized_order_number]).get(normalized_order_number, "")

        blocked_parts = _find_blocked_selected_parts(
            fetch_detail_stage_rows_by_order(order_number=normalized_order_number),
            selected_parts=selected_parts,
            task_type=normalized_task_type,
        )
        if blocked_parts:
            raise ValueError(
                "Неможливо призначити вироби через некоректний статус: "
                + ", ".join(blocked_parts[:5])
            )

        for source_user_id, scheduled_for in normalized_cells:
            insert_values.append(
                (
                    source_user_id,
                    allowed_workers.get(source_user_id, ""),
                    normalized_subdivision,
                    scheduled_for,
                    normalized_task_type,
                    TASK_STATUS_QUEUED,
                    normalized_order_number,
                    canonical_customer or aggregated_customers,
                    aggregated_part_numbers,
                    aggregated_product_names,
                    aggregated_constructor_statuses,
                    "",
                )
            )

    created_count = insert_schedule_tasks(insert_values)

    if normalized_order_number:
        enqueue_detail_metrics_recalculation([normalized_order_number], source="schedule_create")

    return {"created_count": created_count}


def edit_schedule_tasks(*, subdivision: str, action: str, task_ids=None, order_number=None, selected_parts=None) -> dict:
    """Edit or delete queued schedule tasks from manager UI."""
    ensure_schedule_schema()
    normalized_subdivision = _safe_text(subdivision)
    if normalized_subdivision not in ALLOWED_SUBDIVISIONS:
        raise ValueError("Невірний підрозділ")

    normalized_action = _safe_text(action)
    if normalized_action not in ALLOWED_EDIT_ACTIONS:
        raise ValueError("Невірна дія редагування")

    normalized_task_ids = _normalize_task_ids(task_ids)
    if not normalized_task_ids:
        raise ValueError("Треба обрати хоча б одну задачу")

    normalized_order_number = _safe_text(order_number)

    tasks = fetch_tasks_for_edit(subdivision=normalized_subdivision, task_ids=normalized_task_ids)
    if not tasks:
        raise ValueError("Не вдалося знайти вибрані задачі")
    if len(tasks) != len(normalized_task_ids):
        raise ValueError("Частину задач не знайдено")
    if normalized_action == "delete" and any(task.get("status") != TASK_STATUS_QUEUED for task in tasks):
        raise ValueError("Редагувати можна лише задачі зі статусом У черзі")

    if normalized_action in {"delete", "admin_delete"}:
        affected_count = delete_schedule_tasks(subdivision=normalized_subdivision, task_ids=normalized_task_ids)
    else:
        unique_orders = {task.get("order_number") for task in tasks if _safe_text(task.get("order_number"))}
        if len(unique_orders) != 1:
            raise ValueError("Для заміни частин оберіть задачі одного замовлення")
        target_order_number = normalized_order_number or unique_orders.pop()

        aggregated_part_numbers, aggregated_customers, aggregated_product_names, aggregated_constructor_statuses = _normalize_selected_parts(selected_parts)
        canonical_customer = fetch_order_customer_map([target_order_number]).get(target_order_number, "")

        affected_count = update_schedule_tasks_parts(
            subdivision=normalized_subdivision,
            task_ids=normalized_task_ids,
            order_number=target_order_number,
            customer=canonical_customer or aggregated_customers,
            part_number=aggregated_part_numbers,
            product_name=aggregated_product_names,
            constructor_status=aggregated_constructor_statuses,
        )

    affected_orders = {
        _safe_text(task.get("order_number"))
        for task in tasks
        if _safe_text(task.get("order_number"))
    }
    if normalized_order_number:
        affected_orders.add(normalized_order_number)
    if affected_orders:
        enqueue_detail_metrics_recalculation(sorted(affected_orders), source="schedule_edit")

    return {"affected_count": affected_count}
