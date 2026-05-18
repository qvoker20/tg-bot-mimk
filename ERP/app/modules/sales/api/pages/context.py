from fastapi import Request
from fastapi.responses import RedirectResponse

from app.modules.sales.dependencies import can_access_sales_module, is_admin_user, require_user


templates = None

PAGES = {
    "main": {
        "label": "Головна",
        "path": "/sales",
        "template": "sales/page.html",
        "title": "Головна",
        "description": "Центральна сторінка відділу продажу: короткий огляд процесів, швидкі переходи та контрольні точки.",
    },
    "dashboard": {
        "label": "Дашборд",
        "path": "/sales/dashboard",
        "template": "sales/page.html",
        "title": "Дашборд",
        "description": "Місце для KPI, план-факту, воронки, активних угод і ключових цифр відділу продажу.",
    },
    "checks": {
        "label": "Перевірки",
        "path": "/sales/checks",
        "template": "sales/page.html",
        "title": "Перевірки",
        "description": "Розділ для контролю якості даних, статусів угод, проблемних записів і ручних перевірок.",
    },
    "settings": {
        "label": "Налаштування",
        "path": "/sales/settings",
        "template": "sales/page.html",
        "title": "Налаштування",
        "description": "Тут будуть налаштування доступів, довідників, правил роботи та параметрів модуля.",
    },
    "calculation": {
        "label": "Прорахунок",
        "path": "/sales/calculation",
        "template": "sales/page.html",
        "title": "Прорахунок",
        "description": "Окремий розділ для розрахунків, оцінок, калькуляцій і попередніх кошторисів.",
    },
}


def set_templates(engine):
    global templates
    templates = engine


def build_top_nav():
    return []


def build_sub_nav(active_key: str, user: dict | None):
    admin_only_pages = {"settings"}
    return [
        {
            "label": page["label"],
            "href": page["path"],
            "active": key == active_key,
        }
        for key, page in PAGES.items()
        if key not in admin_only_pages or is_admin_user(user)
    ]


def build_page_context(request: Request, active_key: str):
    user, redirect = require_user(request)
    if redirect:
        return None, redirect

    if not can_access_sales_module(user):
        return None, RedirectResponse(url="/main", status_code=303)

    page = PAGES[active_key]
    return {
        "user": user,
        "is_admin": is_admin_user(user),
        "top_nav": build_top_nav(),
        "sub_nav": build_sub_nav(active_key, user),
        "page": {**page, "key": active_key},
    }, None


def render_page(request: Request, active_key: str):
    page_context, redirect = build_page_context(request, active_key)
    if redirect:
        return redirect

    page = PAGES[active_key]
    return templates.TemplateResponse(
        request,
        page.get("template", "sales/page.html"),
        page_context,
    )