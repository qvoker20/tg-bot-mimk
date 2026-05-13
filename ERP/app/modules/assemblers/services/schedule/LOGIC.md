# Schedule Module Logic

## Purpose
- Manage assembler task lifecycle for manager planning UI and mobile executor app.

## Files
- `constants.py`: domain constants and allowed transitions.
- `schema.py`: table bootstrap and DB triggers for lifecycle timestamps.
- `helpers.py`: input normalization and row mapping helpers.
- `admin.py`: manager operations (list/create/edit weekly tasks).
- `mobile.py`: executor operations (list daily tasks and status transitions).

## Data Access
- `admin.py` and `mobile.py` keep business rules and transition validation.
- SQL access is delegated to `modules/assemblers/repositories/schedule_repo.py`.

## Business Rules
- Manager can create tasks only for workers in selected subdivision.
- `related` tasks require description and do not bind to order.
- `assembly`/`install` tasks require order and selected parts.
- Completed part cannot be re-assigned for the same task type.
- Mobile state transitions:
  - queued -> in_progress (start)
  - in_progress -> paused (pause)
  - paused -> in_progress (resume)
  - in_progress/paused -> completed (finish)

## Trigger Policy
- Schedule table uses trigger function `assemblers_schedule_before_write`.
- Trigger sets `updated_at` and lifecycle timestamps (`started_at`, `paused_at`, `completed_at`) when status changes.
