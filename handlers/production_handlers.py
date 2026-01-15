import os
import sqlite3
import logging
from datetime import datetime
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import CallbackContext
from utils.drive_utils import upload_to_gdrive
import httpx
import asyncio
import psycopg2
import os
from dotenv import load_dotenv

load_dotenv()


PG_CONN = {
    'host': os.environ.get("PG_HOST"),
    'port': int(os.environ.get("PG_PORT")),
    'dbname': os.environ.get("PG_DBNAME"),
    'user': os.environ.get("PG_USER"),
    'password': os.environ.get("PG_PASSWORD")
}

def get_pg_connection():
    return psycopg2.connect(**PG_CONN)

GOOGLE_SCRIPT_URL = os.environ.get("GOOGLE_SCRIPT_URL")
ISSUE_GOOGLE_SCRIPT_URL = os.environ.get("ISSUE_GOOGLE_SCRIPT_URL")

# функція для перевірки, чи є користувач дозволеним
async def show_production_menu(update: Update, context: CallbackContext):
    # Видаляємо попереднє повідомлення з inline-кнопками виробництва, якщо є
    if "production_message_id" in context.user_data:
        try:
            await context.bot.delete_message(
                chat_id=update.effective_chat.id,
                message_id=context.user_data["production_message_id"]
            )
        except Exception as e:
            logging.warning(f"Не вдалося видалити попереднє повідомлення 'Виробництво': {e}")

    keyboard = [
        [InlineKeyboardButton("Переріз", callback_data='cut_menu')],
        [InlineKeyboardButton("Проблема", callback_data='issue_submit')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    # Відправляємо нове повідомлення з inline-кнопками
    if hasattr(update, "callback_query") and update.callback_query:
        sent = await update.callback_query.message.reply_text(
            "⬇️ Оберіть дію для виробництва:", reply_markup=reply_markup
        )
    else:
        sent = await update.message.reply_text(
            "⬇️ Оберіть дію для виробництва:",
            reply_markup=reply_markup
        )
    # Зберігаємо message_id для подальшого видалення
    context.user_data["production_message_id"] = sent.message_id
# функція для обробки натискань кнопок в меню виробництва
async def production_button_handler(update: Update, context: CallbackContext):
    print("production_button_handler called:", update.callback_query.data)
    query = update.callback_query
    await query.answer()

    if query.data == 'cut_menu':
        await show_cut_menu(update, context)

    elif query.data == 'cut_submit':
        context.user_data['cut_step'] = 'order_number'
        # Дістаємо ім'я користувача з бази
        user_id = update.effective_user.id
        conn = get_pg_connection()
        cursor = conn.cursor()
        try:
            cursor.execute("SELECT name FROM database_app_userdatatelegram WHERE telegram_id = %s", (user_id,))
            row = cursor.fetchone()
            context.user_data['user_name'] = row[0] if row else ""
        finally:
            cursor.close()
            conn.close()
        await query.edit_message_text("✂️ Введіть номер замовлення:")

    elif query.data == 'cut_confirm':
        loading_msg = await query.edit_message_text("⏳ <b>Завантаження...</b>", parse_mode="HTML")
        context.user_data["loading_message_id"] = loading_msg.message_id
        try:
            res = await send_cut_to_google_sheet(update, context)
            if res == "OK":
                await query.edit_message_text("✅ Переріз надіслано.")
            else:
                await query.edit_message_text(str(res))
        except Exception as e:
            logging.error(f"Помилка при відправці у Google Sheet: {e}")
            await query.edit_message_text("❌ Сталася помилка при відправці.")
        finally:
            for k in ['cut_step','cut_order_number','cut_launch_number','cut_cut_number','cut_reason','loading_message_id']:
                context.user_data.pop(k, None)

    elif query.data == 'cut_cancel':
        await query.edit_message_text("❌ Операцію скасовано.")
        for k in ['cut_step','cut_order_number','cut_launch_number','cut_cut_number','cut_reason','loading_message_id']:
            context.user_data.pop(k, None)

    elif query.data == 'cut_search':
        await query.edit_message_text("У розробці...")

    elif query.data == 'issue_submit':
        # старт збору даних про проблему
        context.user_data['issue_step'] = 'order_number'
        # зберігаємо ім'я користувача
        user_id = update.effective_user.id
        conn = get_pg_connection()
        cursor = conn.cursor()
        try:
            cursor.execute("SELECT name FROM database_app_userdatatelegram WHERE telegram_id = %s", (user_id,))
            row = cursor.fetchone()
            context.user_data['issue_user_name'] = row[0] if row else ""
        finally:
            cursor.close()
            conn.close()
        await query.edit_message_text("⚠️ Вкажіть номер замовлення:")

    elif query.data == 'issue_confirm':
        # Не чекаємо відповіді від скрипта — відправляємо у фоні
        try:
            await send_issue_to_google_sheet(update, context)  # fire-and-forget усередині
        finally:
            await query.edit_message_text("✅ Проблему надіслано. Очікуйте сповіщення від системи.")
            for k in ['issue_step','issue_order_number','issue_part_name','issue_launch_number','issue_description','issue_user_name','issue_loading_message_id']:
                context.user_data.pop(k, None)

    elif query.data == 'issue_cancel':
        await query.edit_message_text("❌ Відправку проблеми скасовано.")
        for k in ['issue_step','issue_order_number','issue_part_name','issue_launch_number','issue_description','issue_user_name','issue_loading_message_id']:
            context.user_data.pop(k, None)

    elif query.data == 'back_to_production':
        await show_production_menu(update, context)



# Меню перерізу
async def show_cut_menu(update: Update, context: CallbackContext):
    keyboard = [
        [InlineKeyboardButton("Подати переріз", callback_data='cut_submit')],
        [InlineKeyboardButton("Знайти переріз", callback_data='cut_search')],
        [InlineKeyboardButton("⬅️ Назад", callback_data='back_to_production')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    if update.callback_query:
        await update.callback_query.edit_message_text(
            "⬇️ Оберіть дію для перерізу:", reply_markup=reply_markup
        )
    else:
        await update.message.reply_text(
            "⬇️ Оберіть дію для перерізу:", reply_markup=reply_markup
        )

# Відправка перерізу в Google Sheet (GET)
async def send_cut_to_google_sheet(update: Update, context: CallbackContext):
    order = context.user_data.get("cut_order_number")
    launch = context.user_data.get("cut_launch_number")
    cut = context.user_data.get("cut_cut_number")
    reason = context.user_data.get("cut_reason")
    tg_id = update.effective_user.id
    name = context.user_data.get("user_name", "")

    logging.info(f"Відправка у Google Sheet: order={order}, launch={launch}, cut={cut}, reason={reason}, name={name}, tg_id={tg_id}")

    params = {
        "order": order,
        "launch": launch,
        "cut": cut,
        "reason": reason,
        "tg_id": tg_id,
        "name": name
    }
    async with httpx.AsyncClient(timeout=5) as client:
        try:
            resp = await client.get(GOOGLE_SCRIPT_URL, params=params)
            text = resp.text.strip()
            logging.info(f"Відповідь від Google Script: {text}")
            if resp.status_code != 200:
                return f"Помилка: Google Script повернув статус {resp.status_code}"
            if text == "OK":
                return "OK"
            elif text.startswith("ERROR:"):
                return f"Помилка від Google Script: {text[6:].strip()}"
            else:
                return f"Помилка: неочікувана відповідь від Google Script:\n{text}"
        except httpx.ReadTimeout:
            return "Помилка: не вдалося дочекатися відповіді від Google Script (таймаут)"
        except httpx.RequestError as e:
            return f"Помилка з'єднання: {e}"

# Відправка проблеми в Google Sheet (GET)
async def send_issue_to_google_sheet(update: Update, context: CallbackContext):
    order = context.user_data.get("issue_order_number")
    part = context.user_data.get("issue_part_name")
    launch = context.user_data.get("issue_launch_number")
    description = context.user_data.get("issue_description")
    tg_id = update.effective_user.id
    name = context.user_data.get("issue_user_name", "")

    params = {
        "order": order,
        "part": part,
        "launch": launch,
        "description": description,
        "tg_id": tg_id,
        "name": name
    }

    # Запускаємо запит у фоні, не очікуючи на "OK"
    asyncio.create_task(_issue_request(params))

async def _issue_request(params: dict):
    try:
        async with httpx.AsyncClient(timeout=5, follow_redirects=True) as client:
            await client.get(ISSUE_GOOGLE_SCRIPT_URL, params=params)
        logging.info("Issue Script request dispatched")
    except Exception as e:
        # Лише лог — користувач отримає сповіщення від Apps Script/бота-нотифікатора
        logging.warning(f"Issue Script request error: {e}")


# ---- СТУБИ, щоб імпорт не падав (якщо ще десь використовується закупівля) ----
def find_purchase_by_order_number(order_number: str):
    # Поверніть реалізацію якщо потрібно. Тимчасово — порожній результат.
    return []

def find_by_nymber_order(detail_number: str):
    # Поверніть реалізацію якщо потрібно. Тимчасово — порожній результат.
    return []