from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from ..db import get_db_connection
from ..services.auth_service import get_fresh_role

router = APIRouter(prefix="/api/komplekt", tags=["komplekt"])

DETAILS_TABLE = "production_launch_details"
COMPLETION_TABLE = "production_launch_completion"
SCAN_HISTORY_TABLE = "production_scan_history"


class ScanBatchPayload(BaseModel):
    scans: list[str]


class ScanHistoryEventPayload(BaseModel):
    status: str = "info"
    message: str = ""
    raw_scan: str = ""
    detail_number: str = ""
    scan_order_number: str = ""
    scan_launch: str = ""


def _safe_text(value: str) -> str:
    return " ".join(str(value or "").strip().split())


def _normalize_code(value: str) -> str:
    return "".join(ch for ch in _safe_text(value).lower() if ch.isalnum())


def _parse_scan_triplet(raw_scan: str) -> tuple[str, str, str] | None:
    parts = [p for p in _safe_text(raw_scan).split(" ") if p]
    if len(parts) != 3:
        return None
    detail_number, order_number, launch = parts
    return _safe_text(detail_number), _safe_text(order_number), _safe_text(launch)


def _display_number(value) -> str:
    text = str(value or "0").strip()
    if not text:
        return "0"
    try:
        num = float(text)
    except Exception:
        return text
    return str(int(num)) if num.is_integer() else (f"{num:.3f}").rstrip("0").rstrip(".")


def _to_float(value) -> float:
    try:
        return float(value or 0)
    except Exception:
        return 0.0


def _has_table(cur, table_name: str) -> bool:
    cur.execute(
        """
        SELECT EXISTS (
            SELECT 1
            FROM information_schema.tables
            WHERE table_schema = 'public' AND table_name = %s
        )
        """,
        (table_name,),
    )
    return bool(cur.fetchone()[0])


def _ensure_completion_table(cur):
    cur.execute(
        f"""
        CREATE TABLE IF NOT EXISTS {COMPLETION_TABLE} (
            id SERIAL PRIMARY KEY,
            order_number TEXT NOT NULL,
            launch TEXT NOT NULL,
            started_at TIMESTAMP,
            started_by TEXT,
            completed_at TIMESTAMP,
            completed_by TEXT,
            updated_at TIMESTAMP NOT NULL DEFAULT NOW(),
            UNIQUE(order_number, launch)
        )
        """
    )
    cur.execute(
        f"CREATE INDEX IF NOT EXISTS idx_{COMPLETION_TABLE}_order_launch ON {COMPLETION_TABLE}(order_number, launch)"
    )


def _ensure_scan_history_table(cur):
    cur.execute(
        f"""
        CREATE TABLE IF NOT EXISTS {SCAN_HISTORY_TABLE} (
            id SERIAL PRIMARY KEY,
            order_number TEXT NOT NULL,
            launch TEXT NOT NULL,
            actor_name TEXT,
            raw_scan TEXT,
            detail_number TEXT,
            scan_order_number TEXT,
            scan_launch TEXT,
            status TEXT,
            message TEXT,
            created_at TIMESTAMP NOT NULL DEFAULT NOW()
        )
        """
    )
    cur.execute(
        f"CREATE INDEX IF NOT EXISTS idx_{SCAN_HISTORY_TABLE}_order_launch_created ON {SCAN_HISTORY_TABLE}(order_number, launch, created_at DESC)"
    )


def _insert_scan_history_rows(cur, order_number: str, launch: str, actor_name: str, events: list[dict]):
    rows = []
    for ev in events or []:
        rows.append(
            (
                order_number,
                launch,
                _safe_text(actor_name),
                _safe_text(ev.get("raw_scan", "")),
                _safe_text(ev.get("detail_number", "")),
                _safe_text(ev.get("scan_order_number", "")),
                _safe_text(ev.get("scan_launch", "")),
                _safe_text(ev.get("status", "info")),
                _safe_text(ev.get("message", "")),
            )
        )

    if not rows:
        return

    cur.executemany(
        f"""
        INSERT INTO {SCAN_HISTORY_TABLE}
            (order_number, launch, actor_name, raw_scan, detail_number, scan_order_number, scan_launch, status, message)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
        """,
        rows,
    )


