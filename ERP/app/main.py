# tg-bot-mimk/ERP/app/main.py

import asyncio
import os
import sys
from contextlib import asynccontextmanager, suppress
from pathlib import Path

import uvicorn
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.concurrency import run_in_threadpool
from starlette.middleware.sessions import SessionMiddleware

try:
    from .config import (
        ALLOWED_HOSTS,
        SECRET_KEY,
        SECURITY_HEADERS_FORCE_HTTPS,
        SESSION_COOKIE_SAMESITE,
        SESSION_COOKIE_SECURE,
        STATIC_DIR,
        TEMPLATES_DIR,
    )
    from .db import close_connection_pool, initialize_connection_pool
    from .modules.assemblers.db.async_connection import dispose_async_engines
    from .modules.assemblers.services.activity_log import record_activity_event
    from .modules.assemblers.services.registry.worker import run_detail_metrics_recalc_worker
    from .modules.router import router as modules_router
    from .modules.router import set_templates
    from .security import apply_security_middleware
except ImportError:
    CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
    PARENT_DIR = os.path.dirname(CURRENT_DIR)
    if PARENT_DIR not in sys.path:
        sys.path.insert(0, PARENT_DIR)

    from app.config import (
        ALLOWED_HOSTS,
        SECRET_KEY,
        SECURITY_HEADERS_FORCE_HTTPS,
        SESSION_COOKIE_SAMESITE,
        SESSION_COOKIE_SECURE,
        STATIC_DIR,
        TEMPLATES_DIR,
    )
    from app.db import close_connection_pool, initialize_connection_pool
    from app.modules.assemblers.db.async_connection import dispose_async_engines
    from app.modules.assemblers.services.activity_log import record_activity_event
    from app.modules.assemblers.services.registry.worker import run_detail_metrics_recalc_worker
    from app.modules.router import router as modules_router
    from app.modules.router import set_templates
    from app.security import apply_security_middleware


@asynccontextmanager
async def lifespan(app: FastAPI):  # noqa: ARG001
    """Start background workers on startup; stop them cleanly on shutdown."""
    # Initialize database connection pool on startup (production safety)
    initialize_connection_pool(minconn=5, maxconn=20)

    stop_event = asyncio.Event()
    recalc_worker_task = asyncio.create_task(
        run_detail_metrics_recalc_worker(stop_event),
        name="detail-metrics-recalc-worker",
    )

    yield  # server is running

    # --- shutdown ---
    stop_event.set()
    for worker_task in (recalc_worker_task,):
        try:
            await worker_task
        except Exception:
            pass
    await dispose_async_engines()
    close_connection_pool()  # Clean up synchronous DB pool


app = FastAPI(title="MIMK ERP", lifespan=lifespan)

apply_security_middleware(
    app,
    allowed_hosts=ALLOWED_HOSTS,
    force_https_headers=SECURITY_HEADERS_FORCE_HTTPS,
)

app.add_middleware(
    SessionMiddleware,
    secret_key=SECRET_KEY,
    max_age=60 * 60 * 12,
    same_site=SESSION_COOKIE_SAMESITE,
    https_only=SESSION_COOKIE_SECURE,
)

app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

templates = Jinja2Templates(directory=str(TEMPLATES_DIR))
set_templates(templates)


@app.middleware("http")
async def assemblers_error_audit_middleware(request, call_next):
    try:
        response = await call_next(request)
    except Exception as error:
        if request.url.path.startswith("/assemblers"):
            try:
                await run_in_threadpool(
                    record_activity_event,
                    action_key="api.exception",
                    action_label="Неперехоплена помилка",
                    description=f"{request.method} {request.url.path}: {error}",
                    actor=request.session.get("user") or {"kind": "system"},
                    entity_type="api_error",
                    entity_id=request.url.path,
                    source_table="http",
                    source_op="EXCEPTION",
                    status_code=500,
                    details={
                        "method": request.method,
                        "path": request.url.path,
                        "query": str(request.url.query),
                        "error_type": type(error).__name__,
                    },
                )
            except Exception:
                pass
        raise

    if request.url.path.startswith("/assemblers") and response.status_code >= 400:
        try:
            await run_in_threadpool(
                record_activity_event,
                action_key="api.error",
                action_label="HTTP помилка",
                description=f"{request.method} {request.url.path} -> {response.status_code}",
                actor=request.session.get("user") or {"kind": "system"},
                entity_type="api_error",
                entity_id=request.url.path,
                source_table="http",
                source_op="RESPONSE",
                status_code=int(response.status_code),
                details={
                    "method": request.method,
                    "path": request.url.path,
                    "query": str(request.url.query),
                    "status_code": int(response.status_code),
                },
            )
        except Exception:
            pass

    return response

app.include_router(modules_router)


PROJECT_DIR = Path(__file__).resolve().parent.parent
RELOAD_ENABLED = os.getenv("ERP_RELOAD", "0") == "1"


if __name__ == "__main__":
    uvicorn.run(
        "app.main:app",
        host="127.0.0.1",
        port=9182,
        reload=RELOAD_ENABLED,
        reload_dirs=[str(PROJECT_DIR)] if RELOAD_ENABLED else None,
    )
