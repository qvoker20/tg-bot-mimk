# MIM-K System Architecture Overview

## 1. Repository Structure (High Level)

This repository is a multi-service workspace with several independent applications:

- `ERP/` - Main FastAPI ERP application for internal company workflows.
- `Production/` - Separate FastAPI application for production operations.
- `hub/` - Flask-based web hub/admin interface.
- `calculation_request_bot/` - Telegram bot for project calculation requests.
- `teg_bot_mimk.py` - Main Telegram bot entrypoint for broader company workflows.
- `google_parset_active.py` - Google Sheets -> PostgreSQL synchronization service.
- `admin_panel/` - Separate admin panel service.
- `wiki-bot-mimk/` - Additional bot/module for wiki-related automation.
- `utils/`, `handlers/`, `docs/` - shared logic and documentation.

## 2. Main Runtime Components

### ERP (FastAPI)

- Entrypoint: `ERP/main.py`.
- App composition: `ERP/app/main.py`.
- Config/environment: `ERP/app/config.py`.
- Security middleware: `ERP/app/security.py`.
- Domain routing root: `ERP/app/modules/router.py`.

ERP uses modular architecture:

- `modules/core` - login page, auth/session endpoints, base navigation.
- `modules/assemblers` - assemblers domain (buffer, details, schedules, closed orders, staff, settings, etc.).

### Production (FastAPI)

- Entrypoint: `Production/main.py`.
- Independent app and config under `Production/app/`.
- Uses a similar auth pattern (phone + Telegram code).

### Hub (Flask)

- Entrypoint: `hub/run_hub.py`.
- Handles web UI pages and API endpoints in Flask style.
- Includes its own rate limiting and security headers.

### Telegram Bots

- Main multifunction bot: `teg_bot_mimk.py`.
- Calculation request bot: `calculation_request_bot/bot.py`.
- Additional wiki bot: `wiki-bot-mimk/wiki-bot-mimk.py`.

### Data Sync Service

- `google_parset_active.py` polls Google Sheets and writes normalized datasets to PostgreSQL tables used by ERP/other modules.

## 3. ERP FastAPI Architecture (Detailed)

ERP follows layered architecture:

- API layer (routers): parse HTTP, auth checks, response mapping.
- Service layer: business rules and orchestration.
- Repository layer: SQL and persistence access.
- DB layer: connections, schema bootstrap, and DB-side functions/triggers.

The architecture intent is documented in `ERP/app/ARCHITECTURE.md`.

Dependency direction:

- API -> Services -> Repositories -> DB

## 4. ERP Request Flow

Typical request flow for ERP pages:

1. Browser calls URL handled by FastAPI router.
2. Middleware chain runs (host checks, security headers, session).
3. Router checks auth/permissions.
4. Service layer loads domain data.
5. Template (`Jinja2`) is rendered or JSON is returned.
6. Frontend JS performs follow-up API calls for data tables/actions.

Example (Assemblers Buffer):

- Page route: `/assemblers/buffer` in `ERP/app/modules/assemblers/api/pages/router.py`.
- Data API: `/assemblers/api/buffer` in `ERP/app/modules/assemblers/api/v1/buffer.py`.
- Frontend script: `ERP/app/static/js/assemblers/assemblers-buffer.js`.
- Template: `ERP/app/templates/assemblers/buffer.html`.

## 5. Authentication Flow (ERP)

Files:

- Auth routes: `ERP/app/modules/core/api/auth.py`.
- Auth service: `ERP/app/services/auth_service.py`.
- Login template: `ERP/app/templates/login.html`.

Flow:

1. User enters phone number.
2. Server normalizes number and finds user in DB (`database_app_userdatatelegram`).
3. One-time code is generated and sent via Telegram Bot API.
4. User submits code.
5. Code is verified in memory (TTL-based).
6. Session is established (`request.session["user"]`).

Anti-spam protections are implemented server-side and client-side:

- Cooldown and rate limits in `auth_service.py`.
- Submit button lock in `login.html`.

## 6. Data Architecture and Integrations

### PostgreSQL

Main persistent store for users, operational tables, schedules, buffer datasets, etc.

### Google Sheets Integration

`google_parset_active.py`:

