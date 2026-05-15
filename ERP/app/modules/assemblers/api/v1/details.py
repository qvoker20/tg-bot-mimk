from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from starlette.concurrency import run_in_threadpool

from app.modules.assemblers.dependencies import require_user
from app.modules.assemblers.services.registry import (
	load_detail_rows,
	search_detail_rows_by_order,
)


router = APIRouter()


@router.get("/api/details")
async def assemblers_details_api(
	request: Request,
	offset: int = 0,
	limit: int = 30,
	order_number: str = "",
	customer: str = "",
	product: str = "",
	requires_assembly: str = "",
	requires_install: str = "",
):
	_, redirect = require_user(request)
	if redirect:
		return JSONResponse({"ok": False, "error": "unauthorized"}, status_code=401)

	rows = await run_in_threadpool(
		load_detail_rows,
		offset=offset,
		limit=limit,
		order_number=order_number,
		customer=customer,
		product=product,
		requires_assembly=requires_assembly,
		requires_install=requires_install,
	)
	return {"ok": True, **rows}


@router.get("/api/details/search")
async def assemblers_details_search_api(request: Request, order_number: str = ""):
	_, redirect = require_user(request)
	if redirect:
		return JSONResponse({"ok": False, "error": "unauthorized"}, status_code=401)

	payload = await run_in_threadpool(search_detail_rows_by_order, order_number)
	return {"ok": True, **payload}

