from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal, InvalidOperation


def safe_text(value) -> str:
    return " ".join(str(value or "").split()).strip()


def parse_decimal(value) -> Decimal:
    raw = safe_text(value).replace(" ", "").replace(",", ".")
    if not raw:
        return Decimal("0")
    try:
        return Decimal(raw)
    except (InvalidOperation, ValueError):
        return Decimal("0")


def format_money(value: Decimal) -> str:
    quantized = value.quantize(Decimal("0.01"))
    text = f"{quantized:,.2f}".replace(",", " ")
    if text.endswith(".00"):
        text = text[:-3]
    return text


def parse_uk_date(value: str) -> date | None:
    raw = safe_text(value)
    if not raw:
        return None
    for fmt in ("%d.%m.%Y", "%d.%m.%y", "%Y-%m-%d"):
        try:
            return datetime.strptime(raw, fmt).date()
        except ValueError:
            continue
    return None


def format_date(value: date | None) -> str:
    return value.strftime("%d.%m.%Y") if value else "—"


def pick_value(rows: list[dict], key: str, default: str = "—") -> str:
    for row in rows:
        value = safe_text(row.get(key))
        if value:
            return value
    return default


def pick_last_date(rows: list[dict], key: str) -> date | None:
    parsed = [parse_uk_date(row.get(key, "")) for row in rows]
    parsed = [item for item in parsed if item is not None]
    return max(parsed) if parsed else None


def order_sort_value(value: str) -> tuple[int, int | str]:
    raw = safe_text(value)
    if raw.isdigit():
        return (0, int(raw))
    return (1, raw.casefold())
