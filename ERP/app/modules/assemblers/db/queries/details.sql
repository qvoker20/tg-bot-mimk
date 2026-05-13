-- Details metrics triggers.
-- Calculates stage day counters and human-readable duration from timestamps.

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

DROP TRIGGER IF EXISTS trg_assemblers_detail_rows_before_write ON assemblers_detail_rows;
CREATE TRIGGER trg_assemblers_detail_rows_before_write
BEFORE INSERT OR UPDATE ON assemblers_detail_rows
FOR EACH ROW
EXECUTE FUNCTION assemblers_details_before_write();
