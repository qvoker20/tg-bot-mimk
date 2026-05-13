import json
import os
from typing import Any, Optional

import psycopg2
from dotenv import load_dotenv
from psycopg2.extras import RealDictCursor

load_dotenv()

PG_CONN = {
    "host": os.getenv("PG_HOST"),
    "port": int(os.getenv("PG_PORT", "5432")),
    "dbname": os.getenv("PG_DBNAME"),
    "user": os.getenv("PG_USER"),
    "password": os.getenv("PG_PASSWORD"),
}

STATUS_WAITING_NAME = "waiting_name"
STATUS_WAITING_PROJECT = "waiting_project"
STATUS_WAITING_PHONE = "waiting_phone"
STATUS_COMPLETED = "completed"
STATUS_CANCELED = "canceled"
STATUS_ABANDONED = "abandoned"

ACTIVE_STATUSES = (
    STATUS_WAITING_NAME,
    STATUS_WAITING_PROJECT,
    STATUS_WAITING_PHONE,
)


def get_db_connection():
    return psycopg2.connect(**PG_CONN)


def ensure_schema() -> None:
    conn = get_db_connection()
    cur = conn.cursor()
    try:
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS project_calculation_requests (
                id BIGSERIAL PRIMARY KEY,
                started_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                telegram_id BIGINT NOT NULL,
                chat_id BIGINT NOT NULL,
                telegram_username TEXT,
                telegram_full_name TEXT,
                source TEXT,
                client_name TEXT,
                first_project_payload JSONB,
                all_project_payloads JSONB NOT NULL DEFAULT '[]'::jsonb,
                local_file_paths JSONB NOT NULL DEFAULT '[]'::jsonb,
                files_dir TEXT,
                archive_file_path TEXT,
                project_sent_at TIMESTAMPTZ,
                contact_phone TEXT,
                status TEXT NOT NULL DEFAULT 'waiting_name',
                completed_at TIMESTAMPTZ
            )
            """
        )
        cur.execute(
            "ALTER TABLE project_calculation_requests ADD COLUMN IF NOT EXISTS all_project_payloads JSONB NOT NULL DEFAULT '[]'::jsonb"
        )
        cur.execute(
            "ALTER TABLE project_calculation_requests ADD COLUMN IF NOT EXISTS local_file_paths JSONB NOT NULL DEFAULT '[]'::jsonb"
        )
        cur.execute(
            "ALTER TABLE project_calculation_requests ADD COLUMN IF NOT EXISTS files_dir TEXT"
        )
        cur.execute(
            "ALTER TABLE project_calculation_requests ADD COLUMN IF NOT EXISTS archive_file_path TEXT"
        )
        cur.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_project_calc_requests_telegram_id
            ON project_calculation_requests(telegram_id)
            """
        )
        cur.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_project_calc_requests_status
            ON project_calculation_requests(status)
            """
        )
        conn.commit()
    finally:
        cur.close()
        conn.close()


def get_active_request(telegram_id: int, chat_id: int) -> Optional[dict[str, Any]]:
    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    try:
        cur.execute(
            """
            SELECT *
            FROM project_calculation_requests
            WHERE telegram_id = %s
              AND chat_id = %s
                            AND status = ANY(%s)
            ORDER BY started_at DESC
            LIMIT 1
            """,
                        (telegram_id, chat_id, list(ACTIVE_STATUSES)),
        )
        return cur.fetchone()
    finally:
        cur.close()
        conn.close()


def create_request(
    telegram_id: int,
    chat_id: int,
    telegram_username: str,
    telegram_full_name: str,
    source: str,
    client_name: str = "",
    contact_phone: str = "",
    status: str = STATUS_WAITING_NAME,
) -> int:
    conn = get_db_connection()
    cur = conn.cursor()
    try:
        cur.execute(
            """
            INSERT INTO project_calculation_requests (
                telegram_id,
                chat_id,
                telegram_username,
                telegram_full_name,
                source,
                client_name,
                contact_phone,
                status
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING id
            """,
            (
                telegram_id,
                chat_id,
                telegram_username,
                telegram_full_name,
                source,
                client_name,
                contact_phone,
                status,
            ),
        )
        request_id = cur.fetchone()[0]
        conn.commit()
        return request_id
    finally:
        cur.close()
        conn.close()


def mark_other_active_as_abandoned(telegram_id: int, chat_id: int, keep_request_id: int) -> None:
    conn = get_db_connection()
    cur = conn.cursor()
    try:
        cur.execute(
            """
            UPDATE project_calculation_requests
                        SET status = %s,
                updated_at = NOW()
            WHERE telegram_id = %s
              AND chat_id = %s
              AND id <> %s
                            AND status = ANY(%s)
            """,
                        (STATUS_ABANDONED, telegram_id, chat_id, keep_request_id, list(ACTIVE_STATUSES)),
        )
        conn.commit()
    finally:
        cur.close()
        conn.close()


def get_request_by_id(request_id: int) -> Optional[dict[str, Any]]:
    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    try:
        cur.execute(
            """
            SELECT *
            FROM project_calculation_requests
            WHERE id = %s
            LIMIT 1
            """,
            (request_id,),
        )
        return cur.fetchone()
    finally:
        cur.close()
        conn.close()


def update_name(request_id: int, name: str) -> None:
    conn = get_db_connection()
    cur = conn.cursor()
    try:
        cur.execute(
            """
            UPDATE project_calculation_requests
            SET client_name = %s,
                updated_at = NOW(),
                status = %s
            WHERE id = %s
            """,
            (name, STATUS_WAITING_PROJECT, request_id),
        )
        conn.commit()
    finally:
        cur.close()
        conn.close()


def append_project_payload(request_id: int, payload: dict[str, Any], local_file_path: str = "") -> dict[str, Any]:
    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    try:
        cur.execute(
            """
            SELECT
                all_project_payloads,
                local_file_paths,
                first_project_payload
            FROM project_calculation_requests
            WHERE id = %s
            FOR UPDATE
            """,
            (request_id,),
        )
        row = cur.fetchone()
        if not row:
            conn.rollback()
            return {}

        all_payloads = row.get("all_project_payloads") or []
        all_paths = row.get("local_file_paths") or []

        all_payloads.append(payload)
        if local_file_path:
            all_paths.append(local_file_path)

        cur.execute(
            """
            UPDATE project_calculation_requests
            SET first_project_payload = COALESCE(first_project_payload, %s::jsonb),
                all_project_payloads = %s::jsonb,
                local_file_paths = %s::jsonb,
                project_sent_at = COALESCE(project_sent_at, NOW()),
                updated_at = NOW()
            WHERE id = %s
            RETURNING *
            """,
            (
                json.dumps(payload, ensure_ascii=False),
                json.dumps(all_payloads, ensure_ascii=False),
                json.dumps(all_paths, ensure_ascii=False),
                request_id,
            ),
        )
        updated = cur.fetchone()
        conn.commit()
        return dict(updated) if updated else {}
    finally:
        cur.close()
        conn.close()


def set_files_dir(request_id: int, files_dir: str) -> None:
    conn = get_db_connection()
    cur = conn.cursor()
    try:
        cur.execute(
            """
            UPDATE project_calculation_requests
            SET files_dir = %s,
                updated_at = NOW()
            WHERE id = %s
            """,
            (files_dir, request_id),
        )
        conn.commit()
    finally:
        cur.close()
        conn.close()


def set_archive_path(request_id: int, archive_path: str) -> None:
    conn = get_db_connection()
    cur = conn.cursor()
    try:
        cur.execute(
            """
            UPDATE project_calculation_requests
            SET archive_file_path = %s,
                updated_at = NOW()
            WHERE id = %s
            """,
            (archive_path, request_id),
        )
        conn.commit()
    finally:
        cur.close()
        conn.close()


def get_last_completed_profile(telegram_id: int) -> Optional[dict[str, Any]]:
    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    try:
        cur.execute(
            """
            SELECT
                client_name,
                contact_phone,
                started_at,
                completed_at
            FROM project_calculation_requests
            WHERE telegram_id = %s
              AND status = %s
              AND COALESCE(client_name, '') <> ''
              AND COALESCE(contact_phone, '') <> ''
            ORDER BY completed_at DESC NULLS LAST, id DESC
            LIMIT 1
            """,
            (telegram_id, STATUS_COMPLETED),
        )
        return cur.fetchone()
    finally:
        cur.close()
        conn.close()


def set_waiting_phone(request_id: int) -> None:
    conn = get_db_connection()
    cur = conn.cursor()
    try:
        cur.execute(
            """
            UPDATE project_calculation_requests
            SET status = %s,
                updated_at = NOW()
            WHERE id = %s
            """,
            (STATUS_WAITING_PHONE, request_id),
        )
        conn.commit()
    finally:
        cur.close()
        conn.close()


def cancel_request(request_id: int) -> None:
    conn = get_db_connection()
    cur = conn.cursor()
    try:
        cur.execute(
            """
            UPDATE project_calculation_requests
            SET status = %s,
                updated_at = NOW()
            WHERE id = %s
              AND status = ANY(%s)
            """,
            (STATUS_CANCELED, request_id, list(ACTIVE_STATUSES)),
        )
        conn.commit()
    finally:
        cur.close()
        conn.close()


def complete_request(request_id: int, phone: str) -> None:
    conn = get_db_connection()
    cur = conn.cursor()
    try:
        cur.execute(
            """
            UPDATE project_calculation_requests
            SET contact_phone = %s,
                status = %s,
                completed_at = NOW(),
                updated_at = NOW()
            WHERE id = %s
            """,
            (phone, STATUS_COMPLETED, request_id),
        )
        conn.commit()
    finally:
        cur.close()
        conn.close()


def list_recent_requests(telegram_id: int, limit: int = 10) -> list[dict[str, Any]]:
    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    try:
        cur.execute(
            """
            SELECT
                id,
                started_at,
                completed_at,
                status,
                client_name,
                contact_phone,
                project_sent_at,
                archive_file_path,
                COALESCE(jsonb_array_length(all_project_payloads), 0) AS payload_count
            FROM project_calculation_requests
            WHERE telegram_id = %s
            ORDER BY id DESC
            LIMIT %s
            """,
            (telegram_id, limit),
        )
        return [dict(row) for row in cur.fetchall()]
    finally:
        cur.close()
        conn.close()
