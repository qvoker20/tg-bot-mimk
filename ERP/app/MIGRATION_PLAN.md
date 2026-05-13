# Migration Plan

## Completed
- Schedule API moved to modular namespace (`modules/assemblers/api/v1/schedule.py`).
- Schedule service split into focused files under `modules/assemblers/services/schedule/`.
- Legacy schedule service converted to compatibility adapter.
- Trigger logic added for schedule lifecycle timestamps and detail/main-order calculations.
- Module logic documentation added (`LOGIC.md` in each assemblers module folder).

## Next
1. Move SQL statements from schedule/admin/mobile services into repository methods.
2. Introduce pydantic schemas for schedule endpoints in `modules/assemblers/schemas`.
3. Migrate `details`, `buffer`, `staff`, `main_orders` routes into modular API namespace.
4. Remove legacy route/service files after endpoint parity and smoke tests.
