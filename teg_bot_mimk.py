from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from telegram import ReplyKeyboardRemove
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
from telegram import Update, ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove
from telegram.ext import CommandHandler, Application, CallbackContext, MessageHandler, CallbackQueryHandler, filters
import logging, sqlite3, re, pytz, json, os, zipfile
from triggers import daily_measurements_trigger, check_for_changes
from datetime import timedelta, time, datetime, date
from openai import OpenAI
import httpx
import os
from utils.imports import *
from handlers.zamiry_handlers import (
    find_specific_order, button_searchpre, search, find_by_order_number, button_search,
    find_order_in_measuring, find_order_in_measuring_specific, show_zamiry_menu, button,
    mservice, mservice_button, check_order_request,
    handle_help_request_input, help_request_confirm  # <-- додати
)
from handlers.zamirnykam_functions import is_user_allowed, get_user_data, is_admin, show_zamirnykam_menu, show_zamiry_today, zamirnykam_button_handler, calculate_bonuses, show_zamiry_tomorrow
from handlers.production_handlers import (
    show_production_menu,
    find_purchase_by_order_number, production_button_handler, find_by_nymber_order
)
from handlers.mimk_ai_handlers import show_mimk_ai, mimk_ai_button_handler, handle_mimk_ai_text  
from handlers.admin_handlers_custom import (
    show_admin_menu, admin_button_handler, send_ai_log_pdf,
    notify_admin_about_restriction, admin_change_role_callback_handler
)
from handlers.assemblers_handlers import show_assemblers_menu, assembler_button_handler
from handlers.logistics_handlers import show_logistics_menu, logistics_button_handler, logistics_text_input
from handlers.assemblers_handlers import show_assemblers_menu, assembler_button_handler
from utils.db_utils import get_user_data
from googleapiclient.http import MediaFileUpload
import psycopg2
import os
from dotenv import load_dotenv

load_dotenv()

PG_CONN = {
    "host": os.environ.get("PG_HOST"),
    "port": int(os.environ.get("PG_PORT")),
    "dbname": os.environ.get("PG_DBNAME"),
    "user": os.environ.get("PG_USER"),
    "password": os.environ.get("PG_PASSWORD")
}

CONSTRUCTOR_ALLOWED_ROLES = {
    "конструктор",
    "керівник конструктор приват",
    "керівник конструктор тендер",
    "головний конструктор",
    "admin",
}

def has_constructor_access(role: str | None) -> bool:
    if not role:
        return False
    return role.strip().casefold() in {r.casefold() for r in CONSTRUCTOR_ALLOWED_ROLES}

ZAMIRNYKAM_ALLOWED_ROLES = {
    "замірник",
    "admin",
}

def has_zamirnykam_access(role: str | None) -> bool:
    if not role:
        return False
    return role.strip().casefold() in {r.casefold() for r in ZAMIRNYKAM_ALLOWED_ROLES}

def get_user_role(user_id: int):
    conn = get_pg_connection()
    cursor = conn.cursor()
    try:
        cursor.execute(
            "SELECT username FROM database_app_userdatatelegram WHERE telegram_id = %s",
            (user_id,)
        )
        row = cursor.fetchone()
        return row[0] if row else None
    finally:
        cursor.close()
        conn.close()

def get_pg_connection():
    return psycopg2.connect(**PG_CONN)

def get_user_data(user_id):
    conn = get_pg_connection()
    cursor = conn.cursor()
    try:
        cursor.execute(
            "SELECT name, telegram_id, phone_number FROM database_app_userdatatelegram WHERE telegram_id = %s",
            (user_id,)
        )
        row = cursor.fetchone()
        return row if row else None
    finally:
        cursor.close()
        conn.close()


OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")
openai_client = OpenAI(api_key=OPENAI_API_KEY) if OPENAI_API_KEY else None

# Глобальний словник для зберігання корист
# увачів і їхніх запитів
user_requests = {}

# Встановлюємо часову зону
local_timezone = pytz.timezone("Europe/Kiev")