def _get_actor_name(request: Request) -> str:
    user = request.session.get("user") or {}
    return _safe_text(user.get("name") or user.get("phone") or "Користувач")


def _refresh_session_role(request: Request, user: dict) -> dict:
    user = dict(user or {})
    fresh_role = get_fresh_role(user)
    user["role"] = fresh_role
    request.session["user"] = user
    return user


def _has_komplekt_access(user: dict) -> bool:
    role = _safe_text((user or {}).get("role") or "").lower()
    return role in {"майстер цеху", "комплектувальник", "admin", "директор з виробництва"}


def _require_komplekt_access(request: Request):
    user = request.session.get("user")
    if not user:
        return None, JSONResponse({"ok": False, "error": "Unauthorized"}, status_code=401)

    user = _refresh_session_role(request, user)
    if not _has_komplekt_access(user):
        return None, JSONResponse({"ok": False, "error": "Недостатньо прав для комплектування"}, status_code=403)
    return user, None


def _completion_info(cur, order_number: str, launch: str):
    cur.execute(
        f"""
        SELECT started_at, COALESCE(started_by, ''), completed_at, COALESCE(completed_by, '')
        FROM {COMPLETION_TABLE}
        WHERE order_number = %s AND launch = %s
        LIMIT 1
        """,
        (order_number, launch),
    )
    row = cur.fetchone()
    if not row:
        return {
            "started_at": "",
            "started_by": "",
            "completed_at": "",
            "completed_by": "",
            "is_completed": False,
        }

    started_at, started_by, completed_at, completed_by = row
    return {
        "started_at": started_at.strftime("%d.%m.%Y %H:%M") if started_at else "",
        "started_by": _safe_text(started_by),
        "completed_at": completed_at.strftime("%d.%m.%Y %H:%M") if completed_at else "",
        "completed_by": _safe_text(completed_by),
        "is_completed": bool(completed_at),
    }


def _mark_started(cur, order_number: str, launch: str, actor_name: str):
    cur.execute(
        f"""
        INSERT INTO {COMPLETION_TABLE} (order_number, launch, started_at, started_by, updated_at)
        VALUES (%s, %s, NOW(), %s, NOW())
        ON CONFLICT (order_number, launch)
        DO UPDATE SET
            started_at = COALESCE({COMPLETION_TABLE}.started_at, NOW()),
            started_by = COALESCE({COMPLETION_TABLE}.started_by, EXCLUDED.started_by),
            updated_at = NOW()
        """,
        (order_number, launch, actor_name),
    )


def _mark_completed_if_needed(cur, order_number: str, launch: str, actor_name: str):
    state = _get_launch_state(cur, order_number, launch)
    if state["pending"] == 0 and state["total"] > 0:
        cur.execute(
            f"""
            INSERT INTO {COMPLETION_TABLE} (order_number, launch, started_at, started_by, completed_at, completed_by, updated_at)
            VALUES (%s, %s, NOW(), %s, NOW(), %s, NOW())
            ON CONFLICT (order_number, launch)
            DO UPDATE SET
                started_at = COALESCE({COMPLETION_TABLE}.started_at, NOW()),
                started_by = COALESCE({COMPLETION_TABLE}.started_by, EXCLUDED.started_by),
                completed_at = COALESCE({COMPLETION_TABLE}.completed_at, NOW()),
                completed_by = COALESCE({COMPLETION_TABLE}.completed_by, EXCLUDED.completed_by),
                updated_at = NOW()
            """,
            (order_number, launch, actor_name, actor_name),
        )
    else:
        cur.execute(
            f"""
            INSERT INTO {COMPLETION_TABLE} (order_number, launch, updated_at)
            VALUES (%s, %s, NOW())
            ON CONFLICT (order_number, launch)
            DO UPDATE SET updated_at = NOW()
            """,
            (order_number, launch),
        )


