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
);

CREATE INDEX IF NOT EXISTS idx_project_calc_requests_telegram_id
    ON project_calculation_requests(telegram_id);

CREATE INDEX IF NOT EXISTS idx_project_calc_requests_status
    ON project_calculation_requests(status);
