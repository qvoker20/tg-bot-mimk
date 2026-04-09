from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from ..db import get_db_connection

router = APIRouter(prefix="/api/komplekt", tags=["komplekt"])

DETAILS_TABLE = "production_launch_details"
COMPLETION_TABLE = "production_launch_completion"


class ScanBatchPayload(BaseModel):
    scans: list[str]


def _safe_text(value: str) -> str:
    return " ".join(str(value or "").strip().split())


def _normalize_code(value: str) -> str:
    return "".join(ch for ch in _safe_text(value).lower() if ch.isalnum())


def _display_number(value) -> str:
    text = str(value or "0").strip()
    if not text:
        return "0"
    try:
        num = float(text)
    except Exception:
        return text
    return str(int(num)) if num.is_integer() else (f"{num:.3f}").rstrip("0").rstrip(".")


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


def _get_actor_name(request: Request) -> str:
    user = request.session.get("user") or {}
    return _safe_text(user.get("name") or user.get("phone") or "Користувач")


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
            COUNT(*)::INT,
            COUNT(*) FILTER (WHERE status = 'укомплектовано')::INT,
            COUNT(*) FILTER (WHERE status <> 'укомплектовано')::INT
        FROM {DETAILS_TABLE}
        WHERE order_number = %s AND launch = %s
        """,
        (order_number, launch),
    )
    total, completed, pending = cur.fetchone() or (0, 0, 0)
    total = int(total or 0)
    completed = int(completed or 0)
    pending = int(pending or 0)
    percent = round((completed / total) * 100, 1) if total else 0.0
    return {
        "total": total,
        "completed": completed,
        "pending": pending,
        "percent": percent,
        "status": "Укомплектовано" if pending == 0 and total > 0 else "В роботі",
    }


def _fetch_launch_details(cur, order_number: str, launch: str, detail_search: str = ""):
    cur.execute(
        f"""
        SELECT
            id,
            COALESCE(detail_number, ''),
            COALESCE(designation, ''),
            COALESCE(quantity, 0),
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
            "quantity": _display_number(row[3]),
            "length": _display_number(row[4]),
            "width": _display_number(row[5]),
            "status": _safe_text(row[6]),
            "completed_at": row[7].strftime("%d.%m.%Y %H:%M") if row[7] else "",
        }

        if needle:
            details_hay = _normalize_code(f"{item['detail_number']} {item['designation']}")
            if needle not in details_hay:
                continue

        if item["status"] == "укомплектовано":
            completed.append(item)
        else:
            pending.append(item)

    return pending, completed


@router.get("/orders")
async def get_orders(request: Request, search: str = "", offset: int = 0, limit: int = 60):
    if not request.session.get("user"):
        return JSONResponse({"ok": False, "error": "Unauthorized"}, status_code=401)

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
                COUNT(*)::INT,
                COUNT(*) FILTER (WHERE status = 'укомплектовано')::INT,
                COUNT(*) FILTER (WHERE status <> 'укомплектовано')::INT
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
            details_total = int(row[2] or 0)
            details_completed = int(row[3] or 0)
            details_pending = int(row[4] or 0)
            percent = round((details_completed / details_total) * 100, 1) if details_total else 0.0

            items.append(
                {
                    "order_number": order_number,
                    "launches_count": launches_count,
                    "details_total": details_total,
                    "details_completed": details_completed,
                    "details_pending": details_pending,
                    "percent": percent,
                    "status": "Укомплектовано" if details_pending == 0 and details_total > 0 else "В роботі",
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
    if not request.session.get("user"):
        return JSONResponse({"ok": False, "error": "Unauthorized"}, status_code=401)

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
                COUNT(*)::INT,
                COUNT(*) FILTER (WHERE status = 'укомплектовано')::INT,
                COUNT(*) FILTER (WHERE status <> 'укомплектовано')::INT
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

            total = int(row[1] or 0)
            completed = int(row[2] or 0)
            pending = int(row[3] or 0)
            is_completed = pending == 0 and total > 0
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
    if not request.session.get("user"):
        return JSONResponse({"ok": False, "error": "Unauthorized"}, status_code=401)

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
    if not request.session.get("user"):
        return JSONResponse({"ok": False, "error": "Unauthorized"}, status_code=401)

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
        actor_name = _get_actor_name(request)

        updated_count = 0
        already_completed_count = 0
        not_found = []
        updated_ids = set()

        for raw_scan in scans:
            scan_norm = _normalize_code(raw_scan)
            if not scan_norm:
                continue

            cur.execute(
                f"""
                SELECT id
                FROM {DETAILS_TABLE}
                WHERE order_number = %s
                  AND launch = %s
                  AND status <> 'укомплектовано'
                  AND (
                        REPLACE(LOWER(COALESCE(detail_number, '')), ' ', '') = %s
                        OR REPLACE(LOWER(COALESCE(search_key, '')), ' ', '') LIKE %s
                        OR %s LIKE '%%' || REPLACE(LOWER(COALESCE(detail_number, '')), ' ', '') || '%%'
                  )
                ORDER BY id
                LIMIT 1
                """,
                (order_number, launch, scan_norm, f"%{scan_norm}%", scan_norm),
            )
            pending_row = cur.fetchone()

            if pending_row:
                detail_id = int(pending_row[0])
                if detail_id in updated_ids:
                    continue

                cur.execute(
                    f"""
                    UPDATE {DETAILS_TABLE}
                    SET status = 'укомплектовано',
                        completed_quantity = quantity,
                        completed_at = NOW()
                    WHERE id = %s AND status <> 'укомплектовано'
                    """,
                    (detail_id,),
                )
                if cur.rowcount:
                    updated_ids.add(detail_id)
                    updated_count += 1
                continue

            cur.execute(
                f"""
                SELECT 1
                FROM {DETAILS_TABLE}
                WHERE order_number = %s
                  AND launch = %s
                  AND status = 'укомплектовано'
                  AND (
                        REPLACE(LOWER(COALESCE(detail_number, '')), ' ', '') = %s
                        OR REPLACE(LOWER(COALESCE(search_key, '')), ' ', '') LIKE %s
                        OR %s LIKE '%%' || REPLACE(LOWER(COALESCE(detail_number, '')), ' ', '') || '%%'
                  )
                LIMIT 1
                """,
                (order_number, launch, scan_norm, f"%{scan_norm}%", scan_norm),
            )
            done_row = cur.fetchone()
            if done_row:
                already_completed_count += 1
            else:
                not_found.append(raw_scan)

        if updated_count > 0:
            _mark_started(cur, order_number, launch, actor_name)
        _mark_completed_if_needed(cur, order_number, launch, actor_name)
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
