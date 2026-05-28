import re
from datetime import datetime
from decimal import Decimal

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from ..db import get_db_connection
from ..services.auth_service import get_fresh_role

router = APIRouter(prefix="/api/zapusky", tags=["zapusky"])

DETAILS_TABLE = "production_launch_details"
REGISTRY_TABLE = "production_launch_registry"
COMPLETION_TABLE = "production_launch_completion"


class DetailPayload(BaseModel):
    detail_number: str
    designation: str
    quantity: str
    length: str
    width: str


class UploadParsedPayload(BaseModel):
    selected_order_number: str
    selected_launch: str
    file_order_number: str
    file_launch: str
    details: list[DetailPayload]
    force_replace: bool = False


class HideItemPayload(BaseModel):
    order_number: str
    launch: str


class BulkHidePayload(BaseModel):
    hidden: bool = True
    items: list[HideItemPayload]


class BulkHideOrdersPayload(BaseModel):
    hidden: bool = True
    order_numbers: list[str]


def _to_decimal(value: str) -> Decimal:
    return Decimal(str(value).replace(",", ".").strip())


def _safe_text(value: str) -> str:
    return " ".join(str(value or "").strip().split())


def _extract_order_launch(pdf_text: str):
    m = re.search(r"Запуск:\s*(\d+)\s+([^\s]+)", pdf_text, flags=re.IGNORECASE)
    if not m:
        return None, None
    return _safe_text(m.group(1)), _safe_text(m.group(2))


def _extract_details(pdf_text: str):
    details = []
    seen = set()

    pattern = re.compile(
        r"^\s*(\d+)\s+([A-Za-zА-Яа-я0-9\-\(\)\./]+)\s+(\d+(?:[\.,]\d+)?)\s+(\d+(?:[\.,]\d+)?)\s+(\d+(?:[\.,]\d+)?)\s*$"
    )

    for line in pdf_text.splitlines():
        line = line.strip()
        if not line:
            continue
        if "Позначення" in line or "Загальна специфікація" in line:
            continue

        m = pattern.match(line)
        if not m:
            continue

        detail_number = _safe_text(m.group(1))
        designation = _safe_text(m.group(2))
        qty = _to_decimal(m.group(3))
        length = _to_decimal(m.group(4))
        width = _to_decimal(m.group(5))

        key = (detail_number, designation, str(qty), str(length), str(width))
        if key in seen:
            continue
        seen.add(key)

        details.append(
            {
                "detail_number": detail_number,
                "designation": designation,
                "quantity": qty,
                "length": length,
                "width": width,
            }
        )

    return details


def _iter_launch_pairs_from_table(cur, table_name: str) -> set[tuple[str, str]]:
    cur.execute(
        """
        SELECT column_name
        FROM information_schema.columns
        WHERE table_schema = 'public' AND table_name = %s
        """,
        (table_name,),
    )
    cols = {r[0] for r in cur.fetchall()}
    if "id" not in cols or "column1" not in cols or "column2" not in cols:
        return set()

    cur.execute(
        f"""
        SELECT id, NULLIF(TRIM(column1), ''), NULLIF(TRIM(column2), '')
        FROM {table_name}
        ORDER BY id
        """
    )
    rows = cur.fetchall()

    result: set[tuple[str, str]] = set()
    last_order = ""
    for idx, (_, order_number, launch) in enumerate(rows):
        # Рядки 1 і 2 службові
        if idx < 2:
            continue

        if order_number:
            last_order = _safe_text(order_number)

        launch_norm = _safe_text(launch)
        if last_order and launch_norm:
            result.add((last_order, launch_norm))

    return result


