from flask import (
    Flask, render_template, request,
    redirect, url_for, session, flash, jsonify
)
import psycopg2
import requests
import random
import uuid
import os
import json
import smtplib
from datetime import datetime
from email.mime.text import MIMEText
from werkzeug.utils import secure_filename
from dotenv import load_dotenv
# ---------------- CONFIG ----------------

load_dotenv()

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY")

PG_CONN = {
    "host": os.environ.get("PG_HOST"),
    "port": int(os.environ.get("PG_PORT")),
    "dbname": os.environ.get("PG_DBNAME"),
    "user": os.environ.get("PG_USER"),
    "password": os.environ.get("PG_PASSWORD")
}

TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
SMTP_HOST = os.environ.get("SMTP_HOST", "smtp.ukr.net")
SMTP_PORT = int(os.environ.get("SMTP_PORT", "465"))
SMTP_USER = os.environ.get("SMTP_USER")
SMTP_PASSWORD = os.environ.get("SMTP_PASSWORD")
SMTP_FROM = os.environ.get("SMTP_FROM", SMTP_USER or "")
PASS_REQUEST_DEFAULT_EMAIL = os.environ.get("PASS_REQUEST_DEFAULT_EMAIL", "").strip()

PASS_STATUS_LABELS = {
    "new": "нова",
    "forwarded": "передано",
    "cancelled": "скасовано",
}

CHUNK_LIMIT = 20

UPLOAD_DIR = os.path.join(os.path.dirname(__file__), "uploads")
os.makedirs(UPLOAD_DIR, exist_ok=True)

# ---------------- HELPERS ----------------

def get_db_connection():
    return psycopg2.connect(**PG_CONN)

def is_logged_in() -> bool:
    return bool(session.get("is_admin"))

def is_super_admin() -> bool:
    return session.get("role") == "admin"

def is_pre_admin() -> bool:
    return session.get("role") == "adminpre"

def is_pass_operator() -> bool:
    return session.get("role") in {"admin", "adminpre", "логіст", "логістика", "закупівля", "керівник збиральників", "керівник збиральників тендер", "керівник збиральників приват"}

def _format_pass_date(value) -> str:
    if value is None:
        return "—"
    if hasattr(value, "strftime"):
        return value.strftime("%d.%m.%Y")
    try:
        return datetime.fromisoformat(str(value)).strftime("%d.%m.%Y")
    except Exception:
        return str(value)


def _parse_date(value: str):
    if not value:
        return None
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except Exception:
        return None


def _group_type_label(pass_type: str, persons_count: int) -> str:
    if persons_count > 1:
        return "Група"
    return "Для авто" if pass_type == "vehicle" else "Для особи"


def _fetch_pass_request_groups(limit: int, offset: int, search_vehicle: str, search_person: str, status_filter: str):
    conn = get_db_connection()
    cur = conn.cursor()
    try:
        ensure_pass_requests_audit_columns()

        params = []
        where_parts = ["1=1"]
        if search_vehicle:
            where_parts.append("COALESCE(lpr.vehicle_plate, '') ILIKE %s")
            params.append(f"%{search_vehicle}%")
        if search_person:
            where_parts.append("COALESCE(lpr.visitor_full_name, '') ILIKE %s")
            params.append(f"%{search_person}%")
        if status_filter:
            where_parts.append("lpr.status = %s")
            params.append(status_filter)

        where_sql = " AND ".join(where_parts)
        params.extend([limit, offset])

        cur.execute(
            f"""
            WITH grouped AS (
                SELECT
                    COALESCE(NULLIF(lpr.request_group_id, ''), lpr.id::text) AS request_group_id,
                    MIN(lpr.id) AS first_request_id,
                    MAX(COALESCE(NULLIF(TRIM(u.name), ''), lpr.requester_name)) AS requester_name,
                    MAX(lpr.requester_username) AS requester_username,
                    MAX(lpr.requester_telegram_id) AS requester_telegram_id,
                    MAX(lpr.pass_type) AS pass_type,
                    MAX(lpr.vehicle_plate) AS vehicle_plate,
                    MAX(lpr.vehicle_brand) AS vehicle_brand,
                    MAX(COALESCE(lpr.date_mode, 'single')) AS date_mode,
                    MAX(lpr.visit_date) AS visit_date,
                    MAX(lpr.visit_date_from) AS visit_date_from,
                    MAX(lpr.visit_date_to) AS visit_date_to,
                    MAX(lpr.status) AS status,
                    MIN(lpr.created_at) AS created_at,
                    MAX(lpr.processed_by_name) AS processed_by_name,
                    MAX(lpr.processed_by_role) AS processed_by_role,
                    MAX(lpr.processed_at) AS processed_at,
                    MAX(lpr.cancel_reason) AS cancel_reason,
                    COUNT(*)::INT AS persons_count,
                    STRING_AGG(COALESCE(lpr.visitor_full_name, '—'), '||' ORDER BY lpr.id) AS visitors_joined
                FROM logistics_pass_requests lpr
                LEFT JOIN database_app_userdatatelegram u
                    ON u.telegram_id = lpr.requester_telegram_id
                WHERE {where_sql}
                GROUP BY COALESCE(NULLIF(lpr.request_group_id, ''), lpr.id::text)
            )
            SELECT *
            FROM grouped
            ORDER BY created_at DESC
            LIMIT %s OFFSET %s
            """,
            params,
        )

        result = []
        rows = cur.fetchall()
        for row in rows:
            visitors = [v for v in (row[19] or "").split("||") if v]
            if row[8] == "range":
                date_text = f"{_format_pass_date(row[10])} — {_format_pass_date(row[11])}"
            else:
                date_text = _format_pass_date(row[10] or row[9])

            processed_by = ((row[14] or "") + (f" ({row[15]})" if row[15] else "")).strip() or "—"

            item = {
                "request_group_id": row[0],
                "first_request_id": row[1],
                "requester_name": row[2] or "—",
                "requester_username": row[3] or "",
                "requester_telegram_id": row[4],
                "pass_type": row[5],
                "vehicle_plate": row[6] or "—",
                "vehicle_brand": row[7] or "",
                "date_mode": row[8] or "single",
                "visit_date": _format_pass_date(row[9]),
                "visit_date_from": _format_pass_date(row[10]),
                "visit_date_to": _format_pass_date(row[11]),
                "status": row[12],
                "created_at": row[13].isoformat() if row[13] else None,
                "created_at_text": row[13].strftime("%d.%m.%Y %H:%M") if row[13] else "—",
                "processed_by": processed_by,
                "processed_at_text": row[16].strftime("%d.%m.%Y %H:%M") if row[16] else "—",
                "cancel_reason": row[17] or "—",
            }
            item["persons_count"] = row[18] or len(visitors)
            item["visitors"] = visitors
            item["visitors_text"] = ", ".join(visitors) if visitors else "—"
            item["date_text"] = date_text
            item["type_label"] = _group_type_label(item["pass_type"], item["persons_count"])
            result.append(item)

        return result
    finally:
        cur.close()
        conn.close()


