from fastapi import APIRouter, Request
from fastapi.responses import RedirectResponse

from app.dependencies import can_access_assemblers_module, get_current_user

from . import context


router = APIRouter()


@router.get("/")
async def login_page(request: Request):
    user = get_current_user(request)
    if user:
        return RedirectResponse(url="/main", status_code=303)

    return context.render_template(
        request,
        "login.html",
        {
            "stage": "phone",
            "phone_number": "",
            "error": None,
            "message": None,
        },
    )


@router.get("/main")
async def main_page(request: Request):
    user = get_current_user(request)
    if not user:
        return RedirectResponse(url="/", status_code=303)

    return context.render_template(
        request,
        "main.html",
        {
            "user": user,
            "can_access_assemblers_module": can_access_assemblers_module(user),
        },
    )
