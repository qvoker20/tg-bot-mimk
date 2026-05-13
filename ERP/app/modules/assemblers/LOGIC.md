# Assemblers Module Logic

## Goal
- Isolate assemblers domain from global app code and provide clear boundaries.

## Layered Architecture
- `api`: HTTP handlers and authorization checks.
- `services`: business workflows and validation rules.
- `repositories`: DB access helpers (query composition and persistence).
- `schemas`: request/response payload contracts.
- `db`: table constants, connection, SQL migrations and triggers.

## Migration Policy
- Runtime compatibility is preserved via adapters in legacy `app/services/*` files.
- New development should target `app/modules/assemblers/*` only.
