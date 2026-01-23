"""
Файл для тригерів Telegram-бота.
Тут будуть зберігатися функції, які обробляють різні тригери.
"""

# Імпортуємо необхідні модулі
from telegram import Update
from telegram.ext import CallbackContext
import sqlite3, asyncio, datetime, logging
import json
import os, re
from datetime import datetime
import time
from io import BytesIO
import os
import psycopg2
from dotenv import load_dotenv

load_dotenv()

PG_CONN = {
    "host": os.environ.get("PG_HOST"),
    "port": int(os.environ.get("PG_PORT")),
    "dbname": os.environ.get("PG_DBNAME"),
    "user": os.environ.get("PG_USER"),
    "password": os.environ.get("PG_PASSWORD")
}

def get_pg_connection():
    return psycopg2.connect(**PG_CONN)

# Шлях до бази даних
DATABASE_FILE = r'C:\Users\user\Desktop\tg-bot\google_sheet_data.db'

STATE_FILE = "last_sent_state.json"  # Файл для збереження стану
STATE_FILE_2 = "state.json"  # Назва JSON-файлу для збереження стану
DELIVERY_TRUE_FILE = "delivery_true_sent.json"

def load_true_sent():
    if os.path.exists(DELIVERY_TRUE_FILE):
        with open(DELIVERY_TRUE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}

def save_true_sent(sent_orders):
    with open(DELIVERY_TRUE_FILE, "w", encoding="utf-8") as f:
        json.dump(sent_orders, f, ensure_ascii=False, indent=4)

def get_overdue_supplier_orders(supplier_name):
    """Повертає список просрочених (НЕ доставлених) закупок для постачальника."""
    today = datetime.now().strftime('%d.%m.%y')
    today_dt = datetime.strptime(today, '%d.%m.%y')
    conn = sqlite3.connect(DATABASE_FILE)
    cursor = conn.cursor()
    try:
        cursor.execute(
            "SELECT * FROM rzm_data WHERE columnH LIKE ? ORDER BY id DESC",
            (f'%{supplier_name}%',)
        )
        rows = cursor.fetchall()
        overdue = []
        for row in rows:
            delivery_date_str = row[7] if len(row) > 7 else None  # Дата доставки
            status_val = row[9] if len(row) > 9 else ""
            if not delivery_date_str or not re.match(r"\d{2}\.\d{2}\.\d{2}", delivery_date_str.strip()):
                continue
            try:
                delivery_dt = datetime.strptime(delivery_date_str.strip(), '%d.%m.%y')
            except Exception:
                continue
            # Тільки якщо дата менша за сьогодні і статус НЕ доставлено
            if delivery_dt < today_dt and str(status_val).strip().lower() in ["false", "0", "ні", "no", ""]:
                order_number = row[1] if len(row) > 1 else "Невідомо"
                name = row[2] if len(row) > 2 else "Невідомо"
                material = row[4] if len(row) > 4 else "Невідомо"
                quantity = row[5] if len(row) > 5 else "Невідомо"
                note = row[10] if len(row) > 10 else ""
                overdue.append(
                    f"<b>🆔 НОМЕР ЗАМОЛЕННЯ:</b> {order_number}\n"
                    f"<b>📦 НАЗВА:</b> {name}\n"
                    f"🧱 <b>МАТЕРІАЛ:</b> {material}\n"
                    f"🔢 <b>КІЛЬКІСТЬ:</b> {quantity}\n"
                    f"📅 <b>ДАТА ОЧІКУВАНОЇ ДОСТАВКИ:</b> {delivery_date_str}\n"
                    f"📝 <b>ПРИМІТКИ:</b> {note}\n"
                    f"<b>═════════════</b>"
                )
        return overdue
    finally:
        cursor.close()
        conn.close()