# Оновлена функція /start
async def start(update: Update, context: CallbackContext):
    user_id = update.message.from_user.id
    user_data = get_user_data(user_id)
    if not user_data:
        # Якщо користувача немає в базі — просимо надіслати номер телефону
        keyboard = [
            [KeyboardButton("Пройти реєстрацію")]
        ]
        reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True, one_time_keyboard=True)
        await update.message.reply_text(
            "Вас немає у базі користувачів. Для доступу до системи натисніть кнопку нижче:",
            reply_markup=reply_markup
        )
        return

    full_name, telegram_id, phone_number = user_data

    # Дізнаємось username (роль) користувача
    username = get_user_role(user_id)

    # Формуємо меню
    # Формуємо меню
    first_row = ["Заміри"]
    if has_zamirnykam_access(username):
        first_row.append("Замірникам")

    third_row = ["Збиральникам"]
    if has_constructor_access(username):
        third_row.insert(0, "Конструктор")

    keyboard = [
        first_row,
        ["Виробництво", "Логістика"],
        ["MIM-K HUB"],
        third_row
    ]
    if (username or "").strip().casefold() == "admin":
        keyboard.append(["Admin"])

    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
    await update.message.reply_text(
        f"✅Вітаємо, {full_name}✅",
        reply_markup=reply_markup
    )
# Надсилання повідомлення адміністратору про спробу доступу
# Запрос номеру телефону, якщо користувач не має доступу, та надислання данних адміністратору
async def handle_contact(update: Update, context: CallbackContext):
    """Обробляє контакт, надісланий користувачем."""
    contact = update.message.contact
    admin_id = 403271614  # ID адміністратора

    # Формуємо повідомлення для адміністратора
    user_info = (
        f"ID: {contact.user_id}\n"
        f"Ім'я: {contact.first_name}\n"
        f"Прізвище: {contact.last_name if contact.last_name else 'немає'}\n"
        f"Номер телефону: {contact.phone_number}"
    )
    message = f"⚠️Заявка на реестрацію:⚠️\n{user_info}"

    # Надсилаємо повідомлення адміністратору
    try:
        await context.bot.send_message(chat_id=admin_id, text=message)
        await update.message.reply_text("✅Запит на доступ надіслано адміністратору. Очікуйте на відповідь✅")
    except Exception as e:
        logging.error(f"Не вдалося надіслати повідомлення адміністратору: {e}")
        await update.message.reply_text("Сталася помилка під час надсилання вашого номера адміністратору.")
# перевірка доступу користувача по id з бази даних
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

from telegram.ext import CallbackQueryHandler

async def registration_callback(update: Update, context: CallbackContext):
    query = update.callback_query
    await query.answer()
    if query.data == "reg_send":
        # Зберігаємо заявку у БД
        try:
            conn = get_pg_connection()
            cursor = conn.cursor()
            cursor.execute(
                "INSERT INTO registration_requests (telegram_id, first_name, last_name, position, phone_number, status) VALUES (%s, %s, %s, %s, %s, %s)",
                (
                    query.from_user.id,
                    context.user_data["reg_first_name"],
                    context.user_data["reg_last_name"],
                    context.user_data["reg_position"],
                    context.user_data["reg_phone"],
                    "pending" 
                )
            )
            conn.commit()
            cursor.close()
            conn.close()
        except Exception as e:
            await query.edit_message_text(f"⚠️ Помилка при збереженні заявки: {e}")
            context.user_data.pop("reg_step", None)
            return

        # Знайти telegram_id адміна (username == 'admin')
        conn = get_pg_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT telegram_id FROM database_app_userdatatelegram WHERE username = %s", ("admin",))
        admin_row = cursor.fetchone()
        cursor.close()
        conn.close()
        admin_id = admin_row[0] if admin_row else None

        msg = (
            f"⚠️ Нова заявка на реєстрацію:\n"
            f"ID: {query.from_user.id}\n"
            f"Прізвище: {context.user_data['reg_last_name']}\n"
            f"Ім'я: {context.user_data['reg_first_name']}\n"
            f"Посада: {context.user_data['reg_position']}\n"
            f"Телефон: {context.user_data['reg_phone']}"
        )
        if admin_id:
            try:
                await context.bot.send_message(chat_id=admin_id, text=msg)
            except Exception as e:
                logging.warning(f"Не вдалося надіслати адміну: {e}")

        await query.edit_message_text("✅ Заявку на реєстрацію надіслано адміністратору. Очікуйте підтвердження.")
        context.user_data.pop("reg_step", None)
    elif query.data == "reg_cancel":
        await query.edit_message_text("❌ Реєстрацію скасовано.")
        context.user_data.pop("reg_step", None)


