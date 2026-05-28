from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from ..services.auth_service import get_fresh_role

router = APIRouter(tags=["pages"])


def set_templates(templates: Jinja2Templates):
    router.templates = templates


def _user(request: Request):
    user = request.session.get("user")
    if not user:
        return None

    role = get_fresh_role(user)
    if role:
        user = dict(user)
        user["role"] = role
        request.session["user"] = user
    return user


def _context(request: Request, title: str):
    return {"request": request, "user": _user(request), "page_title": title}


def _has_zapusky_access(request: Request) -> bool:
    user = _user(request) or {}
    role = str(user.get("role") or "").strip().lower()
    return role in {"admin", "адмін", "технолог виробництво", "технолог виробництва"}


def _has_komplekt_access(request: Request) -> bool:
    user = _user(request) or {}
    role = str(user.get("role") or "").strip().lower()
    return role in {"майстер цеху", "комплектувальник", "admin", "директор з виробництва"}


@router.get("/", response_class=HTMLResponse)
async def root(request: Request):
    if _user(request):
        return RedirectResponse(url="/reestr", status_code=302)
    return RedirectResponse(url="/login", status_code=302)


@router.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    if _user(request):
        return RedirectResponse(url="/reestr", status_code=302)
    return router.templates.TemplateResponse("login.html", {"request": request})


@router.get("/main", response_class=HTMLResponse)
async def main_page(request: Request):
    if not _user(request):
        return RedirectResponse(url="/login", status_code=302)
    return RedirectResponse(url="/reestr", status_code=302)


@router.get("/komplektuvannya", response_class=HTMLResponse)
async def komplektuvannya_page(request: Request):
    if not _user(request):
        return RedirectResponse(url="/login", status_code=302)
    if not _has_komplekt_access(request):
        return RedirectResponse(url="/reestr", status_code=302)
    return router.templates.TemplateResponse("komplektuvannya.html", _context(request, "Комплектування"))


@router.get("/zapusky", response_class=HTMLResponse)
async def zapusky_page(request: Request):
    if not _user(request):
        return RedirectResponse(url="/login", status_code=302)
    if not _has_zapusky_access(request):
        return RedirectResponse(url="/reestr", status_code=302)
    return router.templates.TemplateResponse("zapusky.html", _context(request, "Запуски"))


@router.get("/reestr", response_class=HTMLResponse)
async def reestr_page(request: Request):
    if not _user(request):
        return RedirectResponse(url="/login", status_code=302)
    return router.templates.TemplateResponse("reestr.html", _context(request, "Реєстр"))


@router.post("/logout")
async def logout(request: Request):
    request.session.clear()
    return RedirectResponse(url="/login", status_code=302)
