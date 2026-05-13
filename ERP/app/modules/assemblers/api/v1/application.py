from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from starlette.concurrency import run_in_threadpool

from app.modules.assemblers.dependencies import require_user
from app.modules.assemblers.services.schedule import (
    load_user_schedule_tasks,
    update_user_task_status,
)


router = APIRouter()


@router.get("/api/app/tasks")
async def assemblers_application_tasks_api(request: Request, day: str = ""):
    user, redirect = require_user(request)
    if redirect:
        return JSONResponse({"ok": False, "error": "unauthorized"}, status_code=401)

    try:
        payload = await run_in_threadpool(load_user_schedule_tasks, source_user_id=user.get("id"), day=day)
    except ValueError as error:
        return JSONResponse({"ok": False, "error": str(error)}, status_code=400)

    return {"ok": True, **payload}


@router.post("/api/app/tasks/{task_id}/action")
async def assemblers_application_task_action_api(request: Request, task_id: int):
    user, redirect = require_user(request)
    if redirect:
        return JSONResponse({"ok": False, "error": "unauthorized"}, status_code=401)

    try:
        payload = await request.json()
    except Exception:
        return JSONResponse({"ok": False, "error": "Некоректні дані запиту."}, status_code=400)

    if not isinstance(payload, dict):
        return JSONResponse({"ok": False, "error": "Некоректні дані запиту."}, status_code=400)

    try:
        result = await run_in_threadpool(
            update_user_task_status,
            source_user_id=user.get("id"),
            task_id=task_id,
            action=payload.get("action", ""),
            pause_reason=payload.get("pause_reason"),
            location=payload.get("location") or {},
            selected_products=payload.get("selected_products") or [],
        )
    except ValueError as error:
        return JSONResponse({"ok": False, "error": str(error)}, status_code=400)

    return {"ok": True, **result}
