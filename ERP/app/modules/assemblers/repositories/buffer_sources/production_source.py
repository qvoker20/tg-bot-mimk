from __future__ import annotations

from sqlalchemy import text

from app.modules.assemblers.db.async_connection import get_async_engine


DATA_PRODUCTION_TABLE = "data_production"


async def fetch_production_rows() -> list[tuple]:
    engine = get_async_engine("production")
    async with engine.connect() as conn:
        result = await conn.execute(
            text(
                f"""
                SELECT column_1, column_8, column_9, column_12
                FROM {DATA_PRODUCTION_TABLE}
                WHERE NULLIF(TRIM(COALESCE(column_1, '')), '') IS NOT NULL
                ORDER BY column_1, id
                """
            )
        )
        return [tuple(row) for row in result.fetchall()]
