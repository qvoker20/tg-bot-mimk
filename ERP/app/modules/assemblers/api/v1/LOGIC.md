# API v1 Logic

## Version Scope
- Stable endpoints used by current frontend and mobile app.

## Schedule Endpoints
- `GET /assemblers/api/schedule/tasks`: weekly manager view.
- `POST /assemblers/api/schedule/tasks`: create manager tasks.
- `POST /assemblers/api/schedule/tasks/edit`: manager edit/delete.

## Contract Rule
- Endpoint response schema and user-facing error text are backward compatible.
