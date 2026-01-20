import logging
import sqlite3
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import CallbackContext
import chromadb
from openai import OpenAI
from datetime import timedelta, time, datetime, date
from utils.db_utils import get_user_data
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update, ReplyKeyboardMarkup, KeyboardButton
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

ROLE_DESCRIPTIONS = {
    "admin": "Адміністратор: повний доступ до всіх функцій бота!.",
    "adminpre": "Адміністратор (обмежений): доступ до всіх функцій окрім керування!.",
    "замірник": "Замірник: доступ до Заміри, Замірникам, Виробництво!",
    "конструктор": "Конструктор: доступ до Заміри, Виробництво",
    "Виробництво": "Виробництво: доступ до Заміри, Виробництво.",
    "Закупівля": "Закупівля: доступ до Заміри, Виробництво",
    # Додай інші ролі за потреби
}

USERS_PER_PAGE = 5

async def notify_admin_about_restriction(update: Update, context: CallbackContext, user_id: int):
    """Надсилає повідомлення адміністратору про спробу доступу."""
    admin_id = 403271614  # ID адміністратора
    user = update.message.from_user

    # Формуємо інформацію про користувача
    user_info = (
        f"ID: {user.id}\n"
        f"Ім'я: {user.first_name}\n"
        f"Прізвище: {user.last_name if user.last_name else 'немає'}\n"
        f"Username: @{user.username if user.username else 'немає'}"
    )
    message = f"⚠️ Спроба користування від користувача без дозволу:\n{user_info}"

    # Видаляємо попереднє повідомлення адміністратору, якщо воно існує
    if "last_admin_message_id" in context.bot_data:
        try:
            await context.bot.delete_message(
                chat_id=admin_id,
                message_id=context.bot_data["last_admin_message_id"]
            )
        except Exception as e:
            logging.warning(f"Не вдалося видалити попереднє повідомлення адміністратору: {e}")

    # Надсилаємо нове повідомлення адміністратору
    try:
        sent_message = await context.bot.send_message(chat_id=admin_id, text=message)
        # Зберігаємо message_id нового повідомлення
        context.bot_data["last_admin_message_id"] = sent_message.message_id
    except Exception as e:
        logging.error(f"Не вдалося надіслати повідомлення адміністратору: {e}")

