from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from starlette.concurrency import run_in_threadpool

from app.modules.assemblers.dependencies import (
    can_transfer_buffer_orders,
    is_admin_user,
    require_user,
)
from app.modules.assemblers.services.buffer import load_buffer_rows
from app.modules.assemblers.services.registry import close_buffer_orders, transfer_buffer_orders


router = APIRouter()


class TransferBufferPayload(BaseModel):
    order_numbers: list[str] = []
    analyze_only: bool = False
    close_all_filtered: bool = False
    exclude_order_numbers: list[str] = []
    order_number_filter: str = ""
    customer_filter: str = ""


def _require_admin_api(user: dict | None):
    if not is_admin_user(user):
        return JSONResponse({"ok": False, "error": "forbidden"}, status_code=403)
    return None


def _require_buffer_transfer_api(user: dict | None):
    if not can_transfer_buffer_orders(user):
        return JSONResponse({"ok": False, "error": "forbidden"}, status_code=403)
    return None


@router.get("/api/buffer")
async def assemblers_buffer_api(
    request: Request,
    offset: int = 0,
    limit: int = 30,
    order_number: str = "",
    customer: str = "",
    sort_by: str = "",
    sort_dir: str = "asc",
    status_percent_op: str = "",
    status_percent_value: int = -1,
):
    _, redirect = require_user(request)
    if redirect:
        return JSONResponse({"ok": False, "error": "unauthorized"}, status_code=401)

    rows = await load_buffer_rows(
        offset=offset,
        limit=limit,
        order_number_query=order_number,
        customer_query=customer,
        sort_by=sort_by,
        sort_dir=sort_dir,
        status_percent_op=status_percent_op,
        status_percent_value=status_percent_value,
    )
    return {"ok": True, **rows}


@router.post("/api/buffer/transfer")
async def assemblers_buffer_transfer(request: Request, payload: TransferBufferPayload):
    user, redirect = require_user(request)
    if redirect:
        return JSONResponse({"ok": False, "error": "unauthorized"}, status_code=401)

    forbidden = _require_buffer_transfer_api(user)
    if forbidden:
        return forbidden

    result = await run_in_threadpool(transfer_buffer_orders, payload.order_numbers)
    return {"ok": True, **result}


@router.post("/api/buffer/close")
async def assemblers_buffer_close(request: Request, payload: TransferBufferPayload):
    user, redirect = require_user(request)
    if redirect:
        return JSONResponse({"ok": False, "error": "unauthorized"}, status_code=401)

    forbidden = _require_admin_api(user)
    if forbidden:
        return forbidden

    order_numbers_to_close = payload.order_numbers

    # Якщо close_all_filtered=true, завантажити всі з буфера і відняти виключення
    if payload.close_all_filtered:
        exclude_set = set(str(v).strip().upper() for v in payload.exclude_order_numbers if v)
        all_buffer_orders = []
        offset = 0
        limit = 100
        
        while True:
            buffer_data = await load_buffer_rows(
                offset=offset,
                limit=limit,
                order_number_query=payload.order_number_filter,
                customer_query=payload.customer_filter,
            )
            batch = [str(row.get("order_number", "")).strip().upper() for row in buffer_data.get("rows", [])]
            all_buffer_orders.extend(batch)
            
            if not buffer_data.get("has_more"):
                break
            offset += len(batch)
        
        order_numbers_to_close = [o for o in all_buffer_orders if o not in exclude_set]

    result = await run_in_threadpool(close_buffer_orders, order_numbers_to_close, user, payload.analyze_only)
    return {"ok": True, **result}