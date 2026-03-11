-- Варіант 1 (рекомендовано): використовувати поточну БД бота,
-- створити лише таблицю заявок на перепустки.

CREATE TABLE IF NOT EXISTS logistics_pass_requests (
    id BIGSERIAL PRIMARY KEY,
    requester_telegram_id BIGINT NOT NULL,
    requester_name TEXT,
    requester_username TEXT,
    pass_type TEXT NOT NULL CHECK (pass_type IN ('vehicle', 'person')),
    vehicle_plate TEXT,
    vehicle_brand TEXT,
    visitor_full_name TEXT NOT NULL,
    visit_date DATE NOT NULL,
    date_mode TEXT NOT NULL DEFAULT 'single' CHECK (date_mode IN ('single', 'range')),
    visit_date_from DATE,
    visit_date_to DATE,
    status TEXT NOT NULL DEFAULT 'new',
    created_at TIMESTAMP NOT NULL DEFAULT NOW()
);

ALTER TABLE logistics_pass_requests ADD COLUMN IF NOT EXISTS date_mode TEXT;
ALTER TABLE logistics_pass_requests ADD COLUMN IF NOT EXISTS visit_date_from DATE;
ALTER TABLE logistics_pass_requests ADD COLUMN IF NOT EXISTS visit_date_to DATE;

UPDATE logistics_pass_requests SET date_mode = 'single' WHERE date_mode IS NULL;
UPDATE logistics_pass_requests SET visit_date_from = visit_date WHERE visit_date_from IS NULL;
UPDATE logistics_pass_requests SET visit_date_to = visit_date WHERE visit_date_to IS NULL;

CREATE INDEX IF NOT EXISTS idx_logistics_pass_requests_visit_date
    ON logistics_pass_requests(visit_date);

CREATE INDEX IF NOT EXISTS idx_logistics_pass_requests_visit_date_from
    ON logistics_pass_requests(visit_date_from);

CREATE INDEX IF NOT EXISTS idx_logistics_pass_requests_visit_date_to
    ON logistics_pass_requests(visit_date_to);

CREATE INDEX IF NOT EXISTS idx_logistics_pass_requests_status
    ON logistics_pass_requests(status);

CREATE INDEX IF NOT EXISTS idx_logistics_pass_requests_requester
    ON logistics_pass_requests(requester_telegram_id);


-- Варіант 2 (якщо потрібна окрема БД):
-- CREATE DATABASE mimk_logistics;
-- \c mimk_logistics
-- далі виконати CREATE TABLE вище.
