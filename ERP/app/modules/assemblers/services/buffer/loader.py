from __future__ import annotations

import asyncio
import re
from datetime import date, datetime
from decimal import Decimal

from app.modules.assemblers.repositories.buffer_sources import (
    fetch_designer_rows,
    fetch_metal_rows,
    fetch_production_rows,
    fetch_transferred_order_numbers,
)

from .constants import NOT_SENT_STATUS
from .grouping import group_designer_rows, group_metal_rows, group_production_rows
from .status import (
    build_materials_list,
    calc_buffer_status,
    calc_metal_status,
    calc_percent,
    has_value,
    is_done_status,
    is_started_constructor,
)
from .utils import (
    format_date,
    format_money,
    order_sort_value,
    parse_decimal,
    parse_uk_date,
    pick_last_date,
    pick_value,
    safe_text,
)


def _parse_percent(raw: str) -> float | None:
    m = re.match(r"^(\d+(?:[.,]\d+)?)%$", raw.strip())
    if m:
        try:
            return float(m.group(1).replace(",", "."))
        except ValueError:
            return None
    return None


def _pick_shop(rows: list[dict], key: str) -> str:
    for row in rows:
        val = safe_text(row.get(key) or "")
        if val and val not in ("-", "—"):
            return val
    return "-"


