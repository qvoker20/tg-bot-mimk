from collections import defaultdict
from datetime import datetime, date
import re

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from ..db import get_db_connection

router = APIRouter(prefix="/api/reestr", tags=["reestr"])

REESTR_TABLES = [
    ("register_data", "Реєстр"),
    ("register_data_closed", "Виконані"),
]

FIELD_COLUMNS = {
    "launch": 2,
    "launches_before_part": 3,
    "part": 4,
    "parts_total": 5,
    "service": 6,
    "name": 9,
    "material_type": 10,
    "adaptor": 11,
    "sheets_count": 12,
    "status": 14,
    "sent_to_production": 15,
    "in_work_production": 16,
    "raw_materials": 17,
    "cut_meters": 18,
    "drilling_qty": 20,
    "cut_operator": 24,
    "cut_done": 25,
    "edge_done": 28,
    "drilling_done": 31,
    "curvilinear": 33,
    "formatter": 35,
    "ties": 37,
    "nesting": 40,
    "production_ready_date": 43,
    "transfer_to": 44,
    "notes": 46,
}

REQUIRED_COLUMN_NUMBERS = sorted({1, *FIELD_COLUMNS.values()})


def _get_existing_columns(cur, table_name: str) -> set[str]:
    cur.execute(
        """
        SELECT column_name
        FROM information_schema.columns
        WHERE table_schema = 'public'
          AND table_name = %s
        """,
        (table_name,),
    )
    return {row[0] for row in cur.fetchall()}


def _select_expr_for_column(existing_columns: set[str], column_number: int) -> str:
    col_name = f"column{column_number}"
    if col_name in existing_columns:
        return f"NULLIF(TRIM({col_name}), '') AS c{column_number}"
    return f"NULL::text AS c{column_number}"


def _fetch_table_rows(cur, table_name: str, source_name: str) -> list[dict]:
    existing_columns = _get_existing_columns(cur, table_name)
    if "column1" not in existing_columns:
        return []

    if "id" not in existing_columns:
        return []

    select_parts = [_select_expr_for_column(existing_columns, n) for n in REQUIRED_COLUMN_NUMBERS]
    select_sql = ", ".join(["id", *select_parts])

    cur.execute(
        f"""
        SELECT {select_sql}
        FROM {table_name}
        ORDER BY id
        """
    )

    rows = []
    last_order_number = ""
    for row_idx, record in enumerate(cur.fetchall()):
        # Рядки 1 і 2 в таблицях службові, беремо дані з 3-го рядка
        if row_idx < 2:
            continue

        row_data = {f"c{n}": record[idx + 1] for idx, n in enumerate(REQUIRED_COLUMN_NUMBERS)}

        current_order = (row_data.get("c1") or "").strip()
        if current_order:
            last_order_number = current_order
        else:
            row_data["c1"] = last_order_number

        if not (row_data.get("c1") or "").strip():
            continue

        row_data["_source"] = source_name
        rows.append(row_data)
    return rows


def _map_launch_row(row: dict) -> dict:
    item = {key: row.get(f"c{col}") or "" for key, col in FIELD_COLUMNS.items()}
    item["source"] = row.get("_source", "")

    # Скільки днів запуск перебуває на виробництві:
    # беремо дату "Передано на виробництво", а якщо її нема - "В роботі виробництво".
    start_date = _parse_uk_date(item.get("sent_to_production", "")) or _parse_uk_date(item.get("in_work_production", ""))
    if start_date:
        days = (date.today() - start_date).days
        item["days_in_production"] = max(days, 0)
        item["is_overdue_production_days"] = days > 7
    else:
        item["days_in_production"] = None
        item["is_overdue_production_days"] = False

    return item


