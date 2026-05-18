from __future__ import annotations

from app.modules.assemblers.db.connection import get_db_connection


ASSEMBLERS_STAFF_TABLE = "assemblers_staff_assignments"
TELEGRAM_USERS_TABLE = "database_app_userdatatelegram"
ALLOWED_ROLE_VALUES = [
    "збиральник",
    "керівник збиральників",
    "керівник збиральників приват",
    "керівник збиральників тендер",
]
ALLOWED_SUBDIVISIONS = ["Приват", "Тендер"]


def _safe_text(value) -> str:
    return " ".join(str(value or "").split()).strip()


def ensure_staff_schema() -> None:
    with get_db_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                f"""
                CREATE TABLE IF NOT EXISTS {ASSEMBLERS_STAFF_TABLE} (
                    source_user_id BIGINT PRIMARY KEY,
                    telegram_id BIGINT,
                    subdivision TEXT NOT NULL DEFAULT '',
                    brigade_number INTEGER,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                )
                """
            )
            cursor.execute(
                f"CREATE INDEX IF NOT EXISTS idx_{ASSEMBLERS_STAFF_TABLE}_subdivision ON {ASSEMBLERS_STAFF_TABLE}(subdivision, brigade_number)"
            )
            cursor.execute(
                f"CREATE INDEX IF NOT EXISTS idx_{ASSEMBLERS_STAFF_TABLE}_telegram_id ON {ASSEMBLERS_STAFF_TABLE}(telegram_id)"
            )
        conn.commit()


def load_assembler_staff() -> list[dict]:
    ensure_staff_schema()
    normalized_roles = [role.casefold() for role in ALLOWED_ROLE_VALUES]

    with get_db_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                f"""
                SELECT
                    u.id,
                    u.telegram_id,
                    COALESCE(u.name, ''),
                    COALESCE(u.username, ''),
                    COALESCE(s.subdivision, ''),
                    s.brigade_number
                FROM {TELEGRAM_USERS_TABLE} u
                LEFT JOIN {ASSEMBLERS_STAFF_TABLE} s ON s.source_user_id = u.id
                WHERE u.telegram_id IS NOT NULL
                  AND LOWER(TRIM(COALESCE(u.username, ''))) = ANY(%s)
                ORDER BY COALESCE(s.subdivision, ''), COALESCE(s.brigade_number, 0), COALESCE(u.name, ''), u.id
                """,
                (normalized_roles,),
            )
            rows = cursor.fetchall()

    return [
        {
            "source_user_id": row[0],
            "telegram_id": row[1],
            "name": _safe_text(row[2]) or "—",
            "username": _safe_text(row[3]) or "—",
            "subdivision": _safe_text(row[4]) or "—",
            "subdivision_value": _safe_text(row[4]),
            "brigade_number": row[5] if row[5] is not None else "—",
            "brigade_number_value": row[5] if row[5] is not None else "",
        }
        for row in rows
    ]


def save_staff_assignment(source_user_id: int, subdivision: str, brigade_number: int) -> None:
    ensure_staff_schema()
    normalized_subdivision = _safe_text(subdivision)
    if normalized_subdivision not in ALLOWED_SUBDIVISIONS:
        raise ValueError("Невірний підрозділ")
    if int(brigade_number) <= 0:
        raise ValueError("Номер бригади має бути більше нуля")

    normalized_roles = [role.casefold() for role in ALLOWED_ROLE_VALUES]

    with get_db_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                f"""
                SELECT telegram_id
                FROM {TELEGRAM_USERS_TABLE}
                WHERE id = %s
                  AND LOWER(TRIM(COALESCE(username, ''))) = ANY(%s)
                LIMIT 1
                """,
                (source_user_id, normalized_roles),
            )
            row = cursor.fetchone()
            if not row:
                raise ValueError("Користувач не належить до ролей збирального напряму")

            telegram_id = row[0]

            cursor.execute(
                f"""
                INSERT INTO {ASSEMBLERS_STAFF_TABLE} (
                    source_user_id,
                    telegram_id,
                    subdivision,
                    brigade_number,
                    updated_at
                ) VALUES (%s, %s, %s, %s, NOW())
                ON CONFLICT (source_user_id)
                DO UPDATE SET
                    telegram_id = EXCLUDED.telegram_id,
                    subdivision = EXCLUDED.subdivision,
                    brigade_number = EXCLUDED.brigade_number,
                    updated_at = NOW()
                """,
                (int(source_user_id), int(telegram_id) if telegram_id is not None else None, normalized_subdivision, int(brigade_number)),
            )
        conn.commit()


def clear_staff_assignment(source_user_id: int) -> None:
    ensure_staff_schema()
    with get_db_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                f"DELETE FROM {ASSEMBLERS_STAFF_TABLE} WHERE source_user_id = %s",
                (int(source_user_id),),
            )
        conn.commit()