async def load_buffer_rows(
    offset: int = 0,
    limit: int = 30,
    order_number_query: str = "",
    customer_query: str = "",
    sort_by: str = "",
    sort_dir: str = "asc",
    status_percent_op: str = "",
    status_percent_value: int = -1,
) -> dict:
    transferred_orders, raw_rows, production_rows, metal_rows = await asyncio.gather(
        fetch_transferred_order_numbers(),
        fetch_designer_rows(),
        fetch_production_rows(),
        fetch_metal_rows(),
    )
    normalized_order_query = safe_text(order_number_query).casefold()
    normalized_customer_query = safe_text(customer_query).casefold()

    grouped = group_designer_rows(raw_rows)
    grouped_production = group_production_rows(production_rows)
    grouped_metal = group_metal_rows(metal_rows, set(grouped))

    items: list[dict] = []
    today = date.today()

    for order_number, rows in grouped.items():
        if order_number in transferred_orders:
            continue

        production = grouped_production.get(order_number, [])
        metal = grouped_metal.get(order_number, [])

        total_products = len(rows)
        constructor_done = sum(1 for row in rows if parse_uk_date(row.get("constructor_completed_at", "")))
        constructor_in_work = sum(
            1
            for row in rows
            if is_started_constructor(row.get("constructor", ""))
            and not parse_uk_date(row.get("constructor_completed_at", ""))
        )
        adapter_done = sum(1 for row in rows if parse_uk_date(row.get("adapter_completed_at", "")))

        production_total = len(production)
        production_done = sum(1 for row in production if is_done_status(row.get("status", "")))
        production_is_sent = production_total > 0
        production_is_complete = production_is_sent and production_done == production_total

        has_metal_flag = any(has_value(row.get("metal_flag")) for row in rows)
        metal_total = len(metal)
        metal_constructor_done = sum(1 for row in metal if has_value(row.get("constructor_processed_at")))
        metal_paint_done = sum(1 for row in metal if has_value(row.get("paint_sent_at")))
        metal_warehouse_done = sum(1 for row in metal if has_value(row.get("warehouse_received_at")))

        install_date = parse_uk_date(pick_value(rows, "install_at", default=""))
        signed_date = parse_uk_date(pick_value(rows, "signed_at", default=""))
        days_to_install = (install_date - today).days if install_date else None
        production_completed_at = pick_last_date(production, "completed_at") if production_is_complete else None

        client_name = pick_value(rows, "client")
        if normalized_order_query and normalized_order_query != order_number.casefold():
            continue
        if normalized_customer_query and normalized_customer_query != client_name.casefold():
            continue

        constructor_status = calc_percent(constructor_done, total_products)
        production_status = calc_percent(production_done, production_total) if production_is_sent else NOT_SENT_STATUS
        materials_status = calc_metal_status(
            has_metal_flag,
            metal_total,
            metal_constructor_done,
            metal_paint_done,
            metal_warehouse_done,
        )

        items.append(
            {
                "order_number": order_number,
                "client": client_name,
                "status": calc_buffer_status(constructor_status, production_status, materials_status),
                "products_hidden": total_products,
                "products_list": [
                    {
                        "name": safe_text(row.get("product", "")) or "—",
                        "status": (
                            "Завершено"
                            if parse_uk_date(row.get("constructor_completed_at", ""))
                            else (
                                "В роботі"
                                if is_started_constructor(row.get("constructor", ""))
                                else "Не запущено"
                            )
                        ),
                    }
                    for row in rows
                ],
                "signed_at": format_date(signed_date),
                "install_at": format_date(install_date),
                "days_to_install": str(days_to_install) if days_to_install is not None else "—",
                "constructor_percent": constructor_status,
                "constructor_total": total_products,
                "constructor_done": constructor_done,
                "constructor_completed_at": format_date(pick_last_date(rows, "constructor_completed_at")),
                "adapter_done": adapter_done,
                "adapter_completed_at": format_date(pick_last_date(rows, "adapter_completed_at")),
                "production_status": production_status,
                "production_total": production_total,
                "production_done": production_done,
                "production_completed_at": format_date(production_completed_at),
                "materials_present": build_materials_list(production),
                "materials_status": materials_status,
                "materials_total": metal_total,
                "materials_constructor_done": metal_constructor_done,
                "materials_metal_done": metal_paint_done,
                "materials_paint_done": metal_warehouse_done,
                "materials_percent": materials_status,
                "warehouse_status": "—",
                "warehouse_note": "—",
                "manager": pick_value(rows, "manager"),
                "constructor": pick_value(rows, "constructor"),
                "order_value": format_money(
                    sum((parse_decimal(row.get("order_value")) for row in rows), start=Decimal("0"))
                ),
                "order_type": pick_value(rows, "order_type"),
                "constructor_in_work": constructor_in_work,
            }
        )
        items[-1]["subcontracts"] = {
            "paint_shop": _pick_shop(rows, "paint_shop"),
            "paint_status": "-",
            "metal": _pick_shop(rows, "metal"),
            "metal_status": f"{metal_constructor_done}/{metal_total}" if metal_total > 0 else "-",
            "veneer": _pick_shop(rows, "veneer"),
            "plastic_hpl": _pick_shop(rows, "plastic_hpl"),
            "joinery_shop": _pick_shop(rows, "joinery_shop"),
            "soft_shop": _pick_shop(rows, "soft_shop"),
            "artificial_stone": _pick_shop(rows, "artificial_stone"),
            "compact_plate": _pick_shop(rows, "compact_plate"),
            "dsp_countertop": _pick_shop(rows, "dsp_countertop"),
            "sliding_systems": _pick_shop(rows, "sliding_systems"),
            "glass_mirror": _pick_shop(rows, "glass_mirror"),
            "glass_status": _pick_shop(rows, "glass_status"),
            "frame_facades": _pick_shop(rows, "frame_facades"),
            "ceramic_granite": _pick_shop(rows, "ceramic_granite"),
        }

    # Фільтр по відсотку статусу
    if status_percent_op in ("gt", "lt") and status_percent_value >= 0:
        if status_percent_op == "gt":
            items = [i for i in items if (_parse_percent(i.get("status", "") or "") or -1) > status_percent_value]
        else:
            items = [
                i for i in items
                if _parse_percent(i.get("status", "") or "") is not None
                and (_parse_percent(i.get("status", "") or "") or 0) < status_percent_value
            ]

    # Сортування
    descending = sort_dir == "desc"
    if sort_by == "install_at":
        def _key_install(item: dict) -> tuple:
            ds = item.get("install_at", "") or ""
            try:
                return (0, datetime.strptime(ds, "%d.%m.%Y").date())
            except ValueError:
                return (1, date(9999, 12, 31))
        items.sort(key=_key_install, reverse=descending)
    elif sort_by == "days_to_install":
        def _key_days(item: dict) -> tuple:
            try:
                return (0, int(item.get("days_to_install", "") or ""))
            except (ValueError, TypeError):
                return (1, 99999)
        items.sort(key=_key_days, reverse=descending)
    elif sort_by == "status":
        def _key_status(item: dict) -> tuple:
            pct = _parse_percent(item.get("status", "") or "")
            return (0, pct) if pct is not None else (1, 0.0)
        items.sort(key=_key_status, reverse=descending)
    else:
        items.sort(key=lambda item: order_sort_value(item["order_number"]), reverse=True)

    offset = max(0, int(offset or 0))
    limit = max(1, min(int(limit or 30), 100))
    total = len(items)

    paged_items = items[offset : offset + limit]

    return {
        "rows": paged_items,
        "total": total,
        "offset": offset,
        "limit": limit,
        "has_more": offset + limit < total,
    }