async def notify_overdue_orders(context: CallbackContext):
    group_chat_id = -1002739662152  # ID вашої групи
    thread_id = 2 # <-- ВСТАВ СВІЙ ID ГІЛКИ (thread_id)
    suppliers = ["Храніпекс", "Кронас", "Арніо", "Віяр", "Інщі"]
    for supplier in suppliers:
        overdue = get_overdue_supplier_orders(supplier)
        if overdue:
            header = f" ⚠️ПРОСРОЧЕНІ ЗАКУПКИ {supplier.upper()}⚠️:\n\n"
            full_text = header + "\n\n".join(overdue)
            for part in split_message(full_text):
                await context.bot.send_message(
                    chat_id=group_chat_id,
                    text=part,
                    parse_mode="HTML",
                    message_thread_id=thread_id
                )
        else:
            await context.bot.send_message(
                chat_id=group_chat_id,
                text=f"✅{supplier.upper()} немає просрочених закупок.✅",
                parse_mode="HTML",
                message_thread_id=thread_id
            )

def load_last_state():
    """Завантажує останній стан із файлу."""
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE, "r") as file:
            return json.load(file)
    return {}

def save_current_state(state):
    """Зберігає поточний стан у файл."""
    with open(STATE_FILE, "w") as file:
        json.dump(state, file)
#   end of save_current_state
async def daily_measurements_trigger(context: CallbackContext):
    """
    Трігер для перевірки замірів на сьогодні та надсилання повідомлення в груповий чат і користувачам.
    """
    conn = None  # Ініціалізуємо conn як None
    try:
        today = datetime.now().strftime("%d.%m.%Y")
        logging.info(f"Сьогоднішня дата: {today}")

        conn = get_pg_connection()
        cursor = conn.cursor()

        # Шукаємо всі записи з сьогоднішньою датою в колонці 16
        query = f"SELECT column1, column3, column5, column6, column15, column7, column17 FROM second_sheet_data WHERE column16 = %s"
        cursor.execute(query, (today,))
        rows = cursor.fetchall()

        if not rows:
            logging.warning("Жодного запису не знайдено для сьогоднішньої дати.")
            return

        logging.info(f"Знайдено записів: {len(rows)}")

        # Ідентифікатор групового чату та гілки
        group_chat_id = -1002597813419  # Ваш chat_id групи
        thread_id = 75  # Гілка "ГРАФІК НА СЬОГОДНІ"

        # Формуємо повідомлення для групового чату
        group_message = f"❗️ <b>Заміри на сьогодні ({today})</b> ❗️\n\n"
        current_state = {}

        for row in rows:
            if len(row) < 7:
                logging.error(f"Неправильний формат рядка: {row}")
                continue

            order_number = row[0]  # Номер заміру (column1)
            manager = row[1]  # Менеджер (column3)
            phone_number = row[2]  # Номер телефону (column5)
            address = row[3]  # Адреса (column6)
            executor = row[4]  # Виконавець (column15)
            notes = row[5]  # Примітки (column7)
            time = row[6]  # Час на коли (column17)

            # Формуємо унікальний ключ для кожного замовлення
            order_key = f"{order_number}_{address}"

            # Зберігаємо поточний стан
            current_state[order_key] = {"executor": executor, "time": time}

            # Формуємо повідомлення для кожного запису
            order_info = (
                f"<b>═════════════</b>\n"
                f"🆔 <b>Номер:</b> {order_number}\n"
                f"👩🏻‍💼 <b>Менеджер:</b> {manager}\n"
                f"📞 <b>Телефон:</b> {phone_number}\n"
                f"🚩 <b>Адреса:</b> {address}\n"
                f"🎦 <b>Виконавець:</b> {executor}\n"
                f"📝 <b>Примітки:</b> {notes}\n"
                f"⏰ <b>Час:</b> {time}\n"
                f"<b>═════════════</b>\n"
            )

            # Додаємо інформацію до загального повідомлення
            group_message += order_info

            # Надсилаємо повідомлення виконавцю (executor)
            try:
                # Отримуємо Telegram ID виконавця з бази даних
                user_query = "SELECT telegram_id FROM database_app_userdatatelegram WHERE name = ?"
                cursor.execute(user_query, (executor,))
                user_row = cursor.fetchone()

                if user_row:
                    telegram_id = user_row[0]
                    personal_message = (
                        f"❗️ <b>Ваш замір на сьогодні:</b>\n"
                        f"🆔 <b>Номер:</b> {order_number}\n"
                        f"👩🏻‍💼 <b>Менеджер:</b> {manager}\n"
                        f"📞 <b>Телефон:</b> {phone_number}\n"
                        f"🚩 <b>Адреса:</b> {address}\n"
                        f"⏰ <b>Час:</b> {time}\n"
                        f"📝 <b>Примітки:</b> {notes}\n"
                    )
                    await context.bot.send_message(
                        chat_id=telegram_id,
                        text=personal_message,
                        parse_mode="HTML",
                    )
                    logging.info(f"Повідомлення успішно надіслано користувачу {executor} (Telegram ID: {telegram_id}).")
                else:
                    logging.warning(f"Telegram ID для виконавця {executor} не знайдено в базі даних.")
            except Exception as e:
                logging.error(f"Не вдалося надіслати повідомлення виконавцю {executor}: {e}")

        # Зберігаємо стан записів, які були надіслані
        save_current_state(current_state)

        # Відправляємо повідомлення в груповий чат
        try:
            await context.bot.send_message(
                chat_id=group_chat_id,
                text=group_message,
                parse_mode="HTML",
                message_thread_id=thread_id,  # Вказуємо гілку
            )
            logging.info("Повідомлення успішно надіслано в груповий чат.")
        except Exception as e:
            logging.error(f"Не вдалося надіслати повідомлення в груповий чат: {e}")

    except Exception as e:
        logging.error(f"Помилка під час виконання тригера: {e}")
    finally:
        if conn:  # Закриваємо з'єднання, якщо воно було створено
            conn.close()
