from datetime import date, timedelta
from urllib.parse import quote

from fastapi import APIRouter, Form, Request
from fastapi.responses import RedirectResponse
from starlette.concurrency import run_in_threadpool

from app.modules.assemblers.dependencies import can_manage_schedule_subdivision, is_admin_user
from app.modules.assemblers.services import (
    ALLOWED_SUBDIVISIONS,
    enqueue_detail_metrics_recalculation,
    load_assembler_staff,
    load_assembly_day_cost,
    load_assembly_workday_hours,
    save_assembly_day_cost,
    save_assembly_workday_hours,
    save_staff_assignment,
)

from . import context


router = APIRouter()

DAY_NAMES = ["ПН", "ВТ", "СР", "ЧТ", "ПТ", "СБ", "НД"]


def _build_schedule_dates(total_days: int = 14) -> list[dict]:
    today = date.today()
    start = today - timedelta(days=today.weekday())
    return [
        {
            "iso": current.isoformat(),
            "label": DAY_NAMES[current.weekday()],
            "day": current.strftime("%d.%m.%Y"),
            "is_today": current == today,
            "is_weekend": current.weekday() >= 5,
        }
        for current in (start + timedelta(days=offset) for offset in range(total_days))
    ]


def _build_schedule_rows(staff_rows: list[dict], subdivision: str) -> list[dict]:
    rows = []
    for row in staff_rows:
        if row.get("subdivision_value") != subdivision:
            continue
        rows.append(
            {
                "source_user_id": row.get("source_user_id"),
                "name": row.get("name") or "—",
                "brigade": row.get("brigade_number") if row.get("brigade_number") != "—" else "—",
            }
        )

    return rows


@router.get("/")
async def assemblers_main_page(request: Request):
    page_context, redirect = context.build_page_context(request, "main")
    if redirect:
        return redirect
    return context.templates.TemplateResponse(request, "assemblers/main.html", page_context)


@router.get("/staff")
async def assemblers_staff_page(request: Request):
    page_context, redirect = context.build_page_context(request, "staff")
    if redirect:
        return redirect

    page_context["staff_rows"] = await run_in_threadpool(load_assembler_staff)
    page_context["subdivision_options"] = ALLOWED_SUBDIVISIONS
    page_context["alert_kind"] = "error" if request.query_params.get("error", "") else "info"
    page_context["alert_text"] = (
        request.query_params.get("error", "")
        or ("Налаштування користувача збережено." if request.query_params.get("saved") == "1" else "")
    )
    return context.templates.TemplateResponse(request, "assemblers/staff.html", page_context)


@router.post("/staff")
async def assemblers_staff_save(
    request: Request,
    source_user_id: int = Form(...),
    subdivision: str = Form(...),
    brigade_number: int = Form(...),
):
    page_context, redirect = context.build_page_context(request, "staff")
    if redirect:
        return redirect

    if not is_admin_user(page_context["user"]):
        return RedirectResponse(url="/assemblers/staff?error=Лише+admin+може+змінювати+налаштування", status_code=303)

    try:
        await run_in_threadpool(save_staff_assignment, source_user_id, subdivision, brigade_number)
    except ValueError as error:
        encoded = quote(str(error))
        return RedirectResponse(url=f"/assemblers/staff?error={encoded}", status_code=303)

    return RedirectResponse(url="/assemblers/staff?saved=1", status_code=303)


@router.get("/settings")
async def assemblers_settings_page(request: Request):
    page_context, redirect = context.build_page_context(request, "settings")
    if redirect:
        return redirect

    if not is_admin_user(page_context["user"]):
        return RedirectResponse(url="/assemblers", status_code=303)

    page_context["assembly_day_cost"] = await run_in_threadpool(load_assembly_day_cost)
    page_context["assembly_workday_hours"] = await run_in_threadpool(load_assembly_workday_hours)
    page_context["alert_kind"] = "error" if request.query_params.get("error", "") else "info"
    page_context["alert_text"] = (
        request.query_params.get("error", "")
        or ("Налаштування збережено." if request.query_params.get("saved") == "1" else "")
    )

    return context.templates.TemplateResponse(request, "assemblers/settings.html", page_context)


@router.post("/settings")
async def assemblers_settings_save(
    request: Request,
    assembly_day_cost: str = Form(...),
    assembly_workday_hours: str = Form("8"),
):
    page_context, redirect = context.build_page_context(request, "settings")
    if redirect:
        return redirect

    if not is_admin_user(page_context["user"]):
        return RedirectResponse(url="/assemblers", status_code=303)

    try:
        await run_in_threadpool(save_assembly_day_cost, assembly_day_cost)
        await run_in_threadpool(save_assembly_workday_hours, assembly_workday_hours)
    except ValueError as error:
        return RedirectResponse(url=f"/assemblers/settings?error={quote(str(error))}", status_code=303)

    await run_in_threadpool(enqueue_detail_metrics_recalculation, source="settings_update")

    return RedirectResponse(url="/assemblers/settings?saved=1", status_code=303)


