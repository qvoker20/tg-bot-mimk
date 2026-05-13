# Repositories Logic

## Responsibility
- Isolate SQL interaction from API and service code.
- Provide predictable data access primitives.

## Transition State
- Repository layer is initialized for gradual migration.
- Schedule domain queries are migrated to `schedule_repo.py` and consumed by `services/schedule/admin.py` and `services/schedule/mobile.py`.
- Existing non-schedule service code still contains direct SQL in some flows and is being moved incrementally.
