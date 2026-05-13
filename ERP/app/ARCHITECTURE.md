# ERP Server Architecture

## Layers
- API (routers): HTTP endpoints, auth checks, request parsing.
- Services: business rules and orchestration.
- Repositories: SQL execution and persistence primitives.
- DB: connection + schema + trigger-driven calculations.
- Schemas: explicit request/response contracts.

## Domain Modules
- `modules/assemblers`: production-ready migration target for assemblers domain.
- Legacy `routers/assemblers` and `services/assemblers_*` remain as compatibility shells while migration is in progress.

## Calculation Policy
- Metric calculations must be performed in PostgreSQL trigger functions whenever possible.
- Python layer writes business events, then reads persisted state.
- Trigger setup is defined in SQL query files and bootstrap schema methods.

## Dependency Direction
- API -> Services -> Repositories -> DB
- Services can call shared domain services but should avoid importing API modules.
- Module package init files should avoid side effects to prevent circular imports.