def _is_meaningful_launch(item: dict) -> bool:
    # Відкидаємо технічні/порожні рядки, що не містять даних запуску.
    check_keys = [
        "launch",
        "name",
        "status",
        "material_type",
        "sheets_count",
        "service",
        "part",
        "cut_meters",
        "drilling_qty",
    ]
    return any(str(item.get(k) or "").strip() for k in check_keys)


def _sort_key(value: str):
    text = (value or "").strip()
    return (0, int(text)) if text.isdigit() else (1, text)


def _parse_uk_date(value: str) -> date | None:
    text = (value or "").strip()
    if not text:
        return None

    match = re.search(r"(\d{2}\.\d{2}\.\d{4})", text)
    if not match:
        return None

    try:
        return datetime.strptime(match.group(1), "%d.%m.%Y").date()
    except Exception:
        return None


def _normalize_status(value: str) -> str:
    return (value or "").strip().lower()


def _build_status_counters(launches: list[dict]) -> dict[str, int]:
    counters: dict[str, int] = {}
    for launch in launches:
        status = (launch.get("status") or "").strip()
        if not status:
            status = "Без статусу"
        counters[status] = counters.get(status, 0) + 1
    return counters


def _calc_overall_status(launches: list[dict]) -> str:
    if not launches:
        return "В роботі"
    normalized = [_normalize_status(launch.get("status", "")) for launch in launches]
    if normalized and all(s == "завершено" for s in normalized):
        return "Завершено"
    return "В роботі"


def _is_true(value: str) -> bool:
    norm = (value or "").strip().lower()
    return norm in {"true", "1", "yes", "так"}


def _to_number(value: str) -> float:
    text = (value or "").strip().replace(",", ".")
    if not text:
        return 0.0

    allowed = "0123456789.-"
    token = ""
    started = False
    for ch in text:
        if ch in allowed:
            token += ch
            started = True
        elif started:
            break

    try:
        return float(token) if token else 0.0
    except Exception:
        return 0.0


def _format_number(value: float) -> str:
    if abs(value - int(value)) < 1e-9:
        return str(int(value))
    return (f"{value:.2f}").rstrip("0").rstrip(".")


def _calc_pending_work(launches: list[dict]) -> tuple[str, str]:
    pending_cut = 0.0
    pending_drilling = 0.0

    for launch in launches:
        cut_done = _is_true(launch.get("cut_done", ""))
        drilling_done = _is_true(launch.get("drilling_done", ""))

        if not cut_done:
            pending_cut += _to_number(launch.get("cut_meters", ""))

        if not drilling_done:
            pending_drilling += _to_number(launch.get("drilling_qty", ""))

    return _format_number(pending_cut), _format_number(pending_drilling)


def _get_first_production_submit_date(launches: list[dict]) -> date | None:
    parsed_dates = []
    for launch in launches:
        dt = _parse_uk_date(launch.get("sent_to_production", ""))
        if dt:
            parsed_dates.append(dt)
    if not parsed_dates:
        return None
    return min(parsed_dates)


def _extract_materials(launches: list[dict]) -> list[str]:
    materials = set()
    for launch in launches:
        material = (launch.get("material_type") or "").strip()
        if material:
            materials.add(material)
    return sorted(materials)


