from fastapi import APIRouter

from .pages import router as pages_router
from .v1 import activity_log, application, buffer, closed_orders, details, main_orders, schedule


router = APIRouter(prefix="/assemblers", tags=["assemblers"])
router.include_router(pages_router)
router.include_router(main_orders.router)
router.include_router(buffer.router)
router.include_router(details.router)
router.include_router(closed_orders.router)
router.include_router(activity_log.router)
router.include_router(application.router)
router.include_router(schedule.router)

__all__ = ["router"]