def _get_launch_state(cur, order_number: str, launch: str):
    cur.execute(
        f"""
        SELECT
            COALESCE(SUM(COALESCE(quantity, 0)), 0),
            COALESCE(SUM(LEAST(COALESCE(quantity, 0), GREATEST(COALESCE(completed_quantity, 0), 0))), 0),
            COALESCE(SUM(GREATEST(COALESCE(quantity, 0) - LEAST(COALESCE(quantity, 0), GREATEST(COALESCE(completed_quantity, 0), 0)), 0)), 0)
        FROM {DETAILS_TABLE}
        WHERE order_number = %s AND launch = %s
        """,
        (order_number, launch),
    )
    total, completed, pending = cur.fetchone() or (0, 0, 0)
    total = _to_float(total)
    completed = _to_float(completed)
    pending = _to_float(pending)
    percent = round((completed / total) * 100, 1) if total else 0.0
    return {
        "total": total,
        "completed": completed,
        "pending": pending,
        "percent": percent,
        "status": "Укомплектовано" if pending <= 0 and total > 0 else "В роботі",
    }


def _fetch_launch_details(cur, order_number: str, launch: str, detail_search: str = ""):
    cur.execute(
        f"""
        SELECT
            id,
            COALESCE(detail_number, ''),
            COALESCE(designation, ''),
            COALESCE(quantity, 0),
            COALESCE(completed_quantity, 0),
            COALESCE(length, 0),
            COALESCE(width, 0),
            COALESCE(status, ''),
            completed_at
        FROM {DETAILS_TABLE}
        WHERE order_number = %s AND launch = %s
        ORDER BY id
        """,
        (order_number, launch),
    )

    pending = []
    completed = []
    needle = _normalize_code(detail_search) if detail_search else ""
    for row in cur.fetchall():
        item = {
            "id": int(row[0]),
            "detail_number": _safe_text(row[1]),
            "designation": _safe_text(row[2]),
            "length": _display_number(row[5]),
            "width": _display_number(row[6]),
            "status": _safe_text(row[7]),
            "completed_at": row[8].strftime("%d.%m.%Y %H:%M") if row[8] else "",
        }

        qty_total = _to_float(row[3])
        qty_done = _to_float(row[4])
        qty_done = min(max(qty_done, 0.0), qty_total)
        qty_pending = max(qty_total - qty_done, 0.0)

        item["quantity_total"] = _display_number(qty_total)
        item["quantity_completed"] = _display_number(qty_done)
        item["quantity"] = _display_number(qty_pending)

        if needle:
            details_hay = _normalize_code(f"{item['detail_number']} {item['designation']}")
            if needle not in details_hay:
                continue

        if qty_pending > 0:
            item["quantity"] = _display_number(qty_pending)
            pending.append(item)

        if qty_done > 0:
            done_item = dict(item)
            done_item["quantity"] = _display_number(qty_pending)
            completed.append(done_item)

    return pending, completed