@router.get("/details")
async def assemblers_details_page(request: Request):
    page_context, redirect = context.build_page_context(request, "details")
    if redirect:
        return redirect
    await context.log_page_visit(request, "details", page_context)
    return context.templates.TemplateResponse(request, "assemblers/details.html", page_context)


@router.get("/buffer")
async def assemblers_buffer_page(request: Request):
    page_context, redirect = context.build_page_context(request, "buffer")
    if redirect:
        return redirect
    await context.log_page_visit(request, "buffer", page_context)
    return context.templates.TemplateResponse(request, "assemblers/buffer.html", page_context)


@router.get("/closed-orders")
async def assemblers_closed_orders_page(request: Request):
    page_context, redirect = context.build_page_context(request, "closed_orders")
    if redirect:
        return redirect
    await context.log_page_visit(request, "closed_orders", page_context)
    return context.templates.TemplateResponse(request, "assemblers/closed_orders.html", page_context)


@router.get("/private-schedule")
async def assemblers_private_schedule_page(request: Request):
    page_context, redirect = context.build_page_context(request, "private_schedule")
    if redirect:
        return redirect

    await context.log_page_visit(request, "private_schedule", page_context)
    staff_rows = await run_in_threadpool(load_assembler_staff)
    schedule_rows = _build_schedule_rows(staff_rows, "Приват")
    page_context["schedule_rows"] = schedule_rows
    page_context["schedule_dates"] = _build_schedule_dates(7)
    page_context["schedule_initial_date"] = date.today().isoformat()
    page_context["schedule_subdivision"] = "Приват"
    page_context["schedule_can_manage"] = can_manage_schedule_subdivision(page_context["user"], "Приват")
    page_context["schedule_summary"] = {
        "brigades": len({row["brigade"] for row in schedule_rows if row["brigade"] != "—"}),
        "assemblers": len(schedule_rows),
    }
    return context.templates.TemplateResponse(request, "assemblers/private_schedule.html", page_context)


@router.get("/tender-schedule")
async def assemblers_tender_schedule_page(request: Request):
    page_context, redirect = context.build_page_context(request, "tender_schedule")
    if redirect:
        return redirect

    await context.log_page_visit(request, "tender_schedule", page_context)
    staff_rows = await run_in_threadpool(load_assembler_staff)
    schedule_rows = _build_schedule_rows(staff_rows, "Тендер")
    page_context["schedule_rows"] = schedule_rows
    page_context["schedule_dates"] = _build_schedule_dates(7)
    page_context["schedule_initial_date"] = date.today().isoformat()
    page_context["schedule_subdivision"] = "Тендер"
    page_context["schedule_can_manage"] = can_manage_schedule_subdivision(page_context["user"], "Тендер")
    page_context["schedule_summary"] = {
        "brigades": len({row["brigade"] for row in schedule_rows if row["brigade"] != "—"}),
        "assemblers": len(schedule_rows),
    }
    return context.templates.TemplateResponse(request, "assemblers/tender_schedule.html", page_context)


@router.get("/app")
async def assemblers_application_page(request: Request):
    page_context, redirect = context.build_page_context(request, "application")
    if redirect:
        return redirect

    await context.log_page_visit(request, "application", page_context)
    page_context["application_initial_date"] = date.today().isoformat()
    return context.templates.TemplateResponse(request, "assemblers/application.html", page_context)


@router.get("/bulk-operations")
async def assemblers_bulk_operations_page(request: Request):
    page_context, redirect = context.build_page_context(request, "bulk_operations")
    if redirect:
        return redirect

    await context.log_page_visit(request, "bulk_operations", page_context)
    if not is_admin_user(page_context["user"]):
        return RedirectResponse(url="/assemblers", status_code=303)

    return context.templates.TemplateResponse(request, "assemblers/bulk_operations.html", page_context)


@router.get("/activity-log")
async def assemblers_activity_log_page(request: Request):
    page_context, redirect = context.build_page_context(request, "activity_log")
    if redirect:
        return redirect

    if not is_admin_user(page_context["user"]):
        return RedirectResponse(url="/assemblers", status_code=303)

    return context.templates.TemplateResponse(request, "assemblers/activity_log.html", page_context)
