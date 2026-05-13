# Schemas Logic

## Responsibility
- Hold typed contracts for input/output payloads.
- Keep API shape explicit and discoverable.

## Migration Note
- Legacy endpoints currently rely on dict payloads.
- Pydantic schemas should be introduced per endpoint during v2 migration.
