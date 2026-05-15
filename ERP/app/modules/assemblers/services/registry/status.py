from __future__ import annotations

from datetime import date
from decimal import Decimal

from .constants import (
    ACTIVE_STATUS,
    ASSEMBLY_TASK_TYPE,
    INSTALL_TASK_TYPE,
    TASK_STATUS_COMPLETED,
    TASK_STATUS_IN_PROGRESS,
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
) -> str:
    from .constants import TASK_STATUS_IN_PROGRESS, TASK_STATUS_PAUSED as _PAUSED
    if not is_required:
        return skipped_label or "—"
    normalized_status = _safe_text(saved_status)
    if completed_at or normalized_status.casefold() == TASK_STATUS_COMPLETED.casefold():
        return TASK_STATUS_COMPLETED
    if normalized_status in {TASK_STATUS_IN_PROGRESS, _PAUSED} or started_days > 0:
        return TASK_STATUS_IN_PROGRESS
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

    if any(
        _safe_text(task.get("status")).casefold() == TASK_STATUS_PAUSED.casefold()
        for task in schedule_tasks
    ):
        return TASK_STATUS_PAUSED

    today = date.today()
    has_future_assembly_tasks = False
    has_future_install_tasks = False
    has_today_assembly = False
    has_today_install = False

    for task in schedule_tasks:
        task_type = _safe_text(task.get("task_type")).casefold()
        if task_type not in {ASSEMBLY_TASK_TYPE, INSTALL_TASK_TYPE}:
            continue

        scheduled_for = task.get("scheduled_for")
        task_status = _safe_text(task.get("status")).casefold()
        if not isinstance(scheduled_for, date) or scheduled_for < today:
            continue

        is_today = scheduled_for == today
        is_future = scheduled_for > today
        is_queued = task_status == "у черзі"

        if task_type == ASSEMBLY_TASK_TYPE:
            if is_today:
                has_today_assembly = True
            elif is_future and is_queued:
                has_future_assembly_tasks = True
        elif task_type == INSTALL_TASK_TYPE:
            if is_today:
                has_today_install = True
            elif is_future and is_queued:
                has_future_install_tasks = True

    # Also check planned dates in details if no schedule tasks found
    if not has_future_assembly_tasks and not has_today_assembly and details:
        for detail in details:
            if detail.get("requires_assembly"):
                planned_assembly = detail.get("planned_assembly_due_at")
                if isinstance(planned_assembly, date):
                    if planned_assembly == today:
                        has_today_assembly = True
                    elif planned_assembly > today:
                        has_future_assembly_tasks = True

    if not has_future_install_tasks and not has_today_install and details:
        for detail in details:
            if detail.get("requires_install"):
                planned_install = detail.get("planned_install_due_at")
                if isinstance(planned_install, date):
                    if planned_install == today:
                        has_today_install = True
                    elif planned_install > today:
                        has_future_install_tasks = True

    if has_today_install:
        return "Монтаж"
    if has_today_assembly:
        return "Збірка"
    if has_future_install_tasks:
        return "Заплановано монтаж"
    if has_future_assembly_tasks:
        return "Запланована збірка"
    if not has_assignment:
        return ACTIVE_STATUS
    return "Простой"
