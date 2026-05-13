-- Main order aggregations.
-- Recalculates total planned hours whenever detail rows change.

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

DROP TRIGGER IF EXISTS trg_assemblers_detail_rows_after_write_recalc_main ON assemblers_detail_rows;
CREATE TRIGGER trg_assemblers_detail_rows_after_write_recalc_main
AFTER INSERT OR UPDATE OR DELETE ON assemblers_detail_rows
FOR EACH ROW
EXECUTE FUNCTION assemblers_details_after_write_recalc_main_order();
