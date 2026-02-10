from flask import (
    Flask, render_template, request,
    redirect, url_for, session, flash
)
import psycopg2
import requests
import random
import os
import json
from datetime import datetime
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

UPLOAD_DIR = os.path.join(os.path.dirname(__file__), "uploads")
os.makedirs(UPLOAD_DIR, exist_ok=True)

# ---------------- HELPERS ----------------

def get_db_connection():
    return psycopg2.connect(**PG_CONN)

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

@app.context_processor
def inject_counts():
    return {
        "pending_requests_count": get_pending_requests_count()
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

        # Перевірка в базі: тільки admin
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("""
            SELECT telegram_id
            FROM database_app_userdatatelegram
            WHERE phone_number = %s AND username = 'admin'
            LIMIT 1
        """, (phone,))
        row = cur.fetchone()
        cur.close(); conn.close()

        if not row:
            flash("Вхід дозволено лише для admin!", "danger")
            return redirect(url_for("login"))

        telegram_id = row[0]
        code = random.randint(100000, 999999)
        session["login_code"] = str(code)
        session["phone"] = phone
        session["admin_telegram_id"] = telegram_id  # Зберігаємо id адміна

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

    query += " ORDER BY name NULLS LAST"

    cur.execute(query, params)
    users = cur.fetchall()

    cur.close()
    conn.close()

    admin_telegram_id = session.get("admin_telegram_id")

    return render_template(
        "index.html",
        users=users,
        search_name=search_name,
        search_id=search_id,
        search_role=search_role,
        roles=roles,
        admin_telegram_id=admin_telegram_id
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
        "менеджер", "директор", "збиральник", "виробництво",
        "логіст", "водій", "бухгалтер", "відвідувач"
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
    if not session.get("is_admin"):
        return redirect(url_for("login"))

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

        if selected_user_ids:
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


# ---------------- RUN ----------------

if __name__ == "__main__":
    app.run(
        host="127.0.0.1",
        port=8000,
        debug=False
    )