- Authenticates using service account JSON.
- Reads multiple sheets.
- Builds normalized data models.
- Writes into PostgreSQL tables (for example `data_designer`, `data_production`, `data_metal`).

### Buffer Data Sources (ERP)

Buffer module reads from configurable DB URLs:

- `BUFFER_DESIGNER_DB_URL`
- `BUFFER_PRODUCTION_DB_URL`
- `BUFFER_METAL_DB_URL`
- fallback: `BUFFER_DB_URL`
- fallback of fallback: main `PG_*` from ERP config

Resolution logic is in `ERP/app/modules/assemblers/db/async_connection.py`.

## 7. Security Model

### ERP security middleware

`ERP/app/security.py` applies:

- `TrustedHostMiddleware` (host header allowlist).
- Security headers:
  - `X-Frame-Options: DENY`
  - `X-Content-Type-Options: nosniff`
  - `Referrer-Policy`
  - `Permissions-Policy`
  - optional HSTS (`SECURITY_HEADERS_FORCE_HTTPS`)

### Session security

Configured in `ERP/app/main.py` and `ERP/app/config.py`:

- `SESSION_COOKIE_SECURE`
- `SESSION_COOKIE_SAMESITE`
- signed session cookie via `SECRET_KEY`

### Role checks

Role/permission checks are done per endpoint/domain (for example buffer transfer/close permissions in assemblers API).

## 8. Background Workers

ERP starts background tasks in app lifespan (`ERP/app/main.py`):

- Detail metrics recalculation worker.
- Schedule daily cutoff worker.

Workers run while app is alive and stop gracefully on shutdown.

## 9. Frontend Architecture

ERP frontend is server-rendered templates + vanilla JS modules:

- Templates: `ERP/app/templates/**`
- Static JS: `ERP/app/static/js/**`
- Static CSS: `ERP/app/static/styles/**`

Pattern:

- Initial page render via Jinja2.
- Data-heavy tables/actions via fetch API to `/assemblers/api/...` endpoints.

## 10. Libraries Used

### Root (`requirements.txt`)

- `python-telegram-bot`
- `psycopg2-binary`
- `pytz`
- `httpx`
- `chromadb`
- `openai`
- `google-api-python-client`
- `google-auth`
- `google-auth-oauthlib`
- `google-auth-httplib2`
- `reportlab`

### ERP (`ERP/requirements.txt`)

- `fastapi`
- `uvicorn[standard]`
- `jinja2`
- `python-dotenv`
- `psycopg2-binary`
- `requests`
- `python-multipart`
- `itsdangerous`

### Production (`Production/requirements.txt`)

- `fastapi`
- `uvicorn[standard]`
- `jinja2`
- `python-dotenv`
- `requests`
- `psycopg2-binary`
- `itsdangerous`

### Calculation Request Bot (`calculation_request_bot/requirements.txt`)

- `python-telegram-bot`
- `python-dotenv`
- `psycopg2-binary`

## 11. Important Environment Variables

Commonly required across services:

- Database: `PG_HOST`, `PG_PORT`, `PG_DBNAME`, `PG_USER`, `PG_PASSWORD`
- Sessions/security: `SECRET_KEY`, `SESSION_COOKIE_SECURE`, `SESSION_COOKIE_SAMESITE`
- Telegram: `TELEGRAM_BOT_TOKEN`
- ERP hosts/security: `ALLOWED_HOSTS`, `ALLOW_ALL_HOSTS`, `SECURITY_HEADERS_FORCE_HTTPS`
- Auth TTL: `COLLECTORS_CODE_TTL_SECONDS`
- Buffer DB aliases: `BUFFER_DB_URL`, `BUFFER_DESIGNER_DB_URL`, `BUFFER_PRODUCTION_DB_URL`, `BUFFER_METAL_DB_URL`

## 12. Operational Notes

- If local data differs from tunnel/domain behavior, first compare process environment and DB source URLs.
- For frontend inconsistencies, check static asset versioning (`?v=...`) and cache invalidation.
- Keep one instance per service where expected, especially for polling/sync scripts and bots.

---

If needed, this document can be split into:

1. `ERP` internal architecture only,
2. bots and integrations architecture,
3. deployment topology (local, tunnel, cloud server).
