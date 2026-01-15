from flask import (
    Flask, render_template, request,
    redirect, url_for, session, flash
)
import psycopg2
import requests
import random
import os
from dotenv import load_dotenv
# ---------------- CONFIG ----------------

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

# ---------------- HELPERS ----------------

def get_db_connection():
    return psycopg2.connect(**PG_CONN)

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

def send_telegram_message(chat_id, text, reply_markup=None):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    try:
        payload = {
            "chat_id": int(chat_id),
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
        username = request.form.get("username", "").strip()

        if username != "admin":
            flash("Доступ дозволено лише адміну", "danger")
            return redirect(url_for("login"))

        code = random.randint(100000, 999999)
        session["login_code"] = str(code)
        session["username"] = "admin"

        telegram_id = get_admin_telegram_id()
        if not telegram_id:
            flash("Не знайдено Telegram ID адміністратора", "danger")
            return redirect(url_for("login"))

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
            if remember:
                session.permanent = True  # Запам'ятати сесію
            flash("Вхід дозволено", "success")
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
    if not session.get("is_admin"):
        return redirect(url_for("login"))

    search_name = request.args.get("search_name", "").strip()
    search_id = request.args.get("search_id", "").strip()

    conn = get_db_connection()
    cur = conn.cursor()

    query = """
        SELECT telegram_id, name, username
        FROM database_app_userdatatelegram
        WHERE 1=1
    """
    params = []

    if search_name:
        query += " AND name ILIKE %s"
        params.append(f"%{search_name}%")

    if search_id:
        query += " AND CAST(telegram_id AS TEXT) ILIKE %s"
        params.append(f"%{search_id}%")

    query += " ORDER BY name NULLS LAST"

    cur.execute(query, params)
    users = cur.fetchall()
    cur.close()
    conn.close()

    return render_template(
        "index.html",
        users=users,
        search_name=search_name,
        search_id=search_id
    )


@app.route("/user_action", methods=["POST"])
def user_action():
    if not session.get("is_admin"):
        return redirect(url_for("login"))

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

        cur.execute("""
            UPDATE database_app_userdatatelegram
            SET name = %s, username = %s
            WHERE telegram_id = %s
        """, (name, role, telegram_id))
        conn.commit()

        send_telegram_message(
            telegram_id,
            f"✏️ <b>Ваш профіль оновлено</b>\n\n"
            f"👤 Імʼя: <b>{name}</b>\n"
            f"🛡 Роль: <b>{role}</b>"
        )
        flash("Користувача оновлено", "success")

    # ---------- DELETE ----------
    elif action == "delete":
        # Використовуємо ANY з кастом до bigint[]
        cur.execute("""
            DELETE FROM database_app_userdatatelegram
            WHERE telegram_id = ANY(%s::bigint[])
        """, (selected_users,))
        conn.commit()

        for uid in selected_users:
            send_telegram_message(
                uid,
                "⛔ <b>Ваш доступ до системи було видалено</b>\n"
                "Якщо це помилка — зверніться до адміністратора."
            )
        flash(f"Видалено користувачів: {len(selected_users)}", "success")
    else:
        flash("Невідома дія", "danger")

    cur.close()
    conn.close()
    return redirect(url_for("index"))


# ---------------- REGISTRATION ----------------

@app.route("/registration_requests")
def registration_requests():
    if not session.get("is_admin"):
        return redirect(url_for("login"))

    conn = get_db_connection()
    cur = conn.cursor()

    cur.execute("""
        SELECT id, telegram_id, first_name, last_name,
               position, phone_number, date_submitted
        FROM registration_requests
        WHERE status = 'pending'
        ORDER BY date_submitted
    """)

    requests_list = cur.fetchall()
    cur.close()
    conn.close()

    roles = [
        "admin", "adminpre", "конструктор", "замірник",
        "менеджер", "директор", "user"
    ]

    return render_template(
        "registration_requests.html",
        requests_list=requests_list,
        roles=roles
    )


@app.route("/process_registration", methods=["POST"])
def process_registration():
    if not session.get("is_admin"):
        return redirect(url_for("login"))

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
            # Вставка з авто датою
            cur.execute("""
                INSERT INTO database_app_userdatatelegram
                (telegram_id, name, username, phone_number, date_registered)
                VALUES (%s, %s, %s, %s, NOW())
            """, (telegram_id, name, role, phone))

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


# ---------------- RUN ----------------

if __name__ == "__main__":
    app.run(
        host="127.0.0.1",
        port=8000,
        debug=False
    )