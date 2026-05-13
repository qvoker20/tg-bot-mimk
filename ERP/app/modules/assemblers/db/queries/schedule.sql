-- Schedule table lifecycle triggers.
-- This function keeps timestamps consistent on status changes.

CREATE OR REPLACE FUNCTION assemblers_schedule_before_write()
RETURNS TRIGGER AS $$
BEGIN
	IF TG_OP = 'INSERT' THEN
		NEW.created_at := COALESCE(NEW.created_at, NOW());
	END IF;

	IF TG_OP = 'UPDATE' THEN
		IF NEW.status = 'В роботі' AND (OLD.status IS DISTINCT FROM NEW.status) AND NEW.started_at IS NULL THEN
			NEW.started_at := NOW();
		END IF;

		IF NEW.status = 'Пауза' AND (OLD.status IS DISTINCT FROM NEW.status) AND NEW.paused_at IS NULL THEN
			NEW.paused_at := NOW();
		END IF;

		IF NEW.status = 'Завершено' AND (OLD.status IS DISTINCT FROM NEW.status) AND NEW.completed_at IS NULL THEN
			NEW.completed_at := NOW();
		END IF;
	END IF;

	NEW.updated_at := NOW();
	RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_assemblers_schedule_tasks_before_write ON assemblers_schedule_tasks;
CREATE TRIGGER trg_assemblers_schedule_tasks_before_write
BEFORE INSERT OR UPDATE ON assemblers_schedule_tasks
FOR EACH ROW
EXECUTE FUNCTION assemblers_schedule_before_write();
