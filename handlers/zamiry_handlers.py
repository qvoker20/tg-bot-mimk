import logging
import re
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import CallbackContext
from datetime import datetime, timedelta
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
# SECOND_TABLE_NAME = "second_sheet_data"

async def search(update: Update, context: CallbackContext):

    keyboard = [
        [InlineKeyboardButton("➡️ Шукати замовлення за всіма частинами", callback_data='by_number')],
        [InlineKeyboardButton("➡️ Шукати замолення за частиною", callback_data='specific')],
        [InlineKeyboardButton("⬅️ Назад", callback_data='back')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    # Видаляємо попереднє повідомлення, якщо воно існує
    if "search_message_id" in context.user_data:
        try:
            await context.bot.delete_message(
                chat_id=update.effective_chat.id,
                message_id=context.user_data["search_message_id"]
            )
        except Exception as e:
            logging.warning(f"Не вдалося видалити попереднє повідомлення: {e}")

    # Відправляємо нове повідомлення
    if update.callback_query:
        try:
            sent_message = await update.callback_query.edit_message_text(
                "⬇️ Вибір типу пошуку для визначення статусу замовлення в 3D адаптаціях:", reply_markup=reply_markup
            )
        except Exception as e:
            logging.warning(f"Не вдалося редагувати повідомлення: {e}")
            return
    else:
        sent_message = await update.message.reply_text(
            "⬇️ Вибір типу пошуку для визначення статусу замовлення в 3D адаптаціях:", reply_markup=reply_markup
        )

    # Зберігаємо message_id нового повідомлення
    context.user_data["search_message_id"] = sent_message.message_id

    def find_specific_order(position, order_number):
        try:
            conn = get_pg_connection()
            cursor = conn.cursor()

            # Звертаємося до відповідних колонок: column2 - номер замовлення, column3 - позиція (заміни на свої, якщо потрібно)
            cursor.execute('SELECT * FROM sheet_data WHERE column2 = %s AND column3 = %s', (order_number, position))
            rows = cursor.fetchall()

            results = []
            for row in rows:
                quantity = row[4] if len(row) > 4 else "Невідомо"
                name = row[6] if len(row) > 6 else "Невідомо"
                technology = row[13] if len(row) > 13 else "Невідомо"
                tech_people = row[11] if len(row) > 11 else "Невідомо"
                comment = row[20] if len(row) > 20 else "Коментар відсутній"

                # Визначаємо статус
                if len(row) > 26 and row[26] and str(row[26]).strip().lower() in ["true", "1", "yes"]:
                    status = f"ПАУЗА ⚠️\n📝Причина: {comment}"
                elif len(row) > 25 and row[25] and str(row[25]).strip().lower() in ["true", "1", "yes"]:
                    status = "ВИКОНАНО ✅"
                elif len(row) > 23 and row[23] and str(row[23]).strip().lower() in ["true", "1", "yes"]:
                    status = "В РОБОТІ ▶️"
                elif len(row) > 13 and row[13].strip():
                    status = f"В ЧЕРЗІ 🐒"
                else:
                    status = "РОЗПОДІЛ🔄"

                order_format = (
                    f"<b>═══════════</b>\n"
                    f"❗️ <b>АДАПТАЦІЇ ЗАМІРІВ</b>❗️\n"
                    f"🆔 <b>НОМЕР:</b> {order_number}-{position}{quantity} {name}\n"
                    f"🤖 <b>ТЕХНОЛОГ: </b> {technology}\n"
                    f"🎦 <b>ЗАМІРНИК: </b> {tech_people}\n"
                    f"📊 <b>СТАТУС: {status}</b>\n"
                    f"<b>═══════════</b>"
                )
                results.append(order_format)

            return "\n\n".join(results) if results else f"⚠️Замовлення {position} {order_number} не знайдено.⚠️"
        except Exception as e:
            logging.error(f"Помилка під час пошуку замовлення: {e}")
            return "Сталася помилка під час пошуку замовлення."
        finally:
            cursor.close()
            conn.close()

def find_by_order_number(order_number):
    try:
        conn = get_pg_connection()
        cursor = conn.cursor()

        results = []

        # Пошук у sheet_data
        cursor.execute('SELECT * FROM sheet_data WHERE column2 = %s', (order_number,))
        rows = cursor.fetchall()
        for row in rows:
            position = row[3] if len(row) > 3 else "Невідомо"
            quantity = row[4] if len(row) > 4 else "Невідомо"
            name = row[6] if len(row) > 6 else "Невідомо"
            tech_people = row[11] if len(row) > 11 else "Невідомо"
            technology = row[13] if len(row) > 13 else "Невідомо"
            comment = row[20] if len(row) > 20 else "Коментар відсутній"
            date = row[12] if len(row) > 12 else "Невідомо"

            status = "не визначено"
            if len(row) > 26 and row[26] and str(row[26]).strip().lower() in ["1"]:
                status = f"ПАУЗА ⚠️\n📝 ПРИЧИНА: {comment}"
            elif len(row) > 25 and row[25] and str(row[25]).strip().lower() in ["1"]:
                status = "ВИКОНАНО ✅"
            elif len(row) > 23 and row[23] and str(row[23]).strip().lower() in ["1"]:
                status = "В РОБОТІ ▶️"
            elif len(row) > 13 and row[13].strip():
                status = f"В ЧЕРЗІ 🐒"
            else:
                status = "РОЗПОДІЛ 🔄"

            order_format = (
                f"<b>═══════════</b>\n"
                f"❗️ <b>АДАПТАЦІЇ ЗАМІРІВ</b>❗️\n"
                f"🆔 <b>НОМЕР:</b> {order_number}-{position}{quantity} {name}\n"
                f"🤖 <b>ТЕХНОЛОГ: </b> {technology}\n"
                f"🎦 <b>ЗАМІРНИК: </b> {tech_people}\n"
                f"📅 <b>ДАТА НА ОБРОБКУ: </b> {date}\n"
                f"📊 <b>СТАТУС: {status}</b>\n"
                f"<b>═══════════</b>"
            )
            results.append(order_format)

        # Пошук у sheet_data_dop (з позначкою)
        cursor.execute('SELECT * FROM sheet_data_dop WHERE column2 = %s', (order_number,))
        rows = cursor.fetchall()
        for row in rows:
            position = row[3] if len(row) > 3 else "Невідомо"
            quantity = row[4] if len(row) > 4 else "Невідомо"
            name = row[6] if len(row) > 6 else "Невідомо"
            tech_people = row[11] if len(row) > 11 else "Невідомо"
            technology = row[13] if len(row) > 13 else "Невідомо"
            comment = row[20] if len(row) > 20 else "Коментар відсутній"
            date = row[12] if len(row) > 12 else "Невідомо"

            status = "не визначено"
            if len(row) > 23 and row[23] and str(row[23]).strip().lower() in ["1"]:
                status = f"ПАУЗА ⚠️\n📝 ПРИЧИНА: {comment}"
            elif len(row) > 22 and row[22] and str(row[22]).strip().lower() in ["1"]:
                status = "ВИКОНАНО ✅"
            elif len(row) > 20 and row[20] and str(row[20]).strip().lower() in ["1"]:
                status = "В РОБОТІ ▶️"
            elif len(row) > 13 and row[13].strip():
                status = f"В ЧЕРЗІ 🐒"
            else:
                status = "РОЗПОДІЛ 🔄"

            order_format = (
                f"<b>═══════════</b>\n"
                f"❗️ <b>АДАПТАЦІЇ ЗАМІРІВ ДОП</b>❗️\n"
                f"🆔 <b>НОМЕР:</b> {order_number}-{position}{quantity} {name}\n"
                f"🤖 <b>ТЕХНОЛОГ: </b> {technology}\n"
                f"🎦 <b>ЗАМІРНИК: </b> {tech_people}\n"
                f"📅 <b>ДАТА НА ОБРОБКУ: </b> {date}\n"
                f"📊 <b>СТАТУС: {status}</b>\n"
                f"<b>═══════════</b>"
            )
            results.append(order_format)

        return results if results else [f"⚠️Замовлення {order_number} не знайдено.⚠️"]
    except Exception as e:
        logging.error(f"Помилка під час пошуку замовлення: {e}")
        return ["Сталася помилка під час пошуку замовлення."]
    finally:
        conn.close()

async def button_search(update: Update, context: CallbackContext):
    query = update.callback_query
    await query.answer()

    if query.data == 'by_number':
        # Установлюємо стан для пошуку за номером
        context.user_data["waiting_for_order_number"] = True
        await query.edit_message_text("⬇️ Введіть 4х значний номер замовлення (наприклад, 5672).")
    elif query.data == 'specific':
        # Установлюємо стан для пошуку конкретного замовлення
        context.user_data["waiting_for_specific_order_find_specific_order"] = True
        await query.edit_message_text("⬇️ Введіть позицію і номер замовлення (наприклад, 1 5672).")
    elif query.data == 'back':
        # Видаляємо поточне повідомлення
        try:
            await context.bot.delete_message(
                chat_id=query.message.chat_id,
                message_id=query.message.message_id
            )
        except Exception as e:
            logging.warning(f"Не вдалося видалити повідомлення: {e}")

        # Повертаємося до головного меню
        await show_zamiry_menu(update, context)

async def searchpre(update: Update, context: CallbackContext):

    keyboard = [
        [InlineKeyboardButton("➡️ Приватне/Тендер", callback_data='input')],
        [InlineKeyboardButton("➡️ Дозамір/Перезамір", callback_data='input_specific')],
        [InlineKeyboardButton("⬅️ Назад", callback_data='back')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    # Видаляємо попереднє повідомлення, якщо воно існує
    if "searchpre_message_id" in context.user_data:
        try:
            await context.bot.delete_message(
                chat_id=update.effective_chat.id,
                message_id=context.user_data["searchpre_message_id"]
            )
        except Exception as e:
            logging.warning(f"Не вдалося видалити попереднє повідомлення: {e}")

    # Відправляємо нове повідомлення
    if update.callback_query:
        try:
            sent_message = await update.callback_query.edit_message_text(
                "⬇️ Виберіть тип пошуку за 'Графіком замірів':", reply_markup=reply_markup
            )
        except Exception as e:
            logging.warning(f"Не вдалося редагувати повідомлення: {e}")
            return
    else:
        sent_message = await update.message.reply_text(
            "⬇️ Виберіть тип пошуку за 'Графіком замірів':", reply_markup=reply_markup
        )

    # Зберігаємо message_id нового повідомлення
    context.user_data["searchpre_message_id"] = sent_message.message_id

async def button_searchpre(update: Update, context: CallbackContext):
    query = update.callback_query
    query.answer()

    if query.data == 'input':
        # Якщо користувач натискає "Ввести номер замовлення"
        context.user_data["waiting_for_order_number_find_order_in_measuring"] = True  # Чекаємо вводу номеру
        await query.edit_message_text("⬇️ (Приватне\Тендер) Будь ласка, введіть номер замовлення:")
        
    elif query.data == 'input_specific':
        context.user_data["waiting_for_order_number_find_order_in_measuring_specific"] = True  # Чекаємо вводу номеру
        await query.edit_message_text("⬇️ (Перезамір\Дозамір) Будь ласка, введіть номер замовлення:")
        
    elif query.data == 'back':
        # Видаляємо поточне повідомлення
        try:
            await context.bot.delete_message(
                chat_id=query.message.chat_id,
                message_id=query.message.message_id
            )
        except Exception as e:
            logging.warning(f"Не вдалося видалити повідомлення: {e}")

        # Повертаємося до головного меню
        await show_zamiry_menu(update, context)
def find_order_in_measuring(order_number):
    try:
        conn = get_pg_connection()
        cursor = conn.cursor()

        query = f"SELECT * FROM second_sheet_data WHERE column1 = %s"
        cursor.execute(query, (order_number,))
        rows = cursor.fetchall()

        results = []
        for row in rows:
            tipe = row[2] if len(row) > 2 else "Невідомо"
            if tipe.lower() not in ["приватне", "тендер"]:  # Перевірка на "Приватне" або "Тендер"
                continue

            maneger = row[3] if len(row) > 3 else "Невідомо"
            adres = row[6] if len(row) > 6 else "Невідомо"
            measurer = row[15] if len(row) > 15 else "Невідомо"
            measure_date = row[16] if len(row) > 16 else "Невідомо"

            order_info = (
                f"<b>═════════════</b>\n"
                f"❗️ <b>ГРАФІК ЗАМІРІВ</b> ❗️\n"
                f"🆔 <b>НОМЕР:</b> {order_number}\n"
                f"♻️ <b>ТИП:</b> {tipe.capitalize()}\n"
                f"👩🏻‍💼 <b>МЕНЕДЖЕР:</b> {maneger}\n"
                f"🚩 <b>АДРЕСА:</b> {adres}\n"
                f"🎦 <b>ЗАМІРНИК:</b> {measurer}\n"
                f"📅 <b>ДАТА ЗАМІРУ:</b> {measure_date}\n"
                f"<b>═════════════</b>"
            )
            results.append(order_info)

        return results if results else [f"Замовлення {order_number} не знайдено."]
    except Exception as e:
        logging.error(f"Помилка під час пошуку замовлення: {e}")
        return ["Сталася помилка під час пошуку замовлення."]
    finally:
        conn.close()       

def find_order_in_measuring_specific(order_number):
    try:
        conn = get_pg_connection()
        cursor = conn.cursor()

        query = f"SELECT * FROM second_sheet_data WHERE column1 = %s"
        cursor.execute(query, (order_number,))
        rows = cursor.fetchall()

        results = []
        for row in rows:
            tipe = row[2] if len(row) > 2 else "Невідомо"
            if tipe.lower() not in ["дозамір", "перезамір"]:  # Перевірка на "дозамір" або "перезамір"
                continue

            maneger = row[3] if len(row) > 3 else "Невідомо"
            adres = row[6] if len(row) > 6 else "Невідомо"
            measurer = row[15] if len(row) > 15 else "Невідомо"
            measure_date = row[16] if len(row) > 16 else "Невідомо"

            order_info = (
                f"<b>═════════════</b>\n"
                f"❗️ <b>ГРАФІК ЗАМІРІВ</b> ❗️\n"
                f"🆔 <b>НОМЕР:</b> {order_number}\n"
                f"♻️ <b>ТИП:</b> {tipe.capitalize()}\n"
                f"👩🏻‍💼 <b>МЕНЕДЖЕР:</b> {maneger}\n"
                f"🚩 <b>АДРЕСА:</b> {adres}\n"
                f"🎦 <b>ЗАМІРНИК:</b> {measurer}\n"
                f"📅 <b>ДАТА ЗАМІРУ:</b> {measure_date}\n"
                f"<b>═════════════</b>"
            )
            results.append(order_info)

        return results if results else [f"Замовлення {order_number} не знайдено."]
    except Exception as e:
        logging.error(f"Помилка під час пошуку замовлення: {e}")
        return ["Сталася помилка під час пошуку замовлення."]
    finally:
        conn.close()

async def show_zamiry_menu(update: Update, context: CallbackContext):
    """Відображає меню 'Заміри'."""
    # Видаляємо повідомлення меню "Замірникам", якщо воно існує
    if "zamirnykam_message_id" in context.user_data:
        try:
            await context.bot.delete_message(
                chat_id=update.effective_chat.id,
                message_id=context.user_data["zamirnykam_message_id"]
            )
        except Exception as e:
            logging.warning(f"Не вдалося видалити повідомлення 'Замірникам': {e}")

    keyboard = [
        [InlineKeyboardButton("➡️ Пошук заміру АДАПТАЦІЇ", callback_data='search')],
        [InlineKeyboardButton("➡️ Пошук заміру ГРАФІК", callback_data='searchpre')],
        [InlineKeyboardButton("➡️ Сервіс замірів", callback_data='mservice')],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    # Видаляємо попереднє повідомлення, якщо воно існує
    if "zamiry_message_id" in context.user_data:
        try:
            await context.bot.delete_message(
                chat_id=update.effective_chat.id,
                message_id=context.user_data["zamiry_message_id"]
            )
        except Exception as e:
            logging.warning(f"Не вдалося видалити попереднє повідомлення: {e}")

    # Надсилаємо нове повідомлення
    message_obj = None
    if hasattr(update, "message") and update.message:
        message_obj = update.message
    elif hasattr(update, "callback_query") and update.callback_query and update.callback_query.message:
        message_obj = update.callback_query.message

    if message_obj:
        sent_message = await message_obj.reply_text(
            "⬇️ Доступні команди для розділу 'Заміри':", reply_markup=reply_markup
        )
        context.user_data["zamiry_message_id"] = sent_message.message_id
    else:
        logging.error("Не знайдено об'єкта для надсилання повідомлення у show_zamiry_menu.")


async def button(update: Update, context: CallbackContext):
    query = update.callback_query
    await query.answer()

    if query.data == 'search':
        await search(update, context)
    elif query.data == 'searchpre':
        await searchpre(update, context)
    elif query.data == 'mservice':
        await mservice(update, context)

async def mservice(update: Update, context: CallbackContext):
    keyboard = [
        [InlineKeyboardButton("➡️ Подача заміру на Адаптацію", callback_data='by_adaptation')],
        [InlineKeyboardButton("➡️ Потрібна допомога (Залишити заявку)", callback_data='by_help')],
        [InlineKeyboardButton("⬅️ Назад", callback_data='back')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    # Видаляємо попереднє повідомлення, якщо воно існує
    if "mservice_message_id" in context.user_data:
        try:
            await context.bot.delete_message(
                chat_id=update.effective_chat.id,
                message_id=context.user_data["mservice_message_id"]
            )
        except Exception as e:
            logging.warning(f"Не вдалося видалити попереднє повідомлення: {e}")

    # Відправляємо нове повідомлення
    if update.callback_query:
        try:
            sent_message = await update.callback_query.edit_message_text(
                "⬇️ Вберіть тип допомоги:", reply_markup=reply_markup
            )
        except Exception as e:
            logging.warning(f"Не вдалося редагувати повідомлення: {e}")
            return
    else:
        sent_message = await update.message.reply_text(
            "⬇️ Вберіть тип допомоги:", reply_markup=reply_markup
        )

    # Зберігаємо message_id нового повідомлення
    context.user_data["mservice_message_id"] = sent_message.message_id

async def mservice_button(update: Update, context: CallbackContext):
    query = update.callback_query
    await query.answer()

    if query.data == 'by_adaptation':
        context.user_data["waiting_for_adaptation_request"] = True
        await query.edit_message_text(
            "❗️Введіть номер замовлення для адаптації за номером 6295, або за частиною 1 6295. "
            "(Врахуйте, якщо замовлення вже є у списку на адаптацію, краще за всього залишити заявку на допомогу!)"
        )
    elif query.data == 'by_help':
        context.user_data["waiting_for_help_request"] = True
        context.user_data.pop("pending_help_request_text", None)
        await query.edit_message_text(
            "⬇️ Введіть текст вашого запиту (Цей запит бачить весь відділ замірів. "
            "Запит буде оброблено якнайшвидше):"
        )
    elif query.data == 'back':
        try:
            await context.bot.delete_message(
                chat_id=query.message.chat_id,
                message_id=query.message.message_id
            )
        except Exception as e:
            logging.warning(f"Не вдалося видалити повідомлення: {e}")

        await show_zamiry_menu(update, context)

def check_order_request(text):
    match_full = re.match(r'^(\d+)\s+(\d{4})$', text)  # Формат "1 6295"
    match_number = re.match(r'^\d{4}$', text)  # Формат "6295"

    try:
        conn = get_pg_connection()
        cursor = conn.cursor()

        if match_full:
            # Якщо введено формат "1 6295"
            position, order_number = match_full.groups()
            cursor.execute('SELECT * FROM sheet_data WHERE column2 = %s AND column3 = %s', (order_number, position))
            row = cursor.fetchone()
            if row:
                return "found", position, order_number
            else:
                return "not_found", position, order_number

        elif match_number:
            # Якщо введено лише чотиризначне число
            order_number = match_number.group(0)
            cursor.execute('SELECT * FROM sheet_data WHERE column2 = %s', (order_number,))
            row = cursor.fetchone()
            if row:
                return "found", None, order_number
            else:
                return "not_found", None, order_number

        return "invalid_format", None, None
    except Exception as e:
        logging.error(f"Помилка під час пошуку замовлення: {e}")
        return "invalid_format", None, None
    finally:
        cursor.close()
        conn.close()

def find_specific_order(position, order_number):
    try:
        conn = get_pg_connection()
        cursor = conn.cursor()

        # Звертаємося до відповідних колонок: column2 - номер замовлення, column3 - позиція (заміни на свої, якщо потрібно)
        cursor.execute('SELECT * FROM sheet_data WHERE column2 = %s AND column3 = %s', (order_number, position))
        rows = cursor.fetchall()

        results = []
        for row in rows:
            quantity = row[4] if len(row) > 4 else "Невідомо"
            name = row[6] if len(row) > 6 else "Невідомо"
            technology = row[13] if len(row) > 13 else "Невідомо"
            tech_people = row[11] if len(row) > 11 else "Невідомо"
            comment = row[20] if len(row) > 20 else "Коментар відсутній"

            # Визначаємо статус
            if len(row) > 26 and row[26] and str(row[26]).strip().lower() in ["true", "1", "yes"]:
                status = f"ПАУЗА ⚠️\n📝Причина: {comment}"
            elif len(row) > 25 and row[25] and str(row[25]).strip().lower() in ["true", "1", "yes"]:
                status = "ВИКОНАНО ✅"
            elif len(row) > 23 and row[23] and str(row[23]).strip().lower() in ["true", "1", "yes"]:
                status = "В РОБОТІ ▶️"
            elif len(row) > 13 and row[13].strip():
                status = f"В ЧЕРЗІ 🐒"
            else:
                status = "РОЗПОДІЛ🔄"

            order_format = (
                f"<b>═══════════</b>\n"
                f"❗️ <b>АДАПТАЦІЇ ЗАМІРІВ</b>❗️\n"
                f"🆔 <b>НОМЕР:</b> {order_number}-{position}{quantity} {name}\n"
                f"🤖 <b>ТЕХНОЛОГ: </b> {technology}\n"
                f"🎦 <b>ЗАМІРНИК: </b> {tech_people}\n"
                f"📊 <b>СТАТУС: {status}</b>\n"
                f"<b>═══════════</b>"
            )
            results.append(order_format)

        return "\n\n".join(results) if results else f"⚠️Замовлення {position} {order_number} не знайдено.⚠️"
    except Exception as e:
        logging.error(f"Помилка під час пошуку замовлення: {e}")
        return "Сталася помилка під час пошуку замовлення."
    finally:
        cursor.close()
        conn.close()

async def button_searchpre(update: Update, context: CallbackContext):
    query = update.callback_query
    query.answer()

    if query.data == 'input':
        # Якщо користувач натискає "Ввести номер замовлення"
        context.user_data["waiting_for_order_number_find_order_in_measuring"] = True  # Чекаємо вводу номеру
        await query.edit_message_text("⬇️ (Приватне\Тендер) Будь ласка, введіть номер замовлення:")
        
    elif query.data == 'input_specific':
        context.user_data["waiting_for_order_number_find_order_in_measuring_specific"] = True  # Чекаємо вводу номеру
        await query.edit_message_text("⬇️ (Перезамір\Дозамір) Будь ласка, введіть номер замовлення:")
        
    elif query.data == 'back':
        # Видаляємо поточне повідомлення
        try:
            await context.bot.delete_message(
                chat_id=query.message.chat_id,
                message_id=query.message.message_id
            )
        except Exception as e:
            logging.warning(f"Не вдалося видалити повідомлення: {e}")

        # Повертаємося до головного меню
        await show_zamiry_menu(update, context)
# функція для пошуку замовлення тендер\приватне в таблиці ЗАМІРИ

async def handle_help_request_input(update: Update, context: CallbackContext):
    """
    Викликати з вашого текстового хендлера.
    Працює лише коли користувач у стані waiting_for_help_request.
    """
    if not context.user_data.get("waiting_for_help_request"):
        return False

    if not update.message or not update.message.text:
        return True

    help_text = update.message.text.strip()
    if not help_text:
        await update.message.reply_text("⚠️ Текст запиту порожній. Введіть, будь ласка, запит.")
        return True

    context.user_data["pending_help_request_text"] = help_text
    context.user_data["waiting_for_help_request"] = False

    keyboard = [
        [
            InlineKeyboardButton("✅ Відправити", callback_data="help_send"),
            InlineKeyboardButton("❌ Скасувати", callback_data="help_cancel"),
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await update.message.reply_text(
        f"📝 Ваш запит:\n\n{help_text}\n\nПідтвердьте дію:",
        reply_markup=reply_markup
    )
    return True

async def help_request_confirm(update: Update, context: CallbackContext):
    query = update.callback_query
    await query.answer()

    action = query.data
    pending_text = context.user_data.get("pending_help_request_text")

    if action == "help_cancel":
        context.user_data.pop("pending_help_request_text", None)
        context.user_data.pop("waiting_for_help_request", None)  # не чекаємо новий текст
        await query.edit_message_text("❌ Запит скасовано.")
        return

    if action == "help_send":
        if not pending_text:
            await query.edit_message_text("⚠️ Немає тексту запиту для відправки.")
            return

        # ... ваша відправка в групу ...
        context.user_data.pop("pending_help_request_text", None)
        context.user_data.pop("waiting_for_help_request", None)
        await query.edit_message_text("✅ Запит відправлено.")