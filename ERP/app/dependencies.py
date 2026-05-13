from fastapi import Request
from fastapi.responses import RedirectResponse

from .services.auth_service import get_user_by_id


SCHEDULE_MANAGE_ROLES = {
    "приват": {"admin", "керівник збиральників", "керівник збиральників приват"},
    "тендер": {"admin", "керівник збиральників", "керівник збиральників тендер"},
}

BUFFER_TRANSFER_ROLES = {
    "admin",
    "керівник збиральників",
    "керівник збиральників приват",
    "керівник збиральників тендер",
}

ASSEMBLERS_MODULE_ROLES = {
    "admin",
    "збиральник",
    "керівник збиральників",
    "керівник збиральників приват",
    "керівник збиральників тендер",
}


def get_current_user(request: Request):
    session_user = request.session.get("user")
    if not isinstance(session_user, dict):
        return None

    user_id = session_user.get("id")
    if not user_id:
        request.session.pop("user", None)
        return None

    fresh_user = get_user_by_id(int(user_id))
    if not fresh_user:
        request.session.pop("user", None)
        return None

    if session_user != fresh_user:
        request.session["user"] = fresh_user

    return fresh_user


def is_admin_user(user: dict | None) -> bool:
    if not isinstance(user, dict):
        return False
    return str(user.get("role") or "").strip().casefold() == "admin"


def can_manage_schedule_subdivision(user: dict | None, subdivision: str) -> bool:
    if not isinstance(user, dict):
        return False

    normalized_subdivision = str(subdivision or "").strip().casefold()
    normalized_role = str(user.get("role") or "").strip().casefold()
    return normalized_role in SCHEDULE_MANAGE_ROLES.get(normalized_subdivision, set())


def can_transfer_buffer_orders(user: dict | None) -> bool:
    if not isinstance(user, dict):
        return False

    normalized_role = str(user.get("role") or "").strip().casefold()
    return normalized_role in BUFFER_TRANSFER_ROLES


def can_manage_main_orders(user: dict | None) -> bool:
    return can_transfer_buffer_orders(user)


def can_access_assemblers_module(user: dict | None) -> bool:
    if not isinstance(user, dict):
        return False

    normalized_role = str(user.get("role") or "").strip().casefold()
    return normalized_role in ASSEMBLERS_MODULE_ROLES


def require_user(request: Request):
    user = get_current_user(request)
    if not user:
        return RedirectResponse(url="/", status_code=303)
    return user