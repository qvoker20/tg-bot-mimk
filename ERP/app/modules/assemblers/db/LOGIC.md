# DB Logic

## Responsibility
- Connection and table constants for assemblers domain.
- SQL-first business calculations via trigger functions.

## Rule
- Computed metrics should be maintained by DB trigger functions.
- Python service layer should request writes and read final persisted state.