def _upsert_order_hidden(cur, order_number: str, hidden: bool, uploaded_by: str) -> int:
    launches = set()
    launches |= {l for o, l in _iter_launch_pairs_from_table(cur, "register_data") if o == order_number}
    launches |= {l for o, l in _iter_launch_pairs_from_table(cur, "register_data_closed") if o == order_number}

    cur.execute(
        f"""
        UPDATE {REGISTRY_TABLE}
        SET hidden = %s
        WHERE order_number = %s
        """,
        (bool(hidden), order_number),
    )
    updated = cur.rowcount or 0

    for launch in launches:
        cur.execute(
            f"""
            INSERT INTO {REGISTRY_TABLE} (order_number, launch, details_uploaded, hidden, details_count, uploaded_by)
            VALUES (%s, %s, FALSE, %s, 0, %s)
            ON CONFLICT (order_number, launch)
            DO UPDATE SET hidden = EXCLUDED.hidden
            """,
            (order_number, launch, bool(hidden), uploaded_by),
        )
        updated += 1

    return updated


def _sort_num_text(value: str):
    text = _safe_text(value)
    return (0, int(text)) if text.isdigit() else (1, text)


def _desc_sort_num_text(value: str):
    text = _safe_text(value)
    # Для DESC: спочатку числові, потім текстові; обидва блоки у зворотному порядку.
    return (0, int(text)) if text.isdigit() else (1, text.lower())


def _can_manage_hidden(user: dict) -> bool:
    role = _safe_text((user or {}).get("role", "")).lower()
    return role in {"admin", "адмін"}


def _has_zapusky_access(user: dict) -> bool:
    role = _safe_text((user or {}).get("role", "")).lower()
    return role in {"admin", "адмін", "технолог виробництво", "технолог виробництва"}


def _refresh_session_role(request: Request, user: dict) -> dict:
    user = dict(user or {})
    fresh_role = get_fresh_role(user)
    user["role"] = fresh_role
    request.session["user"] = user
    return user


def _normalize_qty_length_width(qty: Decimal, length: Decimal, width: Decimal) -> tuple[Decimal, Decimal, Decimal]:
    # У частини PDF останні 3 числа йдуть як довжина, ширина, кількість.
    # Якщо кількість виглядає як розмір, а ширина - як малий лічильник, міняємо місцями.
    if qty > 50 and length > 50 and width <= 20:
        return width, qty, length
    return qty, length, width


def _ensure_tables(cur):
    cur.execute(
        f"""
        CREATE TABLE IF NOT EXISTS {REGISTRY_TABLE} (
            id SERIAL PRIMARY KEY,
            order_number TEXT NOT NULL,
            launch TEXT NOT NULL,
            details_uploaded BOOLEAN NOT NULL DEFAULT TRUE,
            hidden BOOLEAN NOT NULL DEFAULT FALSE,
            details_count INT NOT NULL DEFAULT 0,
            uploaded_at TIMESTAMP NOT NULL DEFAULT NOW(),
            uploaded_by TEXT,
            UNIQUE(order_number, launch)
        )
        """
    )

    cur.execute(
        f"""
        CREATE TABLE IF NOT EXISTS {DETAILS_TABLE} (
            id SERIAL PRIMARY KEY,
            order_number TEXT NOT NULL,
            launch TEXT NOT NULL,
            detail_number TEXT NOT NULL,
            designation TEXT NOT NULL,
            quantity NUMERIC(12, 3) NOT NULL,
            length NUMERIC(12, 3) NOT NULL,
            width NUMERIC(12, 3) NOT NULL,
            status TEXT NOT NULL DEFAULT 'у черзі',
            completed_quantity NUMERIC(12, 3) NOT NULL DEFAULT 0,
            completed_at TIMESTAMP,
            search_key TEXT NOT NULL,
            created_at TIMESTAMP NOT NULL DEFAULT NOW()
        )
        """
    )

    cur.execute(f"CREATE INDEX IF NOT EXISTS idx_{DETAILS_TABLE}_order_launch ON {DETAILS_TABLE}(order_number, launch)")
    cur.execute(f"CREATE INDEX IF NOT EXISTS idx_{DETAILS_TABLE}_search_key ON {DETAILS_TABLE}(search_key)")


