from __future__ import annotations

from datetime import date

from app.modules.assemblers.repositories.schedule_repo import (
    fetch_detail_rows_for_product_match,
    fetch_order_customer_map,
    fetch_task_by_id,
    fetch_task_for_user,
    fetch_user_day_task_rows,
    mark_detail_rows_completed,
    mark_task_completed,
    mark_task_paused,
    mark_task_resumed,
    mark_task_started,
)
from app.modules.assemblers.services.activity_log import record_activity_event
from app.modules.assemblers.services.registry import enqueue_detail_metrics_recalculation

from .constants import (
    ALLOWED_APP_TASK_ACTIONS,
    TASK_STATUS_COMPLETED,
    TASK_STATUS_IN_PROGRESS,
    TASK_STATUS_PAUSED,
    TASK_STATUS_QUEUED,
    SCHEDULE_TASKS_TABLE,
)
from .helpers import (
    _detail_row_matches_selected_product,
    _normalize_completed_products,
    _normalize_location_payload,
    _normalize_task_type,
    _parse_iso_date,
    _safe_text,
    _task_row_to_dict,
)
from .schema import ensure_schedule_schema


def load_user_schedule_tasks(*, source_user_id: int, day: str) -> dict:
    """Load one-day task list for assembler mobile app."""
    ensure_schedule_schema()
    try:
        normalized_user_id = int(source_user_id)
    except (TypeError, ValueError):
        raise ValueError("Не вдалося визначити користувача")

    target_day = _parse_iso_date(day) or date.today()

    rows = fetch_user_day_task_rows(source_user_id=normalized_user_id, target_day=target_day)
    customer_fallbacks = fetch_order_customer_map(
        [_safe_text(row[6]) for row in rows if _safe_text(row[6])]
    )

    tasks = [_task_row_to_dict(row, customer_fallbacks) for row in rows]
    return {
        "day": target_day.isoformat(),
        "tasks": tasks,
    }


