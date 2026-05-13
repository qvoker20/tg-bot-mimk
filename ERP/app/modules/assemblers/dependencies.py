from fastapi import Request
from fastapi.responses import RedirectResponse

from app.dependencies import (
    can_access_assemblers_module,
    can_manage_main_orders,
    can_manage_schedule_subdivision,
    can_transfer_buffer_orders,
    get_current_user,
    is_admin_user,
)


def require_user(request: Request):
    """Return authenticated user or redirect response for unauthorized access."""
    user = get_current_user(request)
    if not user:
        return None, RedirectResponse(url="/", status_code=303)
    return user, None

__all__ = [
    "can_access_assemblers_module",
    "can_manage_main_orders",
    "can_manage_schedule_subdivision",
    "can_transfer_buffer_orders",
    "get_current_user",
    "is_admin_user",
    "require_user",
]