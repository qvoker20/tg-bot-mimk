# SQL Queries & Triggers Logic

## Purpose
- Store idempotent SQL functions and triggers used by assemblers module.

## Trigger Strategy
- `schedule.sql`: lifecycle timestamps and `updated_at` maintenance.
- `details.sql`: stage duration counters and text duration fields.
- `main_orders.sql`: aggregate `total_planned_hours` from detail rows.

## Deployment
- SQL files are safe to run multiple times.
- Trigger functions use `CREATE OR REPLACE FUNCTION` and `DROP TRIGGER IF EXISTS`.
