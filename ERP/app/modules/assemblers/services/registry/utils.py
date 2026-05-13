from __future__ import annotations

import re
from datetime import date, datetime
from decimal import Decimal, InvalidOperation

from .constants import PRODUCTION_DONE_STATUS


def _safe_text(value) -> str:
    return " ".join(str(value or "").split()).strip()


def _split_csv_text(value) -> list[str]:
    return [_safe_text(chunk) for chunk in str(value or "").split(",") if _safe_text(chunk)]


def _clean_free_text(value) -> str:
    if value is None:
        return ""
    normalized = str(value).replace("\r\n", "\n").replace("\r", "\n")
    return "\n".join(line.rstrip() for line in normalized.split("\n")).strip()


def _parse_decimal(value) -> Decimal:
    raw = _safe_text(value).replace(" ", "").replace(",", ".")
    if not raw:
        return Decimal("0")
    try:
        return Decimal(raw)
    except (InvalidOperation, ValueError):
        return Decimal("0")


def _parse_uk_date(value: str) -> date | None:
    raw = _safe_text(value)
    if not raw:
        return None
    for fmt in ("%d.%m.%Y", "%d.%m.%y", "%Y-%m-%d"):
        try:
            return datetime.strptime(raw, fmt).date()
        except ValueError:
            continue
    return None


def _format_date(value: date | None) -> str:
    return value.strftime("%d.%m.%Y") if value else " "


def _format_date_input(value: date | None) -> str:
    return value.strftime("%Y-%m-%d") if value else ""


def _format_datetime(value) -> str:
    if not value:
        return "-"
    if hasattr(value, "strftime"):
        return value.strftime("%d.%m.%Y %H:%M")
    try:
        parsed = datetime.fromisoformat(str(value))
        return parsed.strftime("%d.%m.%Y %H:%M")
    except ValueError:
        return _safe_text(value) or "-"


def _format_money(value: Decimal) -> str:
    quantized = value.quantize(Decimal("0.01"))
    text = f"{quantized:,.2f}".replace(",", " ")
    if text.endswith(".00"):
        text = text[:-3]
    return text


def _format_hours(value: Decimal) -> str:
    quantized = value.quantize(Decimal("0.01"))
    text = format(quantized, "f")
    return text.rstrip("0").rstrip(".") if "." in text else text


def _normalize_datetime(value) -> datetime | None:
    if not value:
        return None
    if isinstance(value, datetime):
        return value
    try:
        return datetime.fromisoformat(str(value))
    except ValueError:
        return None


def _format_duration(value_in_minutes: int) -> str:
    total_minutes = max(0, int(value_in_minutes or 0))
    hours = total_minutes // 60
    minutes = total_minutes % 60
    if hours and minutes:
        return f"{hours} год {minutes} хв"
    if hours:
        return f"{hours} год"
    return f"{minutes} хв"


def _calculate_stage_metrics(*, started_at, completed_at, fallback_days: int) -> tuple[int, str]:
    normalized_started_at = _normalize_datetime(started_at)
    normalized_completed_at = _normalize_datetime(completed_at)
    if normalized_started_at and normalized_completed_at and normalized_completed_at >= normalized_started_at:
        total_minutes = int((normalized_completed_at - normalized_started_at).total_seconds() // 60)
        total_days = (normalized_completed_at.date() - normalized_started_at.date()).days + 1
        return max(total_days, 1), _format_duration(total_minutes)

    if fallback_days > 0:
        return fallback_days, ""

    return 0, ""


def _parse_duration_minutes(text: str) -> int:
    s = _safe_text(text)
    total = 0
    hours_match = re.search(r"(\d+)\s*год", s)
    minutes_match = re.search(r"(\d+)\s*хв", s)
    if hours_match:
        total += int(hours_match.group(1)) * 60
    if minutes_match:
        total += int(minutes_match.group(1))
    return total


def _count_workers(value: str) -> int:
    normalized = _safe_text(value)
    if not normalized or normalized == "—":
        return 0
    return len([part for part in (item.strip() for item in normalized.split(",")) if part])


def _calculate_planned_hours(
    *,
    item_value: Decimal,
    assembly_worker: str,
    install_worker: str,
    day_cost: Decimal,
    workday_hours: Decimal,
) -> tuple[str, str]:
    if item_value <= 0 or day_cost <= 0 or workday_hours <= 0:
        return "0", "0"

    assembly_count = _count_workers(assembly_worker)
    install_count = _count_workers(install_worker)
    people = max(assembly_count, install_count)
    if people == 0:
        people = 2

    people_decimal = Decimal(people)
    planned_hours = (item_value / (day_cost * people_decimal)) * workday_hours
    total_hours = planned_hours * people_decimal
    return _format_hours(planned_hours), _format_hours(total_hours)


def _build_products_text(values: list[str]) -> str:
    products = []
    seen: set[str] = set()
    for value in values:
        product = _safe_text(value)
        normalized = product.casefold()
        if not product or normalized in seen:
            continue
        seen.add(normalized)
        products.append(product)
    return ", ".join(products) if products else "—"


def _days_until(value: date | None) -> str:
    if not value:
        return "-"
    return str((value - date.today()).days)


def _normalize_limit(value: int) -> int:
    return max(1, min(int(value or 30), 100))


def _normalize_offset(value: int) -> int:
    return max(0, int(value or 0))


def _build_ratio(done: int, total: int) -> str:
    return f"{done}/{total}" if total > 0 else "0/0"


def _parse_part_number(value) -> int | None:
    text = _safe_text(value)
    if not text:
        return None
    try:
        return int(Decimal(text))
    except (InvalidOperation, ValueError):
        return None


def _is_done_status(value: str) -> bool:
    return _safe_text(value).casefold() == PRODUCTION_DONE_STATUS


def _pick_first_value(values: list[str], default: str = "-") -> str:
    for value in values:
        text = _safe_text(value)
        if text:
            return text
    return default
