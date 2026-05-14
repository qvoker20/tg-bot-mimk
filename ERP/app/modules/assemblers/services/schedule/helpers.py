from __future__ import annotations

from datetime import date, datetime, timedelta

from .constants import TASK_STATUS_COMPLETED, TASK_STATUS_QUEUED, TASK_TYPE_ALIASES


def _safe_text(value) -> str:
    return " ".join(str(value or "").split()).strip()


def _normalize_task_type(value) -> str:
    normalized = _safe_text(value).casefold()
    return TASK_TYPE_ALIASES.get(normalized, _safe_text(value))


def _split_csv_text(value) -> list[str]:
    return [_safe_text(chunk) for chunk in str(value or "").split(",") if _safe_text(chunk)]


def _join_unique_texts(values) -> str:
    items: list[str] = []
    seen: set[str] = set()
    for value in values or []:
        for chunk in _split_csv_text(value):
            normalized = _safe_text(chunk)
            if not normalized or normalized in seen:
                continue
            seen.add(normalized)
            items.append(normalized)
    return ", ".join(items)


def _normalize_task_ids(task_ids) -> list[int]:
    normalized_ids: list[int] = []
    seen_ids: set[int] = set()
    for raw_id in task_ids or []:
        try:
            task_id = int(raw_id)
        except (TypeError, ValueError):
            continue
        if task_id <= 0 or task_id in seen_ids:
            continue
        seen_ids.add(task_id)
        normalized_ids.append(task_id)
    return normalized_ids


def _normalize_selected_parts(selected_parts) -> tuple[str, str, str, str]:
    normalized_parts = []
    for item in selected_parts or []:
        if not isinstance(item, dict):
            continue
        part_number = _safe_text(item.get("part_number"))
        customer = _safe_text(item.get("customer"))
        product_name = _safe_text(item.get("product_name"))
        constructor_status = _safe_text(item.get("constructor_status"))
        if not part_number and not product_name:
            continue
        normalized_parts.append((part_number, customer, product_name, constructor_status))

    if not normalized_parts:
        raise ValueError("Треба обрати хоча б одну частину замовлення")

    return (
        _join_unique_texts(part_number for part_number, _, _, _ in normalized_parts),
        _join_unique_texts(customer for _, customer, _, _ in normalized_parts),
        _join_unique_texts(product_name for _, _, product_name, _ in normalized_parts),
        _join_unique_texts(constructor_status for _, _, _, constructor_status in normalized_parts),
    )


def _normalize_completed_products(selected_products) -> list[dict[str, str]]:
    normalized_products: list[dict[str, str]] = []
    seen_products: set[tuple[str, str]] = set()
    for item in selected_products or []:
        if not isinstance(item, dict):
            continue
        part_number = _safe_text(item.get("part_number"))
        product_name = _safe_text(item.get("product_name"))
        if not part_number and not product_name:
            continue
        product_key = (product_name.casefold(), part_number.casefold())
        if product_key in seen_products:
            continue
        seen_products.add(product_key)
        normalized_products.append(
            {
                "part_number": part_number,
                "product_name": product_name,
            }
        )
    return normalized_products


def _detail_row_matches_selected_product(detail_row, selected_product: dict[str, str]) -> bool:
    detail_part_number = _safe_text(detail_row[1])
    detail_product_name = _safe_text(detail_row[2])
    selected_part_number = _safe_text(selected_product.get("part_number"))
    selected_product_name = _safe_text(selected_product.get("product_name"))

    if selected_product_name and selected_part_number:
        return (
            detail_product_name.casefold() == selected_product_name.casefold()
            and detail_part_number.casefold() == selected_part_number.casefold()
        )
    if selected_product_name:
        return detail_product_name.casefold() == selected_product_name.casefold()
    return detail_part_number.casefold() == selected_part_number.casefold()


def _parse_iso_date(value) -> date | None:
    raw = _safe_text(value)
    if not raw:
        return None
    try:
        return datetime.strptime(raw, "%Y-%m-%d").date()
    except ValueError:
        return None


def _parse_float(value) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _normalize_location_payload(location) -> dict:
    if not isinstance(location, dict):
        raise ValueError("Не вдалося отримати локацію користувача")

    latitude = _parse_float(location.get("latitude"))
    longitude = _parse_float(location.get("longitude"))
    accuracy = _parse_float(location.get("accuracy"))
    if latitude is None or longitude is None:
        raise ValueError("Не вдалося отримати координати користувача")

    label = _safe_text(location.get("label")) or f"{latitude:.6f}, {longitude:.6f}"
    return {
        "label": label,
        "latitude": latitude,
        "longitude": longitude,
        "accuracy": accuracy,
    }


def _serialize_datetime(value) -> str:
    if not value:
        return ""
    return value.isoformat()