def ensure_pass_requests_audit_columns():
    conn = get_db_connection()
    cur = conn.cursor()
    try:
        cur.execute("ALTER TABLE logistics_pass_requests ADD COLUMN IF NOT EXISTS processed_by_telegram_id BIGINT")
        cur.execute("ALTER TABLE logistics_pass_requests ADD COLUMN IF NOT EXISTS processed_by_name TEXT")
        cur.execute("ALTER TABLE logistics_pass_requests ADD COLUMN IF NOT EXISTS processed_by_role TEXT")
        cur.execute("ALTER TABLE logistics_pass_requests ADD COLUMN IF NOT EXISTS processed_at TIMESTAMP")
        cur.execute("ALTER TABLE logistics_pass_requests ADD COLUMN IF NOT EXISTS cancel_reason TEXT")
        cur.execute("ALTER TABLE logistics_pass_requests ADD COLUMN IF NOT EXISTS request_group_id TEXT")
        cur.execute("UPDATE logistics_pass_requests SET request_group_id = id::text WHERE request_group_id IS NULL")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_logistics_pass_requests_group ON logistics_pass_requests(request_group_id)")
        conn.commit()
    finally:
        cur.close()
        conn.close()


def get_current_operator_identity() -> tuple[int | None, str, str]:
    operator_id = session.get("admin_telegram_id")
    operator_role = (session.get("role") or "").strip()
    operator_name = ""

    if operator_id is not None:
        conn = get_db_connection()
        cur = conn.cursor()
        try:
            cur.execute(
                "SELECT COALESCE(name, '') FROM database_app_userdatatelegram WHERE telegram_id = %s LIMIT 1",
                (int(operator_id),)
            )
            row = cur.fetchone()
            operator_name = (row[0] if row else "") or ""
        finally:
            cur.close()
            conn.close()

    if not operator_name:
        operator_name = f"ID {operator_id}" if operator_id is not None else "Невідомо"

    return (int(operator_id) if operator_id is not None else None, operator_name, operator_role)

def send_pass_request_email(
    to_email: str,
    visitor_names: list[str],
    vehicle_plate: str | None,
    visit_date_text: str,
):
    if not SMTP_USER or not SMTP_PASSWORD or not SMTP_FROM:
        raise RuntimeError("SMTP не налаштовано: потрібні SMTP_USER, SMTP_PASSWORD, SMTP_FROM")

    if not to_email:
        raise RuntimeError("Не вказано email отримувача")

    clean_plate = (vehicle_plate or "").strip()
    title = f"Перепустка на {visit_date_text}"
    if clean_plate and clean_plate != "—":
        title = f"{title} | Авто: {clean_plate}"
    names_block = "\n".join([f"- {name}" for name in visitor_names]) if visitor_names else "- —"

    body = (
        f"{title}\n"
        f"Кількість осіб до заявки: {len(visitor_names)}\n"
        f"Особи:\n{names_block}\n\n"
        f"Авто: {clean_plate or '—'}\n\n"
        "Компанія \"MIM-K\"\n"
        "Киев, бул. Вацлава Гавела,16, корпус 4\n"
        "тел.:(044) 599-81-12\n"
        "http://mim-k.com.ua/\n"
    )

    msg = MIMEText(body, _subtype="plain", _charset="utf-8")
    msg["Subject"] = title
    msg["From"] = SMTP_FROM
    msg["To"] = to_email

    with smtplib.SMTP_SSL(SMTP_HOST, SMTP_PORT, timeout=20) as server:
        server.login(SMTP_USER, SMTP_PASSWORD)
        server.sendmail(SMTP_FROM, [to_email], msg.as_string())


def notify_requester_status_change(
    requester_telegram_id: int | None,
    request_id: int,
    status_code: str,
    visitor_name: str,
    vehicle_plate: str,
    visit_date_text: str,
    processed_by: str | None = None,
    cancel_reason: str | None = None,
):
    if not requester_telegram_id:
        return

    status_text = PASS_STATUS_LABELS.get(status_code, status_code)
    text = (
        f"🛂 <b>Оновлення заявки #{request_id}</b>\n\n"
        f"<b>Статус:</b> {status_text}\n"
        f"<b>Особа:</b> {visitor_name or '—'}\n"
        f"<b>Авто:</b> {vehicle_plate or '—'}\n"
        f"<b>Дата:</b> {visit_date_text}"
    )
    if processed_by:
        text += f"\n<b>Опрацював:</b> {processed_by}"
    if status_code == "cancelled" and cancel_reason:
        text += f"\n<b>Причина скасування:</b> {cancel_reason}"
    send_telegram_message(requester_telegram_id, text)

# --- NEW: лічильник активних заявок ---
def get_pending_requests_count() -> int:
    conn = get_db_connection()
    cur = conn.cursor()
    try:
        # TODO: за потреби підкоригуй назву таблиці/умову статусу
        cur.execute(
            "SELECT COUNT(*) FROM registration_requests WHERE status = 'pending'"
        )
        return cur.fetchone()[0]
    except Exception:
        return 0
    finally:
        cur.close()
        conn.close()

