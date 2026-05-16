from __future__ import annotations

import os
from sqlalchemy.engine import URL
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine
from sqlalchemy.pool import NullPool

from app.config import PG_CONN


_BUFFER_DB_ENV_BY_ALIAS = {
    "designer": "BUFFER_DESIGNER_DB_URL",
    "production": "BUFFER_PRODUCTION_DB_URL",
    "metal": "BUFFER_METAL_DB_URL",
}

_ENGINE_CACHE: dict[str, AsyncEngine] = {}
USE_PGBOUNCER = (os.getenv("USE_PGBOUNCER", "0") == "1")


def _build_default_async_db_url() -> str | None:
    if not PG_CONN.get("host") or not PG_CONN.get("dbname") or not PG_CONN.get("user"):
        return None

    return URL.create(
        "postgresql+asyncpg",
        username=PG_CONN.get("user"),
        password=PG_CONN.get("password"),
        host=PG_CONN.get("host"),
        port=PG_CONN.get("port"),
        database=PG_CONN.get("dbname"),
    ).render_as_string(hide_password=False)


def _resolve_async_db_url(alias: str) -> str | None:
    alias_key = str(alias or "").strip().casefold()
    alias_env_name = _BUFFER_DB_ENV_BY_ALIAS.get(alias_key)
    if alias_env_name:
        alias_url = (os.getenv(alias_env_name) or "").strip()
        if alias_url:
            return alias_url

    common_buffer_url = (os.getenv("BUFFER_DB_URL") or "").strip()
    if common_buffer_url:
        return common_buffer_url

    return _build_default_async_db_url()


def get_async_engine(alias: str = "main") -> AsyncEngine:
    normalized_alias = str(alias or "main").strip().casefold() or "main"
    cached = _ENGINE_CACHE.get(normalized_alias)
    if cached is not None:
        return cached

    resolved_url = _resolve_async_db_url(normalized_alias)
    if not resolved_url:
        raise RuntimeError("Async database URL is not configured for buffer sources.")

    engine_kwargs = {
        "future": True,
    }
    if USE_PGBOUNCER:
        # PgBouncer is the pool manager; disable SQLAlchemy internal pooling.
        engine_kwargs["poolclass"] = NullPool
    else:
        engine_kwargs["pool_pre_ping"] = True
        engine_kwargs["pool_recycle"] = 1800

    engine = create_async_engine(resolved_url, **engine_kwargs)
    _ENGINE_CACHE[normalized_alias] = engine
    return engine


async def dispose_async_engines() -> None:
    engines = list(_ENGINE_CACHE.values())
    _ENGINE_CACHE.clear()
    for engine in engines:
        await engine.dispose()