async def show_admin_menu(update: Update, context: CallbackContext):
    keyboard = [
        [InlineKeyboardButton("Реєстрація користувача", callback_data='admin_register')],
        [InlineKeyboardButton("Видалення користувача", callback_data='admin_delete')],
        [InlineKeyboardButton("Користувачі", callback_data='admin_users')],
        [InlineKeyboardButton("Оголошення", callback_data='admin_announce')],
        [InlineKeyboardButton("Змінити роль користувача", callback_data='admin_change_role')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    if update.callback_query:
        await update.callback_query.edit_message_text("⬇️ Оберіть дію (Admin):", reply_markup=reply_markup)
    else:
        await update.message.reply_text("⬇️ Оберіть дію (Admin):", reply_markup=reply_markup)

async def admin_button_handler(update: Update, context: CallbackContext):
    query = update.callback_query
    await query.answer()
    if query.data == 'admin_register':
        context.user_data["admin_register_step"] = "telegram_id"
        await query.edit_message_text("Введіть telegram_id нового користувача:")
    elif query.data == 'admin_delete':
        context.user_data["admin_delete"] = True
        await query.edit_message_text("Введіть telegram_id користувача для видалення:")
    elif query.data == 'admin_users':
        # Вивід списку користувачів
        conn = get_pg_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT telegram_id, name, username FROM database_app_userdatatelegram")
        users = cursor.fetchall()
        cursor.close()
        conn.close()
        msg = "\n".join([f"{u[0]} | {u[1]} | {u[2]}" for u in users]) or "Користувачів не знайдено."
        await query.edit_message_text(f"<b>Список користувачів:</b>\n{msg}", parse_mode="HTML")
    elif query.data == 'admin_announce':
        context.user_data["admin_announce"] = True
        await query.edit_message_text("Введіть текст оголошення для всіх користувачів:")
    elif query.data == 'admin_change_role':
        # Отримуємо список користувачів один раз і зберігаємо в context.user_data
        conn = get_pg_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT telegram_id, name, username FROM database_app_userdatatelegram")
        users = cursor.fetchall()
        cursor.close()
        conn.close()
        context.user_data["role_users"] = users
        context.user_data["change_role_page"] = 0
        await show_user_list_for_role_change(query, context, page=0)

async def send_ai_log_pdf(update: Update, context: CallbackContext):
    user_id = update.effective_user.id
    # Дозволяємо тільки admin/adminpre
    user_data = get_user_data(user_id)
    if not user_data:
        await update.message.reply_text("У вас немає доступу до цієї команди.")
        return
    conn = get_pg_connection()
    cursor = conn.cursor()
    try:
        cursor.execute(
            "SELECT username FROM database_app_userdatatelegram WHERE telegram_id = %s",
            (user_id,)
        )
        row = cursor.fetchone()
        username = row[0] if row else None
    finally:
        cursor.close()
        conn.close()
    if username not in ("admin", "adminpre"):
        await update.message.reply_text("🚫 У вас немає доступу до цієї команди 🚫")
        return

    # Генеруємо PDF
    pdf_filename = "ai_dialogs_report.pdf"
    ai_log_to_pdf(pdf_filename)
    # Відправляємо PDF
    try:
        with open(pdf_filename, "rb") as pdf_file:
            await update.message.reply_document(pdf_file, filename=pdf_filename)
    except Exception as e:
        await update.message.reply_text("⚠️ Не вдалося надіслати PDF.")
        logging.error(f"Помилка надсилання PDF: {e}")


async def admin_change_role_handler(update: Update, context: CallbackContext):
    logging.info(f"admin_change_role_handler step: {context.user_data.get('change_role_step')}")
    logging.info(f"admin_change_role_handler id: {context.user_data.get('change_role_id')}")
    if context.user_data.get("change_role_step") == "get_id":
        telegram_id = update.message.text.strip()
        context.user_data["change_role_id"] = telegram_id
        context.user_data["change_role_step"] = "get_role"
        await update.message.reply_text("Введіть нову роль (username) для цього користувача:")
    elif context.user_data.get("change_role_step") == "get_role":
        new_role = update.message.text.strip()
        telegram_id = context.user_data.get("change_role_id")
        conn = get_pg_connection()
        cursor = conn.cursor()
        try:
            cursor.execute(
                "UPDATE database_app_userdatatelegram SET username = %s WHERE telegram_id = %s",
                (new_role, telegram_id)
            )
            conn.commit()
            await update.message.reply_text(f"✅ Роль користувача {telegram_id} змінено на '{new_role}'!")

            # Надсилаємо повідомлення користувачу
            role_text = ROLE_DESCRIPTIONS.get(new_role, "Опис ролі не знайдено.")
            try:
                await context.bot.send_message(
                    chat_id=int(telegram_id),
                    text=(
                        f"🔔 Вашу роль змінено!\n"
                        f"Нова роль: <b>{new_role}</b>\n"
                        f"{role_text}\n"
                        f"Натисніть /start для оновлення меню."
                    ),
                    parse_mode="HTML",
                    reply_markup=ReplyKeyboardMarkup(
                        [[KeyboardButton("/start")]],
                        resize_keyboard=True,
                        one_time_keyboard=True
                    )
                )
            except Exception as e:
                logging.error(f"Не вдалося надіслати повідомлення користувачу: {e}")

        except Exception as e:
            await update.message.reply_text("⚠️ Не вдалося змінити роль. Перевірте дані.")
            logging.error(f"Помилка зміни ролі: {e}")
        finally:
            cursor.close()
            conn.close()
        context.user_data.pop("change_role_step", None)
        context.user_data.pop("change_role_id", None)

async def show_user_list_for_role_change(query, context, page=0):
    logging.info(f"show_user_list_for_role_change page={page}")
    logging.info(f"role_users: {context.user_data.get('role_users')}")
    users = context.user_data.get("role_users", [])
    total_pages = (len(users) - 1) // USERS_PER_PAGE + 1
    start = page * USERS_PER_PAGE
    end = start + USERS_PER_PAGE
    page_users = users[start:end]

    keyboard = [
        [InlineKeyboardButton(f"{u[1]} ({u[2]})", callback_data=f"change_role_select_{u[0]}")] for u in page_users
    ]
    nav_buttons = []
    if page > 0:
        nav_buttons.append(InlineKeyboardButton("◀️", callback_data=f"change_role_page_{page-1}"))
    if page < total_pages - 1:
        nav_buttons.append(InlineKeyboardButton("▶️", callback_data=f"change_role_page_{page+1}"))
    nav_buttons.append(InlineKeyboardButton("⬅️ Назад", callback_data="change_role_back"))
    if nav_buttons:
        keyboard.append(nav_buttons)

    reply_markup = InlineKeyboardMarkup(keyboard)
    text = f"Оберіть користувача для зміни ролі (сторінка {page+1}/{total_pages}):"

    try:
        await query.edit_message_text(text, reply_markup=reply_markup)
    except Exception as e:
        # Якщо не вдалося редагувати, надсилаємо нове повідомлення
        logging.warning(f"edit_message_text не спрацював: {e}")
        await query.message.reply_text(text, reply_markup=reply_markup)

async def admin_change_role_callback_handler(update: Update, context: CallbackContext):
    logging.info(f"admin_change_role_callback_handler: {update.callback_query.data}")
    
    logging.info(f"CallbackQuery: {update.callback_query.data}")
    logging.info(f"role_users: {context.user_data.get('role_users')}")
    query = update.callback_query
    await query.answer()
    data = query.data

    if data.startswith("change_role_page_"):
        page = int(data.split("_")[-1])
        await show_user_list_for_role_change(query, context, page=page)
    elif data.startswith("change_role_select_"):
        telegram_id = data.split("_")[-1]
        context.user_data["change_role_id"] = telegram_id
        context.user_data["change_role_step"] = "get_role"
        await query.edit_message_text(f"Введіть нову роль для користувача {telegram_id}:")
    elif data == "change_role_back":
        await show_admin_menu(update, context)