def get_pending_pass_requests_count() -> int:
    conn = get_db_connection()
    cur = conn.cursor()
    try:
        cur.execute(
            "SELECT COUNT(*) FROM logistics_pass_requests WHERE status = 'new'"
        )
        return cur.fetchone()[0]
    except Exception:
        return 0
    finally:
        cur.close()
        conn.close()

@app.context_processor
def inject_counts():
    return {
        "pending_requests_count": get_pending_requests_count(),
        "pending_pass_requests_count": get_pending_pass_requests_count(),
        "current_role": session.get("role")
    }


def get_admin_telegram_id():
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("""
        SELECT telegram_id
        FROM database_app_userdatatelegram
        WHERE username = 'admin'
        ORDER BY telegram_id
        LIMIT 1
    """)
    row = cur.fetchone()
    cur.close()
    conn.close()
    return row[0] if row else None

def send_telegram_message(chat_id, text, reply_markup=None, file_path=None, mime=None):
    """
    Якщо file_path передано:
      - для image/* відправляє як фото
      - для інших типів відправляє як документ
    Інакше — звичайне текстове повідомлення.
    """
    try:
        chat_id = int(chat_id)
    except Exception:
        print("Невірний chat_id:", chat_id)
        return

    try:
        if file_path:
            # Відправка фото / документа
            if mime and mime.startswith("image/"):
                method = "sendPhoto"
                file_field = "photo"
            else:
                method = "sendDocument"
                file_field = "document"

            url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/{method}"
            data = {
                "chat_id": chat_id,
                "caption": text or "",
                "parse_mode": "HTML",
            }
            if reply_markup:
                data["reply_markup"] = json.dumps(reply_markup)

            with open(file_path, "rb") as f:
                files = {file_field: f}
                r = requests.post(url, data=data, files=files, timeout=20)
                print("Telegram file:", r.status_code, r.text)
        else:
            # Звичайне текстове повідомлення
            url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
            payload = {
                "chat_id": chat_id,
                "text": text,
                "parse_mode": "HTML",
            }
            if reply_markup:
                payload["reply_markup"] = reply_markup
            r = requests.post(url, json=payload, timeout=8)
            print("Telegram:", r.status_code, r.text)
    except Exception as e:
        print("Telegram error:", e)

# ---------------- AUTH ----------------

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        phone = request.form.get("phone", "").strip()
        phone = phone.replace(" ", "").replace("-", "")
        if phone.startswith("0") and len(phone) == 10:
            phone = "+38" + phone
        elif phone.startswith("380") and len(phone) == 12:
            phone = "+" + phone
        elif phone.startswith("+380") and len(phone) == 13:
            pass
        else:
            flash("Невірний формат телефону", "danger")
            return redirect(url_for("login"))

        # Перевірка в базі: admin + adminpre
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("""
            SELECT telegram_id, LOWER(TRIM(COALESCE(username, '')))
            FROM database_app_userdatatelegram
            WHERE phone_number = %s
              AND LOWER(TRIM(COALESCE(username, ''))) IN ('admin', 'adminpre', 'логіст', 'логістика', 'закупівля')
            LIMIT 1
        """, (phone,))
        row = cur.fetchone()
        cur.close(); conn.close()

        if not row:
            flash("Вхід дозволено лише для admin/adminpre/логістика/закупівля!", "danger")
            return redirect(url_for("login"))

        telegram_id = row[0]
        role = row[1]
        code = random.randint(100000, 999999)
        session["login_code"] = str(code)
        session["phone"] = phone
        session["admin_telegram_id"] = telegram_id  # Зберігаємо id адміна
        session["login_role"] = role

        send_telegram_message(
            telegram_id,
            f"🔐 <b>Код входу в адмін-панель</b>\n\n<b>{code}</b>"
        )

        flash("Код надіслано в Telegram", "info")
        return redirect(url_for("verify"))

    return render_template("login.html")

@app.route("/verify", methods=["GET", "POST"])
def verify():
    if "login_code" not in session:
        return redirect(url_for("login"))

    if request.method == "POST":
        code = request.form.get("code", "").strip()
        remember = request.form.get("remember") == "on"  # Checkbox

        if code == session.get("login_code"):
            session.pop("login_code", None)
            session["is_admin"] = True
            session["role"] = session.pop("login_role", "admin")
            if remember:
                session.permanent = True  # Запам'ятати сесію
            flash("Вхід дозволено", "success")
            if session.get("role") == "adminpre":
                return redirect(url_for("pass_requests"))
            return redirect(url_for("index"))

        flash("Невірний код", "danger")

    return render_template("verify.html")


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


# ---------------- USERS ----------------

@app.route("/")
def index():
    if not is_logged_in():
        return redirect(url_for("login"))
    if not is_super_admin():
        flash("Недостатньо прав для цього розділу", "danger")
        return redirect(url_for("pass_requests"))

    search_name = request.args.get("search_name", "").strip()
    search_id = request.args.get("search_id", "").strip()
    search_role = request.args.get("search_role", "").strip()

    conn = get_db_connection()
    cur = conn.cursor()

    # Отримуємо тільки ті ролі, які реально є в БД
    cur.execute("""
        SELECT DISTINCT username
        FROM database_app_userdatatelegram
        WHERE username IS NOT NULL
        ORDER BY username
    """)
    roles = [r[0] for r in cur.fetchall()]

    query = """
        SELECT telegram_id, name, username, phone_number
        FROM database_app_userdatatelegram
        WHERE 1=1
    """
    params: list[str] = []

    if search_name:
        query += " AND name ILIKE %s"
        params.append(f"%{search_name}%")

    if search_id:
        query += " AND CAST(telegram_id AS TEXT) ILIKE %s"
        params.append(f"%{search_id}%")

    if search_role:
        query += " AND username = %s"
        params.append(search_role)

    query += " ORDER BY name NULLS LAST LIMIT %s OFFSET %s"
    params.extend([CHUNK_LIMIT, 0])

    cur.execute(query, params)
    users = cur.fetchall()

    cur.close()
    conn.close()

    admin_telegram_id = session.get("admin_telegram_id")

    return render_template(
        "index.html",
        users=users,
        users_has_more=len(users) == CHUNK_LIMIT,
        search_name=search_name,
        search_id=search_id,
        search_role=search_role,
        roles=roles,
        admin_telegram_id=admin_telegram_id
    )