def _is_komplekt_started(cur, order_number: str, launch: str) -> bool:
    cur.execute(
        """
        SELECT EXISTS (
            SELECT 1
            FROM information_schema.tables
            WHERE table_schema = 'public' AND table_name = %s
        )
        """,
        (COMPLETION_TABLE,),
    )
    has_completion_table = bool(cur.fetchone()[0])
    if not has_completion_table:
        return False

    cur.execute(
        f"""
        SELECT EXISTS (
            SELECT 1
            FROM {COMPLETION_TABLE}
            WHERE order_number = %s
              AND launch = %s
              AND started_at IS NOT NULL
        )
        """,
        (order_number, launch),
    )
    return bool(cur.fetchone()[0])


def _launch_exists_in_production(cur, order_number: str, launch: str) -> bool:
    cur.execute(
        """
        SELECT EXISTS (
            SELECT 1 FROM register_data
            WHERE COALESCE(NULLIF(TRIM(column1), ''), '') = %s
              AND COALESCE(NULLIF(TRIM(column2), ''), '') = %s
        )
        """,
        (order_number, launch),
    )
    exists_open = bool(cur.fetchone()[0])

    cur.execute(
        """
        SELECT EXISTS (
            SELECT 1 FROM register_data_closed
            WHERE COALESCE(NULLIF(TRIM(column1), ''), '') = %s
              AND COALESCE(NULLIF(TRIM(column2), ''), '') = %s
        )
        """,
        (order_number, launch),
    )
    exists_closed = bool(cur.fetchone()[0])

    return exists_open or exists_closed


@router.get("/production-launches")
async def production_launches(
    request: Request,
    order_number: str = "",
    status_filter: str = "",
    hidden_mode: str = "visible",
    offset: int = 0,
    limit: int = 80,
):
    user = request.session.get("user")
    if not user:
        return JSONResponse({"ok": False, "error": "Unauthorized"}, status_code=401)

    user = _refresh_session_role(request, user)

    if not _has_zapusky_access(user):
        return JSONResponse({"ok": False, "error": "Недостатньо прав для модуля Запуски"}, status_code=403)

    user = user or {}
    can_manage_hidden = _can_manage_hidden(user)

    conn = get_db_connection()
    cur = conn.cursor()
    try:
        _ensure_tables(cur)

        launch_pairs = set()
        launch_pairs |= _iter_launch_pairs_from_table(cur, "register_data")
        launch_pairs |= _iter_launch_pairs_from_table(cur, "register_data_closed")

        search = _safe_text(order_number).lower()
        if search:
            launch_pairs = {(o, l) for (o, l) in launch_pairs if search in o.lower()}

        status_filter_norm = _safe_text(status_filter).lower()
        hidden_mode_norm = _safe_text(hidden_mode).lower()

        cur.execute(
            f"""
            SELECT order_number, launch, details_uploaded, hidden, details_count, uploaded_at, COALESCE(uploaded_by, '')
            FROM {REGISTRY_TABLE}
            """
        )
        reg_rows = cur.fetchall()
        reg_map = {
            (_safe_text(r[0]), _safe_text(r[1])): {
                "details_uploaded": bool(r[2]),
                "hidden": bool(r[3]),
                "details_count": int(r[4] or 0),
                "uploaded_at": r[5],
                "uploaded_by": _safe_text(r[6]),
            }
            for r in reg_rows
        }

        cur.execute(
            f"""
            SELECT order_number, launch,
                   COUNT(*)::INT,
                   COUNT(*) FILTER (WHERE status = 'у черзі')::INT,
                   COUNT(*) FILTER (WHERE status = 'укомплектовано')::INT
            FROM {DETAILS_TABLE}
            GROUP BY order_number, launch
            """
        )
        detail_stats = {
            (_safe_text(r[0]), _safe_text(r[1])): {
                "details_total": int(r[2] or 0),
                "queue_count": int(r[3] or 0),
                "done_count": int(r[4] or 0),
            }
            for r in cur.fetchall()
        }

        items = []
        for order_num, launch in sorted(launch_pairs, key=lambda x: (_desc_sort_num_text(x[0]), _desc_sort_num_text(x[1])), reverse=True):
            reg = reg_map.get((order_num, launch), {})
            details = detail_stats.get((order_num, launch), {})

            is_hidden = bool(reg.get("hidden", False))
            if hidden_mode_norm == "hidden":
                if not is_hidden:
                    continue
            elif is_hidden:
                continue

            is_uploaded = bool(reg.get("details_uploaded", False))
            needs_upload = not is_uploaded

            if status_filter_norm == "needs_upload" and not needs_upload:
                continue
            if status_filter_norm == "uploaded" and needs_upload:
                continue

            uploaded_at = reg.get("uploaded_at")
            uploaded_at_text = uploaded_at.strftime("%d.%m.%Y %H:%M") if uploaded_at else ""

            items.append(
                {
                    "order_number": order_num,
                    "launch": launch,
                    "needs_upload": needs_upload,
                    "details_uploaded": is_uploaded,
                    "hidden": is_hidden,
                    "details_count": reg.get("details_count", 0) or details.get("details_total", 0),
                    "queue_count": details.get("queue_count", 0),
                    "done_count": details.get("done_count", 0),
                    "uploaded_at": uploaded_at_text,
                    "uploaded_by": reg.get("uploaded_by", ""),
                }
            )

        # Спочатку ті, де потрібен файл, потім завантажені.
        items.sort(
            key=lambda x: (
                0 if x.get("needs_upload") else 1,
                _desc_sort_num_text(x.get("order_number", "")),
                _desc_sort_num_text(x.get("launch", "")),
            )
        )

        try:
            offset = max(int(offset), 0)
        except Exception:
            offset = 0
        try:
            limit = max(min(int(limit), 300), 20)
        except Exception:
            limit = 80

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
            "can_manage_hidden": can_manage_hidden,
        }
    except Exception as exc:
        return JSONResponse({"ok": False, "error": str(exc)}, status_code=500)
    finally:
        cur.close()
        conn.close()