# end of daily_measurements_trigger
async def check_for_changes(context: CallbackContext):
    """
    Перевіряє базу даних на наявність змін для записів, які були надіслані сьогодні,
    повідомляє про перенесення заміру, нові заміри на сьогодні та зміни у графіку.
    """
    now = datetime.now()
    # Працює тільки з 8:40 до 19:00
    if not (now.hour > 8 or (now.hour == 8 and now.minute >= 40)) or now.hour >= 19:
        return
    
    try:
        conn = get_pg_connection()
        cursor = conn.cursor()

        # Завантажуємо останній стан
        last_state = load_last_state()
        current_state = {}

        today = datetime.now().strftime("%d.%m.%Y")

        # Отримуємо всі заміри на сьогодні
        cursor.execute(
            "SELECT column1, column3, column5, column6, column15, column7, column17, column16 FROM second_sheet_data",
        )
        rows = cursor.fetchall()

        # Формуємо поточний стан тільки для сьогоднішніх замірів
        for row in rows:
            if len(row) < 8:
                continue
            order_number = row[0]
            manager = row[1]
            phone_number = row[2]
            address = row[3]
            executor = row[4]
            notes = row[5]
            time = row[6]
            date = row[7]
            order_key = f"{order_number}_{address}"
            if date == today:
                current_state[order_key] = {
                    "executor": executor,
                    "time": time,
                    "date": today,
                    "manager": manager,
                    "phone": phone_number,
                    "notes": notes
                }
        # 1. Перевірка на перенесення заміру (з сьогодні на іншу дату)
        for order_key, last_data in last_state.items():
            last_date = last_data.get("date", today)
            if last_date == today and order_key not in current_state:
                order_number, address = order_key.split("_")
                msg = (
                    f"⚠️ <b>Заміри перенесено!</b>\n"
                    f"🆔 <b>Номер:</b> {order_number}\n"
                    f"🚩 <b>Адреса:</b> {address}\n"
                    f"📅 <b>Дата була:</b> {today}\n"
                    f"Заміри перенесено на іншу дату."
                )
                await context.bot.send_message(
                    chat_id=-1002597813419,
                    text=msg,
                    parse_mode="HTML",
                    message_thread_id=75,
                )

        # 2. Перевірка на нові заміри на сьогодні
        for order_key, data in current_state.items():
            if order_key not in last_state:
                order_number, address = order_key.split("_")
                msg = (
                    f"❗️ <b>Додано новий замір на сьогодні!</b>\n"
                    f"🆔 <b>Номер:</b> {order_number}\n"
                    f"🚩 <b>Адреса:</b> {address}\n"
                    f"👩🏻‍💼 <b>Менеджер:</b> {data['manager']}\n"
                    f"📞 <b>Телефон:</b> {data['phone']}\n"
                    f"🎦 <b>Виконавець:</b> {data['executor']}\n"
                    f"📝 <b>Примітки:</b> {data['notes']}\n"
                    f"⏰ <b>Час:</b> {data['time']}\n"
                )
                await context.bot.send_message(
                    chat_id=-1002597813419,
                    text=msg,
                    parse_mode="HTML",
                    message_thread_id=75,
                )

        # 3. Перевірка на зміну виконавця або часу у замірах на сьогодні
        for order_key, last_data in last_state.items():
            last_date = last_data.get("date", today)
            if last_date == today and order_key in current_state:
                current = current_state[order_key]
                if (
                    current["executor"] != last_data.get("executor", "")
                    or current["time"] != last_data.get("time", "")
                ):
                    order_number, address = order_key.split("_")
                    msg = (
                        f"<b>⚠️ ЗМІНИ В ГРАФІКУ ЗАМІРІВ</b>\n"
                        f"🆔 <b>Номер:</b> {order_number}\n"
                        f"🚩 <b>Адреса:</b> {address}\n"
                        f"🎦 <b>Виконавець:</b> {last_data.get('executor','')} ➡️ {current['executor']}\n"
                        f"⏰ <b>Час:</b> {last_data.get('time','')} ➡️ {current['time']}\n"
                    )
                    await context.bot.send_message(
                        chat_id=-1002597813419,
                        text=msg,
                        parse_mode="HTML",
                        message_thread_id=75,
                    )

        # Оновлюємо стан
        save_current_state(current_state)

    except Exception as e:
        logging.error(f"Помилка під час перевірки змін: {e}")
    finally:
        if conn:
            conn.close()

