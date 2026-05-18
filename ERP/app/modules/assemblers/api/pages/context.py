from fastapi import Request
from fastapi.responses import RedirectResponse
from starlette.concurrency import run_in_threadpool

from app.modules.assemblers.dependencies import (
    can_manage_main_orders,
    can_manage_assemblers_staff,
    is_admin_user,
    require_user,
)
from app.modules.assemblers.services import (
    ensure_activity_log_schema,
    ensure_schema,
    ensure_settings_schema,
    ensure_staff_schema,
    record_activity_event,
)


templates = None

PAGES = {
    "main": {
        "label": "Головна",
        "path": "/assemblers",
        "template": "assemblers/main.html",
        "script": "/js/assemblers/assemblers-main.js",
        "title": "Головна сторінка збиральників",
        "description": "Тут буде оперативна зведена інформація по роботі збирального цеху: активні задачі, статуси та контрольні точки.",
    },
    "staff": {
        "label": "Збиральники",
        "path": "/assemblers/staff",
        "template": "assemblers/staff.html",
        "script": "/js/assemblers/assemblers-staff.js",
        "title": "Збиральники",
        "description": "Список користувачів збирального напряму з корпоративної бази та їх прив'язка до підрозділів і бригад.",
    },
    "application": {
        "label": "Додаток Збиральників",
        "path": "/assemblers/app",
        "template": "assemblers/application.html",
        "script": "/js/assemblers/assemblers-application.js",
        "title": "Додаток Збиральників",
        "description": "Окремий розділ під матеріали, посилання та подальші інструменти для додатка збиральників.",
        "new_tab": True,
    },
    "settings": {
        "label": "Налаштування",
        "path": "/assemblers/settings",
        "template": "assemblers/settings.html",
        "title": "Налаштування",
        "description": "Розділ зарезервовано під окремі налаштування, які будуть додані пізніше.",
    },
    "details": {
        "label": "Деталі",
        "path": "/assemblers/details",
        "template": "assemblers/details.html",
        "script": "/js/assemblers/assemblers-details.js",
        "title": "Деталі",
        "description": "Розділ для деталізації по замовленнях, позиціях, комплектуванню та робочих нюансах цеху.",
    },
    "closed_orders": {
        "label": "Закриті замовлення",
        "path": "/assemblers/closed-orders",
        "template": "assemblers/closed_orders.html",
        "script": "/js/assemblers/assemblers-closed-orders.js",
        "title": "Закриті замовлення",
        "description": "Тут буде список уже закритих замовлень з можливістю швидкого перегляду та подальшого аналізу.",
    },
    "private_schedule": {
        "label": "Графік Приват",
        "path": "/assemblers/private-schedule",
        "template": "assemblers/private_schedule.html",
        "script": "/js/assemblers/assemblers-schedule.js",
        "title": "Графік Приват",
        "description": "Окрема сторінка для приватного графіка виробництва і планування навантаження по цьому напрямку.",
    },
    "tender_schedule": {
        "label": "Графік Тендер",
        "path": "/assemblers/tender-schedule",
        "template": "assemblers/tender_schedule.html",
        "script": "/js/assemblers/assemblers-schedule.js",
        "title": "Графік Тендер",
        "description": "Окрема сторінка для тендерного графіка, щоб розвести планування між різними потоками роботи.",
    },
    "buffer": {
        "label": "Буфер",
        "path": "/assemblers/buffer",
        "template": "assemblers/buffer.html",
        "script": "/js/assemblers/assemblers-buffer.js",
        "title": "Буфер",
        "description": "Буферний розділ для тимчасових замовлень, затримок, перенесень і ручного контролю черги.",
    },
    "bulk_operations": {
        "label": "Масові операції",
        "path": "/assemblers/bulk-operations",
        "template": "assemblers/bulk_operations.html",
        "script": "/js/bulk-operations.js",
        "title": "Масові операції",
        "description": "Управління масовим закриттям та повертанням замовлень з буфера.",
    },
    "activity_log": {
        "label": "Журнал дій",
        "path": "/assemblers/activity-log",
        "template": "assemblers/activity_log.html",
        "script": "/js/assemblers/assemblers-activity-log.js",
        "title": "Журнал дій",
        "description": "Журнал дій збиральників із фільтрами, пошуком по виконавцю, замовленню та типу події.",
    },
}


def set_templates(engine):
    global templates
    templates = engine


def build_top_nav():
    return []


def build_sub_nav(active_key: str, user: dict | None):
    admin_only_pages = {"settings", "bulk_operations", "activity_log"}
    return [
        {
            "label": page["label"],
            "href": page["path"],
            "active": key == active_key,
            "new_tab": bool(page.get("new_tab")),
        }
        for key, page in PAGES.items()
        if key not in admin_only_pages or is_admin_user(user)
    ]


def build_page_context(request: Request, active_key: str):
    user, redirect = require_user(request)
    if redirect:
        return None, redirect

    ensure_schema()
    ensure_staff_schema()
    ensure_settings_schema()
    ensure_activity_log_schema()

    page = PAGES[active_key]
    return {
        "user": user,
        "is_admin": is_admin_user(user),
        "can_manage_staff": can_manage_assemblers_staff(user),
        "can_manage_main_orders": can_manage_main_orders(user),
        "top_nav": build_top_nav(),
        "sub_nav": build_sub_nav(active_key, user),
        "page": {**page, "key": active_key},
        "page_script": page.get("script"),
    }, None


def render_page(request: Request, active_key: str):
    page_context, redirect = build_page_context(request, active_key)
    if redirect:
        return redirect

    page = PAGES[active_key]
    return templates.TemplateResponse(
        request,
        page.get("template", "assemblers/main.html"),
        page_context,
    )


async def log_page_visit(request: Request, active_key: str, page_context: dict | None = None) -> None:
    return