@router.post("/upload-details")
async def upload_details(request: Request, payload: UploadParsedPayload):
    user = request.session.get("user")
    if not user:
        return JSONResponse({"ok": False, "error": "Unauthorized"}, status_code=401)

    user = _refresh_session_role(request, user)

    if not _has_zapusky_access(user):
        return JSONResponse({"ok": False, "error": "Недостатньо прав для модуля Запуски"}, status_code=403)

    selected_order_number = _safe_text(payload.selected_order_number)
    selected_launch = _safe_text(payload.selected_launch)
    file_order_number = _safe_text(payload.file_order_number)
    file_launch = _safe_text(payload.file_launch)

    if not selected_order_number or not selected_launch:
        return JSONResponse({"ok": False, "error": "Спочатку вкажіть номер замовлення і запуск"}, status_code=400)

    if not file_order_number or not file_launch:
        return JSONResponse(
            {
                "ok": False,
                "error": "З файлу не вдалося зчитати номер замовлення/запуск",
            },
            status_code=400,
        )

    if selected_order_number != file_order_number or selected_launch != file_launch:
        return JSONResponse(
            {
                "ok": False,
                "error": (
                    "Перевірка не пройдена: вибрано "
                    f"{selected_order_number} / {selected_launch}, "
                    f"а у файлі {file_order_number} / {file_launch}"
                ),
            },
            status_code=400,
        )

    details = payload.details or []
    if not details:
        return JSONResponse(
            {
                "ok": False,
                "error": "У файлі не знайдено рядків деталей",
            },
            status_code=400,
        )

    normalized_details = []
    for d in details:
        try:
            detail_number = _safe_text(d.detail_number)
            designation = _safe_text(d.designation)
            qty = _to_decimal(d.quantity)
            length = _to_decimal(d.length)
            width = _to_decimal(d.width)
            qty, length, width = _normalize_qty_length_width(qty, length, width)
        except Exception:
            continue

        if not detail_number or not designation:
            continue

        normalized_details.append(
            {
                "detail_number": detail_number,
                "designation": designation,
                "quantity": qty,
                "length": length,
                "width": width,
            }
        )

    if not normalized_details:
        return JSONResponse({"ok": False, "error": "Деталі невалідні або порожні"}, status_code=400)

    conn = get_db_connection()
    cur = conn.cursor()
    try:
        _ensure_tables(cur)

        if not _launch_exists_in_production(cur, selected_order_number, selected_launch):
            conn.rollback()
            return JSONResponse(
                {
                    "ok": False,
                    "error": f"Запуск {selected_launch} для замовлення {selected_order_number} не знайдено у виробничих таблицях",
                },
                status_code=400,
            )

        if _is_komplekt_started(cur, selected_order_number, selected_launch) and not _can_manage_hidden(user):
            conn.rollback()
            return JSONResponse(
                {
                    "ok": False,
                    "code": "komplekt_started",
                    "error": (
                        "Перезапис заборонено: для цього запуску вже розпочато комплектування. "
                        "Перезапис після старту комплектування дозволений лише адміністратору."
                    ),
                },
                status_code=409,
            )

        cur.execute(
            f"""
            SELECT details_uploaded
            FROM {REGISTRY_TABLE}
            WHERE order_number = %s AND launch = %s
            LIMIT 1
            """,
            (selected_order_number, selected_launch),
        )
        reg_row = cur.fetchone()
        already_uploaded = bool(reg_row and reg_row[0])
        if already_uploaded and not bool(payload.force_replace):
            conn.rollback()
            return JSONResponse(
                {
                    "ok": False,
                    "code": "already_uploaded",
                    "error": "Деталі для цього запуску вже завантажені. Підтвердіть перезапис.",
                },
                status_code=409,
            )

        cur.execute(
            f"DELETE FROM {DETAILS_TABLE} WHERE order_number = %s AND launch = %s",
            (selected_order_number, selected_launch),
        )

        uploaded_by = _safe_text(user.get("name") or "Користувач")

        for d in normalized_details:
            search_key = f"{d['detail_number']} {selected_order_number} {selected_launch}"
            cur.execute(
                f"""
                INSERT INTO {DETAILS_TABLE} (
                    order_number, launch, detail_number, designation,
                    quantity, length, width,
                    status, completed_quantity, completed_at,
                    search_key
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, 'у черзі', 0, NULL, %s)
                """,
                (
                    selected_order_number,
                    selected_launch,
                    d["detail_number"],
                    d["designation"],
                    d["quantity"],
                    d["length"],
                    d["width"],
                    search_key,
                ),
            )

        cur.execute(
            f"""
            INSERT INTO {REGISTRY_TABLE} (
                order_number, launch, details_uploaded, hidden, details_count, uploaded_at, uploaded_by
            ) VALUES (%s, %s, TRUE, FALSE, %s, NOW(), %s)
            ON CONFLICT (order_number, launch)
            DO UPDATE SET
                details_uploaded = TRUE,
                hidden = FALSE,
                details_count = EXCLUDED.details_count,
                uploaded_at = NOW(),
                uploaded_by = EXCLUDED.uploaded_by
            """,
            (selected_order_number, selected_launch, len(normalized_details), uploaded_by),
        )

        conn.commit()

        return {
            "ok": True,
            "order_number": selected_order_number,
            "launch": selected_launch,
            "details_count": len(normalized_details),
            "details": [
                {
                    "detail_number": x["detail_number"],
                    "designation": x["designation"],
                    "quantity": str(x["quantity"]),
                    "length": str(x["length"]),
                    "width": str(x["width"]),
                }
                for x in normalized_details
            ],
        }
    except Exception as exc:
        conn.rollback()
        return JSONResponse({"ok": False, "error": f"Помилка збереження: {exc}"}, status_code=500)
    finally:
        cur.close()
        conn.close()


