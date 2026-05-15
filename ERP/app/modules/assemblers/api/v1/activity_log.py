from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from starlette.concurrency import run_in_threadpool

from app.modules.assemblers.dependencies import is_admin_user, require_user
from app.modules.assemblers.services import load_activity_log_rows


router = APIRouter()


@router.get("/api/activity-log")
async def assemblers_activity_log_api(
    request: Request,
    offset: int = 0,
    limit: int = 30,
    search: str = "",
    actor: str = "",
    order_number: str = "",
    subdivision: str = "",
    source: str = "",
    date_from: str = "",
    date_to: str = "",
):
    user, redirect = require_user(request)
    if redirect:
        return JSONResponse({"ok": False, "error": "unauthorized"}, status_code=401)

    if not is_admin_user(user):
        return JSONResponse({"ok": False, "error": "forbidden"}, status_code=403)

    payload = await run_in_threadpool(
        load_activity_log_rows,
        offset=offset,
        limit=limit,
        search=search,
        actor=actor,
        order_number=order_number,
        subdivision=subdivision,
        source=source,
        date_from=date_from,
        date_to=date_to,
    )
    return {"ok": True, **payload}