async def handle_text(update: Update, context: CallbackContext):

    if update.effective_chat.id in [-1002597813419, -1002739662152]:
        return
    
    user = update.message.from_user
    chat = update.effective_chat
    message = update.message
    logging.info(
        f"[TEXT] chat_id={chat.id} "
        f"chat_title='{chat.title if hasattr(chat, 'title') else 'PRIVATE'}' "
        f"thread_id={getattr(message, 'message_thread_id', None)} "
        f"user_id={user.id} username={user.username} "
        f"text='{message.text}' date={message.date}"
    )

    user_id = update.message.from_user.id
    text = update.message.text.strip()

    if text == "Пройти реєстрацію":
        context.user_data["reg_step"] = "last_name"
        await update.message.reply_text("Введіть ваше прізвище:")
        return

     # --- Діалог реєстрації ---
    if context.user_data.get("reg_step"):
        step = context.user_data["reg_step"]
        if step == "last_name":
            context.user_data["reg_last_name"] = text
            context.user_data["reg_step"] = "first_name"
            await update.message.reply_text("Введіть ваше ім'я:")
            return
        elif step == "first_name":
            context.user_data["reg_first_name"] = text
            context.user_data["reg_step"] = "position"
            await update.message.reply_text("Введіть вашу посаду:")
            return
        elif step == "position":
            context.user_data["reg_position"] = text
            context.user_data["reg_step"] = "phone"
            await update.message.reply_text("Введіть ваш номер телефону (у форматі +380...):")
            return
        elif step == "phone":
            context.user_data["reg_phone"] = text
            # Показуємо попередній перегляд і кнопки
            preview = (
                "<b>Перевірте ваші дані:</b>\n"
                f"Прізвище: <b>{context.user_data['reg_last_name']}</b>\n"
                f"Ім'я: <b>{context.user_data['reg_first_name']}</b>\n"
                f"Посада: <b>{context.user_data['reg_position']}</b>\n"
                f"Телефон: <b>{context.user_data['reg_phone']}</b>\n"
            )
            keyboard = [
                [InlineKeyboardButton("✅ Надіслати", callback_data="reg_send")],
                [InlineKeyboardButton("❌ Відміна", callback_data="reg_cancel")]
            ]
            await update.message.reply_text(
                preview,
                reply_markup=InlineKeyboardMarkup(keyboard),
                parse_mode="HTML"
            )
            context.user_data["reg_step"] = "confirm"
            return
        
    # Перевіряємо доступ через базу даних
    user_data = get_user_data(user_id)
    if not user_data:
        await notify_admin_about_restriction(update, context, user_id)
        await update.message.reply_text(
            "⚠️ У вас немає доступу до цього бота. Передійти до реєстрації /start.\n"
            "Або до адміністратора @mindalovv"
        )
        return  
    
    # Ініціалізуємо змінну result за замовчуванням
    result = []

    handled = await handle_help_request_input(update, context)
    if handled:
        return

    handled = await logistics_text_input(update, context)
    if handled:
        return

    if context.user_data.get("waiting_for_adaptation_request"):
        # Скидаємо стан
        context.user_data["waiting_for_adaptation_request"] = False

        # Викликаємо функцію перевірки
        status, position, order_number = check_order_request(text)

        if status == "found":
            if position:
                await update.message.reply_text(f"❗️Замовлення {order_number} з позицією {position} вже є в списку на адаптацію.❗️")
            else:
                await update.message.reply_text(f"❗️Замовлення {order_number} вже є в списку на адаптацію.❗️\n скористайтеся пошуком адаптації.\n або подайте запит на адаптацію за частиною.")
        elif status == "not_found":
            # Ідентифікатор групи та гілки
            group_chat_id = -1002597813419  # Замініть на реальний chat_id вашої групи
            thread_id = 2  # Замініть на реальний message_thread_id гілки (якщо це гілка)

            # Отримуємо інформацію про користувача
            user = update.message.from_user
            user_data = get_user_data(user.id)  # Отримуємо дані з бази
            full_name = user_data[0] if user_data else user.first_name
            username = f"@{user.username}" if user.username else "немає username"
            user_link = f'<a href="tg://user?id={user.id}">{full_name}</a>'

            # Формуємо повідомлення
            message = (
                f"Новий запит на адаптацію:\n"
                f"{text}\n\n"
                f"Від користувача: {user_link}"
            )

            try:
                # Надсилання повідомлення в гілку або основний чат
                await context.bot.send_message(
                    chat_id=group_chat_id,
                    text=message,
                    message_thread_id=thread_id,  # Вказуємо гілку, якщо потрібно
                    parse_mode="HTML"  # Додаємо HTML для посилання
                )
                await update.message.reply_text("Ваш запит на адаптацію успішно надіслано.")
            except Exception as e:
                logging.error(f"Не вдалося надіслати повідомлення в гілку: {e}")
                await update.message.reply_text("Сталася помилка під час надсилання запиту. Спробуйте пізніше.")
        elif status == "invalid_format":
            await update.message.reply_text("Неправильний формат! Введіть 4х значний номер або формат '1 6295'.")
        return
    # Обробка для "Шукати конкретне замовлення"
    if context.user_data.get("waiting_for_specific_order_find_specific_order"):
        try:
            # Розділяємо текст на позицію і номер замовлення
            position, order_number = text.split()
            result = find_specific_order(position, order_number)
        except ValueError:
            result = "Неправильний формат!!!"
        context.user_data["waiting_for_specific_order_find_specific_order"] = False
        await update.message.reply_text(result, parse_mode="HTML")
        return

    if context.user_data.get("waiting_for_order_number"):
        # Перевіряємо, чи введений текст є чотиризначним числом
        if text.isdigit() and len(text) == 4:
            result = find_by_order_number(text)  # Викликаємо функцію пошуку за номером

            # Зберігаємо користувача і номер замовлення в глобальному словнику
            user_requests[text] = user_id

            # Якщо результатів немає, повідомляємо користувача
            if not result:
                await update.message.reply_text("⚠️ Замовлення не знайдено. Перевірте номер і спробуйте ще раз.")
            else:
                # Надсилаємо кожен результат окремим повідомленням
                for res in result:
                    await update.message.reply_text(res, parse_mode="HTML")
        else:
            # Якщо формат неправильний, повідомляємо користувача
            await update.message.reply_text("❌ Неправильний формат! Введіть 4-значний номер замовлення (наприклад, 5672).")

        context.user_data["waiting_for_order_number"] = False  # Скидаємо стан
        return
    
    if context.user_data.get("waiting_for_order_number_find_order_in_measuring_specific"):
    # Перевіряємо, чи введений текст є чотиризначним числом
        if text.isdigit() and len(text) == 4:
            results = find_order_in_measuring_specific(text)  # Викликаємо функцію пошуку за номером
        else:
            results = ["Неправильний формат!!!"]

        context.user_data["waiting_for_order_number_find_order_in_measuring_specific"] = False  # Скидаємо стан

        # Відправляємо кожен результат окремим повідомленням
        for result in results:
            await update.message.reply_text(result, parse_mode="HTML")
        return

    if context.user_data.get("waiting_for_order_number_find_order_in_measuring"):
        if text.isdigit() and len(text) == 4:
            results = find_order_in_measuring(text)
        else:
            results = ["Неправильний формат!!!"]

        context.user_data["waiting_for_order_number_find_order_in_measuring"] = False

        for result in results:
            await update.message.reply_text(result, parse_mode="HTML")
        return
    # Обробка запиту "Потрібна допомога"
    if context.user_data.get("waiting_for_help_request"):
        context.user_data["waiting_for_help_request"] = False  # Скидаємо стан

        group_chat_id = -1002597813419
        thread_id = 4

        user = update.message.from_user
        full_name = user_data[0] if user_data else user.first_name
        phone = user_data[2] if user_data and len(user_data) > 2 else "не вказано"

        message = (
            f"❗️ Новий запит на допомогу ❗️\n"
            f"👤 Користувач: {full_name} (id: {user.id})\n"
            f"📞 Телефон: {phone}\n"
        )
        if text:
            message += f"📄 Текст запиту: {text}"

        try:
            await context.bot.send_message(
                chat_id=group_chat_id,
                text=message,
                message_thread_id=thread_id
            )
            await update.message.reply_text("✅ Ваш запит на допомогу успішно надіслано.")
        except Exception as e:
            logging.exception(f"Не вдалося надіслати запит у сервіс-чат: {e}")
            await update.message.reply_text("⚠️ Не вдалося надіслати запит. Спробуйте пізніше або зверніться до адміністратора.")
        return

    # Додаємо обробку для prod_search (Пошук закупки за замовленням)
    if context.user_data.get("waiting_for_prod_search"):
        context.user_data["waiting_for_prod_search"] = False

        # Витягуємо перші 4 цифри з тексту (навіть якщо там є дефіси, коми, пробіли тощо)
        match = re.search(r'(\d{4})', text)
        if match:
            order_number = match.group(1)
            results = find_purchase_by_order_number(order_number)
            for res in results:
                await update.message.reply_text(res, parse_mode="HTML")
        else:
            await update.message.reply_text("❌ Введть 4-значний номер замовлення (наприклад, 5672).")
        return

    # Додаємо обробку для prod_search (Пошук закупки за замовленням)
    if context.user_data.get("waiting_for_detail_search"):
        context.user_data["waiting_for_detail_search"] = False

        match = re.search(r'(\d{4})', text)
        if match:
            detail_number = match.group(1)
            results = find_by_nymber_order(detail_number)
            if len(results) > 5:  # якщо багато результатів, формуємо PDF
                filename = f"details_{detail_number}_{user_id}.pdf"
                save_messages_to_pdf(results, filename)
                with open(filename, "rb") as pdf_file:
                    await update.message.reply_document(pdf_file, filename=filename)
                os.remove(filename)  # видаляємо файл після відправки
            else:
                for res in results:
                    await update.message.reply_text(res, parse_mode="HTML")
        else:
            await update.message.reply_text("❌ Введть 4-значний номер деталі (наприклад, 5672).")
        return

    if context.user_data.get("ai_mode") in ("sales", "add_knowledge"):
        if openai_client is None:
            context.user_data.pop("ai_mode", None)
            await update.message.reply_text("AI MIM-K тимчасово вимкнено.")
            return
        await handle_mimk_ai_text(update, context, openai_client)
        return
    
    if context.user_data.get("admin_register_step"):
        step = context.user_data["admin_register_step"]
        if step == "telegram_id":
            context.user_data["new_user_telegram_id"] = update.message.text.strip()
            context.user_data["admin_register_step"] = "name"
            await update.message.reply_text("Введіть ПІБ користувача:")
            return
        elif step == "name":
            context.user_data["new_user_name"] = update.message.text.strip()
            context.user_data["admin_register_step"] = "phone"
            await update.message.reply_text("Введіть телефон користувача:")
            return
        elif step == "phone":
            context.user_data["new_user_phone"] = update.message.text.strip()
            context.user_data["admin_register_step"] = "username"
            await update.message.reply_text("Введіть роль (username) користувача:")
            return
        elif step == "username":
            context.user_data["new_user_username"] = update.message.text.strip()
            try:
                # Додаємо користувача в базу
                conn = get_pg_connection()
                cursor = conn.cursor()
                # Перевіряємо, чи вже існує користувач
                cursor.execute(
                    "SELECT 1 FROM database_app_userdatatelegram WHERE telegram_id = %s",
                    (context.user_data["new_user_telegram_id"],)
                )
                if cursor.fetchone():
                    await update.message.reply_text("❗️ Користувач з таким Telegram ID вже існує.")
                else:
                    cursor.execute(
                        "INSERT INTO database_app_userdatatelegram (telegram_id, name, phone_number, username, date_registered) VALUES (%s, %s, %s, %s, %s)",
                        (
                            context.user_data["new_user_telegram_id"],
                            context.user_data["new_user_name"],
                            context.user_data["new_user_phone"],
                            context.user_data["new_user_username"],
                            datetime.now().isoformat()
                        )
                    )
                    conn.commit()
                    await update.message.reply_text("Користувача успішно зареєстровано!")
                    # Надсилаємо повідомлення новому користувачу
                    try:
                        from telegram import ReplyKeyboardMarkup, KeyboardButton
                        await context.bot.send_message(
                            chat_id=int(context.user_data["new_user_telegram_id"]),
                            text="✅Вас додано до системи! Тепер ви можете користуватись ботом✅\n\nНатисніть /start для початку роботи.",
                            reply_markup=ReplyKeyboardMarkup([[KeyboardButton("/start")]], resize_keyboard=True, one_time_keyboard=True)
                        )
                    except Exception as e:
                        logging.warning(f"Не вдалося надіслати повідомлення новому користувачу: {e}")
                        await update.message.reply_text("⚠️ Не вдалося надіслати повідомлення новому користувачу. Переконайтесь, що він писав боту першим.")
            except Exception as e:
                logging.error(f"Помилка реєстрації користувача: {e}")
                await update.message.reply_text(f"⚠️ Помилка реєстрації: {e}")
            finally:
                cursor.close()
                conn.close()
            context.user_data.pop("admin_register_step")
            return
    # Видалення користувача
    if context.user_data.get("admin_delete"):
        telegram_id = update.message.text.strip()
        cconn = get_pg_connection()
        cursor = cconn.cursor()
        cursor.execute("DELETE FROM database_app_userdatatelegram WHERE telegram_id = %s", (telegram_id,))
        cconn.commit()
        cursor.close()
        cconn.close()
        await update.message.reply_text("Користувача видалено (якщо існував).")
        context.user_data.pop("admin_delete")
        return

    logging.info(f"handle_text: change_role_step={context.user_data.get('change_role_step')}")
    logging.info(f"handle_text: change_role_id={context.user_data.get('change_role_id')}")
    # Оголошення
    if context.user_data.get("admin_announce"):
        text = update.message.text.strip()
        conn = get_pg_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT telegram_id FROM database_app_userdatatelegram")
        users = cursor.fetchall()
        cursor.close()
        conn.close()
        for user in users:
            try:
                await context.bot.send_message(chat_id=int(user[0]), text=f"📢 Оголошення:\n{text}")
            except Exception as e:
                logging.warning(f"Не вдалося надіслати оголошення {user[0]}: {e}")
        await update.message.reply_text("Оголошення надіслано всім користувачам.")
        context.user_data.pop("admin_announce")
        return

    if context.user_data.get("change_role_step"):
        from handlers.admin_handlers_custom import admin_change_role_handler
        await admin_change_role_handler(update, context)
        return

    # === Діалог подачі перерізу ===
    if context.user_data.get("cut_step"):
        step = context.user_data["cut_step"]
        if step == "order_number":
            context.user_data["cut_order_number"] = text
            context.user_data["cut_step"] = "launch_number"
            await update.message.reply_text("Введіть номер запуску:")
            return
        elif step == "launch_number":
            context.user_data["cut_launch_number"] = text
            context.user_data["cut_step"] = "cut_number"
            await update.message.reply_text("Введіть номер порізки та частину 1/2:")
            return
        elif step == "cut_number":
            context.user_data["cut_cut_number"] = text
            context.user_data["cut_step"] = "reason"
            await update.message.reply_text("Введіть причину:")
            return
        elif step == "reason":
            context.user_data["cut_reason"] = text
            order = context.user_data.get("cut_order_number")
            launch = context.user_data.get("cut_launch_number")
            cut = context.user_data.get("cut_cut_number")
            reason = context.user_data.get("cut_reason")
            confirm_text = (
                "🔎 <b>Перевірте введені дані:</b>\n"
                "━━━━━━━━━━━━━━━━━━━━━━\n"
                f"🆔 <b>Номер замовлення:</b> <code>{order}</code>\n"
                f"🚀 <b>Номер запуску:</b> <code>{launch}</code>\n"
                f"✂️ <b>Номер деталі та частину:</b> <code>{cut}</code>\n"
                f"📝 <b>Причина:</b> <code>{reason}</code>\n"
                "━━━━━━━━━━━━━━━━━━━━━━\n"
                "<b>Надіслати ці дані?</b>"
            )
            keyboard = [
                [InlineKeyboardButton("✅ Надіслати", callback_data='cut_confirm')],
                [InlineKeyboardButton("❌ Відміна", callback_data='cut_cancel')]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await update.message.reply_text(confirm_text, reply_markup=reply_markup, parse_mode="HTML")
            context.user_data["cut_step"] = "confirm"
            return

    # === Діалог подачі ПРОБЛЕМИ ===
    if context.user_data.get("issue_step"):
        step = context.user_data["issue_step"]
        if step == "order_number":
            context.user_data["issue_order_number"] = text
            context.user_data["issue_step"] = "part_name"
            await update.message.reply_text("📦 Вкажіть одну частину замовлення (без ком):")
            return
        elif step == "part_name":
            context.user_data["issue_part_name"] = text
            context.user_data["issue_step"] = "launch_number"
            await update.message.reply_text("🚀 Вкажіть номер запуску:")
            return
        elif step == "launch_number":
            context.user_data["issue_launch_number"] = text
            context.user_data["issue_step"] = "description"
            await update.message.reply_text("📝 Дайте опис проблеми:")
            return
        elif step == "description":
            context.user_data["issue_description"] = text
            order = context.user_data.get("issue_order_number", "")
            part = context.user_data.get("issue_part_name", "")
            launch = context.user_data.get("issue_launch_number", "")
            desc = context.user_data.get("issue_description", "")
            summary = (
                "🔎 <b>Перевірте дані проблеми:</b>\n"
                "━━━━━━━━━━━━━━━━━━━━━━\n"
                f"🆔 <b>Номер замовлення:</b> <code>{order}</code>\n"
                f"📦 <b>Частина замовлення:</b> <code>{part}</code>\n"
                f"🚀 <b>Номер запуску:</b> <code>{launch}</code>\n"
                f"📝 <b>Опис:</b> <code>{desc}</code>\n"
                "━━━━━━━━━━━━━━━━━━━━━━\n"
                "<b>Надіслати ці дані?</b>"
            )
            keyboard = [
                [InlineKeyboardButton("✅ Відправити", callback_data='issue_confirm')],
                [InlineKeyboardButton("❌ Скасувати", callback_data='issue_cancel')]
            ]
            await update.message.reply_text(summary, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(keyboard))
            context.user_data["issue_step"] = "confirm"
            return

    
   

    if text == "Виробництво":
        await show_production_menu(update, context)
        return

    # Обробка кнопки "Заміри"
    if text == "Заміри":
        await show_zamiry_menu(update, context)
        return
    # Обробка кнопки "Замірникам🛠"
    if text == "Замірникам":
        username = get_user_role(user_id)
        if not has_zamirnykam_access(username):
            await update.message.reply_text("🚫 Доступно тільки для замірника або admin 🚫")
            return
        await show_zamirnykam_menu(update, context)
        return
    
    if text == "Збиральникам":
        await show_assemblers_menu(update, context)
        return

    if text == "Логістика":
        await show_logistics_menu(update, context)
        return

    if text == "MIM-K HUB":
        hub_message = (
            "🌐 <b>MIM-K HUB</b>\n\n"
            "Це корпоративний сайт, де зібрані всі сервіси та Google-таблиці нашої компанії.\n\n"
            "<b>Як увійти:</b>\n"
            "1) Введіть свій номер телефону\n"
            "2) Отримайте код підтвердження\n"
            "3) Увійдіть у систему\n\n"
            "У HUB ви також знайдете інформацію про наших робітників і їхні контакти, щоб швидко зв'язатися з потрібною людиною."
        )
        reply_markup = InlineKeyboardMarkup(
            [[InlineKeyboardButton("Відкрити", url="https://hub.mim-k.website/")]]
        )
        await update.message.reply_text(
            hub_message,
            parse_mode="HTML",
            reply_markup=reply_markup
        )
        return

    if text == "AI MIM-K":
        if openai_client is None:
            await update.message.reply_text("AI MIM-K вимкнено для цього бота.")
            return
        # Перевірка доступу по username
        user_data = get_user_data(user_id)
        if not user_data:
            await update.message.reply_text("У вас немає доступу до цього розділу.")
            return
        username = get_user_role(user_id)
        if (username or "").strip().casefold() not in ("admin", "adminpre"):
            await update.message.reply_text("🚫 У вас немає доступу до AI MIM-K 🚫")
            return
        await show_mimk_ai(update, context)
        return

    if text == "Admin":
            # Перевірка доступу по username
            user_data = get_user_data(user_id)
            if not user_data:
                await update.message.reply_text("У вас немає доступу до цього розділу.")
                return
            username = get_user_role(user_id)
            if (username or "").strip().casefold() != "admin":
                await update.message.reply_text("🚫 У вас немає доступу до цього розділу 🚫")
                return
            await show_admin_menu(update, context)
            return

    if text == "Конструктор":
        # Отримуємо роль користувача з бази
        username = get_user_role(user_id)
        if not has_constructor_access(username):
            await update.message.reply_text("🚫 Доступно тільки для конструкторів 🚫")
            return
        # Створюємо кнопку для переходу на профіль перевірки
        keyboard = [
            [InlineKeyboardButton("Профіль перевірки", url="https://script.google.com/macros/s/AKfycbxaTNhShNjyN8GIIJt5nHJrqqcnkHigjE-maJSXhpyDbLe3hpdBjEFIQIk87Jw90Fn1aA/exec")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text(
            "Оберіть дію:",
            reply_markup=reply_markup
        )
        return

    if "loading_message_id" in context.user_data:
            try:
                await context.bot.delete_message(
                    chat_id=update.effective_chat.id,
                    message_id=context.user_data["loading_message_id"]
                )
            except Exception as e:
                logging.warning(f"Не вдалося видалити повідомлення 'Завантаження': {e}")
            context.user_data.pop("loading_message_id")

    # Якщо жоден стан не активний
    await update.message.reply_text("Будь ласка, скористайтесь меню для вибору дії.")
# Основна функція запуску бота
def main():
    TELEGRAM_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")

    # asyncio.create_task(update_google_sheets())

    application = Application.builder().token(TELEGRAM_TOKEN).build()

    application.add_handler(CommandHandler('start', start))
    application.add_handler(CallbackQueryHandler(registration_callback, pattern="^reg_"))
    application.add_handler(CallbackQueryHandler(button_search, pattern='^(specific|by_number|back)$'))
    application.add_handler(CallbackQueryHandler(button_searchpre, pattern='^(input|input_specific|back)$'))
    application.add_handler(CallbackQueryHandler(mservice_button, pattern='^(by_adaptation|by_help|back)$'))
    application.add_handler(CallbackQueryHandler(button, pattern='^(search|searchpre|searchtabgraf|searchday|mservice)$'))
    application.add_handler(CallbackQueryHandler(zamirnykam_button_handler,pattern='^(zamiry_today|zamiry_tomorrow|adaptations_today|new_adaptations|bonus|bonus_prev|back_to_main)$'))
    application.add_handler(CallbackQueryHandler(
        production_button_handler,
        pattern='^(cut_menu|cut_submit|cut_confirm|cut_cancel|cut_search|issue_submit|issue_confirm|issue_cancel|back_to_production)$'
    ))
    application.add_handler(CallbackQueryHandler(help_request_confirm, pattern='^help_(send|cancel)$'))
    application.add_handler(MessageHandler(filters.CONTACT, handle_contact))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))  # Обробник для головного меню
    application.add_handler(CallbackQueryHandler(mimk_ai_button_handler, pattern='^(ai_sales|ai_tech|ai_work)$'))
    application.add_handler(CallbackQueryHandler(admin_button_handler, pattern='^(admin_register|admin_delete|admin_users|admin_announce|admin_change_role)$'))
    application.add_handler(CallbackQueryHandler(admin_change_role_callback_handler, pattern='^(change_role_page_.*|change_role_select_.*|change_role_back)$'))
    application.add_handler(CallbackQueryHandler(assembler_button_handler, pattern='^(asm_.*)$'))
    application.add_handler(CallbackQueryHandler(
        logistics_button_handler,
        pattern='^(logistics_request|logistics_driver_profile|logistics_menu_back|logistics_back|lp_.*)$'
    ))
    job_queue = application.job_queue

    job_queue.run_daily(
        daily_measurements_trigger,  # Функція, яка буде виконуватися
        time(hour=8, minute=30, tzinfo=local_timezone)  # Час запуску (8:00 ранку за локальним часом)
    )

    # Додаємо періодичну перевірку змін (кожні 5 хвилин)
    job_queue.run_repeating(
        check_for_changes,  # Функція для перевірки змін
        interval=timedelta(minutes=1),  # Інтервал перевірки
        first=0  # Почати одразу після запуску
    )

    application.run_polling()
    
if __name__ == '__main__':
    print("Бот запускається...")
    main()