@app.route("/users/chunk")
def users_chunk():
    if not is_logged_in() or not is_super_admin():
        return jsonify({"items": [], "has_more": False}), 403

    search_name = request.args.get("search_name", "").strip()
    search_id = request.args.get("search_id", "").strip()
    search_role = request.args.get("search_role", "").strip()
    offset_raw = request.args.get("offset", "0").strip()
    try:
        offset = max(0, int(offset_raw))
    except Exception:
        offset = 0

    conn = get_db_connection()
    cur = conn.cursor()
    try:
        query = """
            SELECT telegram_id, name, username, phone_number
            FROM database_app_userdatatelegram
            WHERE 1=1
        """
        params: list[str | int] = []

        if search_name:
            query += " AND name ILIKE %s"
            params.append(f"%{search_name}%")

        if search_id:
            query += " AND CAST(telegram_id AS TEXT) ILIKE %s"
            params.append(f"%{search_id}%")

        if search_role:
            query += " AND username = %s"
            params.append(search_role)

        query += " ORDER BY name NULLS LAST LIMIT %s OFFSET %s"
        params.extend([CHUNK_LIMIT, offset])

        cur.execute(query, params)
        rows = cur.fetchall()
    finally:
        cur.close()
        conn.close()

    admin_telegram_id = session.get("admin_telegram_id")
    items = [
        {
            "telegram_id": row[0],
            "name": row[1] or "",
            "role": row[2] or "",
            "phone": row[3] or "",
            "is_self": bool(admin_telegram_id is not None and int(row[0]) == int(admin_telegram_id)),
        }
        for row in rows
    ]

    return jsonify({"items": items, "has_more": len(items) == CHUNK_LIMIT})


@app.route("/user_action", methods=["POST"])
def user_action():
    if not is_logged_in():
        return redirect(url_for("login"))
    if not is_super_admin():
        flash("Недостатньо прав для цієї дії", "danger")
        return redirect(url_for("pass_requests"))

    action = request.form.get("action")
    selected_users = request.form.getlist("selected_users")
    if not selected_users:
        flash("Виберіть хоча б одного користувача", "danger")
        return redirect(url_for("index"))

    # Приведення до int для коректної типізації
    try:
        selected_users = [int(x) for x in selected_users]
    except ValueError:
        flash("Невірні ідентифікатори користувачів", "danger")
        return redirect(url_for("index"))

    conn = get_db_connection()
    cur = conn.cursor()

    # ---------- EDIT ----------
    if action == "edit":
        if len(selected_users) != 1:
            flash("Редагувати можна лише одного користувача", "danger")
            cur.close(); conn.close()
            return redirect(url_for("index"))

        telegram_id = selected_users[0]
        name = request.form.get("name", "").strip()
        role = request.form.get("role", "").strip()
        phone = request.form.get("phone", "").strip()  # New: Get phone number

        cur.execute("""
            UPDATE database_app_userdatatelegram
            SET name = %s, username = %s, phone_number = %s
            WHERE telegram_id = %s
        """, (name, role, phone, telegram_id))
        conn.commit()

        send_telegram_message(
            telegram_id,
            f"✏️ <b>Ваш профіль оновлено</b>\n\n"
            f"👤 Імʼя: <b>{name}</b>\n"
            f"🛡 Роль: <b>{role}</b>\n"
            f"📞 Телефон: <b>{phone}</b>"
        )
        flash("Користувача оновлено", "success")
        cur.close(); conn.close()
        return redirect(url_for("index"))

     # ---------- DELETE ----------
    elif action == "delete":
        for telegram_id in selected_users:
            cur.execute("DELETE FROM database_app_userdatatelegram WHERE telegram_id = %s", (telegram_id,))
            send_telegram_message(
                telegram_id,
                "❌ <b>Ваш акаунт видалено з системи</b>"
            )
        conn.commit()
        flash("Користувачів видалено", "success")
        cur.close(); conn.close()
        return redirect(url_for("index"))

    # ---------- INVALID ACTION ----------
    else:
        flash("Невідома дія", "danger")
        cur.close(); conn.close()
        return redirect(url_for("index"))


# ---------------- REGISTRATION ----------------

@app.route("/registration_requests")
def registration_requests():
    if not is_logged_in():
        return redirect(url_for("login"))
    if not is_super_admin():
        flash("Недостатньо прав для цього розділу", "danger")
        return redirect(url_for("pass_requests"))

    conn = get_db_connection()
    cur = conn.cursor()

    cur.execute("""
        SELECT id, telegram_id, first_name, last_name,
               position, phone_number, date_submitted
        FROM registration_requests
        WHERE status = 'pending'
        ORDER BY date_submitted
        LIMIT %s OFFSET %s
    """, (CHUNK_LIMIT, 0))

    requests_list = cur.fetchall()
    cur.close()
    conn.close()

    roles = [
        "admin", "adminpre", "конструктор", "замірник",
        "менеджер", "директор", "збиральник", "виробництво",
        "логіст", "водій", "бухгалтер", "відвідувач", "керівник збиральників", "Директор з виробництва", "Головний конструктор",
        "Закупівля", "Технолог приват", "Технолог тендер", "Керівник продажів", "Керівник продажів тендер", "Керівник продажів приват",
        "Технолог виробництво", "Керівник збиральників тендер", "Керівник конструктор приват","Керівник збиральників приват", "Керівник збиральників",
        "Майстер цеху", "Керівник М`який цех", "М`який цех", "Керівник метал цех", "Метал цех", "Керівник малярка", "Малярка","Директор з розвитку",
        "Комплектувальник"
    ]

    return render_template(
        "registration_requests.html",
        requests_list=requests_list,
        roles=roles,
        count=get_pending_requests_count(),
        requests_has_more=len(requests_list) == CHUNK_LIMIT,
    )


