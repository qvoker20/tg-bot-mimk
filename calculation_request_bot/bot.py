import json
import logging
import os
import re
import zipfile
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

from dotenv import load_dotenv
from telegram import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    Message,
    ReplyKeyboardMarkup,
    ReplyKeyboardRemove,
    Update,
)
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

from db import (
    STATUS_COMPLETED,
    STATUS_WAITING_NAME,
    STATUS_WAITING_PHONE,
    STATUS_WAITING_PROJECT,
    append_project_payload,
    cancel_request,
    complete_request,
    create_request,
    ensure_schema,
    get_active_request,
    get_last_completed_profile,
    get_request_by_id,
    list_recent_requests,
    mark_other_active_as_abandoned,
    set_archive_path,
    set_files_dir,
    update_name,
    set_waiting_phone,
)

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
)
logger = logging.getLogger("calculation_request_bot")

BOT_TOKEN = os.getenv("CALCULATION_BOT_TOKEN") or os.getenv("TELEGRAM_BOT_TOKEN", "")
MANAGER_CHAT_ID = os.getenv("CALC_MANAGER_CHAT_ID", "").strip()

BASE_DIR = Path(__file__).resolve().parent
UPLOAD_ROOT = BASE_DIR / "aload"
ARCHIVE_ROOT = UPLOAD_ROOT / "archives"

UPLOAD_ROOT.mkdir(parents=True, exist_ok=True)
ARCHIVE_ROOT.mkdir(parents=True, exist_ok=True)

WELCOME_TEXT = (
    "Вітаємо в MIM-K.\n"
    "Тут ви можете надіслати проєкт на розрахунок.\n"
    "Будь ласка, напишіть, як до вас звертатись."
)

ASK_PROJECT_TEXT = (
    "Дякуємо.\n"
    "Надішліть сюди, будь ласка, ваш проєкт для розрахунку.\n"
    "Це можуть бути файли, фото, PDF, креслення, візуалізації або текстовий опис."
)

ASK_PHONE_TEXT = "Супер. Будь ласка, надішліть ваш номер телефону для зв’язку."

DONE_TEXT = (
    "Дякуємо, ми отримали ваш запит на розрахунок.\n"
    "Менеджер MIM-K перегляне матеріали та звʼяжеться з вами."
)

PHONE_HINT_TEXT = (
    "Будь ласка, надішліть номер телефону у форматі +380..., "
    "або звичайним номером з цифрами."
)

HELP_TEXT = (
    "Команди:\n"
    "/start або /calculate - нова заявка на розрахунок\n"
    "/myrequests - перегляд та скасування заявок"
)


def upload_controls_markup(request_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("Завантажити", callback_data=f"calc_finish:{request_id}")],
            [InlineKeyboardButton("Скасувати", callback_data=f"calc_cancel:{request_id}")],
        ]
    )


def myrequests_cancel_markup(request_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [[InlineKeyboardButton("Скасувати заявку", callback_data=f"calc_mycancel:{request_id}")]]
    )


