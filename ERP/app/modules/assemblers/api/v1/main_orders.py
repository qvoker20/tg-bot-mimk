from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from starlette.concurrency import run_in_threadpool

from app.modules.assemblers.dependencies import can_manage_main_orders, require_user
from app.modules.assemblers.services.main import (
    load_main_filter_options,
    load_main_order_card,
    load_main_rows,
    update_main_order_card,
	update_main_order_status,
)
from app.modules.assemblers.services.registry import (
    load_column_preferences,
    save_column_preferences,
)


router = APIRouter()


@router.get("/api/main")
async def assemblers_main_api(
	request: Request,
	offset: int = 0,
	limit: int = 30,
	order_number: str = "",
	customer: str = "",
	status: str = "",
	order_type: str = "",
	deadline_bucket: str = "",
):
	_, redirect = require_user(request)
	if redirect:
		return JSONResponse({"ok": False, "error": "unauthorized"}, status_code=401)

	rows = await run_in_threadpool(
		load_main_rows,
		offset=offset,
		limit=limit,
		order_number_query=order_number,
		customer_query=customer,
		status_query=status,
		order_type_query=order_type,
		deadline_bucket=deadline_bucket,
	)

	return {"ok": True, **rows}


@router.get("/api/main/filter-options")
async def assemblers_main_filter_options_api(
	request: Request,
	order_number: str = "",
	customer: str = "",
):
	_, redirect = require_user(request)
	if redirect:
		return JSONResponse({"ok": False, "error": "unauthorized"}, status_code=401)

	options = await run_in_threadpool(
		load_main_filter_options,
		order_number_query=order_number,
		customer_query=customer,
	)

	return {"ok": True, **options}


@router.get("/api/main/{order_number}")
async def assemblers_main_order_api(request: Request, order_number: str):
	_, redirect = require_user(request)
	if redirect:
		return JSONResponse({"ok": False, "error": "unauthorized"}, status_code=401)

	order = await run_in_threadpool(load_main_order_card, order_number)
	if not order:
		return JSONResponse({"ok": False, "error": "Замовлення не знайдено."}, status_code=404)

	return {"ok": True, "order": order}


@router.post("/api/main/{order_number}")
async def assemblers_main_order_update_api(request: Request, order_number: str):
	user, redirect = require_user(request)
	if redirect:
		return JSONResponse({"ok": False, "error": "unauthorized"}, status_code=401)

	if not can_manage_main_orders(user):
		return JSONResponse(
			{"ok": False, "error": "Недостатньо прав для керування замовленням."},
			status_code=403,
		)

	try:
		payload = await request.json()
	except Exception:
		return JSONResponse({"ok": False, "error": "Некоректні дані запиту."}, status_code=400)

	if not isinstance(payload, dict):
		return JSONResponse({"ok": False, "error": "Некоректні дані запиту."}, status_code=400)

	try:
		order = await run_in_threadpool(
			update_main_order_card,
			order_number,
			address=payload.get("address"),
			address_note=payload.get("address_note"),
			note=payload.get("note"),
			note_color=payload.get("note_color"),
			note_text_color=payload.get("note_text_color"),
			vat=payload.get("vat"),
			details=payload.get("details"),
			actor=user,
		)
	except ValueError as error:
		return JSONResponse({"ok": False, "error": str(error)}, status_code=400)
	if not order:
		return JSONResponse({"ok": False, "error": "Замовлення не знайдено."}, status_code=404)

	return {
		"ok": True,
		"order": order,
		"message": "Керування замовленням збережено.",
	}


@router.post("/api/main/{order_number}/status")
async def assemblers_main_order_status_update_api(request: Request, order_number: str):
	user, redirect = require_user(request)
	if redirect:
		return JSONResponse({"ok": False, "error": "unauthorized"}, status_code=401)

	if not can_manage_main_orders(user):
		return JSONResponse(
			{"ok": False, "error": "Недостатньо прав для керування замовленням."},
			status_code=403,
		)

	try:
		payload = await request.json()
	except Exception:
		return JSONResponse({"ok": False, "error": "Некоректні дані запиту."}, status_code=400)

	if not isinstance(payload, dict):
		return JSONResponse({"ok": False, "error": "Некоректні дані запиту."}, status_code=400)

	action = str(payload.get("action") or "").strip()
	if not action:
		return JSONResponse({"ok": False, "error": "Не вказано дію зміни статусу."}, status_code=400)

	try:
		order = await run_in_threadpool(
			update_main_order_status,
			order_number,
			action=action,
			actor=user,
		)
	except ValueError as error:
		return JSONResponse({"ok": False, "error": str(error)}, status_code=400)

	if not order:
		return JSONResponse({"ok": False, "error": "Замовлення не знайдено."}, status_code=404)

	message_map = {
		"close": "Замовлення закрито.",
		"mark_reclamation": "Статус змінено на 'Рекламація'.",
		"cancel_reclamation": "Рекламацію скасовано, замовлення повернуто в 'Закрито'.",
	}

	return {
		"ok": True,
		"order": order,
		"message": message_map.get(action.casefold(), "Статус замовлення оновлено."),
	}


@router.get("/api/column-preferences/{page_key}")
async def get_column_preferences(request: Request, page_key: str):
	"""Загружає предпочтения порядка колонок користувача."""
	user, redirect = require_user(request)
	if redirect:
		return JSONResponse({"ok": False, "error": "unauthorized"}, status_code=401)

	telegram_id = user.get("telegram_id")
	if not telegram_id:
		return JSONResponse({"ok": False, "error": "Немає telegram_id"}, status_code=400)

	prefs = await run_in_threadpool(
		load_column_preferences,
		telegram_id=telegram_id,
		page_key=page_key,
	)

	if prefs is None:
		return {"ok": True, "column_order": None, "pinned": None, "widths": None}

	return {
		"ok": True,
		"column_order": prefs["order"],
		"pinned": prefs.get("pinned", []),
		"widths": prefs.get("widths", {}),
	}


@router.post("/api/column-preferences/{page_key}")
async def save_column_preferences_api(request: Request, page_key: str):
	"""Зберігає предпочтения порядка колонок користувача."""
	user, redirect = require_user(request)
	if redirect:
		return JSONResponse({"ok": False, "error": "unauthorized"}, status_code=401)

	telegram_id = user.get("telegram_id")
	if not telegram_id:
		return JSONResponse({"ok": False, "error": "Немає telegram_id"}, status_code=400)

	try:
		payload = await request.json()
	except Exception:
		return JSONResponse({"ok": False, "error": "Некоректні дані запиту."}, status_code=400)

	if not isinstance(payload, dict):
		return JSONResponse({"ok": False, "error": "Некоректні дані запиту."}, status_code=400)

	column_order = payload.get("column_order")
	if not isinstance(column_order, list):
		return JSONResponse({"ok": False, "error": "column_order повинен бути списком."}, status_code=400)

	pinned = payload.get("pinned", [])
	if not isinstance(pinned, list):
		pinned = []

	widths = payload.get("widths", {})
	if not isinstance(widths, dict):
		widths = {}

	success = await run_in_threadpool(
		save_column_preferences,
		telegram_id=telegram_id,
		page_key=page_key,
		column_order=column_order,
		pinned=pinned,
		widths=widths,
	)

	if not success:
		return JSONResponse({"ok": False, "error": "Не вдалось зберегти предпочтення."}, status_code=400)

	return {"ok": True, "message": "Предпочтення колонок збережено."}