@app.route("/registration_requests/chunk")
def registration_requests_chunk():
    if not is_logged_in() or not is_super_admin():
        return jsonify({"items": [], "has_more": False}), 403

    offset_raw = request.args.get("offset", "0").strip()
    try:
        offset = max(0, int(offset_raw))
    except Exception:
        offset = 0

    conn = get_db_connection()
    cur = conn.cursor()
    try:
        cur.execute(
            """
            SELECT id, telegram_id, first_name, last_name,
                   position, phone_number, date_submitted
            FROM registration_requests
            WHERE status = 'pending'
            ORDER BY date_submitted
            LIMIT %s OFFSET %s
            """,
            (CHUNK_LIMIT, offset),
        )
        rows = cur.fetchall()
    finally:
        cur.close()
        conn.close()

    items = [
        {
            "id": row[0],
            "telegram_id": row[1],
            "first_name": row[2] or "",
            "last_name": row[3] or "",
            "position": row[4] or "",
            "phone_number": row[5] or "",
        }
        for row in rows
    ]

    return jsonify({"items": items, "has_more": len(items) == CHUNK_LIMIT})

@app.route("/process_registration", methods=["POST"])
def process_registration():
    if not is_logged_in():
        return redirect(url_for("login"))
    if not is_super_admin():
        flash("Недостатньо прав для цієї дії", "danger")
        return redirect(url_for("pass_requests"))

    action = request.form.get("action")
    if action and action.startswith("delete_"):
        req_id = action.split("_")[1]
        try:
            conn = get_db_connection()
            cur = conn.cursor()
            cur.execute("DELETE FROM registration_requests WHERE id = %s", (req_id,))
            conn.commit()
            flash("Заявку видалено", "success")
        except Exception as e:
            flash(f"Помилка видалення: {e}", "danger")
        finally:
            cur.close()
            conn.close()
        return redirect(url_for("registration_requests"))

    selected = request.form.getlist("selected_requests")
    if not selected:
        flash("Виберіть хоча б одну заявку", "danger")
        return redirect(url_for("registration_requests"))

    conn = get_db_connection()
    cur = conn.cursor()

    for req_id in selected:
        name = request.form.get(f"name_{req_id}", "").strip()
        role = request.form.get(f"role_{req_id}", "").strip()
        phone = request.form.get(f"phone_{req_id}", "").strip()

        # Автовиправлення номера на бекенді
        phone = phone.replace(" ", "").replace("-", "")
        if phone.startswith("0") and len(phone) == 10:
            phone = "+380" + phone[1:]
        elif phone.startswith("380") and len(phone) == 12:
            phone = "+" + phone
        elif phone.startswith("+380") and len(phone) == 13:
            pass
        else:
            flash("Невірний формат телефону!", "danger")
            continue

        # Витягуємо telegram_id із заявки
        cur.execute("SELECT telegram_id FROM registration_requests WHERE id = %s", (req_id,))
        row = cur.fetchone()
        if not row:
            continue
        telegram_id = int(row[0])

        # Перевіряємо існування користувача
        cur.execute("SELECT 1 FROM database_app_userdatatelegram WHERE telegram_id = %s", (telegram_id,))
        exists = cur.fetchone()

        if not exists:
             # Отримуємо максимальний id
            cur.execute("SELECT COALESCE(MAX(id), 0) FROM database_app_userdatatelegram")
            max_id = cur.fetchone()[0]
            new_id = max_id + 1

            cur.execute("""
                INSERT INTO database_app_userdatatelegram
                (id, telegram_id, name, username, phone_number, date_registered)
                VALUES (%s, %s, %s, %s, %s, NOW())
            """, (new_id, telegram_id, name, role, phone))

        # Позначаємо заявку як зареєстровану
        cur.execute("""
            UPDATE registration_requests
            SET status = 'registered'
            WHERE id = %s
        """, (req_id,))

        # Повідомлення з кнопкою /start
        keyboard = {
            "keyboard": [[{"text": "/start"}]],
            "resize_keyboard": True,
            "one_time_keyboard": True
        }
        send_telegram_message(
            telegram_id,
            f"✅ <b>Вас зареєстровано</b>\n\n"
            f"👤 {name}\n🛡 Роль: <b>{role}</b>\n\n"
            f"Натисніть /start для початку роботи.",
            reply_markup=keyboard
        )

    conn.commit()
    cur.close()
    conn.close()

    flash("Користувачів зареєстровано", "success")
    return redirect(url_for("registration_requests"))

# ---------------- ANNOUNCEMENTS ----------------

