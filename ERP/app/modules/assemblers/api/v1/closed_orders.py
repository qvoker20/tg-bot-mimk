from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from starlette.concurrency import run_in_threadpool

from app.modules.assemblers.dependencies import require_user
from app.modules.assemblers.services.main import load_main_rows, reopen_closed_orders


router = APIRouter()


@router.get("/api/closed-orders")
async def assemblers_closed_orders_api(request: Request, offset: int = 0, limit: int = 30):
    _, redirect = require_user(request)
    if redirect:
        return JSONResponse({"ok": False, "error": "unauthorized"}, status_code=401)

    rows = await run_in_threadpool(load_main_rows, offset=offset, limit=limit, closed_only=True)
    return {"ok": True, **rows}

@router.post("/api/closed-orders/reopen")
async def assemblers_reopen_closed_orders(request: Request):
    user, redirect = require_user(request)
    if redirect:
        return JSONResponse({"ok": False, "error": "unauthorized"}, status_code=401)

    from app.modules.assemblers.dependencies import is_admin_user

    if not is_admin_user(user):
        return JSONResponse(
            {"ok": False, "error": "Тільки адмін може повернути закриті замовлення."},
            status_code=403,
        )

    try:
        payload = await request.json()
    except Exception:
        return JSONResponse({"ok": False, "error": "Некоректні дані запиту."}, status_code=400)

    order_numbers = payload.get("order_numbers", [])
    if not isinstance(order_numbers, list):
        return JSONResponse({"ok": False, "error": "order_numbers мають бути списком."}, status_code=400)

    result = await run_in_threadpool(reopen_closed_orders, order_numbers, user)
    return {
        "ok": True,
        **result,
        "message": f"Повернено {result.get('reopened_orders', 0)} замовлень в активні.",
    }