def phone_contact_markup() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        [[KeyboardButton("Надати контакт", request_contact=True)]],
        resize_keyboard=True,
        one_time_keyboard=True,
    )


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.effective_user or not update.effective_chat or not update.effective_message:
        return

    payload = ""
    if context.args:
        payload = " ".join(context.args).strip()

    user = update.effective_user
    chat_id = update.effective_chat.id

    active = get_active_request(user.id, chat_id)
    if active:
        status = active.get("status")
        if status == STATUS_WAITING_NAME:
            await update.effective_message.reply_text("Будь ласка, напишіть, як до вас звертатись.")
            return
        if status == STATUS_WAITING_PROJECT:
            await update.effective_message.reply_text(
                "У вас вже є активна заявка. Надсилайте файли або текст.\n"
                "Коли завершите додавання файлів, натисніть 'Завантажити'.",
                reply_markup=upload_controls_markup(active["id"]),
            )
            return
        if status == STATUS_WAITING_PHONE:
            await update.effective_message.reply_text(
                ASK_PHONE_TEXT,
                reply_markup=phone_contact_markup(),
            )
            return

    profile = get_last_completed_profile(user.id)
    if profile:
        context.user_data["calc_profile_offer"] = {
            "name": profile.get("client_name") or "",
            "phone": profile.get("contact_phone") or "",
            "source": payload or "direct",
        }
        name = profile.get("client_name") or "-"
        phone = profile.get("contact_phone") or "-"
        await update.effective_message.reply_text(
            "Ваші дані вже є в системі:\n"
            f"Ім'я: {name}\n"
            f"Телефон: {phone}\n\n"
            "Продовжити з цими даними чи створити нові?",
            reply_markup=InlineKeyboardMarkup(
                [
                    [InlineKeyboardButton("Продовжити з цими даними", callback_data="calc_reuse_yes")],
                    [InlineKeyboardButton("Створити нові", callback_data="calc_reuse_new")],
                ]
            ),
        )
        return

    request_id = create_request(
        telegram_id=user.id,
        chat_id=chat_id,
        telegram_username=user.username or "",
        telegram_full_name=user.full_name or "",
        source=payload or "direct",
        status=STATUS_WAITING_NAME,
    )
    mark_other_active_as_abandoned(user.id, chat_id, request_id)

    await update.effective_message.reply_text(WELCOME_TEXT)


