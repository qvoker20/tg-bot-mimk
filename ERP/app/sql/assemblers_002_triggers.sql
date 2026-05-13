-- ============================================================
-- Migration: assemblers_002_triggers.sql
-- All trigger functions and triggers for assemblers tables.
-- Idempotent: safe to run multiple times (OR REPLACE / DROP IF EXISTS).
-- ============================================================


-- --------------------------------------------------------
-- HELPER: Convert integer minutes → human-readable duration text
-- --------------------------------------------------------

CREATE OR REPLACE FUNCTION assemblers_stage_duration_text(total_minutes INTEGER)
RETURNS TEXT AS $$
DECLARE
    hours_part   INTEGER;
    minutes_part INTEGER;
BEGIN
    IF total_minutes IS NULL OR total_minutes <= 0 THEN
        RETURN '';
    END IF;

    hours_part   := total_minutes / 60;
    minutes_part := total_minutes % 60;

    IF hours_part > 0 AND minutes_part > 0 THEN
        RETURN hours_part::TEXT || ' год ' || minutes_part::TEXT || ' хв';
    ELSIF hours_part > 0 THEN
        RETURN hours_part::TEXT || ' год';
    END IF;

    RETURN minutes_part::TEXT || ' хв';
END;
$$ LANGUAGE plpgsql IMMUTABLE;


-- --------------------------------------------------------
-- TRIGGER: Auto-compute stage metrics on detail row write
-- Sets assembly_days_count, assembly_hours, install_days_count,
-- install_hours, and updated_at automatically.
-- --------------------------------------------------------

CREATE OR REPLACE FUNCTION assemblers_details_before_write()
RETURNS TRIGGER AS $$
DECLARE
    assembly_minutes INTEGER;
    install_minutes  INTEGER;
BEGIN
    -- Assembly stage
    IF NEW.assembly_started_at IS NOT NULL
       AND NEW.assembly_completed_at IS NOT NULL
       AND NEW.assembly_completed_at >= NEW.assembly_started_at THEN

        NEW.assembly_days_count :=
            GREATEST((NEW.assembly_completed_at::DATE - NEW.assembly_started_at::DATE) + 1, 1);
        assembly_minutes :=
            FLOOR(EXTRACT(EPOCH FROM (NEW.assembly_completed_at - NEW.assembly_started_at)) / 60);
        NEW.assembly_hours := assemblers_stage_duration_text(assembly_minutes);

    ELSIF COALESCE(NEW.assembly_days_count, 0) <= 0 THEN
        NEW.assembly_days_count := 0;
        NEW.assembly_hours      := '';
    END IF;

    -- Install stage
    IF NEW.install_started_at IS NOT NULL
       AND NEW.install_completed_at IS NOT NULL
       AND NEW.install_completed_at >= NEW.install_started_at THEN

        NEW.install_days_count :=
            GREATEST((NEW.install_completed_at::DATE - NEW.install_started_at::DATE) + 1, 1);
        install_minutes :=
            FLOOR(EXTRACT(EPOCH FROM (NEW.install_completed_at - NEW.install_started_at)) / 60);
        NEW.install_hours := assemblers_stage_duration_text(install_minutes);

    ELSIF COALESCE(NEW.install_days_count, 0) <= 0 THEN
        NEW.install_days_count := 0;
        NEW.install_hours      := '';
    END IF;

    NEW.updated_at := NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_assemblers_detail_rows_before_write ON assemblers_detail_rows;

CREATE TRIGGER trg_assemblers_detail_rows_before_write
BEFORE INSERT OR UPDATE ON assemblers_detail_rows
FOR EACH ROW
EXECUTE FUNCTION assemblers_details_before_write();


-- --------------------------------------------------------
-- STORED PROCEDURE: Recalculate total_planned_hours for a main order
-- Called after any insert/update/delete on assemblers_detail_rows.
-- --------------------------------------------------------

