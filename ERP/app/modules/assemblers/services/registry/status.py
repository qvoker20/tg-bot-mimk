from __future__ import annotations

from datetime import date
from decimal import Decimal

from .constants import (
    ACTIVE_STATUS,
    ASSEMBLY_TASK_TYPE,
    INSTALL_TASK_TYPE,
    TASK_STATUS_COMPLETED,
    TASK_STATUS_IN_PROGRESS,
    TASK_STATUS_NO_EXECUTION,
    TASK_STATUS_PAUSED,
    TASK_STATUS_QUEUED,
)
from .utils import _safe_text, _count_workers, _normalize_datetime


def _filter_required_stage_details(details: list[dict], *, required_key: str) -> list[dict]:
    return [detail for detail in details if bool(detail.get(required_key, True))]


def _build_detail_status_value(
    *,
    assembly_status: str,
    install_status: str,
    assembly_completed_at,
    install_completed_at,
) -> str:
    normalized_assembly_status = _safe_text(assembly_status)
    normalized_install_status = _safe_text(install_status)
    if normalized_assembly_status == "—":
        normalized_assembly_status = ""
    if normalized_install_status == "—":
        normalized_install_status = ""

    if install_completed_at:
        return "Монтаж завершено"
    if assembly_completed_at:
        return "Збірку завершено"
    if normalized_install_status:
        return f"Монтаж: {normalized_install_status}"
    if normalized_assembly_status:
        return f"Збірка: {normalized_assembly_status}"
    return "—"


def _normalize_execution_status(
    saved_status: str,
    completed_at,
    started_days: int,
    *,
    is_required: bool = True,
    skipped_label: str = "",
    has_today_schedule: bool = False,
) -> str:
    from .constants import TASK_STATUS_IN_PROGRESS, TASK_STATUS_PAUSED as _PAUSED
    if not is_required:
        return skipped_label or "—"
    normalized_status = _safe_text(saved_status)
    if completed_at or normalized_status.casefold() == TASK_STATUS_COMPLETED.casefold():
        return TASK_STATUS_COMPLETED
    if has_today_schedule:
        return TASK_STATUS_IN_PROGRESS
    if normalized_status.casefold() == _PAUSED.casefold():
        return TASK_STATUS_QUEUED
    if normalized_status.casefold() == TASK_STATUS_IN_PROGRESS.casefold():
        return TASK_STATUS_QUEUED
    return TASK_STATUS_QUEUED


def _calc_plan_percent(details: list[dict], key: str, *, required_key: str | None = None) -> str:
    relevant_details = (
        _filter_required_stage_details(details, required_key=required_key)
        if required_key
        else list(details)
    )
    total = len(relevant_details)
    if total == 0:
        return "—"
    planned = sum(1 for d in relevant_details if d.get(key))
    return f"{round(planned / total * 100)}%"


def _build_status_distribution(statuses: list[str], *, empty_label: str = "-") -> str:
    if not statuses:
        return empty_label

    total = len(statuses)
    counts = {
        TASK_STATUS_QUEUED.lower(): 0,
        TASK_STATUS_IN_PROGRESS.lower(): 0,
        TASK_STATUS_PAUSED.lower(): 0,
        TASK_STATUS_COMPLETED.lower(): 0,
    }

    for status in statuses:
        normalized = _safe_text(status).lower()
        if not normalized or normalized == "-":
            counts["у черзі"] += 1
        elif normalized in counts:
            counts[normalized] += 1
        else:
            counts["у черзі"] += 1

    parts = []
    for label, count in counts.items():
        if count > 0:
            pct = round(count / total * 100)
            parts.append(f"{pct}% {label}")

    return " | ".join(parts) if parts else empty_label


def _build_stage_status_distribution(
    details: list[dict],
    *,
    status_key: str,
    completed_at_key: str,
    required_key: str,
    empty_label: str = "Не потрібно",
) -> str:
    relevant_details = _filter_required_stage_details(details, required_key=required_key)
    if not relevant_details:
        return empty_label

    normalized_statuses: list[str] = []
    for detail in relevant_details:
        if _normalize_datetime(detail.get(completed_at_key)):
            normalized_statuses.append(TASK_STATUS_COMPLETED)
            continue
        normalized_statuses.append(_safe_text(detail.get(status_key)))

    return _build_status_distribution(normalized_statuses, empty_label=empty_label)


