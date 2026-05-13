from __future__ import annotations

from decimal import Decimal, InvalidOperation

from .constants import NO_MATERIAL_STATUS, NOT_SENT_STATUS, PRODUCTION_DONE_STATUS
from .utils import safe_text


def is_started_constructor(value: str) -> bool:
    raw = safe_text(value)
    if not raw:
        return False
    normalized = raw.replace(",", ".")
    try:
        Decimal(normalized)
        return False
    except InvalidOperation:
        return True


def calc_percent(done: int, total: int) -> str:
    if total <= 0:
        return "0%"
    percent = (done / total) * 100
    return f"{percent:.0f}%"


def is_done_status(value: str) -> bool:
    return safe_text(value).casefold() == PRODUCTION_DONE_STATUS


def has_value(value) -> bool:
    return bool(safe_text(value))


def calc_metal_status(has_metal_flag: bool, total: int, constructor_done: int, paint_done: int, warehouse_done: int) -> str:
    if has_metal_flag and total == 0:
        return NO_MATERIAL_STATUS
    if total == 0:
        return NOT_SENT_STATUS

    percent = ((constructor_done + paint_done + warehouse_done) / (3 * total)) * 100
    return f"{percent:.0f}%"


def parse_percent_status(value: str) -> int | None:
    raw = safe_text(value)
    if not raw.endswith("%"):
        return None

    try:
        return int(Decimal(raw[:-1].replace(",", ".")))
    except (InvalidOperation, ValueError):
        return None


def calc_buffer_status(constructor_status: str, production_status: str, metal_status: str) -> str:
    components: list[int] = []

    constructor_percent = parse_percent_status(constructor_status)
    components.append(constructor_percent if constructor_percent is not None else 0)

    production_percent = parse_percent_status(production_status)
    components.append(production_percent if production_percent is not None else 0)

    if safe_text(metal_status).casefold() != NOT_SENT_STATUS:
        metal_percent = parse_percent_status(metal_status)
        components.append(metal_percent if metal_percent is not None else 0)

    if not components:
        return "0%"

    percent = sum(components) / len(components)
    return f"{percent:.0f}%"


def build_materials_list(rows: list[dict]) -> str:
    materials: list[str] = []
    seen: set[str] = set()

    for row in rows:
        material = safe_text(row.get("material"))
        normalized = material.casefold()
        if not material or normalized in seen:
            continue
        seen.add(normalized)
        materials.append(material)

    return ", ".join(materials) if materials else "—"