@app.route("/announcements", methods=["GET", "POST"])
def announcements():
    if not is_logged_in():
        return redirect(url_for("login"))
    if not is_super_admin():
        flash("Недостатньо прав для цього розділу", "danger")
        return redirect(url_for("pass_requests"))

    conn = get_db_connection()
    cur = conn.cursor()

    # Ролі з БД
    cur.execute("""
        SELECT DISTINCT username
        FROM database_app_userdatatelegram
        WHERE username IS NOT NULL
        ORDER BY username
    """)
    roles = [r[0] for r in cur.fetchall()]

    # Усі користувачі для селекту
    cur.execute("""
        SELECT telegram_id, COALESCE(name, ''), COALESCE(username, '')
        FROM database_app_userdatatelegram
        WHERE telegram_id IS NOT NULL
        ORDER BY COALESCE(name, ''), telegram_id
    """)
    users = cur.fetchall()

    if request.method == "POST":
        selected_roles = request.form.getlist("roles")
        selected_user_ids = request.form.getlist("target_users")  # список telegram_id як str
        send_all = request.form.get("send_all") == "1"
        message = request.form.get("message", "").strip()

        # кілька файлів
        uploads = request.files.getlist("attachment")
        file_infos: list[tuple[str, str | None]] = []  # (path, mime)

        # немає ні тексту, ні файлів
        if (not message) and (not uploads or all(not f.filename for f in uploads)):
            flash("Введіть повідомлення або додайте хоча б один файл/фото.", "danger")
            cur.close(); conn.close()
            return redirect(url_for("announcements"))

        # зберігаємо всі файли
        for upload in uploads:
            if not upload or not upload.filename:
                continue
            mime = upload.mimetype
            filename = datetime.now().strftime("%Y%m%d_%H%M%S_") + secure_filename(upload.filename)
            file_path = os.path.join(UPLOAD_DIR, filename)
            upload.save(file_path)
            file_infos.append((file_path, mime))

        recipients: list[int] = []
        history_roles_text = ""

        if send_all:
            cur.execute(
                """
                SELECT DISTINCT telegram_id
                FROM database_app_userdatatelegram
                WHERE telegram_id IS NOT NULL
                """
            )
            recipients = [row[0] for row in cur.fetchall()]
            history_roles_text = "all"
        elif selected_user_ids:
            # розсилка тільки обраним користувачам
            for uid in selected_user_ids:
                try:
                    recipients.append(int(uid))
                except ValueError:
                    continue
            history_roles_text = "users:" + ",".join(selected_user_ids)
        else:
            # розсилка за ролями
            if not selected_roles:
                flash("Виберіть хоча б одну роль або користувача.", "danger")
                cur.close(); conn.close()
                return redirect(url_for("announcements"))

            cur.execute("""
                SELECT telegram_id
                FROM database_app_userdatatelegram
                WHERE username = ANY(%s) AND telegram_id IS NOT NULL
            """, (selected_roles,))
            recipients = [row[0] for row in cur.fetchall()]
            history_roles_text = ", ".join(selected_roles)

        recipients = sorted(set(recipients))

        if not recipients:
            flash("Не знайдено жодного отримувача.", "warning")
            cur.close(); conn.close()
            return redirect(url_for("announcements"))

        text = f"📢 <b>Оголошення</b>\n\n{message}" if message else "📢 <b>Оголошення</b>"

        sent_count = 0
        for chat_id in recipients:
            try:
                if file_infos:
                    first = True
                    for path, mime in file_infos:
                        caption = text if first else ""
                        send_telegram_message(
                            chat_id,
                            caption,
                            file_path=path,
                            mime=mime
                        )
                        first = False
                else:
                    send_telegram_message(chat_id, text)
                sent_count += 1
            except Exception as e:
                print(f"Помилка відправки до {chat_id}: {e}")

        # запис в історію
        cur.execute(
            "INSERT INTO announcements_history (message, roles) VALUES (%s, %s)",
            (message, history_roles_text)
        )
        conn.commit()

        flash(f"Повідомлення надіслано {sent_count} отримувачам", "success")
        cur.close(); conn.close()
        return redirect(url_for("announcements"))

    # GET: історія
    cur.execute("""
        SELECT message, roles, sent_at
        FROM announcements_history
        ORDER BY sent_at DESC
        LIMIT 20
    """)
    history = cur.fetchall()

    cur.close(); conn.close()
    return render_template("announcements.html", roles=roles, users=users, history=history)


@app.route("/pass_requests")
def pass_requests():
    if not is_logged_in():
        return redirect(url_for("login"))
    if not is_pass_operator():
        flash("Недостатньо прав для цього розділу", "danger")
        return redirect(url_for("logout"))

    search_vehicle = request.args.get("search_vehicle", "").strip()
    search_person = request.args.get("search_person", "").strip()
    status_filter = request.args.get("status", "").strip().lower()
    if status_filter and status_filter not in PASS_STATUS_LABELS:
        status_filter = ""

    try:
        rows = _fetch_pass_request_groups(
            limit=20,
            offset=0,
            search_vehicle=search_vehicle,
            search_person=search_person,
            status_filter=status_filter,
        )
    except Exception as e:
        rows = []
        flash(f"Не вдалося завантажити заявки на пропуск: {e}", "danger")

    return render_template(
        "pass_requests.html",
        requests_list=rows,
        default_target_email=PASS_REQUEST_DEFAULT_EMAIL,
        search_vehicle=search_vehicle,
        search_person=search_person,
        status_filter=status_filter,
        status_labels=PASS_STATUS_LABELS,
    )


@app.route("/pass_requests/chunk")
def pass_requests_chunk():
    if not is_logged_in() or not is_pass_operator():
        return jsonify({"items": [], "has_more": False}), 403

    offset_raw = request.args.get("offset", "0").strip()
    search_vehicle = request.args.get("search_vehicle", "").strip()
    search_person = request.args.get("search_person", "").strip()
    status_filter = request.args.get("status", "").strip().lower()
    if status_filter and status_filter not in PASS_STATUS_LABELS:
        status_filter = ""

    try:
        offset = int(offset_raw)
    except Exception:
        offset = 0

    items = _fetch_pass_request_groups(
        limit=20,
        offset=offset,
        search_vehicle=search_vehicle,
        search_person=search_person,
        status_filter=status_filter,
    )
    return jsonify({"items": items, "has_more": len(items) == 20})


def _resolve_group_id(cur, request_id: int) -> str | None:
    cur.execute(
        "SELECT COALESCE(NULLIF(request_group_id, ''), id::text) FROM logistics_pass_requests WHERE id = %s",
        (request_id,),
    )
    row = cur.fetchone()
    return row[0] if row else None


def _get_group_rows(cur, request_group_id: str):
    cur.execute(
        """
        SELECT id,
               COALESCE(NULLIF(request_group_id, ''), id::text) AS request_group_id,
               pass_type,
               vehicle_plate,
               visitor_full_name,
               COALESCE(date_mode, 'single') AS date_mode,
               visit_date,
               visit_date_from,
               visit_date_to,
               status,
               requester_telegram_id
        FROM logistics_pass_requests
        WHERE COALESCE(NULLIF(request_group_id, ''), id::text) = %s
        ORDER BY id
        """,
        (request_group_id,),
    )
    return cur.fetchall()


