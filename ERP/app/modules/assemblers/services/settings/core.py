from __future__ import annotations

import threading
from decimal import Decimal, InvalidOperation

from app.modules.assemblers.db.connection import get_db_connection


ASSEMBLERS_SETTINGS_TABLE = "assemblers_settings"
ASSEMBLY_DAY_COST_KEY = "assembly_day_cost_per_assembler"
ASSEMBLY_WORKDAY_HOURS_KEY = "assembly_workday_hours"
DEFAULT_ASSEMBLY_DAY_COST = Decimal("35000")
DEFAULT_ASSEMBLY_WORKDAY_HOURS = Decimal("8")
_SETTINGS_SCHEMA_LOCK = threading.Lock()
_SETTINGS_SCHEMA_READY = False


def _safe_text(value) -> str:
    return " ".join(str(value or "").split()).strip()


def _normalize_decimal(value) -> Decimal:
    raw = _safe_text(value).replace(" ", "").replace(",", ".")
    if not raw:
        raise ValueError("Вкажіть вартість дня збірки")
    try:
        amount = Decimal(raw)
    except (InvalidOperation, ValueError):
        raise ValueError("Вартість дня збірки має бути числом")

    if amount < 0:
        raise ValueError("Вартість дня збірки не може бути від'ємною")

    return amount.quantize(Decimal("0.01"))


def _normalize_workday_hours(value) -> Decimal:
    amount = _normalize_decimal(value)
    if amount == 0:
        raise ValueError("Годин у робочому дні має бути більше нуля")
    return amount


def ensure_settings_schema() -> None:
    global _SETTINGS_SCHEMA_READY

    if _SETTINGS_SCHEMA_READY:
        return

    with _SETTINGS_SCHEMA_LOCK:
        if _SETTINGS_SCHEMA_READY:
            return

        with get_db_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    f"""
                    CREATE TABLE IF NOT EXISTS {ASSEMBLERS_SETTINGS_TABLE} (
                        setting_key TEXT PRIMARY KEY,
                        setting_value TEXT NOT NULL DEFAULT '',
                        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                        updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                    )
                    """
                )
            conn.commit()

        _SETTINGS_SCHEMA_READY = True


def load_assemblers_settings() -> dict[str, str]:
    ensure_settings_schema()
    with get_db_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                f"""
                SELECT setting_key, setting_value
                FROM {ASSEMBLERS_SETTINGS_TABLE}
                """
            )
            rows = cursor.fetchall()

    return {_safe_text(row[0]): _safe_text(row[1]) for row in rows if _safe_text(row[0])}


def load_assembly_day_cost() -> str:
    settings = load_assemblers_settings()
    return settings.get(ASSEMBLY_DAY_COST_KEY, "")


def load_assembly_workday_hours() -> str:
    settings = load_assemblers_settings()
    return settings.get(ASSEMBLY_WORKDAY_HOURS_KEY, "")


def load_calculation_settings() -> dict[str, Decimal]:
    settings = load_assemblers_settings()

    day_cost_raw = settings.get(ASSEMBLY_DAY_COST_KEY, "")
    workday_hours_raw = settings.get(ASSEMBLY_WORKDAY_HOURS_KEY, "")

    try:
        day_cost = _normalize_decimal(day_cost_raw) if day_cost_raw else DEFAULT_ASSEMBLY_DAY_COST
    except ValueError:
        day_cost = DEFAULT_ASSEMBLY_DAY_COST

    try:
        workday_hours = _normalize_workday_hours(workday_hours_raw) if workday_hours_raw else DEFAULT_ASSEMBLY_WORKDAY_HOURS
    except ValueError:
        workday_hours = DEFAULT_ASSEMBLY_WORKDAY_HOURS

    return {
        "assembly_day_cost": day_cost,
        "assembly_workday_hours": workday_hours,
    }


def save_assembly_day_cost(value) -> str:
    normalized_value = format(_normalize_decimal(value), "f")
    ensure_settings_schema()

    with get_db_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                f"""
                INSERT INTO {ASSEMBLERS_SETTINGS_TABLE} (
                    setting_key,
                    setting_value,
                    updated_at
                ) VALUES (%s, %s, NOW())
                ON CONFLICT (setting_key)
                DO UPDATE SET
                    setting_value = EXCLUDED.setting_value,
                    updated_at = NOW()
                """,
                (ASSEMBLY_DAY_COST_KEY, normalized_value),
            )
        conn.commit()

    return normalized_value


def save_assembly_workday_hours(value) -> str:
    normalized_value = format(_normalize_workday_hours(value), "f")
    ensure_settings_schema()

    with get_db_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                f"""
                INSERT INTO {ASSEMBLERS_SETTINGS_TABLE} (
                    setting_key,
                    setting_value,
                    updated_at
                ) VALUES (%s, %s, NOW())
                ON CONFLICT (setting_key)
                DO UPDATE SET
                    setting_value = EXCLUDED.setting_value,
                    updated_at = NOW()
                """,
                (ASSEMBLY_WORKDAY_HOURS_KEY, normalized_value),
            )
        conn.commit()

    return normalized_value
