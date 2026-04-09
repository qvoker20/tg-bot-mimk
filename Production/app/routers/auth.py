from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, RedirectResponse

from ..schemas.auth import RequestCodePayload, VerifyCodePayload
from ..services.auth_service import (
    LOGIN_CODES,
    get_user_by_phone,
    issue_code,
    normalize_phone_380,
    verify_code,
)

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.post("/request-code")
async def request_code(payload: RequestCodePayload, request: Request):
    phone_380 = normalize_phone_380(payload.phone)
    if not phone_380:
        return JSONResponse(
            {"ok": False, "error": "Невірний номер. Вводьте у форматі 380XXXXXXXXX."},
            status_code=400,
        )

    user = get_user_by_phone(phone_380)
    if not user:
        return JSONResponse(
            {"ok": False, "error": "Користувача з таким номером не знайдено."},
            status_code=404,
        )

    if not user.get("telegram_id"):
        return JSONResponse(
            {"ok": False, "error": "Для користувача не вказано Telegram ID."},
            status_code=400,
        )

    ip = request.headers.get("x-forwarded-for") or (request.client.host if request.client else "unknown")
    user_agent = request.headers.get("user-agent", "")[:120]
    where_text = f"Production Web, IP: {ip}, UA: {user_agent or '-'}"

    try:
        issue_code(phone_380, user, where_text)
    except Exception as exc:
        LOGIN_CODES.pop(phone_380, None)
        return JSONResponse(
            {"ok": False, "error": f"Не вдалося надіслати код: {exc}"},
            status_code=500,
        )

    return {"ok": True, "message": "Код відправлено у Telegram."}


@router.post("/verify")
async def verify(payload: VerifyCodePayload, request: Request):
    phone_380 = normalize_phone_380(payload.phone)
    code = str(payload.code or "").strip()

    if not phone_380:
        return JSONResponse(
            {"ok": False, "error": "Невірний номер. Вводьте у форматі 380XXXXXXXXX."},
            status_code=400,
        )

    user, error = verify_code(phone_380, code)
    if error:
        return JSONResponse({"ok": False, "error": error}, status_code=400)

    request.session["user"] = user
    return {"ok": True, "redirect": "/reestr"}


@router.get("/me")
async def me(request: Request):
    user = request.session.get("user")
    if not user:
        return JSONResponse({"ok": False}, status_code=401)
    return {"ok": True, "user": user}


@router.post("/logout")
async def api_logout(request: Request):
    request.session.clear()
    return {"ok": True}


@router.post("/logout-web")
async def logout_web(request: Request):
    request.session.clear()
    return RedirectResponse(url="/login", status_code=302)
