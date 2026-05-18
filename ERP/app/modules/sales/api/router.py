from fastapi import APIRouter

from .pages import router as pages_router


router = APIRouter(prefix="/sales", tags=["sales"])
router.include_router(pages_router)

__all__ = ["router"]