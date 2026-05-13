"""Schedule domain service package.

This module is the single source of truth for manager and mobile task workflows.
"""

from .admin import create_schedule_tasks, edit_schedule_tasks, load_schedule_tasks
from .constants import (
    ALLOWED_APP_TASK_ACTIONS,
    ALLOWED_EDIT_ACTIONS,
    ALLOWED_TASK_TYPES,
    SCHEDULE_TASKS_TABLE,
    TASK_STATUS_COMPLETED,
    TASK_STATUS_IN_PROGRESS,
    TASK_STATUS_NO_EXECUTION,
    TASK_STATUS_PAUSED,
    TASK_STATUS_QUEUED,
)
from .mobile import load_user_schedule_tasks, update_user_task_status
from .schema import ensure_schedule_schema, run_schedule_daily_cutoff_catchup

__all__ = [
    "ALLOWED_APP_TASK_ACTIONS",
    "ALLOWED_EDIT_ACTIONS",
    "ALLOWED_TASK_TYPES",
    "SCHEDULE_TASKS_TABLE",
    "TASK_STATUS_COMPLETED",
    "TASK_STATUS_IN_PROGRESS",
    "TASK_STATUS_NO_EXECUTION",
    "TASK_STATUS_PAUSED",
    "TASK_STATUS_QUEUED",
    "create_schedule_tasks",
    "edit_schedule_tasks",
    "ensure_schedule_schema",
    "run_schedule_daily_cutoff_catchup",
    "load_schedule_tasks",
    "load_user_schedule_tasks",
    "update_user_task_status",
]
