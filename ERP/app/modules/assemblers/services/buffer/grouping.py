from __future__ import annotations

from collections import defaultdict

from .constants import ORDER_NUMBER_PATTERN
from .utils import safe_text


def resolve_order_number(value, known_orders: set[str]) -> str:
    raw = safe_text(value)
    if not raw:
        return ""
    if raw in known_orders:
        return raw

    for candidate in ORDER_NUMBER_PATTERN.findall(raw):
        if candidate in known_orders:
            return candidate

    return ""


def group_designer_rows(raw_rows: list[tuple]) -> dict[str, list[dict]]:
    grouped: dict[str, list[dict]] = defaultdict(list)
    for record in raw_rows:
        order_number = safe_text(record[0])
        if not order_number:
            continue
        grouped[order_number].append(
            {
                "order_number": order_number,
                "client": record[1],
                "product": record[2],
                "manager": record[3],
                "order_type": record[4],
                "order_value": record[5],
                "constructor": record[6],
                "constructor_completed_at": record[7],
                "adapter_completed_at": record[8],
                "metal_flag": record[9],
                "metal": record[9],
                "signed_at": record[10],
                "install_at": record[12] or record[11],
                "paint_shop": record[13] if len(record) > 13 else None,
                "veneer": record[14] if len(record) > 14 else None,
                "plastic_hpl": record[15] if len(record) > 15 else None,
                "joinery_shop": record[16] if len(record) > 16 else None,
                "soft_shop": record[17] if len(record) > 17 else None,
                "artificial_stone": record[18] if len(record) > 18 else None,
                "compact_plate": record[19] if len(record) > 19 else None,
                "dsp_countertop": record[20] if len(record) > 20 else None,
                "sliding_systems": record[21] if len(record) > 21 else None,
                "glass_mirror": record[22] if len(record) > 22 else None,
                "frame_facades": record[23] if len(record) > 23 else None,
                "glass_status": record[24] if len(record) > 24 else None,
                "ceramic_granite": record[25] if len(record) > 25 else None,
            }
        )
    return grouped


def group_production_rows(production_rows: list[tuple]) -> dict[str, list[dict]]:
    grouped_production: dict[str, list[dict]] = defaultdict(list)
    for record in production_rows:
        order_number = safe_text(record[0])
        if not order_number:
            continue
        grouped_production[order_number].append(
            {
                "order_number": order_number,
                "material": record[1],
                "status": record[2],
                "completed_at": record[3],
            }
        )
    return grouped_production


def group_metal_rows(metal_rows: list[tuple], known_orders: set[str]) -> dict[str, list[dict]]:
    grouped_metal: dict[str, list[dict]] = defaultdict(list)
    for record in metal_rows:
        matched_order = resolve_order_number(record[0], known_orders)
        if not matched_order:
            continue
        grouped_metal[matched_order].append(
            {
                "part_number": record[1],
                "constructor_processed_at": record[2],
                "paint_sent_at": record[3],
                "warehouse_received_at": record[4],
            }
        )
    return grouped_metal
