# API Logic

## Responsibility
- Receive HTTP requests.
- Validate auth/permissions.
- Delegate business logic to services.
- Return stable JSON payloads and error messages.

## Rules
- API handlers do not contain SQL.
- API handlers do not calculate domain metrics.
- All state transitions are delegated to service layer.