@router.get("/orders")
async def get_uploaded_orders(request: Request, include_hidden: bool = False):
    user = request.session.get("user")
    if not user:
        return JSONResponse({"ok": False, "error": "Unauthorized"}, status_code=401)

    user = _refresh_session_role(request, user)

    if not _has_zapusky_access(user):
        return JSONResponse({"ok": False, "error": "Недостатньо прав для модуля Запуски"}, status_code=403)

    conn = get_db_connection()
    cur = conn.cursor()
    try:
        _ensure_tables(cur)

        if include_hidden:
            cur.execute(
                f"""
                SELECT order_number, launch, details_count, hidden, uploaded_at, COALESCE(uploaded_by, '')
                FROM {REGISTRY_TABLE}
                ORDER BY uploaded_at DESC
                """
            )
        else:
            cur.execute(
                f"""
                SELECT order_number, launch, details_count, hidden, uploaded_at, COALESCE(uploaded_by, '')
                FROM {REGISTRY_TABLE}
                WHERE hidden = FALSE
                ORDER BY uploaded_at DESC
                """
            )

        rows = cur.fetchall()

        items = []
        for order_number, launch, details_count, hidden, uploaded_at, uploaded_by in rows:
            cur.execute(
                f"""
                SELECT
                    COUNT(*)::INT,
                    COUNT(*) FILTER (WHERE status = 'у черзі')::INT,
                    COUNT(*) FILTER (WHERE status = 'укомплектовано')::INT
                FROM {DETAILS_TABLE}
                WHERE order_number = %s AND launch = %s
                """,
                (order_number, launch),
            )
            total, queue_count, done_count = cur.fetchone()

            items.append(
                {
                    "order_number": order_number,
                    "launch": launch,
                    "details_count": details_count or total or 0,
                    "queue_count": queue_count or 0,
                    "done_count": done_count or 0,
                    "hidden": bool(hidden),
                    "uploaded_at": uploaded_at.strftime("%d.%m.%Y %H:%M") if uploaded_at else "",
                    "uploaded_by": uploaded_by,
                }
            )

        return {"ok": True, "items": items}
    except Exception as exc:
        return JSONResponse({"ok": False, "error": str(exc)}, status_code=500)
    finally:
        cur.close()
        conn.close()