async def calculate(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await start(update, context)


async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.effective_message:
        return
    await update.effective_message.reply_text(HELP_TEXT)


async def myrequests(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.effective_user or not update.effective_message:
        return

    rows = list_recent_requests(update.effective_user.id, limit=10)
    if not rows:
        await update.effective_message.reply_text("У вас ще немає заявок.")
        return

    for row in rows:
        rid = row.get("id")
        status = row.get("status")
        payload_count = row.get("payload_count") or 0
        started = row.get("started_at")
        archive_path = row.get("archive_file_path") or "-"
        text = (
            f"Заявка #{rid}\n"
            f"Статус: {status}\n"
            f"Старт: {started}\n"
            f"Матеріалів: {payload_count}\n"
            f"Архів: {archive_path}"
        )
        if status in (STATUS_WAITING_NAME, STATUS_WAITING_PROJECT, STATUS_WAITING_PHONE):
            await update.effective_message.reply_text(text, reply_markup=myrequests_cancel_markup(int(rid)))
        else:
            await update.effective_message.reply_text(text)


def normalize_phone(raw_value: str) -> str:
    value = raw_value.strip()
    value = value.replace(" ", "").replace("-", "").replace("(", "").replace(")", "")
    return value


def is_phone_valid(raw_value: str) -> bool:
    value = normalize_phone(raw_value)
    if value.startswith("+"):
        digits = value[1:]
    else:
        digits = value
    return digits.isdigit() and 8 <= len(digits) <= 15


def extract_project_payload(message: Message) -> Optional[dict[str, Any]]:
    if message.text and not message.text.startswith("/"):
        return {
            "type": "text",
            "text": message.text,
            "message_id": message.message_id,
            "date": message.date.isoformat(),
        }

    if message.photo:
        largest = message.photo[-1]
        return {
            "type": "photo",
            "file_id": largest.file_id,
            "file_unique_id": largest.file_unique_id,
            "caption": message.caption or "",
            "message_id": message.message_id,
            "date": message.date.isoformat(),
        }

    if message.document:
        return {
            "type": "document",
            "file_id": message.document.file_id,
            "file_unique_id": message.document.file_unique_id,
            "file_name": message.document.file_name,
            "mime_type": message.document.mime_type,
            "file_size": message.document.file_size,
            "caption": message.caption or "",
            "message_id": message.message_id,
            "date": message.date.isoformat(),
        }

    if message.video:
        return {
            "type": "video",
            "file_id": message.video.file_id,
            "file_unique_id": message.video.file_unique_id,
            "caption": message.caption or "",
            "message_id": message.message_id,
            "date": message.date.isoformat(),
        }

    if message.audio:
        return {
            "type": "audio",
            "file_id": message.audio.file_id,
            "file_unique_id": message.audio.file_unique_id,
            "caption": message.caption or "",
            "message_id": message.message_id,
            "date": message.date.isoformat(),
        }

    if message.voice:
        return {
            "type": "voice",
            "file_id": message.voice.file_id,
            "file_unique_id": message.voice.file_unique_id,
            "message_id": message.message_id,
            "date": message.date.isoformat(),
        }

    if message.animation:
        return {
            "type": "animation",
            "file_id": message.animation.file_id,
            "file_unique_id": message.animation.file_unique_id,
            "caption": message.caption or "",
            "message_id": message.message_id,
            "date": message.date.isoformat(),
        }

    if message.video_note:
        return {
            "type": "video_note",
            "file_id": message.video_note.file_id,
            "file_unique_id": message.video_note.file_unique_id,
            "message_id": message.message_id,
            "date": message.date.isoformat(),
        }

    if message.sticker:
        return {
            "type": "sticker",
            "file_id": message.sticker.file_id,
            "file_unique_id": message.sticker.file_unique_id,
            "message_id": message.message_id,
            "date": message.date.isoformat(),
        }

    return None


def build_archive_for_request(request: dict[str, Any]) -> str:
    request_id = int(request["id"])
    request_dir = UPLOAD_ROOT / f"request_{request_id}"
    request_dir.mkdir(parents=True, exist_ok=True)

    payloads = request.get("all_project_payloads") or []
    manifest_path = request_dir / "payloads.json"
    with manifest_path.open("w", encoding="utf-8") as f:
        json.dump(payloads, f, ensure_ascii=False, indent=2)

    archive_path = ARCHIVE_ROOT / f"request_{request_id}.zip"
    with zipfile.ZipFile(archive_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for file_path in request_dir.rglob("*"):
            if file_path.is_file():
                zf.write(file_path, file_path.relative_to(request_dir))

    return str(archive_path)


def safe_filename(name: str) -> str:
    return re.sub(r"[^a-zA-Z0-9._-]+", "_", name).strip("._") or "file"


async def store_payload_and_file(update: Update, request: dict[str, Any], payload: dict[str, Any]) -> dict[str, Any]:
    request_id = int(request["id"])
    request_dir = UPLOAD_ROOT / f"request_{request_id}"
    request_dir.mkdir(parents=True, exist_ok=True)
    set_files_dir(request_id, str(request_dir))

    local_file_path = ""
    file_id = payload.get("file_id")
    if file_id:
        ts = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        payload_type = payload.get("type") or "file"
        orig_name = payload.get("file_name") or f"{payload_type}_{ts}"
        filename = safe_filename(orig_name)
        if payload_type == "photo" and "." not in filename:
            filename = f"{filename}.jpg"
        if payload_type == "voice" and "." not in filename:
            filename = f"{filename}.ogg"
        if payload_type == "video_note" and "." not in filename:
            filename = f"{filename}.mp4"

        final_path = request_dir / f"{ts}_{filename}"
        tg_file = await update.get_bot().get_file(file_id)
        await tg_file.download_to_drive(custom_path=str(final_path))
        local_file_path = str(final_path)

    return append_project_payload(request_id, payload, local_file_path)


async def ensure_active_request(update: Update) -> Optional[dict[str, Any]]:
    if not update.effective_user or not update.effective_chat:
        return None

    user = update.effective_user
    chat_id = update.effective_chat.id
    request = get_active_request(user.id, chat_id)
    if request:
        return request

    request_id = create_request(
        telegram_id=user.id,
        chat_id=chat_id,
        telegram_username=user.username or "",
        telegram_full_name=user.full_name or "",
        source="implicit",
        status=STATUS_WAITING_NAME,
    )
    mark_other_active_as_abandoned(user.id, chat_id, request_id)
    return get_request_by_id(request_id)


async def notify_manager_if_configured(update: Update, request: dict[str, Any]) -> None:
    if not MANAGER_CHAT_ID:
        return

    try:
        manager_chat_id = int(MANAGER_CHAT_ID)
    except ValueError:
        logger.warning("CALC_MANAGER_CHAT_ID is not a number: %s", MANAGER_CHAT_ID)
        return

    payload = request.get("first_project_payload")
    payload_compact = json.dumps(payload, ensure_ascii=False) if payload else "{}"
    username = request.get("telegram_username") or ""
    username_view = f"@{username}" if username else "(немає username)"

    msg = (
        "Нова заявка на розрахунок\n"
        f"ID заявки: {request.get('id')}\n"
        f"Старт: {request.get('started_at')}\n"
        f"Telegram ID: {request.get('telegram_id')}\n"
        f"Username: {username_view}\n"
        f"Ім'я: {request.get('client_name') or ''}\n"
        f"Проєкт надіслано: {request.get('project_sent_at')}\n"
        f"Телефон: {request.get('contact_phone') or ''}\n"
        f"Архів: {request.get('archive_file_path') or ''}\n"
        f"Перший payload: {payload_compact[:1500]}"
    )

    try:
        await update.get_bot().send_message(chat_id=manager_chat_id, text=msg)
    except Exception:
        logger.exception("Failed to notify manager about request %s", request.get("id"))


async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.callback_query or not update.effective_user:
        return

    query = update.callback_query
    await query.answer()
    data = query.data or ""

    if data == "calc_reuse_yes":
        profile = context.user_data.get("calc_profile_offer") or {}
        if not update.effective_chat:
            return
        request_id = create_request(
            telegram_id=update.effective_user.id,
            chat_id=update.effective_chat.id,
            telegram_username=update.effective_user.username or "",
            telegram_full_name=update.effective_user.full_name or "",
            source=profile.get("source") or "direct",
            client_name=profile.get("name") or "",
            contact_phone=profile.get("phone") or "",
            status=STATUS_WAITING_PROJECT,
        )
        mark_other_active_as_abandoned(update.effective_user.id, update.effective_chat.id, request_id)
        context.user_data.pop("calc_profile_offer", None)

        await query.edit_message_text(
            "Дякуємо. Ваші дані підтягнули з системи.\n"
            "Надсилайте файли або текст проєкту.\n"
            "Коли завершите - натисніть 'Завантажити'."
        )
        await query.message.reply_text("Керуйте завантаженням:", reply_markup=upload_controls_markup(request_id))
        return

    if data == "calc_reuse_new":
        if not update.effective_chat:
            return
        request_id = create_request(
            telegram_id=update.effective_user.id,
            chat_id=update.effective_chat.id,
            telegram_username=update.effective_user.username or "",
            telegram_full_name=update.effective_user.full_name or "",
            source=(context.user_data.get("calc_profile_offer") or {}).get("source") or "direct",
            status=STATUS_WAITING_NAME,
        )
        mark_other_active_as_abandoned(update.effective_user.id, update.effective_chat.id, request_id)
        context.user_data.pop("calc_profile_offer", None)
        await query.edit_message_text(WELCOME_TEXT)
        return

    finish_match = re.match(r"^calc_finish:(\d+)$", data)
    if finish_match:
        request_id = int(finish_match.group(1))
        request = get_request_by_id(request_id)
        if not request or int(request.get("telegram_id", 0)) != update.effective_user.id:
            await query.edit_message_text("Заявка не знайдена або немає доступу.")
            return
        payload_count = len(request.get("all_project_payloads") or [])
        if payload_count == 0:
            await query.message.reply_text("Спочатку додайте хоча б один файл або текст опису проєкту.")
            return
        set_waiting_phone(request_id)
        await query.message.reply_text(ASK_PHONE_TEXT, reply_markup=phone_contact_markup())
        return

    cancel_match = re.match(r"^calc_cancel:(\d+)$", data)
    if cancel_match:
        request_id = int(cancel_match.group(1))
        request = get_request_by_id(request_id)
        if not request or int(request.get("telegram_id", 0)) != update.effective_user.id:
            await query.edit_message_text("Заявка не знайдена або немає доступу.")
            return
        cancel_request(request_id)
        await query.edit_message_text(f"Заявку #{request_id} скасовано.")
        return

    my_cancel_match = re.match(r"^calc_mycancel:(\d+)$", data)
    if my_cancel_match:
        request_id = int(my_cancel_match.group(1))
        request = get_request_by_id(request_id)
        if not request or int(request.get("telegram_id", 0)) != update.effective_user.id:
            await query.edit_message_text("Заявка не знайдена або немає доступу.")
            return
        cancel_request(request_id)
        await query.edit_message_text(f"Заявку #{request_id} скасовано.")
        return


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.effective_message:
        return

    request = await ensure_active_request(update)
    if not request:
        return

    message = update.effective_message
    text = (message.text or "").strip()
    payload = extract_project_payload(message)
    status = request.get("status", STATUS_WAITING_NAME)

    if status == STATUS_WAITING_NAME:
        if text and not text.startswith("/"):
            update_name(request["id"], text)
            fresh = get_request_by_id(request["id"])
            await message.reply_text(ASK_PROJECT_TEXT, reply_markup=upload_controls_markup(request["id"]))

            if fresh and fresh.get("first_project_payload") is not None:
                await message.reply_text(
                    "Ми вже отримали ваш проєкт у попередньому повідомленні.\n"
                    "Можете додати ще файли, а потім натисніть 'Завантажити'."
                )
            return

        if payload is not None:
            await store_payload_and_file(update, request, payload)
            await message.reply_text(
                "Отримали ваш проєкт. Спочатку, будь ласка, напишіть, як до вас звертатись."
            )
            return

        await message.reply_text(
            "Будь ласка, напишіть, як до вас звертатись."
        )
        return

    if status == STATUS_WAITING_PROJECT:
        if payload is None:
            await message.reply_text(
                "Будь ласка, надішліть проєкт: файл, фото, PDF, архів або текстовий опис.\n"
                "Коли завершите - натисніть 'Завантажити'.",
                reply_markup=upload_controls_markup(request["id"]),
            )
            return

        updated = await store_payload_and_file(update, request, payload)
        payload_count = len(updated.get("all_project_payloads") or [])
        await message.reply_text(
            f"Матеріал додано. Зараз у заявці: {payload_count}.\n"
            "Можете додати ще або натиснути 'Завантажити'.",
            reply_markup=upload_controls_markup(request["id"]),
        )
        return

    if status == STATUS_WAITING_PHONE:
        phone = ""
        if message.contact and message.contact.phone_number:
            phone = normalize_phone(message.contact.phone_number)
        elif text and not text.startswith("/"):
            phone = normalize_phone(text)

        if not phone or not is_phone_valid(phone):
            await message.reply_text(PHONE_HINT_TEXT)
            return

        complete_request(request["id"], phone)
        completed = get_request_by_id(request["id"])
        if completed:
            archive_path = build_archive_for_request(completed)
            set_archive_path(request["id"], archive_path)
            completed = get_request_by_id(request["id"])

        await message.reply_text(DONE_TEXT, reply_markup=ReplyKeyboardRemove())
        if completed:
            await notify_manager_if_configured(update, completed)
        return

    if status == STATUS_COMPLETED:
        await message.reply_text(
            "Ваш запит вже зафіксовано. Якщо хочете створити новий, натисніть /start."
        )
        return

    await message.reply_text("Для нового звернення натисніть /start.")


def main() -> None:
    if not BOT_TOKEN:
        raise RuntimeError(
            "Не знайдено токен бота. Додайте CALCULATION_BOT_TOKEN у .env"
        )

    ensure_schema()

    app = Application.builder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("calculate", calculate))
    app.add_handler(CommandHandler("myrequests", myrequests))
    app.add_handler(CommandHandler("help", help_cmd))
    app.add_handler(CallbackQueryHandler(handle_callback, pattern=r"^calc_"))
    app.add_handler(
        MessageHandler(
            (filters.TEXT & ~filters.COMMAND)
            | filters.PHOTO
            | filters.Document.ALL
            | filters.VIDEO
            | filters.AUDIO
            | filters.VOICE
            | filters.ANIMATION
            | filters.VIDEO_NOTE
            | filters.Sticker.ALL
            | filters.CONTACT,
            handle_message,
        )
    )

    logger.info("Calculation request bot started")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
