from __future__ import annotations

import threading

from app.modules.assemblers.db.connection import get_db_connection

from .constants import (
    DATA_DESIGNER_TABLE,
    MAIN_TABLE_NAME,
    DETAILS_TABLE_NAME,
    DETAIL_RECALC_QUEUE_TABLE,
)

_SCHEMA_LOCK = threading.Lock()
_SCHEMA_READY = False


def ensure_schema() -> None:
    global _SCHEMA_READY

    if _SCHEMA_READY:
        return

    with _SCHEMA_LOCK:
        if _SCHEMA_READY:
            return

        with get_db_connection() as conn:
            with conn.cursor() as cursor:
                # Serialize DDL across processes to avoid deadlocks on ALTER TABLE.
                cursor.execute("SELECT pg_advisory_xact_lock(%s)", (764321987654321,))
                cursor.execute(
                    f"""
                    CREATE TABLE IF NOT EXISTS {MAIN_TABLE_NAME} (
                        id BIGSERIAL PRIMARY KEY,
                        order_number TEXT NOT NULL UNIQUE,
                        customer TEXT NOT NULL DEFAULT '',
                        order_type TEXT NOT NULL DEFAULT '',
                        signed_at DATE,
                        contract_due_at DATE,
                        manager_name TEXT NOT NULL DEFAULT '',
                        constructor_name TEXT NOT NULL DEFAULT '',
                        status TEXT NOT NULL DEFAULT '',
                        note TEXT NOT NULL DEFAULT '',
                        note_color TEXT NOT NULL DEFAULT '',
                        note_text_color TEXT NOT NULL DEFAULT '',
                        planned_install_at DATE,
                        install_completed_at DATE,
                        address TEXT NOT NULL DEFAULT '',
                        address_note TEXT NOT NULL DEFAULT '',
                        materials TEXT NOT NULL DEFAULT '',
                        assembly_workers TEXT NOT NULL DEFAULT '',
                        install_workers TEXT NOT NULL DEFAULT '',
                        assembly_status TEXT NOT NULL DEFAULT '',
                        install_status TEXT NOT NULL DEFAULT '',
                        assembler_pause_at TIMESTAMPTZ,
                        closed_at TIMESTAMPTZ,
                        closed_by_name TEXT NOT NULL DEFAULT '',
                        closed_by_role TEXT NOT NULL DEFAULT '',
                        closed_by_telegram_id BIGINT,
                        recorded_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                        updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                        total_planned_hours NUMERIC(14, 2) NOT NULL DEFAULT 0
                    )
                    """
                )
                cursor.execute(f"ALTER TABLE {MAIN_TABLE_NAME} ADD COLUMN IF NOT EXISTS closed_at TIMESTAMPTZ")
                cursor.execute(f"ALTER TABLE {MAIN_TABLE_NAME} ADD COLUMN IF NOT EXISTS closed_by_name TEXT NOT NULL DEFAULT ''")
                cursor.execute(f"ALTER TABLE {MAIN_TABLE_NAME} ADD COLUMN IF NOT EXISTS closed_by_role TEXT NOT NULL DEFAULT ''")
                cursor.execute(f"ALTER TABLE {MAIN_TABLE_NAME} ADD COLUMN IF NOT EXISTS closed_by_telegram_id BIGINT")
                cursor.execute(f"ALTER TABLE {MAIN_TABLE_NAME} ADD COLUMN IF NOT EXISTS total_planned_hours NUMERIC(14, 2) NOT NULL DEFAULT 0")
                cursor.execute(f"ALTER TABLE {MAIN_TABLE_NAME} ADD COLUMN IF NOT EXISTS note_color TEXT NOT NULL DEFAULT ''")
                cursor.execute(f"ALTER TABLE {MAIN_TABLE_NAME} ADD COLUMN IF NOT EXISTS note_text_color TEXT NOT NULL DEFAULT ''")

                cursor.execute(
                    f"""
                    CREATE TABLE IF NOT EXISTS {DETAILS_TABLE_NAME} (
                        id BIGSERIAL PRIMARY KEY,
                        order_number TEXT NOT NULL REFERENCES {MAIN_TABLE_NAME}(order_number) ON DELETE CASCADE,
                        part_number TEXT NOT NULL DEFAULT '',
                        customer TEXT NOT NULL DEFAULT '',
                        product_name TEXT NOT NULL DEFAULT '',
                        planned_assembly_due_at DATE,
                        assembly_worker TEXT NOT NULL DEFAULT '',
                        assembly_started_at TIMESTAMPTZ,
                        assembly_completed_at TIMESTAMPTZ,
                        assembly_days_count INTEGER NOT NULL DEFAULT 0,
                        assembly_hours TEXT NOT NULL DEFAULT '',
                        assembly_status TEXT NOT NULL DEFAULT '',
                        planned_install_due_at DATE,
                        install_worker TEXT NOT NULL DEFAULT '',
                        install_started_at TIMESTAMPTZ,
                        install_completed_at TIMESTAMPTZ,
                        install_days_count INTEGER NOT NULL DEFAULT 0,
                        install_hours TEXT NOT NULL DEFAULT '',
                        install_status TEXT NOT NULL DEFAULT '',
                        item_type TEXT NOT NULL DEFAULT '',
                        constructor_status TEXT NOT NULL DEFAULT '',
                        production_launches INTEGER NOT NULL DEFAULT 0,
                        production_completed INTEGER NOT NULL DEFAULT 0,
                        metal TEXT NOT NULL DEFAULT '',
                        glass_eta TEXT NOT NULL DEFAULT '',
                        glass_delivered TEXT NOT NULL DEFAULT '',
                        planned_hours TEXT NOT NULL DEFAULT '',
                        item_value NUMERIC(14, 2) NOT NULL DEFAULT 0,
                        requires_assembly BOOLEAN NOT NULL DEFAULT TRUE,
                        requires_install BOOLEAN NOT NULL DEFAULT TRUE,
                        total_hours TEXT NOT NULL DEFAULT '',
                        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                        updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                    )
                    """
                )
                cursor.execute(f"ALTER TABLE {DETAILS_TABLE_NAME} ADD COLUMN IF NOT EXISTS assembly_days_count INTEGER NOT NULL DEFAULT 0")
                cursor.execute(f"ALTER TABLE {DETAILS_TABLE_NAME} ADD COLUMN IF NOT EXISTS install_days_count INTEGER NOT NULL DEFAULT 0")
                cursor.execute(f"ALTER TABLE {MAIN_TABLE_NAME} ADD COLUMN IF NOT EXISTS vat BOOLEAN NOT NULL DEFAULT FALSE")
                cursor.execute(f"ALTER TABLE {DETAILS_TABLE_NAME} ADD COLUMN IF NOT EXISTS item_percent NUMERIC(8,2) NOT NULL DEFAULT 0")
                cursor.execute(f"ALTER TABLE {DETAILS_TABLE_NAME} ADD COLUMN IF NOT EXISTS requires_assembly BOOLEAN NOT NULL DEFAULT TRUE")
                cursor.execute(f"ALTER TABLE {DETAILS_TABLE_NAME} ADD COLUMN IF NOT EXISTS requires_install BOOLEAN NOT NULL DEFAULT TRUE")

                cursor.execute(
                    """
                    CREATE TABLE IF NOT EXISTS assemblers_column_preferences (
                        id BIGSERIAL PRIMARY KEY,
                        telegram_id BIGINT NOT NULL,
                        page_key TEXT NOT NULL,
                        column_order TEXT NOT NULL,
                        updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                        UNIQUE(telegram_id, page_key)
                    )
                    """
                )
                cursor.execute(
                    f"CREATE INDEX IF NOT EXISTS idx_{MAIN_TABLE_NAME}_recorded_at ON {MAIN_TABLE_NAME}(recorded_at DESC, order_number DESC)"
                )
                cursor.execute(
                    f"CREATE INDEX IF NOT EXISTS idx_{DETAILS_TABLE_NAME}_order_number ON {DETAILS_TABLE_NAME}(order_number, id)"
                )
                cursor.execute(
                    f"CREATE INDEX IF NOT EXISTS idx_{MAIN_TABLE_NAME}_status_closed_at ON {MAIN_TABLE_NAME}(status, closed_at DESC, order_number DESC)"
                )

                cursor.execute(
                    """
                    CREATE OR REPLACE FUNCTION assemblers_stage_duration_text(total_minutes INTEGER)
                    RETURNS TEXT AS $$
                    DECLARE
                        hours_part INTEGER;
                        minutes_part INTEGER;
                    BEGIN
                        IF total_minutes IS NULL OR total_minutes <= 0 THEN
                            RETURN '';
                        END IF;

                        hours_part := total_minutes / 60;
                        minutes_part := total_minutes % 60;

                        IF hours_part > 0 AND minutes_part > 0 THEN
                            RETURN hours_part::TEXT || ' год ' || minutes_part::TEXT || ' хв';
                        ELSIF hours_part > 0 THEN
                            RETURN hours_part::TEXT || ' год';
                        END IF;

                        RETURN minutes_part::TEXT || ' хв';
                    END;
                    $$ LANGUAGE plpgsql IMMUTABLE;
                    """
                )

                cursor.execute(
                    f"""
                    CREATE OR REPLACE FUNCTION assemblers_details_before_write()
                    RETURNS TRIGGER AS $$
                    DECLARE
                        assembly_minutes INTEGER;
                        install_minutes INTEGER;
                    BEGIN
                        IF NEW.assembly_started_at IS NOT NULL
                           AND NEW.assembly_completed_at IS NOT NULL
                           AND NEW.assembly_completed_at >= NEW.assembly_started_at THEN
                            NEW.assembly_days_count := GREATEST((NEW.assembly_completed_at::DATE - NEW.assembly_started_at::DATE) + 1, 1);
                            assembly_minutes := FLOOR(EXTRACT(EPOCH FROM (NEW.assembly_completed_at - NEW.assembly_started_at)) / 60);
                            NEW.assembly_hours := assemblers_stage_duration_text(assembly_minutes);
                        ELSIF COALESCE(NEW.assembly_days_count, 0) <= 0 THEN
                            NEW.assembly_days_count := 0;
                            NEW.assembly_hours := '';
                        END IF;

                        IF NEW.install_started_at IS NOT NULL
                           AND NEW.install_completed_at IS NOT NULL
                           AND NEW.install_completed_at >= NEW.install_started_at THEN
                            NEW.install_days_count := GREATEST((NEW.install_completed_at::DATE - NEW.install_started_at::DATE) + 1, 1);
                            install_minutes := FLOOR(EXTRACT(EPOCH FROM (NEW.install_completed_at - NEW.install_started_at)) / 60);
                            NEW.install_hours := assemblers_stage_duration_text(install_minutes);
                        ELSIF COALESCE(NEW.install_days_count, 0) <= 0 THEN
                            NEW.install_days_count := 0;
                            NEW.install_hours := '';
                        END IF;

                        NEW.updated_at := NOW();
                        RETURN NEW;
                    END;
                    $$ LANGUAGE plpgsql;
                    """
                )
                cursor.execute(
                    f"DROP TRIGGER IF EXISTS trg_{DETAILS_TABLE_NAME}_before_write ON {DETAILS_TABLE_NAME}"
                )
                cursor.execute(
                    f"""
                    CREATE TRIGGER trg_{DETAILS_TABLE_NAME}_before_write
                    BEFORE INSERT OR UPDATE ON {DETAILS_TABLE_NAME}
                    FOR EACH ROW
                    EXECUTE FUNCTION assemblers_details_before_write();
                    """
                )

                cursor.execute(
                    f"""
                    CREATE OR REPLACE FUNCTION assemblers_recalculate_order_total_planned_hours(target_order_number TEXT)
                    RETURNS VOID AS $$
                    BEGIN
                        UPDATE {MAIN_TABLE_NAME} mo
                        SET
                            total_planned_hours = COALESCE((
                                SELECT SUM(
                                    CASE
                                        WHEN REPLACE(TRIM(COALESCE(dr.planned_hours, '')), ',', '.') ~ '^-?[0-9]+(\\.[0-9]+)?$'
                                            THEN REPLACE(TRIM(COALESCE(dr.planned_hours, '')), ',', '.')::NUMERIC
                                        ELSE 0::NUMERIC
                                    END
                                )
                                FROM {DETAILS_TABLE_NAME} dr
                                WHERE TRIM(COALESCE(dr.order_number, '')) = TRIM(COALESCE(target_order_number, ''))
                            ), 0),
                            updated_at = NOW()
                        WHERE TRIM(COALESCE(mo.order_number, '')) = TRIM(COALESCE(target_order_number, ''));
                    END;
                    $$ LANGUAGE plpgsql;
                    """
                )
                cursor.execute(
                    """
                    CREATE OR REPLACE FUNCTION assemblers_details_after_write_recalc_main_order()
                    RETURNS TRIGGER AS $$
                    BEGIN
                        IF TG_OP = 'DELETE' THEN
                            PERFORM assemblers_recalculate_order_total_planned_hours(OLD.order_number);
                        ELSE
                            PERFORM assemblers_recalculate_order_total_planned_hours(NEW.order_number);
                            IF TG_OP = 'UPDATE' AND TRIM(COALESCE(OLD.order_number, '')) <> TRIM(COALESCE(NEW.order_number, '')) THEN
                                PERFORM assemblers_recalculate_order_total_planned_hours(OLD.order_number);
                            END IF;
                        END IF;

                        RETURN COALESCE(NEW, OLD);
                    END;
                    $$ LANGUAGE plpgsql;
                    """
                )
                cursor.execute(
                    f"DROP TRIGGER IF EXISTS trg_{DETAILS_TABLE_NAME}_after_write_recalc_main ON {DETAILS_TABLE_NAME}"
                )
                cursor.execute(
                    f"""
                    CREATE TRIGGER trg_{DETAILS_TABLE_NAME}_after_write_recalc_main
                    AFTER INSERT OR UPDATE OR DELETE ON {DETAILS_TABLE_NAME}
                    FOR EACH ROW
                    EXECUTE FUNCTION assemblers_details_after_write_recalc_main_order();
                    """
                )

                cursor.execute(
                    f"""
                    CREATE TABLE IF NOT EXISTS {DETAIL_RECALC_QUEUE_TABLE} (
                        order_number TEXT PRIMARY KEY,
                        requested_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                        source TEXT NOT NULL DEFAULT ''
                    )
                    """
                )
                cursor.execute(
                    f"CREATE INDEX IF NOT EXISTS idx_{DETAIL_RECALC_QUEUE_TABLE}_requested_at ON {DETAIL_RECALC_QUEUE_TABLE}(requested_at)"
                )

                cursor.execute(
                    f"""
                    CREATE OR REPLACE FUNCTION assemblers_enqueue_detail_recalc(target_order_number TEXT, source_label TEXT DEFAULT '')
                    RETURNS VOID AS $$
                    DECLARE
                        normalized_order_number TEXT := TRIM(COALESCE(target_order_number, ''));
                    BEGIN
                        IF normalized_order_number = '' THEN
                            RETURN;
                        END IF;

                        INSERT INTO {DETAIL_RECALC_QUEUE_TABLE} (order_number, requested_at, source)
                        VALUES (normalized_order_number, NOW(), LEFT(TRIM(COALESCE(source_label, '')), 120))
                        ON CONFLICT (order_number)
                        DO UPDATE SET
                            requested_at = EXCLUDED.requested_at,
                            source = EXCLUDED.source;
                    END;
                    $$ LANGUAGE plpgsql;
                    """
                )
                cursor.execute(
                    """
                    CREATE OR REPLACE FUNCTION assemblers_details_after_write_enqueue_recalc()
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
                    f"DROP TRIGGER IF EXISTS trg_{DETAILS_TABLE_NAME}_after_write_enqueue_recalc ON {DETAILS_TABLE_NAME}"
                )
                cursor.execute(
                    f"""
                    CREATE TRIGGER trg_{DETAILS_TABLE_NAME}_after_write_enqueue_recalc
                    AFTER INSERT OR UPDATE OR DELETE ON {DETAILS_TABLE_NAME}
                    FOR EACH ROW
                    EXECUTE FUNCTION assemblers_details_after_write_enqueue_recalc();
                    """
                )

                cursor.execute("SELECT to_regclass(%s)", (DATA_DESIGNER_TABLE,))
                designer_table_exists = cursor.fetchone()[0] is not None
                if designer_table_exists:
                    cursor.execute(
                        f"""
                        CREATE OR REPLACE FUNCTION assemblers_sync_main_order_from_designer()
                        RETURNS TRIGGER AS $$
                        DECLARE
                            target_order_number TEXT;
                        BEGIN
                            target_order_number := TRIM(COALESCE(
                                CASE WHEN TG_OP = 'DELETE' THEN OLD.column_1 ELSE NEW.column_1 END,
                                ''
                            ));

                            IF target_order_number = '' THEN
                                RETURN COALESCE(NEW, OLD);
                            END IF;

                            UPDATE {MAIN_TABLE_NAME} mo
                            SET
                                customer = COALESCE(src.customer, mo.customer),
                                order_type = COALESCE(src.order_type, mo.order_type),
                                manager_name = COALESCE(src.manager_name, mo.manager_name),
                                constructor_name = COALESCE(src.constructor_name, mo.constructor_name),
                                signed_at = COALESCE(src.signed_at, mo.signed_at),
                                contract_due_at = COALESCE(src.contract_due_at, mo.contract_due_at),
                                planned_install_at = COALESCE(src.contract_due_at, mo.planned_install_at),
                                updated_at = NOW()
                            FROM (
                                SELECT
                                    NULLIF(TRIM(COALESCE(column_3, '')), '') AS customer,
                                    NULLIF(TRIM(COALESCE(column_9, '')), '') AS order_type,
                                    NULLIF(TRIM(COALESCE(column_7, '')), '') AS manager_name,
                                    NULLIF(TRIM(COALESCE(column_11, '')), '') AS constructor_name,
                                    CASE
                                        WHEN TRIM(COALESCE(column_30, '')) ~ '^\\d{2}\\.\\d{2}\\.\\d{4}$'
                                            THEN TO_DATE(TRIM(column_30), 'DD.MM.YYYY')
                                        WHEN TRIM(COALESCE(column_30, '')) ~ '^\\d{2}\\.\\d{2}\\.\\d{2}$'
                                            THEN TO_DATE(TRIM(column_30), 'DD.MM.YY')
                                        WHEN TRIM(COALESCE(column_30, '')) ~ '^\\d{4}-\\d{2}-\\d{2}$'
                                            THEN TO_DATE(TRIM(column_30), 'YYYY-MM-DD')
                                        ELSE NULL
                                    END AS signed_at,
                                    CASE
                                        WHEN COALESCE(NULLIF(TRIM(COALESCE(column_32, '')), ''), NULLIF(TRIM(COALESCE(column_31, '')), '')) ~ '^\\d{2}\\.\\d{2}\\.\\d{4}$'
                                            THEN TO_DATE(COALESCE(NULLIF(TRIM(column_32), ''), NULLIF(TRIM(column_31), '')), 'DD.MM.YYYY')
                                        WHEN COALESCE(NULLIF(TRIM(COALESCE(column_32, '')), ''), NULLIF(TRIM(COALESCE(column_31, '')), '')) ~ '^\\d{2}\\.\\d{2}\\.\\d{2}$'
                                            THEN TO_DATE(COALESCE(NULLIF(TRIM(column_32), ''), NULLIF(TRIM(column_31), '')), 'DD.MM.YY')
                                        WHEN COALESCE(NULLIF(TRIM(COALESCE(column_32, '')), ''), NULLIF(TRIM(COALESCE(column_31, '')), '')) ~ '^\\d{4}-\\d{2}-\\d{2}$'
                                            THEN TO_DATE(COALESCE(NULLIF(TRIM(column_32), ''), NULLIF(TRIM(column_31), '')), 'YYYY-MM-DD')
                                        ELSE NULL
                                    END AS contract_due_at
                                FROM {DATA_DESIGNER_TABLE}
                                WHERE TRIM(COALESCE(column_1, '')) = target_order_number
                                ORDER BY id DESC
                                LIMIT 1
                            ) src
                            WHERE TRIM(COALESCE(mo.order_number, '')) = target_order_number;

                            RETURN COALESCE(NEW, OLD);
                        END;
                        $$ LANGUAGE plpgsql;
                        """
                    )
                    cursor.execute(
                        f"DROP TRIGGER IF EXISTS trg_{DATA_DESIGNER_TABLE}_after_write_sync_main ON {DATA_DESIGNER_TABLE}"
                    )
                    cursor.execute(
                        f"""
                        CREATE TRIGGER trg_{DATA_DESIGNER_TABLE}_after_write_sync_main
                        AFTER INSERT OR UPDATE OR DELETE ON {DATA_DESIGNER_TABLE}
                        FOR EACH ROW
                        EXECUTE FUNCTION assemblers_sync_main_order_from_designer();
                        """
                    )
            conn.commit()

        _SCHEMA_READY = True
