from __future__ import annotations

import threading

from app.modules.assemblers.db.connection import get_db_connection
from app.modules.assemblers.db.tables import ACTIVITY_JOURNAL_TABLE


_ACTIVITY_LOG_SCHEMA_LOCK = threading.Lock()
_ACTIVITY_LOG_SCHEMA_READY = False


def ensure_activity_log_schema() -> None:
    global _ACTIVITY_LOG_SCHEMA_READY

    if _ACTIVITY_LOG_SCHEMA_READY:
        return

    with _ACTIVITY_LOG_SCHEMA_LOCK:
        if _ACTIVITY_LOG_SCHEMA_READY:
            return

        with get_db_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    f"""
                    CREATE TABLE IF NOT EXISTS {ACTIVITY_JOURNAL_TABLE} (
                        id BIGSERIAL PRIMARY KEY,
                        event_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                        actor_kind TEXT NOT NULL DEFAULT 'system',
                        actor_id BIGINT,
                        actor_name TEXT NOT NULL DEFAULT '',
                        actor_role TEXT NOT NULL DEFAULT '',
                        action_key TEXT NOT NULL DEFAULT '',
                        action_label TEXT NOT NULL DEFAULT '',
                        entity_type TEXT NOT NULL DEFAULT '',
                        entity_id TEXT NOT NULL DEFAULT '',
                        order_number TEXT NOT NULL DEFAULT '',
                        subdivision TEXT NOT NULL DEFAULT '',
                        source_table TEXT NOT NULL DEFAULT '',
                        source_op TEXT NOT NULL DEFAULT '',
                        status_code INTEGER NOT NULL DEFAULT 0,
                        description TEXT NOT NULL DEFAULT '',
                        details JSONB NOT NULL DEFAULT '{{}}'::jsonb
                    )
                    """
                )
                cursor.execute(
                    f"ALTER TABLE {ACTIVITY_JOURNAL_TABLE} ADD COLUMN IF NOT EXISTS status_code INTEGER NOT NULL DEFAULT 0"
                )
                cursor.execute(
                    f"CREATE INDEX IF NOT EXISTS idx_{ACTIVITY_JOURNAL_TABLE}_event_at ON {ACTIVITY_JOURNAL_TABLE}(event_at DESC, id DESC)"
                )
                cursor.execute(
                    f"CREATE INDEX IF NOT EXISTS idx_{ACTIVITY_JOURNAL_TABLE}_action_key ON {ACTIVITY_JOURNAL_TABLE}(action_key, event_at DESC)"
                )
                cursor.execute(
                    f"CREATE INDEX IF NOT EXISTS idx_{ACTIVITY_JOURNAL_TABLE}_actor_name ON {ACTIVITY_JOURNAL_TABLE}(actor_name, event_at DESC)"
                )
                cursor.execute(
                    f"CREATE INDEX IF NOT EXISTS idx_{ACTIVITY_JOURNAL_TABLE}_order_number ON {ACTIVITY_JOURNAL_TABLE}(order_number, event_at DESC)"
                )
                cursor.execute(
                    f"CREATE INDEX IF NOT EXISTS idx_{ACTIVITY_JOURNAL_TABLE}_subdivision ON {ACTIVITY_JOURNAL_TABLE}(subdivision, event_at DESC)"
                )

        _ACTIVITY_LOG_SCHEMA_READY = True