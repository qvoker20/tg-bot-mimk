from __future__ import annotations

MAIN_TABLE_NAME = "assemblers_main_orders"
DETAILS_TABLE_NAME = "assemblers_detail_rows"
DATA_DESIGNER_TABLE = "data_designer"
DATA_PRODUCTION_TABLE = "data_production"
DATA_METAL_TABLE = "data_metal"
PRODUCTION_DONE_STATUS = "завершено"
ACTIVE_STATUS = "Розподіл"
CLOSED_STATUS = "Закрито"
RECLAMATION_STATUS = "Рекламація"
SCHEDULE_TASKS_TABLE = "assemblers_schedule_tasks"
DETAIL_RECALC_QUEUE_TABLE = "assemblers_detail_recalc_queue"
ASSEMBLY_TASK_TYPE = "assembly"
INSTALL_TASK_TYPE = "install"
TASK_STATUS_QUEUED = "У черзі"
TASK_STATUS_IN_PROGRESS = "В роботі"
TASK_STATUS_PAUSED = "Пауза"
TASK_STATUS_COMPLETED = "Завершено"

DESIGNER_SHOP_COLUMNS: dict[str, str] = {
    "paint_shop": "column_14",
    "metal": "column_15",
    "veneer": "column_16",
    "plastic_hpl": "hpl",
    "joinery_shop": "column_18",
    "soft_shop": "column_19",
    "artificial_stone": "column_20",
    "compact_plate": "column_21",
    "dsp_countertop": "c",
    "sliding_systems": "column_23",
    "glass_mirror": "column_24",
    "frame_facades": "column_25",
    "glass_status": "column_26",
    "sliding_systems_status": "column_27",
    "frame_facades_status": "column_28",
    "ceramic_granite": "column_29",
}
