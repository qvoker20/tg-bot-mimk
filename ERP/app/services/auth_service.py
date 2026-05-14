import random
from collections import deque
from threading import Lock
import time
from typing import Any

import requests

from ..config import CODE_TTL_SECONDS, TELEGRAM_BOT_TOKEN
from ..db import get_db_connection


LOGIN_CODES: dict[str, dict[str, Any]] = {}
_CODE_REQUEST_WINDOW_SECONDS = 10 * 60
_CODE_REQUEST_COOLDOWN_SECONDS = 60
_MAX_REQUESTS_PER_PHONE_WINDOW = 5
_MAX_REQUESTS_PER_IP_WINDOW = 20
_PHONE_REQUEST_TIMESTAMPS: dict[str, deque[float]] = {}
_IP_REQUEST_TIMESTAMPS: dict[str, deque[float]] = {}
_PHONE_COOLDOWN_UNTIL: dict[str, float] = {}
_REQUEST_GUARD_LOCK = Lock()


class CodeRequestRateLimitError(Exception):
    """Raised when auth code requests exceed anti-spam limits."""


def _trim_old_requests(queue: deque[float], now_ts: float) -> None:
    threshold = now_ts - _CODE_REQUEST_WINDOW_SECONDS
    while queue and queue[0] < threshold:
        queue.popleft()


def _seconds_until_next_allowed(phone_380: str) -> int:
    wait_until = float(_PHONE_COOLDOWN_UNTIL.get(phone_380, 0.0))
    return max(0, int(wait_until - time.time()))


def has_active_code(phone_380: str) -> bool:
    record = LOGIN_CODES.get(phone_380)
    return bool(record and float(record.get("expires_at", 0)) > time.time())


def _register_code_request(phone_380: str, ip_address: str | None) -> None:
    now_ts = time.time()
    with _REQUEST_GUARD_LOCK:
        wait_seconds = _seconds_until_next_allowed(phone_380)
        if wait_seconds > 0:
            raise CodeRequestRateLimitError(
                f"Код уже надіслано. Повторіть запит через {wait_seconds} с."
            )

        phone_queue = _PHONE_REQUEST_TIMESTAMPS.setdefault(phone_380, deque())
        _trim_old_requests(phone_queue, now_ts)
        if len(phone_queue) >= _MAX_REQUESTS_PER_PHONE_WINDOW:
            raise CodeRequestRateLimitError(
                "Занадто багато запитів коду для цього номера. Спробуйте пізніше."
            )

        ip_key = (ip_address or "").strip()
        if ip_key:
            ip_queue = _IP_REQUEST_TIMESTAMPS.setdefault(ip_key, deque())
            _trim_old_requests(ip_queue, now_ts)
            if len(ip_queue) >= _MAX_REQUESTS_PER_IP_WINDOW:
                raise CodeRequestRateLimitError(
                    "Занадто багато запитів з вашої адреси. Спробуйте пізніше."
                )
            ip_queue.append(now_ts)

        phone_queue.append(now_ts)
        _PHONE_COOLDOWN_UNTIL[phone_380] = now_ts + _CODE_REQUEST_COOLDOWN_SECONDS


def _build_user_payload(row, fallback_phone_380: str = ""):
    return {
        "id": row[0],
        "telegram_id": row[1],
        "name": row[2] or "Користувач",
        "username": row[3] or "",
        "role": row[3] or "",
        "phone_number": row[4] or (f"+{fallback_phone_380}" if fallback_phone_380 else ""),
    }


def normalize_phone_380(value: str) -> str:
    digits = "".join(ch for ch in str(value) if ch.isdigit())
    if len(digits) == 10 and digits.startswith("0"):
        return f"38{digits}"
    if len(digits) == 12 and digits.startswith("380"):
        return digits
    return ""


def get_user_by_phone(phone_380: str):
    with get_db_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                """
                SELECT id, telegram_id, COALESCE(name, ''), COALESCE(username, ''), COALESCE(phone_number, '')
                FROM public.database_app_userdatatelegram
                WHERE regexp_replace(COALESCE(phone_number, ''), '\\D', '', 'g') = %s
                LIMIT 1
                """,
                (phone_380,),
            )
            row = cursor.fetchone()
            if not row:
                return None

            return _build_user_payload(row, fallback_phone_380=phone_380)


def get_user_by_id(user_id: int):
    with get_db_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                """
                SELECT id, telegram_id, COALESCE(name, ''), COALESCE(username, ''), COALESCE(phone_number, '')
                FROM public.database_app_userdatatelegram
                WHERE id = %s
                LIMIT 1
                """,
                (int(user_id),),
            )
            row = cursor.fetchone()
            if not row:
                return None

            return _build_user_payload(row)


def send_telegram_code(chat_id: int, code: str, phone_380: str):
    if not TELEGRAM_BOT_TOKEN:
        raise RuntimeError("TELEGRAM_BOT_TOKEN is not configured")

    response = requests.post(
        f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage",
        json={
            "chat_id": int(chat_id),
            "text": (
                "🔐 Вхід у MIMK ERP\n"
                f"Телефон: +{phone_380}\n"
                "Код входу:\n"
                f"<code>{code}</code>\n"
                f"Дійсний {CODE_TTL_SECONDS // 60} хв."
            ),
            "parse_mode": "HTML",
        },
        timeout=12,
    )
    response.raise_for_status()


def issue_code(phone_380: str, user: dict[str, Any], ip_address: str | None, user_agent: str | None):
    _register_code_request(phone_380=phone_380, ip_address=ip_address)

    code = str(random.randint(100000, 999999))
    LOGIN_CODES[phone_380] = {
        "code": code,
        "expires_at": time.time() + CODE_TTL_SECONDS,
        "user": user,
    }

    send_telegram_code(int(user["telegram_id"]), code, phone_380)


def verify_code(phone_380: str, code: str, ip_address: str | None, user_agent: str | None):
    record = LOGIN_CODES.get(phone_380)
    if not record:
        return None, "Спочатку запросіть код входу."

    if time.time() > float(record["expires_at"]):
        LOGIN_CODES.pop(phone_380, None)
        return None, "Термін дії коду закінчився. Запросіть новий."

    if code != str(record["code"]):
        return None, "Невірний код."

    user = record["user"]
    LOGIN_CODES.pop(phone_380, None)
    return user, None