def update_user_task_status(*, source_user_id: int, task_id: int, action: str, pause_reason=None, location=None, selected_products=None, actor=None) -> dict:
    """Perform start/pause/resume/finish transition for a mobile task."""
    ensure_schedule_schema()
    try:
        normalized_user_id = int(source_user_id)
        normalized_task_id = int(task_id)
    except (TypeError, ValueError):
        raise ValueError("Некоректна задача")

    normalized_action = _safe_text(action)
    if normalized_action not in ALLOWED_APP_TASK_ACTIONS:
        raise ValueError("Невірна дія по задачі")

    normalized_pause_reason = _safe_text(pause_reason)
    normalized_location = _normalize_location_payload(location) if normalized_action in {"start", "finish"} else None
    normalized_selected_products = _normalize_completed_products(selected_products) if normalized_action == "finish" else []

    row = fetch_task_for_user(task_id=normalized_task_id, source_user_id=normalized_user_id)
    if not row:
        raise ValueError("Задачу не знайдено")

    task = _task_row_to_dict(row)
    current_status = task.get("status") or TASK_STATUS_QUEUED
    scheduled_for = row[3]
    normalized_task_type = _normalize_task_type(task.get("task_type"))

    if normalized_action == "start":
        if current_status != TASK_STATUS_QUEUED:
            raise ValueError("Розпочати можна лише задачу зі статусом У черзі")
        if scheduled_for != date.today():
            raise ValueError("Розпочати можна лише сьогоднішню задачу")
        mark_task_started(task_id=normalized_task_id, location=normalized_location)
        message = "Задачу розпочато."
        record_activity_event(
            action_key="schedule.mobile.start",
            action_label="Розпочато задачу",
            description=f"Розпочато задачу {task.get('order_number', '')} {task.get('part_number', '')}".strip(),
            actor=actor,
            entity_type="schedule_task",
            entity_id=str(normalized_task_id),
            order_number=_safe_text(task.get("order_number")),
            subdivision=_safe_text(task.get("subdivision")),
            source_table=SCHEDULE_TASKS_TABLE,
            source_op="UPDATE",
            details={"task_id": normalized_task_id, "task_type": normalized_task_type},
        )
    elif normalized_action == "pause":
        if current_status != TASK_STATUS_IN_PROGRESS:
            raise ValueError("На паузу можна поставити лише задачу зі статусом В роботі")
        if not normalized_pause_reason:
            raise ValueError("Вкажіть причину паузи")
        mark_task_paused(task_id=normalized_task_id, pause_reason=normalized_pause_reason)
        message = "Задачу поставлено на паузу."
        record_activity_event(
            action_key="schedule.mobile.pause",
            action_label="Поставлено на паузу",
            description=f"Пауза задачі {task.get('order_number', '')} {task.get('part_number', '')}: {normalized_pause_reason}",
            actor=actor,
            entity_type="schedule_task",
            entity_id=str(normalized_task_id),
            order_number=_safe_text(task.get("order_number")),
            subdivision=_safe_text(task.get("subdivision")),
            source_table=SCHEDULE_TASKS_TABLE,
            source_op="UPDATE",
            details={"task_id": normalized_task_id, "pause_reason": normalized_pause_reason},
        )
    elif normalized_action == "resume":
        if current_status != TASK_STATUS_PAUSED:
            raise ValueError("Продовжити можна лише задачу зі статусом Пауза")
        mark_task_resumed(task_id=normalized_task_id)
        message = "Задачу повернуто в роботу."
        record_activity_event(
            action_key="schedule.mobile.resume",
            action_label="Продовжено задачу",
            description=f"Продовжено задачу {task.get('order_number', '')} {task.get('part_number', '')}".strip(),
            actor=actor,
            entity_type="schedule_task",
            entity_id=str(normalized_task_id),
            order_number=_safe_text(task.get("order_number")),
            subdivision=_safe_text(task.get("subdivision")),
            source_table=SCHEDULE_TASKS_TABLE,
            source_op="UPDATE",
            details={"task_id": normalized_task_id},
        )
    else:
        auto_closed_at = task.get("auto_closed_at")
        if not row[12]:
            raise ValueError("Завершити можна лише після фіксації початку виконання")
        if not (
            current_status in {TASK_STATUS_IN_PROGRESS, TASK_STATUS_PAUSED}
            or (current_status == TASK_STATUS_COMPLETED and auto_closed_at)
        ):
            raise ValueError("Завершити можна лише активну задачу")
        if normalized_task_type in {"assembly", "install"} and normalized_selected_products:
            detail_rows = fetch_detail_rows_for_product_match(order_number=task.get("order_number", ""))
            matched_detail_ids = []
            seen_detail_ids: set[int] = set()
            for detail_row in detail_rows:
                detail_id = int(detail_row[0])
                if detail_id in seen_detail_ids:
                    continue
                if any(_detail_row_matches_selected_product(detail_row, product) for product in normalized_selected_products):
                    seen_detail_ids.add(detail_id)
                    matched_detail_ids.append(detail_id)

            if not matched_detail_ids:
                raise ValueError("Не вдалося знайти вибрані вироби в замовленні. Оновіть список задач і спробуйте ще раз.")

            details_updated = mark_detail_rows_completed(
                detail_ids=matched_detail_ids,
                task_type=normalized_task_type,
                assembler_name=task.get("assembler_name", ""),
                started_at=row[12],
            )

            if details_updated <= 0:
                raise ValueError("Сервер не підтвердив завершення вибраних виробів. Спробуйте ще раз.")
        mark_task_completed(task_id=normalized_task_id, location=normalized_location)
        message = "Задачу завершено."
        record_activity_event(
            action_key="schedule.mobile.finish",
            action_label="Завершено задачу",
            description=f"Завершено задачу {task.get('order_number', '')} {task.get('part_number', '')}".strip(),
            actor=actor,
            entity_type="schedule_task",
            entity_id=str(normalized_task_id),
            order_number=_safe_text(task.get("order_number")),
            subdivision=_safe_text(task.get("subdivision")),
            source_table=SCHEDULE_TASKS_TABLE,
            source_op="UPDATE",
            details={
                "task_id": normalized_task_id,
                "task_type": normalized_task_type,
                "selected_products_count": len(normalized_selected_products),
            },
        )

    updated_row = fetch_task_by_id(normalized_task_id)
    customer_fallbacks = fetch_order_customer_map(
        [_safe_text(updated_row[6])] if updated_row and _safe_text(updated_row[6]) else []
    )

    recalculation_orders = []
    if normalized_task_type in {"assembly", "install"} and _safe_text(task.get("order_number")):
        recalculation_orders.append(_safe_text(task.get("order_number")))
    if recalculation_orders:
        enqueue_detail_metrics_recalculation(recalculation_orders, source="schedule_mobile_status")

    return {
        "task": _task_row_to_dict(updated_row, customer_fallbacks),
        "message": message,
    }
