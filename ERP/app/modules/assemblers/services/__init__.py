"""Публічна точка доступу до сервісів модуля assemblers.

Файл експортує стабільний API для роутерів та інших модулів,
щоб зовнішній код не залежав від внутрішньої структури підпакетів.
"""

# Buffer / замовлення в буфері
from .buffer import load_buffer_rows
# Activity journal / журнал дій
from .activity_log import ensure_activity_log_schema, load_activity_log_rows, record_activity_event
from .registry import close_buffer_orders, transfer_buffer_orders

# Details / рядки деталей
from .registry import load_detail_rows, search_detail_rows_by_order

# Main orders / картка і список головних замовлень
from .main import load_main_order_card, load_main_rows, update_main_order_card

# Registry / перерахунки, черга, ensure_schema
from .registry import (
    enqueue_detail_metrics_recalculation,
    ensure_schema,
    process_detail_metrics_recalc_queue,
    recalculate_detail_metrics,
)

# Schedule / календар-планувальник задач
from .schedule import (
    create_schedule_tasks,
    edit_schedule_tasks,
    load_schedule_tasks,
    load_user_schedule_tasks,
    update_user_task_status,
)

# Settings / налаштування розрахунків
from .settings import (
    ensure_settings_schema,
    load_assembly_day_cost,
    load_assembly_workday_hours,
    save_assembly_day_cost,
    save_assembly_workday_hours,
)

# Staff / кадрові прив'язки збиральників
from .staff import ALLOWED_SUBDIVISIONS, ensure_staff_schema, load_assembler_staff, save_staff_assignment

__all__ = [
    "ALLOWED_SUBDIVISIONS",
    "close_buffer_orders",
    "ensure_activity_log_schema",
    "create_schedule_tasks",
    "enqueue_detail_metrics_recalculation",
    "edit_schedule_tasks",
    "ensure_schema",
    "ensure_settings_schema",
    "ensure_staff_schema",
    "load_assembler_staff",
    "load_assembly_day_cost",
    "load_assembly_workday_hours",
    "load_activity_log_rows",
    "load_buffer_rows",
    "load_detail_rows",
    "load_main_order_card",
    "load_main_rows",
    "load_schedule_tasks",
    "load_user_schedule_tasks",
    "process_detail_metrics_recalc_queue",
    "recalculate_detail_metrics",
    "save_assembly_day_cost",
    "save_assembly_workday_hours",
    "save_staff_assignment",
    "record_activity_event",
    "search_detail_rows_by_order",
    "transfer_buffer_orders",
    "update_main_order_card",
    "update_user_task_status",
]
