from __future__ import annotations

import json

from app.modules.assemblers.db.connection import get_db_connection

from .schema import ensure_schema
from .utils import _safe_text


def load_column_preferences(telegram_id: int, page_key: str) -> dict | None:
    ensure_schema()
    try:
        normalized_telegram_id = int(telegram_id or 0)
        normalized_page_key = _safe_text(page_key)
    except (TypeError, ValueError):
        return None

    if normalized_telegram_id <= 0 or not normalized_page_key:
        return None

    with get_db_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                """
                SELECT column_order
                FROM assemblers_column_preferences
                WHERE telegram_id = %s AND page_key = %s
                LIMIT 1
                """,
                (normalized_telegram_id, normalized_page_key),
            )
            row = cursor.fetchone()

    if not row:
        return None

    try:
        parsed = json.loads(row[0])
        if isinstance(parsed, dict):
            order = parsed.get("order")
            pinned = parsed.get("pinned", [])
            widths = parsed.get("widths", {})
            if isinstance(order, list) and all(isinstance(x, int) for x in order):
                normalized_pinned = (
                    [x for x in pinned if isinstance(x, int)] if isinstance(pinned, list) else []
                )
                normalized_widths: dict[str, int] = {}
                if isinstance(widths, dict):
                    for key, value in widths.items():
                        try:
                            key_int = int(key)
                            value_int = int(value)
                        except (TypeError, ValueError):
                            continue
                        if key_int < 0:
                            continue
                        normalized_widths[str(key_int)] = max(24, min(value_int, 1200))
                return {"order": order, "pinned": normalized_pinned, "widths": normalized_widths}
        if isinstance(parsed, list) and all(isinstance(x, int) for x in parsed):
            return {"order": parsed, "pinned": [], "widths": {}}
    except (json.JSONDecodeError, TypeError, ValueError):
        pass

    return None


def save_column_preferences(
    telegram_id: int,
    page_key: str,
    column_order: list[int],
    pinned: list[int] | None = None,
    widths: dict | None = None,
) -> bool:
    ensure_schema()
    try:
        normalized_telegram_id = int(telegram_id or 0)
        normalized_page_key = _safe_text(page_key)
    except (TypeError, ValueError):
        return False

    if normalized_telegram_id <= 0 or not normalized_page_key:
        return False

    if not isinstance(column_order, list) or not all(isinstance(x, int) for x in column_order):
        return False

    normalized_pinned = [x for x in (pinned or []) if isinstance(x, int)]
    normalized_widths: dict[str, int] = {}
    if isinstance(widths, dict):
        for key, value in widths.items():
            try:
                key_int = int(key)
                value_int = int(value)
            except (TypeError, ValueError):
                continue
            if key_int < 0:
                continue
            normalized_widths[str(key_int)] = max(24, min(value_int, 1200))

    try:
        state_json = json.dumps(
            {"order": column_order, "pinned": normalized_pinned, "widths": normalized_widths}
        )
    except (TypeError, ValueError):
        return False

    with get_db_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO assemblers_column_preferences (telegram_id, page_key, column_order, updated_at)
                VALUES (%s, %s, %s, NOW())
                ON CONFLICT (telegram_id, page_key)
                DO UPDATE SET
                    column_order = EXCLUDED.column_order,
                    updated_at = NOW()
                """,
                (normalized_telegram_id, normalized_page_key, state_json),
            )
        conn.commit()

    return True