CREATE OR REPLACE FUNCTION assemblers_recalculate_order_total_planned_hours(target_order_number TEXT)
RETURNS VOID AS $$
BEGIN
    UPDATE assemblers_main_orders mo
    SET
        total_planned_hours = COALESCE((
            SELECT SUM(
                CASE
                    WHEN REPLACE(TRIM(COALESCE(dr.planned_hours, '')), ',', '.') ~ '^-?[0-9]+(\.[0-9]+)?$'
                        THEN REPLACE(TRIM(COALESCE(dr.planned_hours, '')), ',', '.')::NUMERIC
                    ELSE 0::NUMERIC
                END
            )
            FROM assemblers_detail_rows dr
            WHERE TRIM(COALESCE(dr.order_number, '')) = TRIM(COALESCE(target_order_number, ''))
        ), 0),
        updated_at = NOW()
    WHERE TRIM(COALESCE(mo.order_number, '')) = TRIM(COALESCE(target_order_number, ''));
END;
$$ LANGUAGE plpgsql;


-- --------------------------------------------------------
-- TRIGGER: Recalculate main order totals after detail row changes
-- --------------------------------------------------------

CREATE OR REPLACE FUNCTION assemblers_details_after_write_recalc_main_order()
RETURNS TRIGGER AS $$
BEGIN
    IF TG_OP = 'DELETE' THEN
        PERFORM assemblers_recalculate_order_total_planned_hours(OLD.order_number);
    ELSE
        PERFORM assemblers_recalculate_order_total_planned_hours(NEW.order_number);
        IF TG_OP = 'UPDATE'
            AND TRIM(COALESCE(OLD.order_number, '')) <> TRIM(COALESCE(NEW.order_number, '')) THEN
            PERFORM assemblers_recalculate_order_total_planned_hours(OLD.order_number);
        END IF;
    END IF;

    RETURN COALESCE(NEW, OLD);
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_assemblers_detail_rows_after_write_recalc_main ON assemblers_detail_rows;

CREATE TRIGGER trg_assemblers_detail_rows_after_write_recalc_main
AFTER INSERT OR UPDATE OR DELETE ON assemblers_detail_rows
FOR EACH ROW
EXECUTE FUNCTION assemblers_details_after_write_recalc_main_order();


-- --------------------------------------------------------
-- STORED PROCEDURE: Enqueue order for metrics recalculation
-- Upserts a record into the recalc queue.
-- --------------------------------------------------------

CREATE OR REPLACE FUNCTION assemblers_enqueue_detail_recalc(
    target_order_number TEXT,
    source_label        TEXT DEFAULT ''
)
RETURNS VOID AS $$
DECLARE
    normalized_order TEXT := TRIM(COALESCE(target_order_number, ''));
BEGIN
    IF normalized_order = '' THEN
        RETURN;
    END IF;

    INSERT INTO assemblers_detail_recalc_queue (order_number, requested_at, source)
    VALUES (normalized_order, NOW(), LEFT(TRIM(COALESCE(source_label, '')), 120))
    ON CONFLICT (order_number)
    DO UPDATE SET
        requested_at = EXCLUDED.requested_at,
        source       = EXCLUDED.source;
END;
$$ LANGUAGE plpgsql;


-- --------------------------------------------------------
-- TRIGGER: Enqueue detail metrics recalculation on row changes
-- --------------------------------------------------------

CREATE OR REPLACE FUNCTION assemblers_details_after_write_enqueue_recalc()
RETURNS TRIGGER AS $$
BEGIN
    IF TG_OP = 'DELETE' THEN
        PERFORM assemblers_enqueue_detail_recalc(
            OLD.order_number,
            TG_TABLE_NAME || ':' || TG_OP
        );
        RETURN OLD;
    END IF;

    PERFORM assemblers_enqueue_detail_recalc(
        NEW.order_number,
        TG_TABLE_NAME || ':' || TG_OP
    );

    IF TG_OP = 'UPDATE'
        AND TRIM(COALESCE(OLD.order_number, '')) <> TRIM(COALESCE(NEW.order_number, '')) THEN
        PERFORM assemblers_enqueue_detail_recalc(
            OLD.order_number,
            TG_TABLE_NAME || ':' || TG_OP || ':old'
        );
    END IF;

    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_assemblers_detail_rows_after_write_enqueue_recalc ON assemblers_detail_rows;

CREATE TRIGGER trg_assemblers_detail_rows_after_write_enqueue_recalc
AFTER INSERT OR UPDATE OR DELETE ON assemblers_detail_rows
FOR EACH ROW
EXECUTE FUNCTION assemblers_details_after_write_enqueue_recalc();