@router.post("/orders/{order_number}/{launch}/hidden")
async def set_order_hidden(order_number: str, launch: str, request: Request):
    user = request.session.get("user")
    if not user:
        return JSONResponse({"ok": False, "error": "Unauthorized"}, status_code=401)

    user = _refresh_session_role(request, user)

    if not _can_manage_hidden(user):
        return JSONResponse({"ok": False, "error": "Недостатньо прав"}, status_code=403)

    payload = await request.json()
    hidden = bool(payload.get("hidden", True))

    conn = get_db_connection()
    cur = conn.cursor()
    try:
        _ensure_tables(cur)
        cur.execute(
            f"""
            UPDATE {REGISTRY_TABLE}
            SET hidden = %s
            WHERE order_number = %s AND launch = %s
            """,
            (hidden, order_number, launch),
        )

        if cur.rowcount == 0 and hidden:
            uploaded_by = _safe_text((user or {}).get("name") or "")
            cur.execute(
                f"""
                INSERT INTO {REGISTRY_TABLE} (order_number, launch, details_uploaded, hidden, details_count, uploaded_by)
                VALUES (%s, %s, FALSE, TRUE, 0, %s)
                ON CONFLICT (order_number, launch)
                DO UPDATE SET hidden = EXCLUDED.hidden
                """,
                (order_number, launch, uploaded_by),
            )

        conn.commit()
        return {"ok": True}
    except Exception as exc:
        conn.rollback()
        return JSONResponse({"ok": False, "error": str(exc)}, status_code=500)
    finally:
        cur.close()
        conn.close()


