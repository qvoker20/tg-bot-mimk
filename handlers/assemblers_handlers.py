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

DATA_PLAN_TABLE_NAME = "data_plan"
DATA_PLAN_DATE_TABLE_NAME = "data_plan_date"
DATA_REC_TABLE_NAME = "data_rec"
USERS_TABLE_NAME = "users"


def get_pg_connection():
    return psycopg2.connect(**PG_CONN)


async def show_assemblers_menu(update: Update, context: CallbackContext):
    keyboard = [
        [InlineKeyboardButton("Мій профіль", callback_data="asm_my_profile")],
        [InlineKeyboardButton("Назад", callback_data="asm_back")],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    if update.message:
        sent_message = await update.message.reply_text("Меню для збиральників:", reply_markup=reply_markup)
        context.user_data["assemblers_message_id"] = sent_message.message_id
    else:
        await update.callback_query.edit_message_text("Меню для збиральників:", reply_markup=reply_markup)
        if update.callback_query and update.callback_query.message:
            context.user_data["assemblers_message_id"] = update.callback_query.message.message_id


async def assembler_button_handler(update: Update, context: CallbackContext):
    query = update.callback_query
    await query.answer()
    data = query.data

    if data == "asm_my_tasks_today":
        await find_my_tasks_today(update, context)
    elif data == "asm_my_profile":
        await show_my_profile(update, context)
    elif data == "asm_back":
        await query.edit_message_text("Повернення. Скористайтесь клавішею меню внизу екрана.")
    else:
        await query.answer("Функція буде додана пізніше.", show_alert=False)


def _get_user_name_by_telegram_id(conn, telegram_id: int) -> str | None:
    cur = conn.cursor()
    try:
        cur.execute(
            "SELECT name FROM database_app_userdatatelegram WHERE telegram_id = %s",
            (telegram_id,)
        )
        row = cur.fetchone()
        return row[0] if row else None
    finally:
        cur.close()


def _table_has_columns(conn, table_name: str, cols: list[str]) -> dict[str, bool]:
    cur = conn.cursor()
    res = {}
    try:
        for c in cols:
            cur.execute(
                """
                SELECT 1
                FROM information_schema.columns
                WHERE table_schema='public' AND table_name=%s AND column_name=%s
                """,
                (table_name, c)
            )
            res[c] = cur.fetchone() is not None
        return res
    finally:
        cur.close()


def _normalize_date(s: str) -> Optional[date]:
    if not s:
        return None
    s = str(s).strip()
    for fmt in ("%d.%m.%Y", "%Y-%m-%d", "%d/%m/%Y", "%Y/%m/%d"):
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            continue
    return None


def _fetch_tasks_for_table(conn, table_name: str, name: str) -> list[dict]:
    # Гнучко перевіряємо наявність колонки column12, щоб не падати якщо її немає
    cols_check = _table_has_columns(conn, table_name, ["column1", "column2", "column3", "column12"])
    select_cols = ["column1", "column2", "column3"]
    if cols_check.get("column12", False):
        select_cols.append("column12")

    cur = conn.cursor()
    try:
        cur.execute(
            f"SELECT {', '.join(select_cols)} FROM {table_name} WHERE column3 = %s",
            (name,)
        )
        rows = cur.fetchall()
        tasks = []
        today = datetime.now().date()

        for row in rows:
            # Формуємо значення безпечним способом за індексами
            # Порядок select_cols: 1 -> замовлення, 2 -> дата, 3 -> ім'я, (12) -> частини
            order = row[0] if len(row) >= 1 else ""
            date_str = row[1] if len(row) >= 2 else ""
            assembler = row[2] if len(row) >= 3 else ""
            parts = row[3] if len(row) >= 4 else "-"  # якщо column12 відсутня

            d = _normalize_date(date_str)
            if d == today:
                tasks.append({
                    "order": order,
                    "date": date_str,
                    "assembler": assembler,
                    "parts": parts
                })
        return tasks
    finally:
        cur.close()

def _format_tasks_html(tasks: list[dict]) -> str:
    lines = []
    for t in tasks:
        esc_order = html.escape(str(t.get("order", "")))
        esc_date = html.escape(str(t.get("date", "")))
        esc_assembler = html.escape(str(t.get("assembler", "")))
        esc_parts = html.escape(str(t.get("parts", "-")))
        lines.append(
            f"📦 <b>№ замовлення:</b> {esc_order}\n"
            f"🗓️ <b>Дата:</b> {esc_date}\n"
            f"👤 <b>Збиральник:</b> {esc_assembler}\n"
            f"🧩 <b>Частини:</b> <code>{esc_parts}</code>"
        )
    return "<b>Мої задачі на сьогодні:</b>\n\n" + "\n\n".join(lines)

async def find_my_tasks_today(update: Update, context: CallbackContext):
    query = update.callback_query
    user_id = query.from_user.id

    conn = get_pg_connection()
    try:
        name = _get_user_name_by_telegram_id(conn, user_id)
        if not name:
            await query.edit_message_text(
                "Вас немає у базі користувачів. Пройдіть реєстрацію або зверніться до адміністратора."
            )
            return

        tasks = []
        tasks += _fetch_tasks_for_table(conn, DATA_PLAN_TABLE_NAME, name)
        tasks += _fetch_tasks_for_table(conn, DATA_PLAN_DATE_TABLE_NAME, name)
        tasks += _fetch_tasks_for_table(conn, DATA_REC_TABLE_NAME, name)

        if not tasks:
            await query.edit_message_text("На сьогодні немає задач. Скористайтеся кнопкою «Потрібна робота».")
            return

        msg = _format_tasks_html(tasks)
        await query.edit_message_text(msg, parse_mode=ParseMode.HTML)
    finally:
        conn.close()

async def show_my_profile(update: Update, context: CallbackContext):
    query = update.callback_query
    user_id = query.from_user.id

    conn = get_pg_connection()
    try:
        name = _get_user_name_by_telegram_id(conn, user_id)

        cur = conn.cursor()
        try:
            # column4 – telegram_id, column3 – код для входу
            cur.execute(
                f"SELECT column3 FROM {USERS_TABLE_NAME} WHERE column4 = %s LIMIT 1",
                (str(user_id),)
            )
            row = cur.fetchone()
        finally:
            cur.close()

        if not row or not row[0]:
            await query.edit_message_text(
                "Ваш профіль не знайдено у таблиці користувачів. Зверніться до адміністратора."
            )
            return

        code = str(row[0])
        profile_url = (
            "https://script.google.com/a/macros/mim-k.com/s/"
            "AKfycbxprWl65BmYlPtDjyD14YURiIb43VBgHH0IYwKF_38DENgKv60kHA0Bk1AuC4vo6c7Beg/exec"
        )
        assembler_app_url = "https://erp.mim-k.website/assemblers/app"

        esc_name = html.escape(name or "Невідомий користувач")
        esc_code = html.escape(code)

        text = (
            f"<b>Профіль</b>\n\n"
            f"Ім'я: <b>{esc_name}</b>\n"
            f"Код для входу: <code>{esc_code}</code>\n\n"
            f"Натисніть кнопку «Мій профіль» або «Додаток збиральника ERP», щоб відкрити сторінку.\n\n"
            f"<b>Примітка:</b> щоб перейти у користування, відкривайте посилання через Google-профіль!"
        )

        keyboard = [
            [InlineKeyboardButton("Мій профіль", url=profile_url)],
            [InlineKeyboardButton("Додаток збиральника ERP", url=assembler_app_url)],
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        await query.edit_message_text(
            text,
            parse_mode=ParseMode.HTML,
            reply_markup=reply_markup
        )
    finally:
        conn.close()