@router.get("/orders")
async def get_orders(request: Request, search: str = "", offset: int = 0, limit: int = 60):
    _, access_error = _require_komplekt_access(request)
    if access_error:
        return access_error

    conn = get_db_connection()
    cur = conn.cursor()
    try:
        if not _has_table(cur, DETAILS_TABLE):
            return {"ok": True, "items": [], "total": 0, "offset": 0, "next_offset": 0, "has_more": False}

        _ensure_completion_table(cur)

        search_norm = _safe_text(search).lower()

        cur.execute(
            f"""
            SELECT
                order_number,
                COUNT(DISTINCT launch)::INT,
                COALESCE(SUM(COALESCE(quantity, 0)), 0),
                COALESCE(SUM(LEAST(COALESCE(quantity, 0), GREATEST(COALESCE(completed_quantity, 0), 0))), 0),
                COALESCE(SUM(GREATEST(COALESCE(quantity, 0) - LEAST(COALESCE(quantity, 0), GREATEST(COALESCE(completed_quantity, 0), 0)), 0)), 0)
            FROM {DETAILS_TABLE}
            GROUP BY order_number
            """
        )

        rows = cur.fetchall()
        items = []
        for row in rows:
            order_number = _safe_text(row[0])
            if search_norm and search_norm not in order_number.lower():
                continue

            launches_count = int(row[1] or 0)
            details_total = _to_float(row[2])
            details_completed = _to_float(row[3])
            details_pending = _to_float(row[4])
            percent = round((details_completed / details_total) * 100, 1) if details_total else 0.0

            items.append(
                {
                    "order_number": order_number,
                    "launches_count": launches_count,
                    "details_total": details_total,
                    "details_completed": details_completed,
                    "details_pending": details_pending,
                    "percent": percent,
                    "status": "Укомплектовано" if details_pending <= 0 and details_total > 0 else "В роботі",
                }
            )

        def order_sort_key(v: str):
            t = _safe_text(v)
            if t.isdigit():
                return (0, -int(t))
            return (1, t.lower())

        items.sort(key=lambda x: order_sort_key(x["order_number"]))

        try:
            offset = max(int(offset), 0)
        except Exception:
            offset = 0
        try:
            limit = max(min(int(limit), 200), 20)
        except Exception:
            limit = 60

        total = len(items)
        chunk = items[offset: offset + limit]
        next_offset = offset + len(chunk)
        has_more = next_offset < total

        return {
            "ok": True,
            "items": chunk,
            "total": total,
            "offset": offset,
            "next_offset": next_offset,
            "limit": limit,
            "has_more": has_more,
        }
    except Exception as exc:
        return JSONResponse({"ok": False, "error": str(exc)}, status_code=500)
    finally:
        cur.close()
        conn.close()


@router.get("/orders/{order_number}/launches")
async def get_order_launches(
    order_number: str,
    request: Request,
    search_launch: str = "",
    status_filter: str = "",
    offset: int = 0,
    limit: int = 120,
):
    _, access_error = _require_komplekt_access(request)
    if access_error:
        return access_error

    order_number = _safe_text(order_number)
    if not order_number:
        return JSONResponse({"ok": False, "error": "Невірний номер замовлення"}, status_code=400)

    conn = get_db_connection()
    cur = conn.cursor()
    try:
        if not _has_table(cur, DETAILS_TABLE):
            return {"ok": True, "order_number": order_number, "items": []}

        _ensure_completion_table(cur)

        cur.execute(
            f"""
            SELECT
                launch,
                COALESCE(SUM(COALESCE(quantity, 0)), 0),
                COALESCE(SUM(LEAST(COALESCE(quantity, 0), GREATEST(COALESCE(completed_quantity, 0), 0))), 0),
                COALESCE(SUM(GREATEST(COALESCE(quantity, 0) - LEAST(COALESCE(quantity, 0), GREATEST(COALESCE(completed_quantity, 0), 0)), 0)), 0)
            FROM {DETAILS_TABLE}
            WHERE order_number = %s
            GROUP BY launch
            """,
            (order_number,),
        )
        rows = cur.fetchall()

        def launch_sort_key(v: str):
            t = _safe_text(v)
            if t.isdigit():
                return (0, int(t))
            return (1, t.lower())

        launch_search = _safe_text(search_launch).lower()
        status_filter_norm = _safe_text(status_filter).lower()
        items = []
        for row in rows:
            launch = _safe_text(row[0])
            if launch_search and launch_search not in launch.lower():
                continue

            total = _to_float(row[1])
            completed = _to_float(row[2])
            pending = _to_float(row[3])
            is_completed = pending <= 0 and total > 0
            if status_filter_norm == "completed" and not is_completed:
                continue
            if status_filter_norm == "in_progress" and is_completed:
                continue

            percent = round((completed / total) * 100, 1) if total else 0.0
            completion = _completion_info(cur, order_number, launch)
            items.append(
                {
                    "order_number": order_number,
                    "launch": launch,
                    "details_total": total,
                    "details_completed": completed,
                    "details_pending": pending,
                    "percent": percent,
                    "status": "Укомплектовано" if is_completed else "В роботі",
                    "completion": completion,
                }
            )

        items.sort(key=lambda x: launch_sort_key(x["launch"]))

        try:
            offset = max(int(offset), 0)
        except Exception:
            offset = 0
        try:
            limit = max(min(int(limit), 300), 30)
        except Exception:
            limit = 120

        total = len(items)
        chunk = items[offset: offset + limit]
        next_offset = offset + len(chunk)
        has_more = next_offset < total

        return {
            "ok": True,
            "order_number": order_number,
            "items": chunk,
            "total": total,
            "offset": offset,
            "next_offset": next_offset,
            "limit": limit,
            "has_more": has_more,
        }
    except Exception as exc:
        return JSONResponse({"ok": False, "error": str(exc)}, status_code=500)
    finally:
        cur.close()
        conn.close()