def _build_workers_list(details: list[dict], key: str) -> str:
    names: list[str] = []
    seen: set[str] = set()

    for detail in details:
        raw = _safe_text(detail.get(key))
        if not raw or raw == "-":
            continue
        for part in raw.split(","):
            name = _safe_text(part)
            if not name or name == "-":
                continue
            normalized = name.lower()
            if normalized in seen:
                continue
            seen.add(normalized)
            names.append(name)

    return ", ".join(names) if names else "-"


def _is_completed_stage_status(value: str) -> bool:
    return _safe_text(value).casefold() == TASK_STATUS_COMPLETED.casefold()


def _has_worker_assignment(value: str) -> bool:
    return _count_workers(value) > 0


def _is_detail_stage_completed(
    detail: dict,
    *,
    status_key: str,
    completed_at_key: str,
    required_key: str,
) -> bool:
    if not bool(detail.get(required_key, True)):
        return True
    if _normalize_datetime(detail.get(completed_at_key)):
        return True
    return _is_completed_stage_status(detail.get(status_key))


def _derive_order_status(
    *, details: list[dict], schedule_tasks: list[dict], has_assignment: bool
) -> str:
    if details:
        all_assembly_completed = all(
            _is_detail_stage_completed(
                detail,
                status_key="assembly_status",
                completed_at_key="assembly_completed_at",
                required_key="requires_assembly",
            )
            for detail in details
        )
        all_install_completed = all(
            _is_detail_stage_completed(
                detail,
                status_key="install_status",
                completed_at_key="install_completed_at",
                required_key="requires_install",
            )
            for detail in details
        )
        if all_assembly_completed and all_install_completed:
            return TASK_STATUS_COMPLETED

    today = date.today()
    has_today_assembly = False
    has_today_install = False
    nearest_future_date = None
    nearest_future_type = ""

    active_task_statuses = {
        TASK_STATUS_QUEUED.casefold(),
        TASK_STATUS_IN_PROGRESS.casefold(),
    }
    closed_task_statuses = {
        TASK_STATUS_COMPLETED.casefold(),
        TASK_STATUS_PAUSED.casefold(),
        TASK_STATUS_NO_EXECUTION.casefold(),
    }

    has_schedule_history = False
    has_today_pause = False

    for task in schedule_tasks:
        task_type = _safe_text(task.get("task_type")).casefold()
        if task_type not in {ASSEMBLY_TASK_TYPE, INSTALL_TASK_TYPE}:
            continue
        has_schedule_history = True

        scheduled_for = task.get("scheduled_for")
        task_status = _safe_text(task.get("status")).casefold()
        if not isinstance(scheduled_for, date) or scheduled_for < today:
            continue

        is_paused = task_status == TASK_STATUS_PAUSED.casefold()
        is_closed_status = task_status in closed_task_statuses
        is_active_status = task_status in active_task_statuses or (task_status and not is_closed_status)

        # Track paused tasks on today specifically
        if is_paused and scheduled_for == today:
            has_today_pause = True

        if not is_active_status:
            continue

        if scheduled_for == today:
            if task_type == INSTALL_TASK_TYPE:
                has_today_install = True
            elif task_type == ASSEMBLY_TASK_TYPE:
                has_today_assembly = True
            continue

        if nearest_future_date is None or scheduled_for < nearest_future_date:
            nearest_future_date = scheduled_for
            nearest_future_type = task_type
            continue

        # On the same nearest day, монтаж has priority over збірка.
        if (
            nearest_future_date is not None
            and scheduled_for == nearest_future_date
            and nearest_future_type != INSTALL_TASK_TYPE
            and task_type == INSTALL_TASK_TYPE
        ):
            nearest_future_type = INSTALL_TASK_TYPE

    if has_today_install:
        return "Монтаж"
    if has_today_assembly:
        return "Збірка"
    if has_today_pause:
        return TASK_STATUS_PAUSED
    if nearest_future_type == INSTALL_TASK_TYPE:
        return "Заплановано монтаж"
    if nearest_future_type == ASSEMBLY_TASK_TYPE:
        return "Запланована збірка"

    has_detail_history = any(
        _normalize_datetime(detail.get("assembly_started_at"))
        or _normalize_datetime(detail.get("assembly_completed_at"))
        or _normalize_datetime(detail.get("install_started_at"))
        or _normalize_datetime(detail.get("install_completed_at"))
        for detail in details
    )

    if not has_assignment and not has_schedule_history and not has_detail_history:
        return ACTIVE_STATUS
    return "Простой"