def _format_pause_hours_label(total_seconds) -> str:
    try:
        seconds = max(0, int(total_seconds or 0))
    except (TypeError, ValueError):
        return ""
    if seconds <= 0:
        return ""
    hours = round(seconds / 3600, 1)
    return f"Пауза: {str(f'{hours:.1f}').replace('.', ',')} год"


def _task_row_to_dict(row, customer_fallbacks: dict[str, str] | None = None) -> dict:
    order_number = _safe_text(row[6])
    customer = (customer_fallbacks or {}).get(order_number, "") or _safe_text(row[7])
    scheduled_for = row[3]
    auto_close_note = _safe_text(row[25]) if len(row) > 25 else ""
    pause_seconds = int(row[26] or 0) if len(row) > 26 and row[26] is not None else 0
    status = _safe_text(row[5]) or TASK_STATUS_QUEUED
    status_label = (
        "Пауза - завершено"
        if status == TASK_STATUS_COMPLETED and auto_close_note.startswith("Пауза - завершено")
        else status
    )

    return {
        "id": int(row[0]),
        "source_user_id": int(row[1]),
        "assembler_name": _safe_text(row[2]),
        "scheduled_for": scheduled_for.isoformat() if scheduled_for else "",
        "task_type": _normalize_task_type(row[4]),
        "status": status,
        "status_label": status_label,
        "order_number": order_number,
        "customer": customer,
        "part_number": _safe_text(row[8]),
        "product_name": _safe_text(row[9]),
        "constructor_status": _safe_text(row[10]),
        "description": _safe_text(row[11]),
        "started_at": _serialize_datetime(row[12]),
        "paused_at": _serialize_datetime(row[13]),
        "completed_at": _serialize_datetime(row[14]),
        "pause_reason": _safe_text(row[15]),
        "started_location_label": _safe_text(row[16]),
        "started_latitude": row[17],
        "started_longitude": row[18],
        "started_accuracy": row[19],
        "completed_location_label": _safe_text(row[20]),
        "completed_latitude": row[21],
        "completed_longitude": row[22],
        "completed_accuracy": row[23],
        "auto_closed_at": _serialize_datetime(row[24]) if len(row) > 24 else None,
        "auto_close_note": auto_close_note,
        "pause_seconds": pause_seconds,
        "pause_hours_label": _format_pause_hours_label(pause_seconds),
    }


def _start_of_week(value: date) -> date:
    return value - timedelta(days=value.weekday())


def _status_is_completed(value) -> bool:
    normalized = _safe_text(value).casefold()
    return normalized == TASK_STATUS_COMPLETED.casefold()


def _find_blocked_selected_parts(detail_rows, *, selected_parts, task_type: str) -> list[str]:
    normalized_products = _normalize_completed_products(selected_parts)
    if not normalized_products:
        return []

    blocked: list[str] = []
    seen: set[str] = set()

    for row in detail_rows:
        part_number = _safe_text(row[0])
        product_name = _safe_text(row[1])
        assembly_status = row[2]
        assembly_completed_at = row[3]
        install_status = row[4]
        install_completed_at = row[5]
        constructor_status = row[6]
        requires_assembly = bool(row[7])
        requires_install = bool(row[8])

        is_target = any(
            _detail_row_matches_selected_product(
                (None, part_number, product_name),
                selected_product,
            )
            for selected_product in normalized_products
        )
        if not is_target:
            continue

        assembly_done = (not requires_assembly) or bool(assembly_completed_at) or _status_is_completed(assembly_status)
        install_done = (not requires_install) or bool(install_completed_at) or _status_is_completed(install_status)
        constructor_ready = _status_is_completed(constructor_status)
        product_done = assembly_done and install_done

        stage_not_required = (
            (task_type == "assembly" and not requires_assembly)
            or (task_type == "install" and not requires_install)
        )

        is_blocked = (
            (not constructor_ready)
            or product_done
            or stage_not_required
            or
            (task_type == "assembly" and assembly_done)
            or (task_type == "install" and install_done)
        )

        if is_blocked:
            title = f"{product_name} ({part_number})" if product_name and part_number else (product_name or part_number or "Виріб")
            if not constructor_ready:
                title = f"{title}: статус конструктора не завершено"
            elif stage_not_required:
                title = f"{title}: {'без збірки' if task_type == 'assembly' else 'без монтажу'}"
            elif product_done:
                title = f"{title}: виріб вже завершено"
            elif task_type == "assembly" and assembly_done:
                title = f"{title}: збірку вже завершено"
            elif task_type == "install" and install_done:
                title = f"{title}: монтаж вже завершено"
            key = title.casefold()
            if key not in seen:
                seen.add(key)
                blocked.append(title)

    return blocked
