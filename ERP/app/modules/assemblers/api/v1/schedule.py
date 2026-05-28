from fastapi import APIRouter, Body, Request
from fastapi.responses import JSONResponse
from starlette.concurrency import run_in_threadpool

from app.modules.assemblers.dependencies import (
    can_manage_schedule_subdivision,
    is_admin_user,
    require_user,
)
from app.modules.assemblers.services.schedule import (
    create_schedule_tasks,
    edit_schedule_tasks,
    load_schedule_tasks,
)
from app.modules.assemblers.services.schedule import run_schedule_daily_cutoff_catchup
from app.modules.assemblers.services.activity_log import record_activity_event


router = APIRouter()


@router.get("/api/schedule/tasks")
async def assemblers_schedule_tasks_api(
    request: Request,
    subdivision: str = "",
    start_date: str = "",
):
    _, redirect = require_user(request)
    if redirect:
        return JSONResponse({"ok": False, "error": "unauthorized"}, status_code=401)

    try:
        payload = await run_in_threadpool(load_schedule_tasks, subdivision, start_date)
    except ValueError as error:
        return JSONResponse({"ok": False, "error": str(error)}, status_code=400)

    return {"ok": True, **payload}


@router.post("/api/schedule/tasks")
async def assemblers_schedule_tasks_create_api(request: Request):
    user, redirect = require_user(request)
    if redirect:
        return JSONResponse({"ok": False, "error": "unauthorized"}, status_code=401)

    try:
        payload = await request.json()
    except Exception:
        return JSONResponse({"ok": False, "error": "Некоректні дані запиту."}, status_code=400)

    if not isinstance(payload, dict):
        return JSONResponse({"ok": False, "error": "Некоректні дані запиту."}, status_code=400)

    subdivision = payload.get("subdivision", "")
    if not can_manage_schedule_subdivision(user, subdivision):
        return JSONResponse({"ok": False, "error": "Недостатньо прав для керування цим графіком."}, status_code=403)

    try:
        result = await run_in_threadpool(
            create_schedule_tasks,
            subdivision=subdivision,
            task_type=payload.get("task_type", ""),
            cells=payload.get("cells") or [],
            order_number=payload.get("order_number"),
            selected_parts=payload.get("selected_parts") or [],
            description=payload.get("description"),
            actor=user,
        )
    except ValueError as error:
        return JSONResponse({"ok": False, "error": str(error)}, status_code=400)

    created_count = int(result.get("created_count") or 0)
    return {
        "ok": True,
        **result,
        "message": f"Задачі записано в базу: {created_count}.",
    }


@router.post("/api/schedule/tasks/edit")
async def assemblers_schedule_tasks_edit_api(request: Request):
    user, redirect = require_user(request)
    if redirect:
        return JSONResponse({"ok": False, "error": "unauthorized"}, status_code=401)

    try:
        payload = await request.json()
    except Exception:
        return JSONResponse({"ok": False, "error": "Некоректні дані запиту."}, status_code=400)

    if not isinstance(payload, dict):
        return JSONResponse({"ok": False, "error": "Некоректні дані запиту."}, status_code=400)

    subdivision = payload.get("subdivision", "")
    if not can_manage_schedule_subdivision(user, subdivision):
        return JSONResponse({"ok": False, "error": "Недостатньо прав для керування цим графіком."}, status_code=403)

    if payload.get("action") == "admin_delete" and not is_admin_user(user):
        return JSONResponse({"ok": False, "error": "Примусове видалення доступне лише адміністратору."}, status_code=403)

    try:
        result = await run_in_threadpool(
            edit_schedule_tasks,
            subdivision=subdivision,
            action=payload.get("action", ""),
            task_ids=payload.get("task_ids") or [],
            order_number=payload.get("order_number"),
            selected_parts=payload.get("selected_parts") or [],
            actor=user,
        )
    except ValueError as error:
        return JSONResponse({"ok": False, "error": str(error)}, status_code=400)

    return {"ok": True, **result, "message": "Задачі видалено."}


@router.post("/api/schedule/run_cutoff")
async def assemblers_run_cutoff_api(
    request: Request,
    days_back: int = Body(31),
    force_current_day: bool = Body(True),
):
    """Manual endpoint to run daily cutoff catchup (admin only).

    Calls `run_schedule_daily_cutoff_catchup` in a threadpool and records
    an activity journal entry with the results.
    """
    user, redirect = require_user(request)
    if redirect:
        return JSONResponse({"ok": False, "error": "unauthorized"}, status_code=401)

    if not is_admin_user(user):
        return JSONResponse({"ok": False, "error": "forbidden"}, status_code=403)

    try:
        summary = await run_in_threadpool(
            run_schedule_daily_cutoff_catchup,
            days_back=days_back,
            force_current_day=force_current_day,
        )
    except Exception as error:
        try:
            await run_in_threadpool(
                record_activity_event,
                action_key="schedule.system.run_cutoff",
                action_label="Помилка при запуску автозакриття",
                description=str(error),
                actor=user,
                entity_type="maintenance",
                source_table="system",
                source_op="run_cutoff",
                details={"error": str(error)},
            )
        except Exception:
            pass
        return JSONResponse({"ok": False, "error": str(error)}, status_code=500)

    # record successful run in activity journal
    try:
        await run_in_threadpool(
            record_activity_event,
            action_key="schedule.system.run_cutoff",
            action_label="Запущено автозакриття (ручний запуск)",
            description=f"Ручний запуск автозакриття: processed_days={summary.get('processed_days')}",
            actor=user,
            entity_type="maintenance",
            source_table="system",
            source_op="run_cutoff",
            details=summary,
        )
    except Exception:
        pass

    return {"ok": True, **summary}