def split_message(message, max_length=4096):
    """
    Розбиває повідомлення на частини, якщо воно перевищує ліміт Telegram.
    """
    parts = []
    while len(message) > max_length:
        split_index = message[:max_length].rfind("\n")
        if split_index == -1:  # Якщо немає переносів рядків
            split_index = max_length
        parts.append(message[:split_index])
        message = message[split_index:]
    parts.append(message)
    return parts

def load_state():
    """Завантажує стан із JSON-файлу."""
    if os.path.exists(STATE_FILE_2):
        with open(STATE_FILE_2, "r", encoding="utf-8") as file:
            return set(json.load(file))  # Завантажуємо список і перетворюємо на множину
    return set()

def save_state(state):
    """Зберігає стан у JSON-файл."""
    with open(STATE_FILE_2, "w", encoding="utf-8") as file:
        json.dump(list(state), file, ensure_ascii=False, indent=4)  # Зберігаємо множину як список

# --- ДОДАНО: допоміжні тригери, які імпортуються у головному файлі, але були відсутні ---
async def check_empty_column16(context: CallbackContext):
    """
    Перевіряє записи у таблиці second_sheet_data з порожнім значенням у column16.
    Це базовий тригер-стаб, щоб уникнути ImportError.
    """
    conn = None
    cursor = None
    try:
        conn = get_pg_connection()
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT COUNT(*)
            FROM second_sheet_data
            WHERE column16 IS NULL OR TRIM(column16) = ''
            """
        )
        count = cursor.fetchone()[0]
        logging.info(f"check_empty_column16: знайдено {count} запис(ів) з порожнім column16")
    except Exception as e:
        logging.error(f"Помилка у check_empty_column16: {e}")
    finally:
        try:
            if cursor:
                cursor.close()
            if conn:
                conn.close()
        except Exception:
            pass

async def check_delivery_true_trigger(context: CallbackContext):
    """
    Заглушка для тригера перевірки доставок (TRUE). Реалізацію можна доповнити пізніше.
    Поточна версія лише фіксує факт виклику, щоб уникнути падіння сервісу.
    """
    try:
        logging.debug("check_delivery_true_trigger: виклик тригера (заглушка)")
    except Exception as e:
        logging.error(f"Помилка у check_delivery_true_trigger: {e}")