@router.get("/launch/{order_number}/{launch}/details")
async def get_launch_details(order_number: str, launch: str, request: Request, detail_search: str = ""):
    _, access_error = _require_komplekt_access(request)
    if access_error:
        return access_error

    order_number = _safe_text(order_number)
    launch = _safe_text(launch)
    if not order_number or not launch:
        return JSONResponse({"ok": False, "error": "Невірні параметри"}, status_code=400)

    conn = get_db_connection()
    cur = conn.cursor()
    try:
        if not _has_table(cur, DETAILS_TABLE):
            return JSONResponse({"ok": False, "error": "Деталі ще не завантажені"}, status_code=404)

        _ensure_completion_table(cur)
        _ensure_scan_history_table(cur)

        state = _get_launch_state(cur, order_number, launch)
        pending, completed = _fetch_launch_details(cur, order_number, launch, detail_search)
        completion = _completion_info(cur, order_number, launch)

        return {
            "ok": True,
            "order_number": order_number,
            "launch": launch,
            "state": state,
            "completion": completion,
            "pending_details": pending,
            "completed_details": completed,
        }
    except Exception as exc:
        return JSONResponse({"ok": False, "error": str(exc)}, status_code=500)
    finally:
        cur.close()
        conn.close()


@router.post("/launch/{order_number}/{launch}/scan-batch")
async def scan_batch(order_number: str, launch: str, payload: ScanBatchPayload, request: Request):
    _, access_error = _require_komplekt_access(request)
    if access_error:
        return access_error

    order_number = _safe_text(order_number)
    launch = _safe_text(launch)
    if not order_number or not launch:
        return JSONResponse({"ok": False, "error": "Невірні параметри"}, status_code=400)

    scans = [s for s in (_safe_text(x) for x in (payload.scans or [])) if s]
    if not scans:
        return JSONResponse({"ok": False, "error": "Порожній пакет сканів"}, status_code=400)

    conn = get_db_connection()
    cur = conn.cursor()
    try:
        if not _has_table(cur, DETAILS_TABLE):
            return JSONResponse({"ok": False, "error": "Деталі ще не завантажені"}, status_code=404)

        _ensure_completion_table(cur)
        _ensure_scan_history_table(cur)
        actor_name = _get_actor_name(request)

        updated_count = 0
        already_completed_count = 0
        not_found = []
        wrong_order_launch = []
        invalid_format = []
        scan_events = []

        for raw_scan in scans:
            parsed = _parse_scan_triplet(raw_scan)
            if not parsed:
                invalid_format.append(raw_scan)
                not_found.append(raw_scan)
                scan_events.append(
                    {
                        "raw_scan": raw_scan,
                        "detail_number": "",
                        "scan_order_number": "",
                        "scan_launch": "",
                        "status": "invalid_format",
                        "message": "Невірний формат. Очікується: номер_деталі номер_замовлення номер_запуску",
                    }
                )
                continue

            detail_number, scan_order_number, scan_launch = parsed
            detail_norm = _normalize_code(detail_number)
            if not detail_norm:
                invalid_format.append(raw_scan)
                not_found.append(raw_scan)
                scan_events.append(
                    {
                        "raw_scan": raw_scan,
                        "detail_number": detail_number,
                        "scan_order_number": scan_order_number,
                        "scan_launch": scan_launch,
                        "status": "invalid_format",
                        "message": "Порожній номер деталі у скані",
                    }
                )
                continue

            if scan_order_number != order_number or scan_launch != launch:
                wrong_order_launch.append(raw_scan)
                not_found.append(raw_scan)
                scan_events.append(
                    {
                        "raw_scan": raw_scan,
                        "detail_number": detail_number,
                        "scan_order_number": scan_order_number,
                        "scan_launch": scan_launch,
                        "status": "wrong_order_launch",
                        "message": f"Невірне замовлення/запуск у скані: {scan_order_number}/{scan_launch}",
                    }
                )
                continue

            cur.execute(
                f"""
                SELECT id
                FROM {DETAILS_TABLE}
                WHERE order_number = %s
                  AND launch = %s
                AND COALESCE(completed_quantity, 0) < COALESCE(quantity, 0)
                  AND (
                        REPLACE(LOWER(COALESCE(detail_number, '')), ' ', '') = %s
                  )
                ORDER BY id
                LIMIT 1
                """,
                (order_number, launch, detail_norm),
            )
            pending_row = cur.fetchone()

            if pending_row:
                detail_id = int(pending_row[0])
                cur.execute(
                    f"""
                    UPDATE {DETAILS_TABLE}
                    SET completed_quantity = LEAST(COALESCE(quantity, 0), GREATEST(COALESCE(completed_quantity, 0), 0) + 1),
                        status = CASE
                            WHEN LEAST(COALESCE(quantity, 0), GREATEST(COALESCE(completed_quantity, 0), 0) + 1) >= COALESCE(quantity, 0)
                                THEN 'укомплектовано'
                            ELSE 'у черзі'
                        END,
                        completed_at = CASE
                            WHEN LEAST(COALESCE(quantity, 0), GREATEST(COALESCE(completed_quantity, 0), 0) + 1) >= COALESCE(quantity, 0)
                                THEN NOW()
                            ELSE NULL
                        END
                    WHERE id = %s
                      AND COALESCE(completed_quantity, 0) < COALESCE(quantity, 0)
                    RETURNING COALESCE(quantity, 0), COALESCE(completed_quantity, 0)
                    """,
                    (detail_id,),
                )
                update_row = cur.fetchone()
                if update_row:
                    qty_total = _to_float(update_row[0])
                    qty_done = _to_float(update_row[1])
                    qty_pending = max(qty_total - qty_done, 0.0)
                    updated_count += 1
                    scan_events.append(
                        {
                            "raw_scan": raw_scan,
                            "detail_number": detail_number,
                            "scan_order_number": scan_order_number,
                            "scan_launch": scan_launch,
                            "status": "updated",
                            "message": f"Відскановано 1 шт. Залишилось: {_display_number(qty_pending)}",
                        }
                    )
                continue

            cur.execute(
                f"""
                SELECT 1
                FROM {DETAILS_TABLE}
                WHERE order_number = %s
                  AND launch = %s
                                    AND COALESCE(completed_quantity, 0) >= COALESCE(quantity, 0)
                  AND (
                        REPLACE(LOWER(COALESCE(detail_number, '')), ' ', '') = %s
                  )
                LIMIT 1
                """,
                (order_number, launch, detail_norm),
            )
            done_row = cur.fetchone()
            if done_row:
                already_completed_count += 1
                scan_events.append(
                    {
                        "raw_scan": raw_scan,
                        "detail_number": detail_number,
                        "scan_order_number": scan_order_number,
                        "scan_launch": scan_launch,
                        "status": "already_completed",
                        "message": "Деталь вже була відсканована раніше",
                    }
                )
            else:
                not_found.append(raw_scan)
                scan_events.append(
                    {
                        "raw_scan": raw_scan,
                        "detail_number": detail_number,
                        "scan_order_number": scan_order_number,
                        "scan_launch": scan_launch,
                        "status": "not_found",
                        "message": "Деталь не знайдено для цього запуску",
                    }
                )

        if updated_count > 0:
            _mark_started(cur, order_number, launch, actor_name)
        _mark_completed_if_needed(cur, order_number, launch, actor_name)
        _insert_scan_history_rows(cur, order_number, launch, actor_name, scan_events)
        conn.commit()

        state = _get_launch_state(cur, order_number, launch)
        pending, completed = _fetch_launch_details(cur, order_number, launch)
        completion = _completion_info(cur, order_number, launch)

        return {
            "ok": True,
            "order_number": order_number,
            "launch": launch,
            "processed": len(scans),
            "updated_count": updated_count,
            "already_completed_count": already_completed_count,
            "not_found": not_found,
            "wrong_order_launch": wrong_order_launch,
            "invalid_format": invalid_format,
            "scan_events": scan_events,
            "state": state,
            "completion": completion,
            "pending_details": pending,
            "completed_details": completed,
        }
    except Exception as exc:
        conn.rollback()
        return JSONResponse({"ok": False, "error": str(exc)}, status_code=500)
    finally:
        cur.close()
        conn.close()


