from fastapi import APIRouter, Form, Request
from fastapi.responses import JSONResponse, RedirectResponse

from app.dependencies import get_current_user
from app.services.auth_service import (
    CodeRequestRateLimitError,
    get_user_by_id,
    get_user_by_phone,
    has_active_code,
    issue_code,
    normalize_phone_380,
    verify_code,
)

from . import context

router = APIRouter(prefix="/auth", tags=["auth"])

def _render_login(
    request: Request,
    *,
    stage: str,
    phone_number: str,
    error: str | None = None,
    message: str | None = None,
):
    return context.render_template(
        request,
        "login.html",
        {
            "stage": stage,
            "phone_number": phone_number,
            "error": error,
            "message": message,
        },
        status_code=400 if error else 200,
    )

@router.post("/request-code")
async def request_code(request: Request, phone_number: str = Form(...)):
    phone_380 = normalize_phone_380(phone_number)
    if not phone_380:
        return _render_login(
            request,
            stage="phone",
            phone_number=phone_number,
            error="Введіть номер у форматі +380XXXXXXXXX або 0XXXXXXXXX.",
        )

    user = get_user_by_phone(phone_380)
    if not user:
        return _render_login(
            request,
            stage="phone",
            phone_number=f"+{phone_380}",
            error="Користувача з таким номером не знайдено в базі.",
        )

    if not user.get("telegram_id"):
        return _render_login(
            request,
            stage="phone",
            phone_number=f"+{phone_380}",
            error="Для цього номера не прив'язаний Telegram ID.",
        )

    try:
        issue_code(
            phone_380=phone_380,
            user=user,
            ip_address=request.client.host if request.client else None,
            user_agent=request.headers.get("user-agent"),
        )
    except CodeRequestRateLimitError as error:
        return _render_login(
            request,
            stage="verify" if has_active_code(phone_380) else "phone",
            phone_number=f"+{phone_380}",
            error=str(error),
        )
    except Exception:
        return _render_login(
            request,
            stage="phone",
            phone_number=f"+{phone_380}",
            error="Не вдалося надіслати код у Telegram. Переконайтесь, що ви вже запускали корпоративного бота.",
        )

    return _render_login(
        request,
        stage="verify",
        phone_number=f"+{phone_380}",
        message="Код входу надіслано у Telegram.",
    )

@router.post("/verify")
async def verify_login(request: Request, phone_number: str = Form(...), code: str = Form(...)):
    phone_380 = normalize_phone_380(phone_number)
    if not phone_380:
        return _render_login(
            request,
            stage="phone",
            phone_number=phone_number,
            error="Номер телефону некоректний.",
        )

    user, error = verify_code(
        phone_380=phone_380,
        code=code.strip(),
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )
    if error:
        return _render_login(
            request,
            stage="verify",
            phone_number=f"+{phone_380}",
            error=error, # Тут error приходить з verify_code, перевірте і той файл також!
        )

    current_user = get_user_by_id(int(user["id"])) if user and user.get("id") else None
    if not current_user:
        return _render_login(
            request,
            stage="phone",
            phone_number=f"+{phone_380}",
            error="Користувача більше немає в системі. Запросіть код ще раз.",
        )

    request.session["user"] = {"id": current_user["id"]}
    return RedirectResponse(url="/main", status_code=303)

@router.get("/session")
async def session_state(request: Request):
    user = get_current_user(request)
    headers = {"Cache-Control": "no-store"}
    if not user:
        return JSONResponse({"authenticated": False}, status_code=401, headers=headers)

    return JSONResponse({"authenticated": True, "user": user}, headers=headers)

@router.post("/logout")
async def logout(request: Request):
    request.session.clear()
    return RedirectResponse(url="/", status_code=303)