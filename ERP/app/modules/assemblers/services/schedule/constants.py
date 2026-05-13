SCHEDULE_TASKS_TABLE = "assemblers_schedule_tasks"

TASK_STATUS_QUEUED = "У черзі"
TASK_STATUS_IN_PROGRESS = "В роботі"
TASK_STATUS_PAUSED = "Пауза"
TASK_STATUS_COMPLETED = "Завершено"
TASK_STATUS_NO_EXECUTION = "Без виконання"

ALLOWED_TASK_TYPES = {"assembly", "install", "related"}
ALLOWED_EDIT_ACTIONS = {"delete", "admin_delete"}
ALLOWED_APP_TASK_ACTIONS = {"start", "pause", "resume", "finish"}

TASK_TYPE_ALIASES = {
    "assembly": "assembly",
    "збірка": "assembly",
    "збирання": "assembly",
    "install": "install",
    "монтаж": "install",
    "related": "related",
    "супутня": "related",
    "супутня задача": "related",
}
