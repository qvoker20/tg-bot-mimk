import random
import time
from typing import Any

import requests

from ..config import ALLOWED_ROLES, CODE_TTL_SECONDS, TELEGRAM_BOT_TOKEN
from ..db import get_db_connection

LOGIN_CODES: dict[str, dict[str, Any]] = {}


def normalize_phone_380(value: str) -> str:
    digits = "".join(ch for ch in str(value) if ch.isdigit())
    if len(digits) == 12 and digits.startswith("380"):
        return digits
    return ""


def phone_to_db_format(phone_380: str) -> str:
    return f"+{phone_380}"


def get_user_by_phone(phone_380: str):
    conn = get_db_connection()
    cur = conn.cursor()
    try:
        cur.execute(
            """
            SELECT telegram_id, COALESCE(name, ''), COALESCE(username, ''), COALESCE(phone_number, '')
            FROM database_app_userdatatelegram
            WHERE regexp_replace(COALESCE(phone_number, ''), '\\D', '', 'g') = %s
            LIMIT 1
            """,
            (phone_380,),
        )
        row = cur.fetchone()
        if not row:
            return None

        role = (row[2] or "").strip().lower()
        return {
            "telegram_id": row[0],
            "name": row[1] or "Користувач",
            "role": role,
            "phone": row[3] or phone_to_db_format(phone_380),
        }
    finally:
        cur.close()
        conn.close()


def get_fresh_role(user: dict[str, Any] | None) -> str:
    user = user or {}
    telegram_id = user.get("telegram_id")
    phone = str(user.get("phone") or "")
    phone_digits = "".join(ch for ch in phone if ch.isdigit())

    conn = get_db_connection()
    cur = conn.cursor()
    try:
        if telegram_id:
            cur.execute(
                """
                SELECT COALESCE(username, '')
                FROM database_app_userdatatelegram
                WHERE telegram_id = %s
                LIMIT 1
                """,
                (telegram_id,),
            )
            row = cur.fetchone()
            if row:
                return str(row[0] or "").strip().lower()

        if phone_digits:
            cur.execute(
                """
                SELECT COALESCE(username, '')
                FROM database_app_userdatatelegram
                WHERE regexp_replace(COALESCE(phone_number, ''), '\\D', '', 'g') = %s
                LIMIT 1
                """,
                (phone_digits,),
            )
            row = cur.fetchone()
            if row:
                return str(row[0] or "").strip().lower()

        return ""
    finally:
        cur.close()
        conn.close()


def is_role_allowed(role: str) -> bool:
    if not ALLOWED_ROLES:
        return True
    return (role or "").strip().lower() in ALLOWED_ROLES


def send_telegram_code(chat_id: int, code: str, phone_380: str, where_text: str):
    if not TELEGRAM_BOT_TOKEN:
        raise RuntimeError("TELEGRAM_BOT_TOKEN не налаштований")

    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    text = (
        "🔐 Вхід у виробництво!\n"
        f"Телефон: +{phone_380}\n"
        f"Куди вхід: {where_text}\n\n"
        f"Код входу: {code}\n"
        f"Дійсний {CODE_TTL_SECONDS // 60} хв."
    )
    response = requests.post(
        url,
        json={"chat_id": int(chat_id), "text": text},
        timeout=12,
    )
    response.raise_for_status()


def issue_code(phone_380: str, user: dict[str, Any], where_text: str):
    code = str(random.randint(100000, 999999))
    LOGIN_CODES[phone_380] = {
        "code": code,
        "expires_at": time.time() + CODE_TTL_SECONDS,
        "user": user,
    }
    send_telegram_code(int(user["telegram_id"]), code, phone_380, where_text)


def verify_code(phone_380: str, code: str):
    record = LOGIN_CODES.get(phone_380)
    if not record:
        return None, "Спочатку запросіть код."

    if time.time() > float(record["expires_at"]):
        LOGIN_CODES.pop(phone_380, None)
        return None, "Термін дії коду закінчився."

    if code != str(record["code"]):
        return None, "Невірний код."

    user = record["user"]
    LOGIN_CODES.pop(phone_380, None)
    return user, None