@app.route("/pass_requests/create", methods=["POST"])
def pass_request_create():
    if not is_logged_in() or not is_pass_operator():
        return redirect(url_for("login"))

    pass_type = request.form.get("pass_type", "person").strip()
    vehicle_plate = request.form.get("vehicle_plate", "").strip()
    date_mode = request.form.get("date_mode", "single").strip()
    visit_date_from = _parse_date(request.form.get("visit_date_from", "").strip())
    visit_date_to = _parse_date(request.form.get("visit_date_to", "").strip())
    persons_count_raw = request.form.get("persons_count", "").strip()
    names = []
    if persons_count_raw.isdigit():
        persons_count = int(persons_count_raw)
        for i in range(1, persons_count + 1):
            val = request.form.get(f"person_{i}", "").strip()
            if val:
                names.append(val)
    else:
        persons_count = 0

    if not names:
        names_raw = request.form.get("visitor_names", "")
        names = [line.strip() for line in names_raw.splitlines() if line.strip()]

    if pass_type not in {"vehicle", "person"}:
        flash("Невірний тип заявки", "danger")
        return redirect(url_for("pass_requests"))
    if pass_type == "vehicle" and not vehicle_plate:
        flash("Для заявки на авто вкажіть номер авто", "danger")
        return redirect(url_for("pass_requests"))
    if not names:
        flash("Вкажіть хоча б одну особу (по одній в рядку)", "danger")
        return redirect(url_for("pass_requests"))
    if persons_count and len(names) != persons_count:
        flash("Заповніть ПІБ для кожної особи", "danger")
        return redirect(url_for("pass_requests"))
    if date_mode not in {"single", "range"}:
        flash("Невірний режим дати", "danger")
        return redirect(url_for("pass_requests"))
    if not visit_date_from:
        flash("Вкажіть дату ВІД", "danger")
        return redirect(url_for("pass_requests"))
    if date_mode == "single":
        visit_date_to = visit_date_from
    if date_mode == "range" and (not visit_date_to or visit_date_to < visit_date_from):
        flash("Для діапазону вкажіть коректну дату ДО", "danger")
        return redirect(url_for("pass_requests"))

    operator_telegram_id, operator_name, operator_role = get_current_operator_identity()
    request_group_id = str(uuid.uuid4())

    conn = get_db_connection()
    cur = conn.cursor()
    try:
        ensure_pass_requests_audit_columns()
        for full_name in names:
            cur.execute(
                """
                INSERT INTO logistics_pass_requests (
                    request_group_id,
                    requester_telegram_id,
                    requester_name,
                    requester_username,
                    pass_type,
                    vehicle_plate,
                    visitor_full_name,
                    date_mode,
                    visit_date_from,
                    visit_date_to,
                    visit_date,
                    status
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, 'new')
                """,
                (
                    request_group_id,
                    operator_telegram_id,
                    operator_name,
                    operator_role,
                    pass_type,
                    vehicle_plate if pass_type == "vehicle" else None,
                    full_name,
                    date_mode,
                    visit_date_from,
                    visit_date_to,
                    visit_date_from,
                ),
            )
        conn.commit()
        flash(f"Заявку створено. ID групи: {request_group_id}", "success")
    except Exception as e:
        conn.rollback()
        flash(f"Помилка створення заявки: {e}", "danger")
    finally:
        cur.close()
        conn.close()

    return redirect(url_for("pass_requests"))


@app.route("/pass_requests/clone", methods=["POST"])
def pass_request_clone():
    if not is_logged_in() or not is_pass_operator():
        return redirect(url_for("login"))

    source_group_id = request.form.get("source_group_id", "").strip()
    date_mode = request.form.get("date_mode", "single").strip()
    visit_date_from = _parse_date(request.form.get("visit_date_from", "").strip())
    visit_date_to = _parse_date(request.form.get("visit_date_to", "").strip())

    if not source_group_id:
        flash("Не вказано ID групи для копіювання", "danger")
        return redirect(url_for("pass_requests"))
    if not visit_date_from:
        flash("Вкажіть дату ВІД", "danger")
        return redirect(url_for("pass_requests"))
    if date_mode == "single":
        visit_date_to = visit_date_from
    if date_mode == "range" and (not visit_date_to or visit_date_to < visit_date_from):
        flash("Для діапазону вкажіть коректну дату ДО", "danger")
        return redirect(url_for("pass_requests"))

    operator_telegram_id, operator_name, operator_role = get_current_operator_identity()
    new_group_id = str(uuid.uuid4())

    conn = get_db_connection()
    cur = conn.cursor()
    try:
        ensure_pass_requests_audit_columns()
        source_rows = _get_group_rows(cur, source_group_id)
        if not source_rows:
            flash("Групу для копіювання не знайдено", "danger")
            return redirect(url_for("pass_requests"))

        pass_type = source_rows[0][2]
        vehicle_plate = source_rows[0][3]
        names = [r[4] for r in source_rows if r[4]]
        if not names:
            flash("У вихідній групі немає осіб", "danger")
            return redirect(url_for("pass_requests"))

        for full_name in names:
            cur.execute(
                """
                INSERT INTO logistics_pass_requests (
                    request_group_id,
                    requester_telegram_id,
                    requester_name,
                    requester_username,
                    pass_type,
                    vehicle_plate,
                    visitor_full_name,
                    date_mode,
                    visit_date_from,
                    visit_date_to,
                    visit_date,
                    status
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, 'new')
                """,
                (
                    new_group_id,
                    operator_telegram_id,
                    operator_name,
                    operator_role,
                    pass_type,
                    vehicle_plate if pass_type == "vehicle" else None,
                    full_name,
                    date_mode,
                    visit_date_from,
                    visit_date_to,
                    visit_date_from,
                ),
            )
        conn.commit()
        flash(f"Копію заявки створено. Нова група: {new_group_id}", "success")
    except Exception as e:
        conn.rollback()
        flash(f"Помилка копіювання заявки: {e}", "danger")
    finally:
        cur.close()
        conn.close()

    return redirect(url_for("pass_requests"))


