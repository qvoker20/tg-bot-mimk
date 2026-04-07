import os
import logging
import psycopg2
import calendar
import uuid
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

PASS_REQUEST_INTRO = (
    "<b>🛂 Подати заявку на перепустку</b>\n\n"
    "Оберіть тип перепустки:"
)

def get_pg_connection():
    return psycopg2.connect(**PG_CONN)

def ensure_pass_requests_table():
    conn = get_pg_connection()
    cursor = conn.cursor()
    try:
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS logistics_pass_requests (
                id BIGSERIAL PRIMARY KEY,
                request_group_id TEXT,
                requester_telegram_id BIGINT NOT NULL,
                requester_name TEXT,
                requester_username TEXT,
                pass_type TEXT NOT NULL CHECK (pass_type IN ('vehicle', 'person')),
                vehicle_plate TEXT,
                vehicle_brand TEXT,
                visitor_full_name TEXT NOT NULL,
                visit_date DATE NOT NULL,
                date_mode TEXT NOT NULL DEFAULT 'single' CHECK (date_mode IN ('single', 'range')),
                visit_date_from DATE,
                visit_date_to DATE,
                status TEXT NOT NULL DEFAULT 'new',
                created_at TIMESTAMP NOT NULL DEFAULT NOW()
            )
            """
        )
        cursor.execute("ALTER TABLE logistics_pass_requests ADD COLUMN IF NOT EXISTS request_group_id TEXT")
        cursor.execute("ALTER TABLE logistics_pass_requests ADD COLUMN IF NOT EXISTS date_mode TEXT")
        cursor.execute("ALTER TABLE logistics_pass_requests ADD COLUMN IF NOT EXISTS visit_date_from DATE")
        cursor.execute("ALTER TABLE logistics_pass_requests ADD COLUMN IF NOT EXISTS visit_date_to DATE")
        cursor.execute("UPDATE logistics_pass_requests SET date_mode = 'single' WHERE date_mode IS NULL")
        cursor.execute("UPDATE logistics_pass_requests SET visit_date_from = visit_date WHERE visit_date_from IS NULL")
        cursor.execute("UPDATE logistics_pass_requests SET visit_date_to = visit_date WHERE visit_date_to IS NULL")
        cursor.execute("UPDATE logistics_pass_requests SET request_group_id = id::text WHERE request_group_id IS NULL")
        cursor.execute(
            """
            ALTER TABLE logistics_pass_requests
            DROP CONSTRAINT IF EXISTS logistics_pass_requests_date_mode_check
            """
        )
        cursor.execute(
            """
            ALTER TABLE logistics_pass_requests
            ADD CONSTRAINT logistics_pass_requests_date_mode_check
            CHECK (date_mode IN ('single', 'range'))
            """
        )
        cursor.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_logistics_pass_requests_group
            ON logistics_pass_requests(request_group_id)
            """
        )
        conn.commit()
    finally:
        cursor.close()
        conn.close()

def build_calendar_keyboard(year: int, month: int) -> InlineKeyboardMarkup:
    rows = []
    month_name = datetime(year, month, 1).strftime("%B %Y")
    rows.append([
        InlineKeyboardButton("◀️", callback_data=f"lp_cal_prev:{year}:{month}"),
        InlineKeyboardButton(month_name.capitalize(), callback_data="lp_noop"),
        InlineKeyboardButton("▶️", callback_data=f"lp_cal_next:{year}:{month}"),
    ])

    weekdays = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Нд"]
    rows.append([InlineKeyboardButton(d, callback_data="lp_noop") for d in weekdays])

    month_days = calendar.monthcalendar(year, month)
    today = date.today()
    for week in month_days:
        row = []
        for day in week:
            if day == 0:
                row.append(InlineKeyboardButton(" ", callback_data="lp_noop"))
            else:
                selected_date = date(year, month, day)
                if selected_date < today:
                    row.append(InlineKeyboardButton("·", callback_data="lp_noop"))
                else:
                    row.append(InlineKeyboardButton(str(day), callback_data=f"lp_day:{selected_date.isoformat()}"))
        rows.append(row)

    rows.append([InlineKeyboardButton("❌ Скасувати", callback_data="lp_cancel")])
    return InlineKeyboardMarkup(rows)

