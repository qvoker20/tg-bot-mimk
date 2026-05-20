-- ============================================================
-- Migration: assemblers_001_initial_schema.sql
-- Creates all assemblers tables, indexes, and DB functions.
-- Idempotent: safe to run multiple times (uses IF NOT EXISTS / OR REPLACE).
-- ============================================================

-- --------------------------------------------------------
-- TABLES
-- --------------------------------------------------------

CREATE TABLE IF NOT EXISTS assemblers_main_orders (
    id                      BIGSERIAL PRIMARY KEY,
    order_number            TEXT NOT NULL UNIQUE,
    customer                TEXT NOT NULL DEFAULT '',
    order_type              TEXT NOT NULL DEFAULT '',
    signed_at               DATE,
    contract_due_at         DATE,
    manager_name            TEXT NOT NULL DEFAULT '',
    constructor_name        TEXT NOT NULL DEFAULT '',
    status                  TEXT NOT NULL DEFAULT '',
    note                    TEXT NOT NULL DEFAULT '',
    planned_install_at      DATE,
    install_completed_at    DATE,
    address                 TEXT NOT NULL DEFAULT '',
    address_note            TEXT NOT NULL DEFAULT '',
    materials               TEXT NOT NULL DEFAULT '',
    assembly_workers        TEXT NOT NULL DEFAULT '',
    install_workers         TEXT NOT NULL DEFAULT '',
    assembly_status         TEXT NOT NULL DEFAULT '',
    install_status          TEXT NOT NULL DEFAULT '',
    assembler_pause_at      TIMESTAMPTZ,
    closed_at               TIMESTAMPTZ,
    closed_by_name          TEXT NOT NULL DEFAULT '',
    closed_by_role          TEXT NOT NULL DEFAULT '',
    closed_by_telegram_id   BIGINT,
    vat                     BOOLEAN NOT NULL DEFAULT FALSE,
    total_planned_hours     NUMERIC(14, 2) NOT NULL DEFAULT 0,
    recorded_at             TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at              TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS assemblers_detail_rows (
    id                      BIGSERIAL PRIMARY KEY,
    order_number            TEXT NOT NULL REFERENCES assemblers_main_orders(order_number) ON DELETE CASCADE,
    part_number             TEXT NOT NULL DEFAULT '',
    customer                TEXT NOT NULL DEFAULT '',
    product_name            TEXT NOT NULL DEFAULT '',
    planned_assembly_due_at DATE,
    assembly_worker         TEXT NOT NULL DEFAULT '',
    assembly_started_at     TIMESTAMPTZ,
    assembly_completed_at   TIMESTAMPTZ,
    assembly_days_count     INTEGER NOT NULL DEFAULT 0,
    assembly_hours          TEXT NOT NULL DEFAULT '',
    assembly_status         TEXT NOT NULL DEFAULT '',
    planned_install_due_at  DATE,
    install_worker          TEXT NOT NULL DEFAULT '',
    install_started_at      TIMESTAMPTZ,
    install_completed_at    TIMESTAMPTZ,
    install_days_count      INTEGER NOT NULL DEFAULT 0,
    install_hours           TEXT NOT NULL DEFAULT '',
    install_status          TEXT NOT NULL DEFAULT '',
    item_type               TEXT NOT NULL DEFAULT '',
    constructor_status      TEXT NOT NULL DEFAULT '',
    production_launches     INTEGER NOT NULL DEFAULT 0,
    production_completed    INTEGER NOT NULL DEFAULT 0,
    metal                   TEXT NOT NULL DEFAULT '',
    glass_eta               TEXT NOT NULL DEFAULT '',
    glass_delivered         TEXT NOT NULL DEFAULT '',
    planned_hours           TEXT NOT NULL DEFAULT '',
    total_hours             TEXT NOT NULL DEFAULT '',
    item_value              NUMERIC(14, 2) NOT NULL DEFAULT 0,
    assembly_percent        NUMERIC(8, 2) NOT NULL DEFAULT 0,
    install_percent         NUMERIC(8, 2) NOT NULL DEFAULT 0,
    item_percent            NUMERIC(8, 2) NOT NULL DEFAULT 0,
    created_at              TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at              TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS assemblers_column_preferences (
    id              BIGSERIAL PRIMARY KEY,
    telegram_id     BIGINT NOT NULL,
    page_key        TEXT NOT NULL,
    column_order    TEXT NOT NULL,
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE(telegram_id, page_key)
);

CREATE TABLE IF NOT EXISTS assemblers_detail_recalc_queue (
    order_number    TEXT PRIMARY KEY,
    requested_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    source          TEXT NOT NULL DEFAULT ''
);

-- --------------------------------------------------------
-- INDEXES
-- --------------------------------------------------------

CREATE INDEX IF NOT EXISTS idx_assemblers_main_orders_recorded_at
    ON assemblers_main_orders(recorded_at DESC, order_number DESC);

CREATE INDEX IF NOT EXISTS idx_assemblers_main_orders_status_closed_at
    ON assemblers_main_orders(status, closed_at DESC, order_number DESC);

CREATE INDEX IF NOT EXISTS idx_assemblers_detail_rows_order_number
    ON assemblers_detail_rows(order_number, id);

CREATE INDEX IF NOT EXISTS idx_assemblers_detail_recalc_queue_requested_at
    ON assemblers_detail_recalc_queue(requested_at);