@app.route("/pass_requests/action", methods=["POST"])
def pass_request_action():
    if not is_logged_in():
        return redirect(url_for("login"))
    if not is_pass_operator():
        flash("Недостатньо прав для цієї дії", "danger")
        return redirect(url_for("pass_requests"))

    action = request.form.get("action", "").strip()
    request_id = request.form.get("request_id", "").strip()
    request_group_id = request.form.get("request_group_id", "").strip()
    target_email = request.form.get("target_email", "").strip()
    cancel_reason = request.form.get("cancel_reason", "").strip()
    if not target_email:
        target_email = PASS_REQUEST_DEFAULT_EMAIL

    if not request_group_id and not request_id.isdigit():
        flash("Невірний ID заявки", "danger")
        return redirect(url_for("pass_requests"))

    conn = get_db_connection()
    cur = conn.cursor()
    try:
        ensure_pass_requests_audit_columns()
        operator_telegram_id, operator_name, operator_role = get_current_operator_identity()

        if not request_group_id:
            request_group_id = _resolve_group_id(cur, int(request_id))

        if not request_group_id:
            flash("Заявку не знайдено", "danger")
            return redirect(url_for("pass_requests"))

        group_rows = _get_group_rows(cur, request_group_id)
        if not group_rows:
            flash("Групу заявки не знайдено", "danger")
            return redirect(url_for("pass_requests"))

        first_row = group_rows[0]
        first_id = first_row[0]
        pass_type = first_row[2]
        vehicle_plate = first_row[3]
        date_mode = first_row[5]
        visit_date = first_row[6]
        visit_date_from = first_row[7]
        visit_date_to = first_row[8]
        requester_telegram_id = first_row[10]
        visitor_names = [r[4] for r in group_rows if r[4]]

        statuses = {r[9] for r in group_rows}
        current_status = statuses.pop() if len(statuses) == 1 else "mixed"

        if current_status != "new":
            flash(f"Група {request_group_id} вже має статус '{PASS_STATUS_LABELS.get(current_status, current_status)}' і недоступна для дій", "warning")
            return redirect(url_for("pass_requests"))

        if date_mode == "range":
            visit_date_text = f"{_format_pass_date(visit_date_from)} — {_format_pass_date(visit_date_to)}"
        else:
            visit_date_text = _format_pass_date(visit_date_from or visit_date)

        if action == "cancel":
            if not cancel_reason:
                flash("Для скасування заявки вкажіть причину", "danger")
                return redirect(url_for("pass_requests"))

            cur.execute(
                """
                UPDATE logistics_pass_requests
                SET status = 'cancelled',
                    processed_by_telegram_id = %s,
                    processed_by_name = %s,
                    processed_by_role = %s,
                    processed_at = NOW(),
                    cancel_reason = %s
                WHERE COALESCE(NULLIF(request_group_id, ''), id::text) = %s
                """,
                (operator_telegram_id, operator_name, operator_role, cancel_reason, request_group_id),
            )
            conn.commit()
            notify_requester_status_change(
                requester_telegram_id=requester_telegram_id,
                request_id=int(first_id),
                status_code="cancelled",
                visitor_name=", ".join(visitor_names) or "—",
                vehicle_plate=(vehicle_plate if pass_type == "vehicle" else "—"),
                visit_date_text=visit_date_text,
                processed_by=f"{operator_name} ({operator_role or 'роль не вказана'})",
                cancel_reason=cancel_reason,
            )
            flash(f"Групу {request_group_id} скасовано", "warning")
            return redirect(url_for("pass_requests"))

        if action == "forward":
            if not target_email:
                flash("Вкажіть email або задайте PASS_REQUEST_DEFAULT_EMAIL у .env", "danger")
                return redirect(url_for("pass_requests"))

            send_pass_request_email(
                to_email=target_email,
                visitor_names=visitor_names,
                vehicle_plate=(vehicle_plate if pass_type == "vehicle" else "—"),
                visit_date_text=visit_date_text,
            )

            if current_status == "new":
                cur.execute(
                    """
                    UPDATE logistics_pass_requests
                    SET status = 'forwarded',
                        processed_by_telegram_id = %s,
                        processed_by_name = %s,
                        processed_by_role = %s,
                        processed_at = NOW(),
                        cancel_reason = NULL
                    WHERE COALESCE(NULLIF(request_group_id, ''), id::text) = %s
                    """,
                    (operator_telegram_id, operator_name, operator_role, request_group_id),
                )
                conn.commit()
            notify_requester_status_change(
                requester_telegram_id=requester_telegram_id,
                request_id=int(first_id),
                status_code="forwarded",
                visitor_name=", ".join(visitor_names) or "—",
                vehicle_plate=(vehicle_plate if pass_type == "vehicle" else "—"),
                visit_date_text=visit_date_text,
                processed_by=f"{operator_name} ({operator_role or 'роль не вказана'})",
            )
            flash(f"Групу {request_group_id} передано на пошту {target_email}", "success")
            return redirect(url_for("pass_requests"))

        flash("Невідома дія", "danger")
        return redirect(url_for("pass_requests"))
    except smtplib.SMTPAuthenticationError:
        conn.rollback()
        flash("SMTP 535: невірний логін/пароль або пошта заборонила вхід сторонньому застосунку", "danger")
        return redirect(url_for("pass_requests"))
    except Exception as e:
        conn.rollback()
        flash(f"Помилка обробки заявки: {e}", "danger")
        return redirect(url_for("pass_requests"))
    finally:
        cur.close()
        conn.close()

# ---------------- RUN ----------------

if __name__ == "__main__":
    app.run(
        host="127.0.0.1",
        port=8000,
        debug=False
    )