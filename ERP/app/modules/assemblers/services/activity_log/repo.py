from __future__ import annotations

import json

from app.modules.assemblers.db.connection import get_db_connection
from app.modules.assemblers.db.tables import ACTIVITY_JOURNAL_TABLE

from .schema import ensure_activity_log_schema


def _safe_text(value) -> str:
    return " ".join(str(value or "").split()).strip()


def _normalize_actor(actor: dict | None) -> dict:
    if not isinstance(actor, dict):
        return {"kind": "system", "id": None, "name": "Система", "role": "system"}

    actor_kind = _safe_text(actor.get("kind")) or "user"
    actor_name = _safe_text(actor.get("name")) or ("Система" if actor_kind == "system" else "Користувач")
    actor_role = _safe_text(actor.get("role")) or ("system" if actor_kind == "system" else "")

    raw_actor_id = actor.get("telegram_id") or actor.get("id")
    try:
        actor_id = int(raw_actor_id) if raw_actor_id is not None and str(raw_actor_id).strip() != "" else None
    except (TypeError, ValueError):
        actor_id = None

    if actor_kind not in {"system", "user"}:
        actor_kind = "user"

    return {"kind": actor_kind, "id": actor_id, "name": actor_name, "role": actor_role}


def _normalize_details(details) -> str:
    if details is None:
        return "{}"
    if isinstance(details, str):
        raw = details.strip()
        return raw if raw.startswith("{") else json.dumps({"value": raw}, ensure_ascii=False)
    return json.dumps(details, ensure_ascii=False, default=str)


def record_activity_event(
    *,
    action_key: str,
    action_label: str,
    description: str = "",
    actor: dict | None = None,
    entity_type: str = "",
    entity_id: str = "",
    order_number: str = "",
    subdivision: str = "",
    source_table: str = "",
    source_op: str = "",
    status_code: int | None = None,
    details=None,
) -> int:
    ensure_activity_log_schema()
    normalized_actor = _normalize_actor(actor)

    with get_db_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                f"""
                INSERT INTO {ACTIVITY_JOURNAL_TABLE} (
                    actor_kind,
                    actor_id,
                    actor_name,
                    actor_role,
                    action_key,
                    action_label,
                    entity_type,
                    entity_id,
                    order_number,
                    subdivision,
                    source_table,
                    source_op,
                    status_code,
                    description,
                    details
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb)
                RETURNING id
                """,
                (
                    normalized_actor["kind"],
                    normalized_actor["id"],
                    normalized_actor["name"],
                    normalized_actor["role"],
                    _safe_text(action_key),
                    _safe_text(action_label),
                    _safe_text(entity_type),
                    _safe_text(entity_id),
                    _safe_text(order_number),
                    _safe_text(subdivision),
                    _safe_text(source_table),
                    _safe_text(source_op),
                    int(status_code or 0),
                    _safe_text(description),
                    _normalize_details(details),
                ),
            )
            new_id = cursor.fetchone()[0]

    return int(new_id)


def load_activity_log_rows(
    *,
    offset: int = 0,
    limit: int = 30,
    search: str = "",
    actor: str = "",
    order_number: str = "",
    subdivision: str = "",
    source: str = "",
    date_from: str = "",
    date_to: str = "",
) -> dict:
    ensure_activity_log_schema()

    normalized_search = _safe_text(search)
    normalized_actor = _safe_text(actor)
    normalized_order_number = _safe_text(order_number)
    normalized_subdivision = _safe_text(subdivision)
    normalized_source = _safe_text(source).casefold()
    normalized_date_from = _safe_text(date_from)
    normalized_date_to = _safe_text(date_to)

    clauses = ["1 = 1"]
    params: list[object] = []

    if normalized_search:
        clauses.append(
            "(" \
            "action_label ILIKE %s OR actor_name ILIKE %s OR description ILIKE %s OR order_number ILIKE %s OR entity_id ILIKE %s OR action_key ILIKE %s"
            ")"
        )
        like_search = f"%{normalized_search}%"
        params.extend([like_search, like_search, like_search, like_search, like_search, like_search])

    if normalized_actor:
        clauses.append("actor_name ILIKE %s")
        params.append(f"%{normalized_actor}%")

    if normalized_order_number:
        clauses.append("order_number ILIKE %s")
        params.append(f"%{normalized_order_number}%")

    if normalized_subdivision:
        clauses.append("subdivision ILIKE %s")
        params.append(f"%{normalized_subdivision}%")

    if normalized_source in {"system", "user"}:
        clauses.append("actor_kind = %s")
        params.append(normalized_source)

    if normalized_date_from:
        clauses.append("event_at::date >= %s::date")
        params.append(normalized_date_from)

    if normalized_date_to:
        clauses.append("event_at::date <= %s::date")
        params.append(normalized_date_to)

    where_sql = " AND ".join(clauses)

    with get_db_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                f"SELECT COUNT(*) FROM {ACTIVITY_JOURNAL_TABLE} WHERE {where_sql}",
                tuple(params),
            )
            total = int(cursor.fetchone()[0] or 0)

            cursor.execute(
                f"""
                SELECT
                    id,
                    event_at,
                    actor_kind,
                    actor_name,
                    actor_role,
                    action_key,
                    action_label,
                    entity_type,
                    entity_id,
                    order_number,
                    subdivision,
                    source_table,
                    source_op,
                    status_code,
                    description,
                    details::text
                FROM {ACTIVITY_JOURNAL_TABLE}
                WHERE {where_sql}
                ORDER BY event_at DESC, id DESC
                LIMIT %s OFFSET %s
                """,
                tuple(params) + (limit, offset),
            )
            rows = [
                {
                    "id": int(row[0]),
                    "event_at": row[1].isoformat() if row[1] else "",
                    "actor_kind": _safe_text(row[2]) or "system",
                    "actor_name": _safe_text(row[3]) or "Система",
                    "actor_role": _safe_text(row[4]) or "",
                    "action_key": _safe_text(row[5]),
                    "action_label": _safe_text(row[6]),
                    "entity_type": _safe_text(row[7]),
                    "entity_id": _safe_text(row[8]),
                    "order_number": _safe_text(row[9]),
                    "subdivision": _safe_text(row[10]),
                    "source_table": _safe_text(row[11]),
                    "source_op": _safe_text(row[12]),
                    "status_code": int(row[13] or 0),
                    "description": _safe_text(row[14]),
                    "details": _safe_text(row[15]),
                }
                for row in cursor.fetchall()
            ]

    return {"rows": rows, "total": total, "has_more": offset + len(rows) < total}