@router.get("/launch/{order_number}/{launch}/scan-history")
async def get_scan_history(order_number: str, launch: str, request: Request, limit: int = 300):
    _, access_error = _require_komplekt_access(request)
    if access_error:
        return access_error

    order_number = _safe_text(order_number)
    launch = _safe_text(launch)
    if not order_number or not launch:
        return JSONResponse({"ok": False, "error": "Невірні параметри"}, status_code=400)

    conn = get_db_connection()
    cur = conn.cursor()
    try:
        _ensure_scan_history_table(cur)
        try:
            limit = max(10, min(int(limit), 1000))
        except Exception:
            limit = 300

        cur.execute(
            f"""
            SELECT
                id,
                COALESCE(actor_name, ''),
                COALESCE(raw_scan, ''),
                COALESCE(detail_number, ''),
                COALESCE(scan_order_number, ''),
                COALESCE(scan_launch, ''),
                COALESCE(status, ''),
                COALESCE(message, ''),
                created_at
            FROM {SCAN_HISTORY_TABLE}
            WHERE order_number = %s AND launch = %s
            ORDER BY id DESC
            LIMIT %s
            """,
            (order_number, launch, limit),
        )

        items = []
        for row in cur.fetchall():
            created_at = row[8]
            items.append(
                {
                    "id": int(row[0]),
                    "actor_name": _safe_text(row[1]),
                    "raw_scan": _safe_text(row[2]),
                    "detail_number": _safe_text(row[3]),
                    "scan_order_number": _safe_text(row[4]),
                    "scan_launch": _safe_text(row[5]),
                    "status": _safe_text(row[6]),
                    "message": _safe_text(row[7]),
                    "created_at": created_at.strftime("%d.%m.%Y %H:%M:%S") if created_at else "",
                }
            )

        return {
            "ok": True,
            "order_number": order_number,
            "launch": launch,
            "items": items,
        }
    except Exception as exc:
        return JSONResponse({"ok": False, "error": str(exc)}, status_code=500)
    finally:
        cur.close()
        conn.close()


@router.post("/launch/{order_number}/{launch}/scan-history-event")
async def add_scan_history_event(order_number: str, launch: str, payload: ScanHistoryEventPayload, request: Request):
    _, access_error = _require_komplekt_access(request)
    if access_error:
        return access_error

    order_number = _safe_text(order_number)
    launch = _safe_text(launch)
    if not order_number or not launch:
        return JSONResponse({"ok": False, "error": "Невірні параметри"}, status_code=400)

    actor_name = _get_actor_name(request)
    event = {
        "raw_scan": payload.raw_scan,
        "detail_number": payload.detail_number,
        "scan_order_number": payload.scan_order_number,
        "scan_launch": payload.scan_launch,
        "status": payload.status,
        "message": payload.message,
    }

    conn = get_db_connection()
    cur = conn.cursor()
    try:
        _ensure_scan_history_table(cur)
        _insert_scan_history_rows(cur, order_number, launch, actor_name, [event])
        conn.commit()
        return {"ok": True}
    except Exception as exc:
        conn.rollback()
        return JSONResponse({"ok": False, "error": str(exc)}, status_code=500)
    finally:
        cur.close()
        conn.close()
