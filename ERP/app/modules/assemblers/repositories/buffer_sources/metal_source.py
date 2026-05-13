from __future__ import annotations

from sqlalchemy import text

from app.modules.assemblers.db.async_connection import get_async_engine


DATA_METAL_TABLE = "data_metal"


async def fetch_metal_rows() -> list[tuple]:
    engine = get_async_engine("metal")
    async with engine.connect() as conn:
        table_exists_result = await conn.execute(
            text("SELECT to_regclass(:table_name)"),
            {"table_name": DATA_METAL_TABLE},
        )
        if table_exists_result.scalar_one_or_none() is None:
            return []

        result = await conn.execute(
            text(
                f"""
                SELECT column_1, column_2, column_3, column_4, column_5
                FROM {DATA_METAL_TABLE}
                WHERE NULLIF(TRIM(COALESCE(column_1, '')), '') IS NOT NULL
                ORDER BY id
                """
            )
        )
        return [tuple(row) for row in result.fetchall()]