@router.post("/orders/hide-bulk")
async def set_orders_hidden_bulk(request: Request, payload: BulkHidePayload):
    user = request.session.get("user")
    if not user:
        return JSONResponse({"ok": False, "error": "Unauthorized"}, status_code=401)

    user = _refresh_session_role(request, user)

    if not _can_manage_hidden(user):
        return JSONResponse({"ok": False, "error": "Недостатньо прав"}, status_code=403)

    items = payload.items or []
    if not items:
        return JSONResponse({"ok": False, "error": "Список замовлень порожній"}, status_code=400)

    conn = get_db_connection()
    cur = conn.cursor()
    try:
        _ensure_tables(cur)

        updated = 0
        uploaded_by = _safe_text((user or {}).get("name") or "")
        for item in items:
            order_number = _safe_text(item.order_number)
            launch = _safe_text(item.launch)
            if not order_number or not launch:
                continue

            cur.execute(
                f"""
                UPDATE {REGISTRY_TABLE}
                SET hidden = %s
                WHERE order_number = %s AND launch = %s
                """,
                (bool(payload.hidden), order_number, launch),
            )

            if cur.rowcount == 0 and bool(payload.hidden):
                cur.execute(
                    f"""
                    INSERT INTO {REGISTRY_TABLE} (order_number, launch, details_uploaded, hidden, details_count, uploaded_by)
                    VALUES (%s, %s, FALSE, TRUE, 0, %s)
                    ON CONFLICT (order_number, launch)
                    DO UPDATE SET hidden = EXCLUDED.hidden
                    """,
                    (order_number, launch, uploaded_by),
                )

            updated += max(cur.rowcount or 0, 1)

        conn.commit()
        return {"ok": True, "updated": updated}
    except Exception as exc:
        conn.rollback()
        return JSONResponse({"ok": False, "error": str(exc)}, status_code=500)
    finally:
        cur.close()
        conn.close()


@router.post("/orders/{order_number}/hidden")
async def set_order_hidden_all_launches(order_number: str, request: Request):
    user = request.session.get("user")
    if not user:
        return JSONResponse({"ok": False, "error": "Unauthorized"}, status_code=401)

    user = _refresh_session_role(request, user)

    if not _can_manage_hidden(user):
        return JSONResponse({"ok": False, "error": "Недостатньо прав"}, status_code=403)

    payload = await request.json()
    hidden = bool(payload.get("hidden", True))
    order_number = _safe_text(order_number)
    if not order_number:
        return JSONResponse({"ok": False, "error": "Невірний номер замовлення"}, status_code=400)

    conn = get_db_connection()
    cur = conn.cursor()
    try:
        _ensure_tables(cur)
        uploaded_by = _safe_text((user or {}).get("name") or "")
        updated = _upsert_order_hidden(cur, order_number, hidden, uploaded_by)
        conn.commit()
        return {"ok": True, "updated": updated}
    except Exception as exc:
        conn.rollback()
        return JSONResponse({"ok": False, "error": str(exc)}, status_code=500)
    finally:
        cur.close()
        conn.close()


@router.post("/orders/hide-orders-bulk")
async def hide_orders_bulk(request: Request, payload: BulkHideOrdersPayload):
    user = request.session.get("user")
    if not user:
        return JSONResponse({"ok": False, "error": "Unauthorized"}, status_code=401)

    user = _refresh_session_role(request, user)

    if not _can_manage_hidden(user):
        return JSONResponse({"ok": False, "error": "Недостатньо прав"}, status_code=403)

    order_numbers = [
        _safe_text(x)
        for x in (payload.order_numbers or [])
        if _safe_text(x)
    ]
    if not order_numbers:
        return JSONResponse({"ok": False, "error": "Не вибрано жодного замовлення"}, status_code=400)

    conn = get_db_connection()
    cur = conn.cursor()
    try:
        _ensure_tables(cur)
        uploaded_by = _safe_text((user or {}).get("name") or "")
        total_updated = 0
        unique_orders = sorted(set(order_numbers), key=_sort_num_text)
        for order_number in unique_orders:
            total_updated += _upsert_order_hidden(cur, order_number, bool(payload.hidden), uploaded_by)

        conn.commit()
        return {"ok": True, "updated": total_updated, "orders": len(unique_orders)}
    except Exception as exc:
        conn.rollback()
        return JSONResponse({"ok": False, "error": str(exc)}, status_code=500)
    finally:
        cur.close()
        conn.close()