def init_pass_flow(context: CallbackContext, pass_type: str):
    context.user_data["logistics_state"] = "pass_plate" if pass_type == "vehicle" else "pass_count"
    context.user_data["logistics_pass"] = {
        "pass_type": pass_type,
        "vehicle_plate": None,
        "vehicle_brand": None,
        "visitor_full_name": None,
        "visitor_names": [],
        "persons_count": None,
        "date_mode": None,
        "visit_date_from": None,
        "visit_date_to": None,
    }

def clear_pass_flow(context: CallbackContext):
    context.user_data.pop("logistics_state", None)
    context.user_data.pop("logistics_pass", None)


def clear_pass_history_flow(context: CallbackContext):
    context.user_data.pop("lp_history_items", None)
    context.user_data.pop("lp_history_index", None)


def _serialize_request_row(row) -> dict:
    return {
        "id": row[0],
        "request_group_id": row[1],
        "pass_type": row[2],
        "vehicle_plate": row[3],
        "vehicle_brand": row[4],
        "visitor_full_name": row[5],
        "date_mode": row[6] or "single",
        "visit_date_from": str(row[7]) if row[7] else None,
        "visit_date_to": str(row[8]) if row[8] else None,
        "created_at": str(row[9]) if row[9] else None,
    }


def get_user_pass_requests(user_id: int, limit: int = 20) -> list[dict]:
    conn = get_pg_connection()
    cursor = conn.cursor()
    try:
        cursor.execute(
            """
            SELECT id, request_group_id, pass_type, vehicle_plate, vehicle_brand, visitor_full_name,
                   COALESCE(date_mode, 'single') AS date_mode,
                   visit_date_from, visit_date_to, created_at
            FROM logistics_pass_requests
            WHERE requester_telegram_id = %s
            ORDER BY created_at DESC, id DESC
            LIMIT %s
            """,
            (user_id, limit)
        )
        return [_serialize_request_row(row) for row in cursor.fetchall()]
    finally:
        cursor.close()
        conn.close()


def _build_history_text(item: dict, index: int, total: int) -> str:
    period_text = (
        html.escape(item.get("visit_date_from") or "—")
        if item.get("date_mode") == "single"
        else f"{html.escape(item.get('visit_date_from') or '—')} — {html.escape(item.get('visit_date_to') or '—')}"
    )

    text = (
        f"<b>🧾 Мої заявки на перепустку</b>\n"
        f"<i>Заявка {index + 1} з {total}</i>\n\n"
        f"<b>Тип:</b> {'Для авто' if item.get('pass_type') == 'vehicle' else 'Для особи'}\n"
        f"<b>ПІБ:</b> {html.escape(item.get('visitor_full_name') or '—')}\n"
        f"<b>Тип дати:</b> {'На один день' if item.get('date_mode') == 'single' else 'Від та до'}\n"
        f"<b>Дата:</b> {period_text}\n"
        f"<b>Створено:</b> {html.escape(item.get('created_at') or '—')}"
    )
    if item.get("pass_type") == "vehicle":
        text += f"\n<b>Номер авто:</b> {html.escape(item.get('vehicle_plate') or '—')}"
    return text


def _build_history_keyboard(index: int, total: int) -> InlineKeyboardMarkup:
    nav_row = []
    if index < total - 1:
        nav_row.append(InlineKeyboardButton("⬅️ Старіша", callback_data="lp_hist_prev"))
    if index > 0:
        nav_row.append(InlineKeyboardButton("➡️ Новіша", callback_data="lp_hist_next"))

    rows = []
    if nav_row:
        rows.append(nav_row)
    rows.append([InlineKeyboardButton("📅 Створити по цій заявці", callback_data="lp_clone_start")])
    rows.append([InlineKeyboardButton("🔙 Назад", callback_data="logistics_menu_back")])
    return InlineKeyboardMarkup(rows)

