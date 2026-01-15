import logging
from datetime import datetime, timedelta
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import CallbackContext
import psycopg2

PG_CONN = {
    'host': 'localhost',
    'port': 5433,  # ваш порт
    'dbname': 'parset_google_mimk',
    'user': 'postgres',
    'password': '123789456'
}

def get_pg_connection():
    return psycopg2.connect(**PG_CONN)

# TABLE_NAME = "sheet_data"
# SECOND_TABLE_NAME = "second_sheet_data"

def is_user_allowed(user_id, allowed_ids):
    """Перевіряє, чи є користувач у списку дозволених."""
    return user_id in allowed_ids

def is_admin(user_id):
    conn = get_pg_connection()
    cursor = conn.cursor()
    try:
        cursor.execute(
            "SELECT username FROM database_app_userdatatelegram WHERE telegram_id = %s",
            (user_id,)
        )
        row = cursor.fetchone()
        return row is not None and row[0] == 'admin'
    finally:
        cursor.close()
        conn.close()

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

async def show_zamirnykam_menu(update: Update, context: CallbackContext):
    """Відображає меню для замірників. Доступ лише для admin, замірники, admin_pre."""
    user_id = update.effective_user.id
    user_data = get_user_data(user_id)
    if not user_data:
        await update.message.reply_text("У вас немає доступу до цього розділу.")
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

    if username not in ("admin", "замірник", "admin_pre"):
        await update.message.reply_text("🚫У вас немає доступу до цього розділу🚫")
        return

    if "zamiry_message_id" in context.user_data:
        try:
            await context.bot.delete_message(
                chat_id=update.effective_chat.id,
                message_id=context.user_data["zamiry_message_id"]
            )
        except Exception as e:
            logging.warning(f"Не вдалося видалити повідомлення 'Заміри': {e}")

    keyboard = [
        [InlineKeyboardButton("➡️ Заміри на сьогодні", callback_data='zamiry_today')],
        [InlineKeyboardButton("➡️ Замір на завтра", callback_data='zamiry_tomorrow')],
        [InlineKeyboardButton("➡️ Адаптації на сьогодні", callback_data='adaptations_today')],
        [InlineKeyboardButton("➡️ Нові адаптації", callback_data='new_adaptations')],
        [InlineKeyboardButton("➡️ Бонуси (цей місяць)", callback_data='bonus')],
        [InlineKeyboardButton("➡️ Бонуси (минулий місяць)", callback_data='bonus_prev')],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    if "zamirnykam_message_id" in context.user_data:
        try:
            await context.bot.delete_message(
                chat_id=update.effective_chat.id,
                message_id=context.user_data["zamirnykam_message_id"]
            )
        except Exception as e:
            logging.warning(f"Не вдалося видалити попереднє повідомлення: {e}")

    sent_message = await update.message.reply_text(
        "⬇️ Виберіть дію для замірників:", reply_markup=reply_markup
    )
    context.user_data["zamirnykam_message_id"] = sent_message.message_id

async def zamirnykam_button_handler(update: Update, context: CallbackContext):
    query = update.callback_query
    await query.answer()

    if query.data == 'zamiry_today':
        await show_zamiry_today(query, query.from_user.id)
    elif query.data == 'zamiry_tomorrow':
        await show_zamiry_tomorrow(query, query.from_user.id)
    elif query.data == 'adaptations_today':
        await query.edit_message_text("📅 Адаптації на сьогодні: (тут буде логіка для отримання даних)")
    elif query.data == 'new_adaptations':
        await query.edit_message_text("📅 Нові адаптації: (тут буде логіка для отримання даних)")
    elif query.data == 'bonus':
        await calculate_bonuses(update, context)
    elif query.data == 'bonus_prev':
        await calculate_bonuses_prev_month(update, context)

async def calculate_bonuses(update: Update, context: CallbackContext):
    """Розраховує бонуси за адаптацію замірів для поточного місяця."""
    user_id = update.effective_user.id
    user_data = get_user_data(user_id)

    if not user_data:
        message = update.message or update.callback_query.message
        await message.reply_text("⚠️ У вас немає доступу до цієї функції.")
        return

    logging.info(f"Користувач: {user_data}")

    full_name = user_data[0]
    conn = get_pg_connection()
    cursor = conn.cursor()

    try:
        current_date = datetime.now()
        start_date = current_date.replace(day=1).strftime('%Y-%m-%d')
        end_date = (current_date.replace(day=1) + timedelta(days=32)).replace(day=1) - timedelta(days=1)
        end_date = end_date.strftime('%Y-%m-%d')

        logging.info(f"Діапазон дат: {start_date} - {end_date}")

        query = f"""
            SELECT column2, column6, column13, column18, column28
            FROM sheet_data
            WHERE TO_DATE(column18, 'DD.MM.YY') BETWEEN %s AND %s
        """
        cursor.execute(query, (start_date, end_date))
        rows = cursor.fetchall()

        logging.info(f"Отримані рядки: {rows}")

        user_orders = [row for row in rows if row[2] == full_name]
        message = update.message or update.callback_query.message

        if not user_orders:
            await message.reply_text("⚠️ У вас немає адаптацій за поточний місяць.")
            return

        total_bonus = 0
        order_numbers = []
        for order in user_orders:
            order_number = order[0]
            bonus_part = order[4]
            bonus = 0
            if bonus_part:
                if "\\" in bonus_part:
                    parts = bonus_part.split("\\")
                    kitchen_count = int(parts[0]) * 50
                    product_count = int(parts[1]) * 30
                    bonus = kitchen_count + product_count
                else:
                    bonus = int(bonus_part) * 30
                total_bonus += bonus
            order_numbers.append(str(order_number))

        summary_message = (
            f"<b>Звіт по бонусах за адаптації:</b>\n"
            f"👤 <b>Виконавець:</b> {full_name}\n"
            f"📅 <b>Місяць:</b> {current_date.strftime('%m.%Y')}\n"
            f"🔢 <b>Кількість адаптацій:</b> {len(user_orders)}\n"
            f"💰 <b>Загальна сума бонусів:</b> {total_bonus} грн\n"
            f"🆔 <b>Номери замовлень:</b> {', '.join(order_numbers)}"
        )
        await message.reply_text(summary_message, parse_mode="HTML")

    except Exception as e:
        logging.error(f"Помилка під час розрахунку бонусів: {e}")
        message = update.message or update.callback_query.message
        await message.reply_text("⚠️ Сталася помилка під час розрахунку бонусів.")
    finally:
        cursor.close()
        conn.close()

async def show_zamiry_today(query, user_id):
    """Показати заміри на сьогодні для користувача або для адміністратора."""
    today = datetime.now().strftime('%d.%m.%Y')
    conn = get_pg_connection()
    cursor = conn.cursor()

    try:
        cursor.execute(f"SELECT * FROM second_sheet_data WHERE column16 = %s", (today,))
        rows = cursor.fetchall()

        if is_admin(user_id):
            if not rows:
                await query.message.reply_text("Сьогодні замірів немає.")
            else:
                messages = []
                for row in rows:
                    order_number = row[1] if len(row) > 1 else "Невідомо"
                    tipe = row[2] if len(row) > 2 else "Невідомо"
                    maneger = row[3] if len(row) > 3 else "Невідомо"
                    adres = row[6] if len(row) > 6 else "Невідомо"
                    measurer = row[15] if len(row) > 15 else "Невідомо"
                    measure_date = row[16] if len(row) > 16 else "Невідомо"
                    time = row[17] if len(row) > 17 else "Невідомо"
                    messages.append(
                        f"<b>═════════════</b>\n"
                        f"❗️ <b>ГРАФІК ЗАМІРІВ</b> ❗️\n"
                        f"🆔 <b>НОМЕР:</b> {order_number}\n"
                        f"♻️ <b>ТИП:</b> {tipe}\n"
                        f"👩🏻‍💼 <b>МЕНЕДЖЕР:</b> {maneger}\n"
                        f"🚩 <b>АДРЕСА:</b> {adres}\n"
                        f"🎦 <b>ЗАМІРНИК:</b> {measurer}\n"
                        f"📅 <b>ДАТА ЗАМІРУ:</b> {measure_date}\n"
                        f"📅 <b>ЧАС:</b> {time}\n"
                        f"<b>═════════════</b>"
                    )
                await query.message.reply_text(
                    "📅 Заміри на сьогодні:\n\n" + "\n\n".join(messages),
                    parse_mode="HTML"
                )
        else:
            user_data = get_user_data(user_id)
            if not user_data:
                await query.message.reply_text("У вас немає доступу до цієї функції.")
                return
            full_name = user_data[0]
            user_rows = [row for row in rows if len(row) > 15 and row[15] == full_name]
            if not user_rows:
                await query.message.reply_text("Сьогодні у вас немає замірів.")
            else:
                messages = []
                for row in user_rows:
                    order_number = row[1] if len(row) > 1 else "Невідомо"
                    tipe = row[2] if len(row) > 2 else "Невідомо"
                    maneger = row[3] if len(row) > 3 else "Невідомо"
                    adres = row[6] if len(row) > 6 else "Невідомо"
                    measure_date = row[16] if len(row) > 16 else "Невідомо"
                    messages.append(
                        f"<b>═════════════</b>\n"
                        f"❗️ <b>ГРАФІК ЗАМІРІВ</b> ❗️\n"
                        f"🆔 <b>НОМЕР:</b> {order_number}\n"
                        f"♻️ <b>ТИП:</b> {tipe}\n"
                        f"👩🏻‍💼 <b>МЕНЕДЖЕР:</b> {maneger}\n"
                        f"🚩 <b>АДРЕСА:</b> {adres}\n"
                        f"🎦 <b>ЗАМІРНИК:</b> {measurer}\n"
                        f"📅 <b>ДАТА ЗАМІРУ:</b> {measure_date}\n"
                        f"<b>═════════════</b>"
                    )
                await query.message.reply_text(
                    "📅 Ваші заміри на сьогодні:\n\n" + "\n\n".join(messages),
                    parse_mode="HTML"
                )
    except Exception as e:
        await query.message.reply_text("Сталася помилка під час пошуку замірів.")
        logging.error(f"Помилка пошуку замірів на сьогодні: {e}")
    finally:
        cursor.close()
        conn.close()

async def show_zamiry_tomorrow(query, user_id):
    """Показати заміри на завтра для користувача або для адміністратора."""
    tomorrow = (datetime.now() + timedelta(days=1)).strftime('%d.%m.%Y')
    conn = get_pg_connection()
    cursor = conn.cursor()
    try:
        cursor.execute(f"SELECT * FROM second_sheet_data WHERE column16 = %s", (tomorrow,))
        rows = cursor.fetchall()

        if is_admin(user_id):
            if not rows:
                await query.message.reply_text("Завтра замірів немає.")
            else:
                messages = []
                for row in rows:
                    order_number = row[1] if len(row) > 1 else "Невідомо"
                    tipe = row[2] if len(row) > 2 else "Невідомо"
                    maneger = row[3] if len(row) > 3 else "Невідомо"
                    adres = row[6] if len(row) > 6 else "Невідомо"
                    measurer = row[15] if len(row) > 15 else "Невідомо"
                    measure_date = row[16] if len(row) > 16 else "Невідомо"
                    time = row[17] if len(row) > 17 else "Невідомо"
                    messages.append(
                        f"<b>═════════════</b>\n"
                        f"❗️ <b>ГРАФІК ЗАМІРІВ</b> ❗️\n"
                        f"🆔 <b>НОМЕР:</b> {order_number}\n"
                        f"♻️ <b>ТИП:</b> {tipe}\n"
                        f"👩🏻‍💼 <b>МЕНЕДЖЕР:</b> {maneger}\n"
                        f"🚩 <b>АДРЕСА:</b> {adres}\n"
                        f"🎦 <b>ЗАМІРНИК:</b> {measurer}\n"
                        f"📅 <b>ДАТА ЗАМІРУ:</b> {measure_date}\n"
                        f"📅 <b>ЧАС:</b> {time}\n"
                        f"<b>═════════════</b>"
                    )
                await query.message.reply_text(
                    "📅 Заміри на завтра:\n\n" + "\n\n".join(messages),
                    parse_mode="HTML"
                )
        else:
            user_data = get_user_data(user_id)
            if not user_data:
                await query.message.reply_text("У вас немає доступу до цієї функції.")
                return
            full_name = user_data[0]
            user_rows = [row for row in rows if len(row) > 15 and row[15] == full_name]
            if not user_rows:
                await query.message.reply_text("Завтра у вас немає замірів.")
            else:
                messages = []
                for row in user_rows:
                    order_number = row[1] if len(row) > 1 else "Невідомо"
                    tipe = row[2] if len(row) > 2 else "Невідомо"
                    maneger = row[3] if len(row) > 3 else "Невідомо"
                    adres = row[6] if len(row) > 6 else "Невідомо"
                    measure_date = row[16] if len(row) > 16 else "Невідомо"
                    messages.append(
                        f"<b>═════════════</b>\n"
                        f"❗️ <b>ГРАФІК ЗАМІРІВ</b> ❗️\n"
                        f"🆔 <b>НОМЕР:</b> {order_number}\n"
                        f"♻️ <b>ТИП:</b> {tipe}\n"
                        f"👩🏻‍💼 <b>МЕНЕДЖЕР:</b> {maneger}\n"
                        f"🚩 <b>АДРЕСА:</b> {adres}\n"
                        f"🎦 <b>ЗАМІРНИК:</b> {measurer}\n"
                        f"📅 <b>ДАТА ЗАМІРУ:</b> {measure_date}\n"
                        f"<b>═════════════</b>"
                    )
                await query.message.reply_text(
                    "📅 Ваші заміри на завтра:\n\n" + "\n\n".join(messages),
                    parse_mode="HTML"
                )
    except Exception as e:
        await query.message.reply_text("Сталася помилка під час пошуку замірів.")
        logging.error(f"Помилка пошуку замірів на завтра: {e}")
    finally:
        cursor.close()
        conn.close()

async def calculate_bonuses_prev_month(update: Update, context: CallbackContext):
    """Розраховує бонуси за адаптацію замірів для минулого місяця."""
    user_id = update.effective_user.id
    user_data = get_user_data(user_id)

    if not user_data:
        message = update.message or update.callback_query.message
        await message.reply_text("⚠️ У вас немає доступу до цієї функції.")
        return

    full_name = user_data[0]
    conn = get_pg_connection()
    cursor = conn.cursor()

    try:
        # Обчислюємо діапазон дат для минулого місяця
        now = datetime.now()
        first_day_this_month = now.replace(day=1)
        last_day_prev_month = first_day_this_month - timedelta(days=1)
        start_date = last_day_prev_month.replace(day=1).strftime('%Y-%m-%d')
        end_date = last_day_prev_month.strftime('%Y-%m-%d')

        query = f"""
            SELECT column2, column6, column13, column18, column28
            FROM sheet_data
            WHERE TO_DATE(column18, 'DD.MM.YY') BETWEEN %s AND %s
        """
        cursor.execute(query, (start_date, end_date))
        rows = cursor.fetchall()

        user_orders = [row for row in rows if row[2] == full_name]
        message = update.message or update.callback_query.message

        if not user_orders:
            await message.reply_text("⚠️ У вас немає адаптацій за минулий місяць.")
            return

        total_bonus = 0
        order_numbers = []
        for order in user_orders:
            order_number = order[0]
            bonus_part = order[4]
            bonus = 0
            if bonus_part:
                if "\\" in bonus_part:
                    parts = bonus_part.split("\\")
                    kitchen_count = int(parts[0]) * 50
                    product_count = int(parts[1]) * 30
                    bonus = kitchen_count + product_count
                else:
                    bonus = int(bonus_part) * 30
                total_bonus += bonus
            order_numbers.append(str(order_number))

        summary_message = (
            f"<b>Звіт по бонусах за адаптації (минулий місяць):</b>\n"
            f"👤 <b>Виконавець:</b> {full_name}\n"
            f"📅 <b>Місяць:</b> {last_day_prev_month.strftime('%m.%Y')}\n"
            f"🔢 <b>Кількість адаптацій:</b> {len(user_orders)}\n"
            f"💰 <b>Загальна сума бонусів:</b> {total_bonus} грн\n"
            f"🆔 <b>Номери замовлень:</b> {', '.join(order_numbers)}"
        )
        await message.reply_text(summary_message, parse_mode="HTML")

    except Exception as e:
        logging.error(f"Помилка під час розрахунку бонусів: {e}")
        message = update.message or update.callback_query.message
        await message.reply_text("⚠️ Сталася помилка під час розрахунку бонусів.")
    finally:
        cursor.close()
        conn.close()