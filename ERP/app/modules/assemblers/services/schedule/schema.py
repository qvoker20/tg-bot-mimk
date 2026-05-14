import threading

from app.modules.assemblers.db.connection import get_db_connection
from app.modules.assemblers.services.registry import ensure_schema

from .constants import (
    SCHEDULE_TASKS_TABLE,
    TASK_STATUS_COMPLETED,
    TASK_STATUS_IN_PROGRESS,
    TASK_STATUS_NO_EXECUTION,
    TASK_STATUS_PAUSED,
    TASK_STATUS_QUEUED,
)

_SCHEDULE_SCHEMA_LOCK = threading.Lock()
_SCHEDULE_SCHEMA_READY = False
_SCHEDULE_AUTO_CLOSE_RUNS_TABLE = "assemblers_schedule_auto_close_runs"


def ensure_schedule_schema() -> None:
    """Ensure the schedule table and trigger-based lifecycle metadata exist."""
    global _SCHEDULE_SCHEMA_READY

    if _SCHEDULE_SCHEMA_READY:
        return

    ensure_schema()

    with _SCHEDULE_SCHEMA_LOCK:
        if _SCHEDULE_SCHEMA_READY:
            return

        with get_db_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                f"""
                CREATE TABLE IF NOT EXISTS {SCHEDULE_TASKS_TABLE} (
                    id BIGSERIAL PRIMARY KEY,
                    source_user_id BIGINT NOT NULL,
                    subdivision TEXT NOT NULL DEFAULT '',
                    scheduled_for DATE NOT NULL,
                    task_type TEXT NOT NULL DEFAULT '',
                    status TEXT NOT NULL DEFAULT '',
                    order_number TEXT NOT NULL DEFAULT '',
                    customer TEXT NOT NULL DEFAULT '',
                    part_number TEXT NOT NULL DEFAULT '',
                    product_name TEXT NOT NULL DEFAULT '',
                    constructor_status TEXT NOT NULL DEFAULT '',
                    description TEXT NOT NULL DEFAULT '',
                    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                )
                """
                )
                cursor.execute(
                f"ALTER TABLE {SCHEDULE_TASKS_TABLE} ADD COLUMN IF NOT EXISTS assembler_name TEXT NOT NULL DEFAULT ''"
                )
                cursor.execute(
                f"ALTER TABLE {SCHEDULE_TASKS_TABLE} ADD COLUMN IF NOT EXISTS customer TEXT NOT NULL DEFAULT ''"
                )
                cursor.execute(
                f"ALTER TABLE {SCHEDULE_TASKS_TABLE} ADD COLUMN IF NOT EXISTS started_at TIMESTAMPTZ"
                )
                cursor.execute(
                f"ALTER TABLE {SCHEDULE_TASKS_TABLE} ADD COLUMN IF NOT EXISTS paused_at TIMESTAMPTZ"
                )
                cursor.execute(
                f"ALTER TABLE {SCHEDULE_TASKS_TABLE} ADD COLUMN IF NOT EXISTS completed_at TIMESTAMPTZ"
                )
                cursor.execute(
                f"ALTER TABLE {SCHEDULE_TASKS_TABLE} ADD COLUMN IF NOT EXISTS pause_reason TEXT NOT NULL DEFAULT ''"
                )
                cursor.execute(
                f"ALTER TABLE {SCHEDULE_TASKS_TABLE} ADD COLUMN IF NOT EXISTS started_location_label TEXT NOT NULL DEFAULT ''"
                )
                cursor.execute(
                f"ALTER TABLE {SCHEDULE_TASKS_TABLE} ADD COLUMN IF NOT EXISTS started_latitude DOUBLE PRECISION"
                )
                cursor.execute(
                f"ALTER TABLE {SCHEDULE_TASKS_TABLE} ADD COLUMN IF NOT EXISTS started_longitude DOUBLE PRECISION"
                )
                cursor.execute(
                f"ALTER TABLE {SCHEDULE_TASKS_TABLE} ADD COLUMN IF NOT EXISTS started_accuracy DOUBLE PRECISION"
                )
                cursor.execute(
                f"ALTER TABLE {SCHEDULE_TASKS_TABLE} ADD COLUMN IF NOT EXISTS completed_location_label TEXT NOT NULL DEFAULT ''"
                )
                cursor.execute(
                f"ALTER TABLE {SCHEDULE_TASKS_TABLE} ADD COLUMN IF NOT EXISTS completed_latitude DOUBLE PRECISION"
                )
                cursor.execute(
                f"ALTER TABLE {SCHEDULE_TASKS_TABLE} ADD COLUMN IF NOT EXISTS completed_longitude DOUBLE PRECISION"
                )
                cursor.execute(
                f"ALTER TABLE {SCHEDULE_TASKS_TABLE} ADD COLUMN IF NOT EXISTS completed_accuracy DOUBLE PRECISION"
                )
                cursor.execute(
                f"ALTER TABLE {SCHEDULE_TASKS_TABLE} ADD COLUMN IF NOT EXISTS auto_closed_at TIMESTAMPTZ"
                )
                cursor.execute(
                f"ALTER TABLE {SCHEDULE_TASKS_TABLE} ADD COLUMN IF NOT EXISTS auto_close_note TEXT NOT NULL DEFAULT ''"
                )

                cursor.execute(
                f"""
                CREATE TABLE IF NOT EXISTS {_SCHEDULE_AUTO_CLOSE_RUNS_TABLE} (
                    run_date DATE PRIMARY KEY,
                    completed_count INTEGER NOT NULL DEFAULT 0,
                    no_execution_count INTEGER NOT NULL DEFAULT 0,
                    processed_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                )
                """
                )

                # Trigger updates lifecycle timestamps and keeps updated_at consistent on every write.
                cursor.execute(
                f"""
                CREATE OR REPLACE FUNCTION assemblers_schedule_before_write()
                RETURNS TRIGGER AS $$
                BEGIN
                    IF TG_OP = 'INSERT' THEN
                        NEW.created_at := COALESCE(NEW.created_at, NOW());
                    END IF;

                    IF TG_OP = 'UPDATE' THEN
                        IF NEW.status = '{TASK_STATUS_IN_PROGRESS}' AND (OLD.status IS DISTINCT FROM NEW.status) AND NEW.started_at IS NULL THEN
                            NEW.started_at := NOW();
                        END IF;

                        IF NEW.status = '{TASK_STATUS_PAUSED}' AND (OLD.status IS DISTINCT FROM NEW.status) AND NEW.paused_at IS NULL THEN
                            NEW.paused_at := NOW();
                        END IF;

                        IF NEW.status = '{TASK_STATUS_COMPLETED}' AND (OLD.status IS DISTINCT FROM NEW.status) AND NEW.completed_at IS NULL THEN
                            NEW.completed_at := NOW();
                        END IF;
                    END IF;

                    NEW.updated_at := NOW();
                    RETURN NEW;
                END;
                $$ LANGUAGE plpgsql;
                """
                )
                cursor.execute(
                f"DROP TRIGGER IF EXISTS trg_{SCHEDULE_TASKS_TABLE}_before_write ON {SCHEDULE_TASKS_TABLE}"
                )
                cursor.execute(
                    f"""
                    CREATE TRIGGER trg_{SCHEDULE_TASKS_TABLE}_before_write
                    BEFORE INSERT OR UPDATE ON {SCHEDULE_TASKS_TABLE}
                    FOR EACH ROW
                    EXECUTE FUNCTION assemblers_schedule_before_write();
                    """
                )

                cursor.execute(
                    """
                    CREATE OR REPLACE FUNCTION assemblers_schedule_after_write_enqueue_recalc()
                    RETURNS TRIGGER AS $$
                    BEGIN
                        IF TG_OP = 'DELETE' THEN
                            PERFORM assemblers_enqueue_detail_recalc(OLD.order_number, TG_TABLE_NAME || ':' || TG_OP);
                            RETURN OLD;
                        END IF;

                        PERFORM assemblers_enqueue_detail_recalc(NEW.order_number, TG_TABLE_NAME || ':' || TG_OP);
                        IF TG_OP = 'UPDATE' AND TRIM(COALESCE(OLD.order_number, '')) <> TRIM(COALESCE(NEW.order_number, '')) THEN
                            PERFORM assemblers_enqueue_detail_recalc(OLD.order_number, TG_TABLE_NAME || ':' || TG_OP || ':old');
                        END IF;

                        RETURN NEW;
                    END;
                    $$ LANGUAGE plpgsql;
                    """
                )
                cursor.execute(
                    f"DROP TRIGGER IF EXISTS trg_{SCHEDULE_TASKS_TABLE}_after_write_enqueue_recalc ON {SCHEDULE_TASKS_TABLE}"
                )
                cursor.execute(
                    f"""
                    CREATE TRIGGER trg_{SCHEDULE_TASKS_TABLE}_after_write_enqueue_recalc
                    AFTER INSERT OR UPDATE OR DELETE ON {SCHEDULE_TASKS_TABLE}
                    FOR EACH ROW
                    EXECUTE FUNCTION assemblers_schedule_after_write_enqueue_recalc();
                    """
                )

                cursor.execute(
                    f"CREATE INDEX IF NOT EXISTS idx_{SCHEDULE_TASKS_TABLE}_subdivision_date ON {SCHEDULE_TASKS_TABLE}(subdivision, scheduled_for, source_user_id)"
                )
                cursor.execute(
                    f"CREATE INDEX IF NOT EXISTS idx_{SCHEDULE_TASKS_TABLE}_worker_date ON {SCHEDULE_TASKS_TABLE}(source_user_id, scheduled_for)"
                )
                cursor.execute(
                    f"CREATE INDEX IF NOT EXISTS idx_{SCHEDULE_TASKS_TABLE}_worker_status_date ON {SCHEDULE_TASKS_TABLE}(source_user_id, status, scheduled_for)"
                )
                cursor.execute(
                    f"CREATE INDEX IF NOT EXISTS idx_{SCHEDULE_TASKS_TABLE}_date_status ON {SCHEDULE_TASKS_TABLE}(scheduled_for, status)"
                )
                cursor.execute(
                f"""
                CREATE OR REPLACE FUNCTION assemblers_schedule_apply_daily_cutoff(
                    target_day DATE,
                    execution_time TIMESTAMPTZ DEFAULT NOW()
                )
                RETURNS TABLE (
                    run_date DATE,
                    completed_count INTEGER,
                    no_execution_count INTEGER,
                    processed BOOLEAN
                ) AS $$
                DECLARE
                    normalized_day DATE;
                    normalized_execution TIMESTAMPTZ := COALESCE(execution_time, NOW());
                    cutoff_at TIMESTAMPTZ;
                    updated_completed INTEGER := 0;
                    updated_no_execution INTEGER := 0;
                BEGIN
                    normalized_day := COALESCE(target_day, (normalized_execution AT TIME ZONE 'Europe/Kyiv')::DATE);
                    cutoff_at := (normalized_day::TIMESTAMP + TIME '18:00') AT TIME ZONE 'Europe/Kyiv';

                    IF normalized_execution < cutoff_at THEN
                        RETURN QUERY SELECT normalized_day, 0, 0, FALSE;
                        RETURN;
                    END IF;

                    IF EXISTS (
                        SELECT 1
                        FROM {_SCHEDULE_AUTO_CLOSE_RUNS_TABLE}
                        WHERE {_SCHEDULE_AUTO_CLOSE_RUNS_TABLE}.run_date = normalized_day
                    ) THEN
                        RETURN QUERY SELECT normalized_day, 0, 0, FALSE;
                        RETURN;
                    END IF;

                    UPDATE {SCHEDULE_TASKS_TABLE}
                    SET
                        status = '{TASK_STATUS_COMPLETED}',
                        completed_at = COALESCE(completed_at, normalized_execution),
                        auto_closed_at = normalized_execution,
                        auto_close_note = 'Автоматично завершено після 18:00',
                        updated_at = normalized_execution
                    WHERE scheduled_for = normalized_day
                      AND status = '{TASK_STATUS_IN_PROGRESS}';
                    GET DIAGNOSTICS updated_completed = ROW_COUNT;

                    UPDATE {SCHEDULE_TASKS_TABLE}
                    SET
                        status = '{TASK_STATUS_NO_EXECUTION}',
                        completed_at = COALESCE(completed_at, normalized_execution),
                        auto_closed_at = normalized_execution,
                        auto_close_note = 'Автоматично переведено у статус Без виконання після 18:00',
                        updated_at = normalized_execution
                    WHERE scheduled_for = normalized_day
                      AND status = '{TASK_STATUS_QUEUED}';
                    GET DIAGNOSTICS updated_no_execution = ROW_COUNT;

                    INSERT INTO {_SCHEDULE_AUTO_CLOSE_RUNS_TABLE} (
                        run_date,
                        completed_count,
                        no_execution_count,
                        processed_at
                    ) VALUES (
                        normalized_day,
                        updated_completed,
                        updated_no_execution,
                        normalized_execution
                    )
                    ON CONFLICT ON CONSTRAINT assemblers_schedule_auto_close_runs_pkey DO NOTHING;

                    RETURN QUERY SELECT normalized_day, updated_completed, updated_no_execution, TRUE;
                END;
                $$ LANGUAGE plpgsql;
                """
                )
                cursor.execute(
                """
                CREATE OR REPLACE FUNCTION assemblers_schedule_run_daily_cutoff_catchup(
                    reference_time TIMESTAMPTZ DEFAULT NOW(),
                    days_back INTEGER DEFAULT 31
                )
                RETURNS TABLE (
                    run_date DATE,
                    completed_count INTEGER,
                    no_execution_count INTEGER
                ) AS $$
                DECLARE
                    normalized_reference TIMESTAMPTZ := COALESCE(reference_time, NOW());
                    local_today DATE := (normalized_reference AT TIME ZONE 'Europe/Kyiv')::DATE;
                    oldest_pending DATE;
                    start_day DATE;
                    end_day DATE := local_today;
                    candidate_day DATE;
                BEGIN
                    SELECT MIN(scheduled_for)
                    INTO oldest_pending
                    FROM assemblers_schedule_tasks
                    WHERE status IN ('У черзі', 'В роботі')
                      AND scheduled_for <= local_today;

                    IF oldest_pending IS NULL THEN
                        RETURN;
                    END IF;

                    start_day := GREATEST(
                        oldest_pending,
                        local_today - GREATEST(COALESCE(days_back, 31), 1)
                    );

                    FOR candidate_day IN
                        SELECT gs::DATE
                        FROM generate_series(start_day::TIMESTAMP, end_day::TIMESTAMP, INTERVAL '1 day') AS gs
                    LOOP
                        PERFORM assemblers_schedule_apply_daily_cutoff(candidate_day, normalized_reference);
                    END LOOP;

                    RETURN QUERY
                    SELECT
                        r.run_date,
                        r.completed_count,
                        r.no_execution_count
                    FROM assemblers_schedule_auto_close_runs r
                    WHERE r.run_date BETWEEN start_day AND end_day
                      AND r.processed_at >= normalized_reference - INTERVAL '5 minutes'
                    ORDER BY r.run_date;
                END;
                $$ LANGUAGE plpgsql;
                """
                )
            conn.commit()

        _SCHEDULE_SCHEMA_READY = True


def run_schedule_daily_cutoff_catchup(*, days_back: int = 31) -> dict[str, int]:
    """Run 18:00 daily auto-close checks, including missed days after downtime."""
    ensure_schedule_schema()
    normalized_days_back = max(1, min(int(days_back or 31), 365))

    with get_db_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                """
                SELECT run_date, completed_count, no_execution_count
                FROM assemblers_schedule_run_daily_cutoff_catchup(NOW(), %s)
                """,
                (normalized_days_back,),
            )
            rows = cursor.fetchall()

    return {
        "processed_days": len(rows),
        "completed_count": sum(int(row[1] or 0) for row in rows),
        "no_execution_count": sum(int(row[2] or 0) for row in rows),
    }
