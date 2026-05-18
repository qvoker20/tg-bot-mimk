from fastapi import APIRouter, Request

from . import context


router = APIRouter()


def _build_dashboard_statuses() -> list[str]:
    return ["Нові", "Перевірка", "Переробка", "Перевірено", "Передано в КБ", "Інші"]


def _build_dashboard_orders() -> list[dict]:
    return []


def _build_subcontract_options() -> list[str]:
    return [
        "Замір",
        "Малярний цех",
        "Метал",
        "Шпон",
        "Пластик HPL",
        "Столярний цех",
        "М'який цех",
        "Штучний камінь",
        "Компакт-плита",
        "Cтільниця ДСП",
        "Розсувні системи",
        "Скло/дзеркало",
        "Рамкові фасади",
        "Керамограніт",
    ]


@router.get("/")
async def sales_main_page(request: Request):
    return context.render_page(request, "main")


@router.get("/dashboard")
async def sales_dashboard_page(request: Request):
    page_context, redirect = context.build_page_context(request, "dashboard")
    if redirect:
        return redirect

    page_context["dashboard_statuses"] = _build_dashboard_statuses()
    page_context["dashboard_orders"] = _build_dashboard_orders()
    page_context["subcontract_options"] = _build_subcontract_options()
    return context.templates.TemplateResponse(request, "sales/page.html", page_context)


@router.get("/checks")
async def sales_checks_page(request: Request):
    return context.render_page(request, "checks")


@router.get("/settings")
async def sales_settings_page(request: Request):
    return context.render_page(request, "settings")


@router.get("/calculation")
async def sales_calculation_page(request: Request):
    return context.render_page(request, "calculation")