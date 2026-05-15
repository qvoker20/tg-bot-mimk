from __future__ import annotations

from sqlalchemy import text

from app.modules.assemblers.db.async_connection import get_async_engine


DATA_DESIGNER_TABLE = "data_designer"


async def fetch_designer_rows() -> list[tuple]:
    engine = get_async_engine("designer")
    async with engine.connect() as conn:
        result = await conn.execute(
            text(
                f"""
                SELECT
                    column_1, column_3, column_6, column_7, column_9,
                    column_10, column_11, column_12, column_13, column_15,
                    column_30, column_31, column_32
                    column_14, column_16, hpl, column_18, column_19,
                    column_20, column_21, c, column_23, column_24,
                    column_25, column_26, column_29,
                    column_2
                FROM {DATA_DESIGNER_TABLE}
                WHERE NULLIF(TRIM(COALESCE(column_1, '')), '') IS NOT NULL
                ORDER BY column_1, id
                """
            )
        )
        return [tuple(row) for row in result.fetchall()]
