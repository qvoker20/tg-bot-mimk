from __future__ import annotations

from sqlalchemy import text

from app.modules.assemblers.db.async_connection import get_async_engine


MAIN_TABLE_NAME = "assemblers_main_orders"


def _safe_text(value) -> str:
    return " ".join(str(value or "").split()).strip()


async def fetch_transferred_order_numbers() -> set[str]:
    engine = get_async_engine("main")
    async with engine.connect() as conn:
        table_exists_result = await conn.execute(
            text("SELECT to_regclass(:table_name)"),
            {"table_name": MAIN_TABLE_NAME},
        )
        if table_exists_result.scalar_one_or_none() is None:
            return set()

        result = await conn.execute(text(f"SELECT order_number FROM {MAIN_TABLE_NAME}"))
        return {_safe_text(row[0]) for row in result.fetchall() if _safe_text(row[0])}