def save_pass_request(telegram_user, data: dict):
    ensure_pass_requests_table()
    names = data.get("visitor_names") or []
    if not names and data.get("visitor_full_name"):
        names = [data.get("visitor_full_name")]
    if not names:
        raise ValueError("Не вказано жодної особи для перепустки")

    request_group_id = data.get("request_group_id") or str(uuid.uuid4())
    data["request_group_id"] = request_group_id

    conn = get_pg_connection()
    cursor = conn.cursor()
    try:
        for full_name in names:
            cursor.execute(
                """
                INSERT INTO logistics_pass_requests (
                    request_group_id,
                    requester_telegram_id,
                    requester_name,
                    requester_username,
                    pass_type,
                    vehicle_plate,
                    vehicle_brand,
                    visitor_full_name,
                    date_mode,
                    visit_date_from,
                    visit_date_to,
                    visit_date
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    request_group_id,
                    telegram_user.id,
                    telegram_user.full_name,
                    telegram_user.username,
                    data.get("pass_type"),
                    data.get("vehicle_plate"),
                    data.get("vehicle_brand"),
                    full_name,
                    data.get("date_mode") or "single",
                    data.get("visit_date_from"),
                    data.get("visit_date_to"),
                    data.get("visit_date_from"),
                )
            )
        conn.commit()
    finally:
        cursor.close()
        conn.close()

def get_role_recipients() -> list[int]:
    target_roles = ["admin", "adminpre", "логіст", "логістика", "закупівля"]
    conn = get_pg_connection()
    cursor = conn.cursor()
    try:
        cursor.execute(
            """
            SELECT telegram_id
            FROM database_app_userdatatelegram
            WHERE telegram_id IS NOT NULL
              AND LOWER(TRIM(COALESCE(username, ''))) = ANY(%s)
            """,
            (target_roles,)
        )
        recipients = list({int(row[0]) for row in cursor.fetchall() if row and row[0]})

        # Fallback: якщо по ролях нікого не знайшли, пробуємо хоча б admin/adminpre
        if not recipients:
            cursor.execute(
                """
                SELECT telegram_id
                FROM database_app_userdatatelegram
                WHERE telegram_id IS NOT NULL
                  AND LOWER(TRIM(COALESCE(username, ''))) IN ('admin', 'adminpre')
                """
            )
            recipients = list({int(row[0]) for row in cursor.fetchall() if row and row[0]})

        return recipients
    finally:
        cursor.close()
        conn.close()

async def notify_pass_request_roles(context: CallbackContext, telegram_user, data: dict) -> tuple[int, int]:
    recipients = get_role_recipients()
    if not recipients:
        logging.warning("Заявка на перепустку: не знайдено отримувачів для ролей admin/adminpre/логіст/закупівля")
        return (0, 0)

    logging.info(f"Заявка на перепустку: знайдено отримувачів {len(recipients)}")
    delivered = 0

    period_text = (
        html.escape(str(data.get('visit_date_from') or '—'))
        if data.get("date_mode") == "single"
        else f"{html.escape(str(data.get('visit_date_from') or '—'))} — {html.escape(str(data.get('visit_date_to') or '—'))}"
    )
    visitor_names = data.get("visitor_names") or []
    if not visitor_names and data.get("visitor_full_name"):
        visitor_names = [data.get("visitor_full_name")]
    persons_count = data.get("persons_count") or len(visitor_names)
    names_text = "\n".join([f"• {html.escape(str(name))}" for name in visitor_names]) if visitor_names else "—"

    text = (
        "🛂 <b>Нова заявка на перепустку</b>\n\n"
        f"<b>ID групи:</b> <code>{html.escape(str(data.get('request_group_id') or '—'))}</code>\n"
        f"<b>Тип:</b> {'Для авто' if data.get('pass_type') == 'vehicle' else 'Для особи'}\n"
        f"<b>Кількість осіб:</b> {persons_count}\n"
        f"<b>Особи:</b>\n{names_text}\n"
        f"<b>Тип дати:</b> {'На один день' if data.get('date_mode') == 'single' else 'Від та до'}\n"
        f"<b>Дата:</b> {period_text}\n"
        f"<b>Хто подав:</b> {html.escape(telegram_user.full_name or '—')}"
    )
    if data.get("pass_type") == "vehicle":
        text += f"\n<b>Номер авто:</b> {html.escape(data.get('vehicle_plate') or '—')}"

    for chat_id in recipients:
        try:
            await context.bot.send_message(chat_id=chat_id, text=text, parse_mode=ParseMode.HTML)
            delivered += 1
        except Exception:
            logging.exception(f"Не вдалося надіслати заявку на перепустку користувачу {chat_id}")

    return (len(recipients), delivered)

async def show_logistics_menu(update: Update, context: CallbackContext):
    keyboard = [
        [InlineKeyboardButton("Мої заявки на перепустку", callback_data="lp_my_requests")],
        [InlineKeyboardButton("Подати заявку на перепустку", callback_data="lp_pass_start")],
        [InlineKeyboardButton("Подати заявку", callback_data="logistics_request")],
        [InlineKeyboardButton("Профіль водія", callback_data="logistics_driver_profile")],
        [InlineKeyboardButton("Назад", callback_data="logistics_back")] # Змінив callback_data на унікальну, щоб не конфліктувала
    ]
    
    # Якщо це нове повідомлення
    if update.message:
        sent_message = await update.message.reply_text(
            "<b>Логістика та автопарк</b>\nОберіть необхідну дію:",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode=ParseMode.HTML
        )
        context.user_data["logistics_message_id"] = sent_message.message_id
    # Якщо це редагування попереднього (наприклад, кнопка "Назад" з іншого меню)
    elif update.callback_query:
        await update.callback_query.edit_message_text(
            "<b>Логістика та автопарк</b>\nОберіть необхідну дію:",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode=ParseMode.HTML
        )
        if update.callback_query.message:
            context.user_data["logistics_message_id"] = update.callback_query.message.message_id

async def logistics_button_handler(update: Update, context: CallbackContext):
    query = update.callback_query
    await query.answer()

    if query.data == "lp_noop":
        return

    if query.data == "lp_cancel":
        clear_pass_flow(context)
        await query.edit_message_text("❌ Подачу заявки на перепустку скасовано.")
        return

    if query.data == "lp_my_requests":
        ensure_pass_requests_table()
        items = get_user_pass_requests(query.from_user.id)
        if not items:
            await query.edit_message_text(
                "ℹ️ У вас ще немає поданих заявок на перепустку.",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("🔙 Назад", callback_data="logistics_menu_back")]
                ])
            )
            return

        context.user_data["lp_history_items"] = items
        context.user_data["lp_history_index"] = 0
        current = items[0]
        await query.edit_message_text(
            _build_history_text(current, 0, len(items)),
            parse_mode=ParseMode.HTML,
            reply_markup=_build_history_keyboard(0, len(items))
        )
        return

    if query.data in ("lp_hist_prev", "lp_hist_next"):
        items = context.user_data.get("lp_history_items") or []
        if not items:
            await query.edit_message_text("⚠️ Історія недоступна. Відкрийте розділ ще раз.")
            return

        idx = int(context.user_data.get("lp_history_index", 0))
        if query.data == "lp_hist_prev" and idx < len(items) - 1:
            idx += 1
        if query.data == "lp_hist_next" and idx > 0:
            idx -= 1

        context.user_data["lp_history_index"] = idx
        current = items[idx]
        await query.edit_message_text(
            _build_history_text(current, idx, len(items)),
            parse_mode=ParseMode.HTML,
            reply_markup=_build_history_keyboard(idx, len(items))
        )
        return

    if query.data == "lp_clone_start":
        items = context.user_data.get("lp_history_items") or []
        idx = int(context.user_data.get("lp_history_index", 0))
        if not items or idx < 0 or idx >= len(items):
            await query.edit_message_text("⚠️ Не вдалося знайти заявку для копіювання. Спробуйте ще раз.")
            return

        base = items[idx]
        init_pass_flow(context, base.get("pass_type") or "person")
        pass_data = context.user_data.get("logistics_pass", {})
        pass_data["vehicle_plate"] = base.get("vehicle_plate")
        pass_data["vehicle_brand"] = base.get("vehicle_brand")
        pass_data["visitor_full_name"] = base.get("visitor_full_name")
        pass_data["visitor_names"] = [base.get("visitor_full_name")] if base.get("visitor_full_name") else []
        pass_data["persons_count"] = 1 if base.get("visitor_full_name") else 0
        pass_data["date_mode"] = base.get("date_mode") or "single"
        pass_data["request_group_id"] = str(uuid.uuid4())

        if pass_data["date_mode"] == "single":
            context.user_data["logistics_state"] = "pass_date"
            today = date.today()
            await query.edit_message_text(
                "📅 Оберіть <b>нову дату</b> для заявки (копія):",
                parse_mode=ParseMode.HTML,
                reply_markup=build_calendar_keyboard(today.year, today.month)
            )
        else:
            context.user_data["logistics_state"] = "pass_date_from"
            today = date.today()
            await query.edit_message_text(
                "📅 Оберіть <b>нову дату ВІД</b> для заявки (копія):",
                parse_mode=ParseMode.HTML,
                reply_markup=build_calendar_keyboard(today.year, today.month)
            )
        return

    if query.data == "lp_pass_start":
        clear_pass_flow(context)
        context.user_data["logistics_pass_request_group_id"] = str(uuid.uuid4())
        keyboard = [
            [InlineKeyboardButton("🚗 Для авто", callback_data="lp_type_vehicle")],
            [InlineKeyboardButton("🧍 Для особи", callback_data="lp_type_person")],
            [InlineKeyboardButton("❌ Скасувати", callback_data="lp_cancel")],
        ]
        await query.edit_message_text(
            text=PASS_REQUEST_INTRO,
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode=ParseMode.HTML,
        )
        return

    if query.data == "lp_type_vehicle":
        init_pass_flow(context, "vehicle")
        await query.edit_message_text("🚗 Вкажіть номер авто (наприклад: АА1234КК):")
        return

    if query.data == "lp_type_person":
        init_pass_flow(context, "person")
        await query.edit_message_text("👥 Вкажіть кількість осіб:")
        return

    if query.data == "lp_date_single":
        pass_data = context.user_data.get("logistics_pass")
        if not pass_data:
            await query.edit_message_text("⚠️ Сесія подачі заявки завершена. Почніть знову.")
            return
        pass_data["date_mode"] = "single"
        context.user_data["logistics_state"] = "pass_date"
        today = date.today()
        await query.edit_message_text(
            "📅 Оберіть дату перепустки:",
            reply_markup=build_calendar_keyboard(today.year, today.month)
        )
        return

    if query.data == "lp_date_range":
        pass_data = context.user_data.get("logistics_pass")
        if not pass_data:
            await query.edit_message_text("⚠️ Сесія подачі заявки завершена. Почніть знову.")
            return
        pass_data["date_mode"] = "range"
        context.user_data["logistics_state"] = "pass_date_from"
        today = date.today()
        await query.edit_message_text(
            "📅 Оберіть <b>дату ВІД</b>:",
            parse_mode=ParseMode.HTML,
            reply_markup=build_calendar_keyboard(today.year, today.month)
        )
        return

    if query.data.startswith("lp_cal_prev:") or query.data.startswith("lp_cal_next:"):
        _, year, month = query.data.split(":")
        year = int(year)
        month = int(month)
        if query.data.startswith("lp_cal_prev:"):
            month -= 1
            if month == 0:
                month = 12
                year -= 1
        else:
            month += 1
            if month == 13:
                month = 1
                year += 1
        await query.edit_message_text(
            "📅 Оберіть дату перепустки:",
            reply_markup=build_calendar_keyboard(year, month)
        )
        return

    if query.data.startswith("lp_day:"):
        selected = query.data.split(":", 1)[1]
        pass_data = context.user_data.get("logistics_pass")
        if not pass_data:
            await query.edit_message_text("⚠️ Сесія подачі заявки завершена. Почніть знову.")
            return

        state = context.user_data.get("logistics_state")
        if state == "pass_date":
            pass_data["visit_date_from"] = selected
            pass_data["visit_date_to"] = selected
            context.user_data["logistics_state"] = "pass_confirm"
        elif state == "pass_date_from":
            pass_data["visit_date_from"] = selected
            context.user_data["logistics_state"] = "pass_date_to"
            dt = datetime.fromisoformat(selected)
            await query.edit_message_text(
                "📅 Оберіть <b>дату ДО</b>:",
                parse_mode=ParseMode.HTML,
                reply_markup=build_calendar_keyboard(dt.year, dt.month)
            )
            return
        elif state == "pass_date_to":
            if selected < (pass_data.get("visit_date_from") or selected):
                await query.answer("Дата ДО не може бути раніше дати ВІД", show_alert=True)
                return
            pass_data["visit_date_to"] = selected
            context.user_data["logistics_state"] = "pass_confirm"
        else:
            await query.edit_message_text("⚠️ Невірний стан сесії. Почніть знову.")
            clear_pass_flow(context)
            return

        period_text = (
            html.escape(pass_data['visit_date_from'] or '—')
            if pass_data.get("date_mode") == "single"
            else f"{html.escape(pass_data['visit_date_from'] or '—')} — {html.escape(pass_data['visit_date_to'] or '—')}"
        )
        visitor_names = pass_data.get("visitor_names") or []
        persons_count = pass_data.get("persons_count") or len(visitor_names)
        names_text = "\n".join([f"• {html.escape(str(name))}" for name in visitor_names]) if visitor_names else "—"

        summary = (
            "🔎 <b>Перевірте заявку на перепустку:</b>\n\n"
            f"<b>ID групи:</b> <code>{html.escape(str(pass_data.get('request_group_id') or '—'))}</code>\n"
            f"<b>Тип:</b> {'Для авто' if pass_data['pass_type'] == 'vehicle' else 'Для особи'}\n"
            f"<b>Кількість осіб:</b> {persons_count}\n"
            f"<b>Особи:</b>\n{names_text}\n"
            f"<b>Тип дати:</b> {'На один день' if pass_data.get('date_mode') == 'single' else 'Від та до'}\n"
            f"<b>Дата:</b> {period_text}"
        )
        if pass_data["pass_type"] == "vehicle":
            summary += f"\n<b>Номер авто:</b> {html.escape(pass_data['vehicle_plate'] or '—')}"

        keyboard = [
            [
                InlineKeyboardButton("✅ Окей", callback_data="lp_confirm"),
                InlineKeyboardButton("❌ Скасувати", callback_data="lp_cancel"),
            ]
        ]

        await query.edit_message_text(
            summary,
            parse_mode=ParseMode.HTML,
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return

    if query.data == "lp_confirm":
        pass_data = context.user_data.get("logistics_pass")
        visitor_names = pass_data.get("visitor_names") if pass_data else []
        if (
            not pass_data
            or not pass_data.get("visit_date_from")
            or not pass_data.get("visit_date_to")
            or not visitor_names
        ):
            await query.edit_message_text("⚠️ Сесія подачі заявки завершена. Почніть знову.")
            clear_pass_flow(context)
            return

        try:
            save_pass_request(query.from_user, pass_data)
            recipients_count, delivered_count = await notify_pass_request_roles(context, query.from_user, pass_data)
        except Exception as e:
            logging.exception("Не вдалося зберегти заявку на перепустку")
            await query.edit_message_text(f"⚠️ Помилка збереження заявки: {html.escape(str(e))}")
            clear_pass_flow(context)
            return

        period_text = (
            html.escape(pass_data['visit_date_from'] or '—')
            if pass_data.get("date_mode") == "single"
            else f"{html.escape(pass_data['visit_date_from'] or '—')} — {html.escape(pass_data['visit_date_to'] or '—')}"
        )
        persons_count = pass_data.get("persons_count") or len(visitor_names)
        names_text = "\n".join([f"• {html.escape(str(name))}" for name in visitor_names]) if visitor_names else "—"

        summary = (
            "✅ <b>Заявку на перепустку збережено</b>\n\n"
            f"<b>ID групи:</b> <code>{html.escape(str(pass_data.get('request_group_id') or '—'))}</code>\n"
            f"<b>Тип:</b> {'Для авто' if pass_data['pass_type'] == 'vehicle' else 'Для особи'}\n"
            f"<b>Кількість осіб:</b> {persons_count}\n"
            f"<b>Особи:</b>\n{names_text}\n"
            f"<b>Тип дати:</b> {'На один день' if pass_data.get('date_mode') == 'single' else 'Від та до'}\n"
            f"<b>Дата:</b> {period_text}"
        )
        if pass_data["pass_type"] == "vehicle":
            summary += f"\n<b>Номер авто:</b> {html.escape(pass_data['vehicle_plate'] or '—')}"

        if recipients_count == 0:
            summary += "\n\n⚠️ Сповіщення не надіслано: не знайдено отримувачів за ролями."
        elif delivered_count == 0:
            summary += "\n\n⚠️ Сповіщення не доставлено отримувачам (ймовірно, чат із ботом не відкрито або бот заблокований)."
        elif delivered_count < recipients_count:
            summary += f"\n\n⚠️ Сповіщення доставлено частково: {delivered_count}/{recipients_count}."

        clear_pass_flow(context)
        await query.edit_message_text(summary, parse_mode=ParseMode.HTML)
        return

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
        clear_pass_history_flow(context)
        await show_logistics_menu(update, context)
        return

    if query.data == "logistics_back":
        # Тут логіка повернення в ГОЛОВНЕ меню бота (main_menu)
        # Наприклад: await show_main_menu(update, context)
        await query.edit_message_text("Повертаю в головне меню...")
        return

async def logistics_text_input(update: Update, context: CallbackContext) -> bool:
    state = context.user_data.get("logistics_state")
    if not state:
        return False

    if not update.message or not update.message.text:
        return True

    value = update.message.text.strip()
    pass_data = context.user_data.get("logistics_pass")
    if not pass_data:
        clear_pass_flow(context)
        return False

    if not pass_data.get("request_group_id"):
        pass_data["request_group_id"] = context.user_data.get("logistics_pass_request_group_id") or str(uuid.uuid4())

    if state == "pass_plate":
        pass_data["vehicle_plate"] = value
        context.user_data["logistics_state"] = "pass_count"
        await update.message.reply_text("👥 Вкажіть кількість осіб:")
        return True

    if state == "pass_count":
        if not value.isdigit() or int(value) <= 0:
            await update.message.reply_text("⚠️ Введіть коректну кількість осіб (ціле число більше 0).")
            return True

        count = int(value)
        if count > 30:
            await update.message.reply_text("⚠️ Максимум 30 осіб за одну заявку. Вкажіть менше число.")
            return True

        pass_data["persons_count"] = count
        pass_data["visitor_names"] = []
        context.user_data["logistics_state"] = "pass_name"
        await update.message.reply_text(f"🧍 Вкажіть ПІБ особи 1 з {count}:")
        return True

    if state == "pass_name":
        names = pass_data.get("visitor_names") or []
        names.append(value)
        pass_data["visitor_names"] = names
        pass_data["visitor_full_name"] = names[0] if names else None

        target = pass_data.get("persons_count") or 1
        if len(names) < target:
            await update.message.reply_text(f"🧍 Вкажіть ПІБ особи {len(names) + 1} з {target}:")
            return True

        context.user_data["logistics_state"] = "pass_date_type"
        keyboard = [
            [InlineKeyboardButton("📅 На один день", callback_data="lp_date_single")],
            [InlineKeyboardButton("📆 Від та до", callback_data="lp_date_range")],
            [InlineKeyboardButton("❌ Скасувати", callback_data="lp_cancel")],
        ]
        await update.message.reply_text(
            "Оберіть тип дати перепустки:",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return True

    if state in ("pass_date_type", "pass_date", "pass_date_from", "pass_date_to", "pass_confirm"):
        await update.message.reply_text("📅 Оберіть дату/підтвердження через кнопки нижче.")
        return True

    return False