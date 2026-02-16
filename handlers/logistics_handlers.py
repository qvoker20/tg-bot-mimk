import os
import psycopg2
from datetime import datetime, date 
from typing import Optional
from dotenv import load_dotenv
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import CallbackContext
from telegram.constants import ParseMode
import html

load_dotenv()

PG_CONN = {
    "host": os.environ.get("PG_HOST"),
    "port": int(os.environ.get("PG_PORT")),
    "dbname": os.environ.get("PG_DBNAME"),
    "user": os.environ.get("PG_USER"),
    "password": os.environ.get("PG_PASSWORD")
}

# ...existing code...
DRIVER_PROFILE_URL = "https://script.google.com/a/macros/mim-k.com/s/AKfycbwntmbkj-hiGviinO2yp7HxBSuJTtxUrp2omLJIUYoIlUt1yAwrUYa7MprTu1YZxf7MSw/exec"
DRIVER_REQUEST_URL = "https://script.google.com/a/macros/mim-k.com/s/AKfycbww6AN75fUVTbRMsWejkM1EFNH5fqWY6orRUOuQJH8EM9EpULBJ-pRahIo9QDSaBHQN/exec"  # TODO: вставити лінк на “Заявка”

DRIVER_PROFILE_URL = "https://script.google.com/a/macros/mim-k.com/s/AKfycbwntmbkj-hiGviinO2yp7HxBSuJTtxUrp2omLJIUYoIlUt1yAwrUYa7MprTu1YZxf7MSw/exec"
DRIVER_REQUEST_URL = "https://script.google.com/a/macros/mim-k.com/s/AKfycbww6AN75fUVTbRMsWejkM1EFNH5fqWY6orRUOuQJH8EM9EpULBJ-pRahIo9QDSaBHQN/exec"

# --- ТЕКСТ ДЛЯ ЗАЯВКИ ---
LOGISTICS_REQUEST_TEXT = (
    "<b>📋 Подача заявки на логістику</b>\n\n"
    "🔐 <b>Доступ:</b> Виключно за номером телефону та прив’язаною Google-поштою, "
    "яку ви надали адміністратору.\n\n"
    "⚠️ <b>Якщо немає доступу:</b>\n"
    "Зв'яжіться з @mindalovv. У повідомленні одразу вкажіть:\n"
    "1. Причину запиту доступу.\n"
    "2. Вашу Google-пошту.\n\n"
    "❗️ <b>Важливо:</b> Переходьте за посиланням у браузері, "
    "де ви вже авторизовані під відповідною поштою."
)

# --- ТЕКСТ ДЛЯ ПРОФІЛЮ ВОДІЯ ---
DRIVER_PROFILE_TEXT = (
    "<b>🚘 Профіль водія</b>\n\n"
    "Цей розділ створено для обліку та контролю транспортних засобів компанії.\n\n"
    "<b>Тут ви можете:</b>\n"
    "✅ Побачити, за ким наразі закріплено авто.\n"
    "✅ Ведення поставлених завдань.\n"
    "✅ Оформити передачу автомобіля іншому водію.\n\n"
    "🔐 <b>Доступ:</b> Здійснюється за вашим номером телефону.\n\n"
    "<i>Будь ласка, відповідально ставтеся до фіксації передачі авто!</i>"
)

async def show_logistics_menu(update: Update, context: CallbackContext):
    keyboard = [
        [InlineKeyboardButton("Подати заявку", callback_data="logistics_request")],
        [InlineKeyboardButton("Профіль водія", callback_data="logistics_driver_profile")],
        [InlineKeyboardButton("Назад", callback_data="logistics_back")] # Змінив callback_data на унікальну, щоб не конфліктувала
    ]
    
    # Якщо це нове повідомлення
    if update.message:
        await update.message.reply_text(
            "<b>Логістика та автопарк</b>\nОберіть необхідну дію:",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode=ParseMode.HTML
        )
    # Якщо це редагування попереднього (наприклад, кнопка "Назад" з іншого меню)
    elif update.callback_query:
        await update.callback_query.edit_message_text(
            "<b>Логістика та автопарк</b>\nОберіть необхідну дію:",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode=ParseMode.HTML
        )

async def logistics_button_handler(update: Update, context: CallbackContext):
    query = update.callback_query
    await query.answer()

    if query.data == "logistics_request":
        keyboard = [
            [InlineKeyboardButton("🔗 Відкрити форму заявки", url=DRIVER_REQUEST_URL)],
            [InlineKeyboardButton("🔙 Назад", callback_data="logistics_menu_back")]
        ]
        await query.edit_message_text(
            text=LOGISTICS_REQUEST_TEXT,
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode=ParseMode.HTML
        )
        return

    if query.data == "logistics_driver_profile":
        keyboard = [
            [InlineKeyboardButton("🔗 Відкрити профіль водія", url=DRIVER_PROFILE_URL)],
            [InlineKeyboardButton("🔙 Назад", callback_data="logistics_menu_back")]
        ]
        await query.edit_message_text(
            text=DRIVER_PROFILE_TEXT,
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode=ParseMode.HTML
        )
        return

    # Обробка повернення в меню логістики
    if query.data == "logistics_menu_back":
        await show_logistics_menu(update, context)
        return

    if query.data == "logistics_back":
        # Тут логіка повернення в ГОЛОВНЕ меню бота (main_menu)
        # Наприклад: await show_main_menu(update, context)
        await query.edit_message_text("Повертаю в головне меню...")
        return