def _build_orders_dataset(cur):
    grouped = defaultdict(list)

    for table_name, source_name in REESTR_TABLES:
        rows = _fetch_table_rows(cur, table_name, source_name)
        for row in rows:
            order_number = (row.get("c1") or "").strip()
            if order_number:
                mapped = _map_launch_row(row)
                if _is_meaningful_launch(mapped):
                    grouped[order_number].append(mapped)

    result = []
    today = date.today()
    all_materials = set()

    for order_number, launches in grouped.items():
        sources = sorted({ln.get("source", "") for ln in launches if ln.get("source")})
        launches_sorted = sorted(launches, key=lambda x: _sort_key(x.get("launch", "")))
        status_counts = _build_status_counters(launches_sorted)
        overall_status = _calc_overall_status(launches_sorted)
        pending_cut_meters, pending_drilling_qty = _calc_pending_work(launches_sorted)
        first_submit_date = _get_first_production_submit_date(launches_sorted)
        days_in_work = (today - first_submit_date).days if first_submit_date else None
        materials = _extract_materials(launches_sorted)
        all_materials.update(materials)

        result.append(
            {
                "order_number": order_number,
                "launches_count": len(launches_sorted),
                "sources": sources,
                "status_counts": status_counts,
                "overall_status": overall_status,
                "pending_cut_meters": pending_cut_meters,
                "pending_drilling_qty": pending_drilling_qty,
                "first_submit_date": first_submit_date.strftime("%d.%m.%Y") if first_submit_date else "",
                "days_in_work": days_in_work,
                "materials": materials,
                "launches": launches_sorted,
            }
        )

    result.sort(
        key=lambda x: (
            0 if x.get("first_submit_date") else 1,
            -((_parse_uk_date(x.get("first_submit_date", "")) or date.min).toordinal()),
            _sort_key(x["order_number"]),
        )
    )

    return result, sorted(all_materials)


def _apply_filters(
    orders: list[dict],
    search: str,
    overall_status: str,
    launch_status: str,
    material: str,
) -> list[dict]:
    search_norm = (search or "").strip().lower()
    overall_norm = (overall_status or "").strip().lower()
    launch_status_norm = (launch_status or "").strip().lower()
    material_norm = (material or "").strip().lower()

    filtered = []
    for order in orders:
        if search_norm and search_norm not in (order.get("order_number") or "").lower():
            continue

        if overall_norm and overall_norm != (order.get("overall_status") or "").strip().lower():
            continue

        launches = order.get("launches") or []

        if launch_status_norm:
            has_launch_status = any((launch.get("status") or "").strip().lower() == launch_status_norm for launch in launches)
            if not has_launch_status:
                continue

        if material_norm:
            has_material = any(material_norm in (launch.get("material_type") or "").strip().lower() for launch in launches)
            if not has_material:
                continue

        filtered.append(order)

    return filtered


@router.get("/orders")
async def get_orders(request: Request):
    if not request.session.get("user"):
        return JSONResponse({"ok": False, "error": "Unauthorized"}, status_code=401)

    conn = get_db_connection()
    cur = conn.cursor()
    try:
        result, materials = _build_orders_dataset(cur)
        return {"ok": True, "orders": result, "materials": materials}
    except Exception as exc:
        return JSONResponse({"ok": False, "error": str(exc)}, status_code=500)
    finally:
        cur.close()
        conn.close()


@router.get("/orders/chunk")
async def get_orders_chunk(request: Request):
    if not request.session.get("user"):
        return JSONResponse({"ok": False, "error": "Unauthorized"}, status_code=401)

    qp = request.query_params
    search = qp.get("search", "")
    overall_status = qp.get("overall_status", "")
    launch_status = qp.get("launch_status", "")
    material = qp.get("material", "")

    try:
        offset = max(int(qp.get("offset", "0")), 0)
    except Exception:
        offset = 0

    try:
        limit = max(min(int(qp.get("limit", "50")), 200), 1)
    except Exception:
        limit = 50

    conn = get_db_connection()
    cur = conn.cursor()
    try:
        all_orders, materials = _build_orders_dataset(cur)
        filtered_orders = _apply_filters(all_orders, search, overall_status, launch_status, material)

        items = filtered_orders[offset: offset + limit]
        has_more = offset + limit < len(filtered_orders)

        return {
            "ok": True,
            "items": items,
            "offset": offset,
            "next_offset": offset + len(items),
            "limit": limit,
            "has_more": has_more,
            "total": len(filtered_orders),
            "materials": materials,
        }
    except Exception as exc:
        return JSONResponse({"ok": False, "error": str(exc)}, status_code=500)
    finally:
        cur.close()
        conn.close()
