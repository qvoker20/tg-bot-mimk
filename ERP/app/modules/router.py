from fastapi import APIRouter

from app.modules.assemblers.api.pages.context import set_templates as set_assemblers_templates
from app.modules.assemblers.api.router import router as assemblers_router
from app.modules.core.api import router as core_router
from app.modules.core.api import set_templates as set_core_templates


router = APIRouter()
router.include_router(core_router)
router.include_router(assemblers_router)


def set_templates(engine) -> None:
    set_core_templates(engine)
    set_assemblers_templates(engine)


__all__ = ["router", "set_templates"]
