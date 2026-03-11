import os
import time
import random
import psycopg2
import requests
from flask import Flask, request, jsonify, session, render_template, redirect, send_from_directory
from werkzeug.utils import secure_filename
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__, template_folder="templates", static_folder="static")
app.secret_key = os.getenv("SECRET_KEY", "CHANGE_ME_SECRET_KEY")

UPLOAD_FOLDER = os.path.join(os.path.dirname(__file__), 'uploads')
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif'}
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

CODES = {}
CODE_TTL = 300

def get_db():
    return psycopg2.connect(
        host=os.getenv("PG_HOST"),
        port=os.getenv("PG_PORT"),
        dbname=os.getenv("PG_DBNAME"),
        user=os.getenv("PG_USER"),
        password=os.getenv("PG_PASSWORD"),
    )

def ensure_hub_tables():
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS hub_user_profiles (
                    user_id BIGINT PRIMARY KEY,
                    avatar_path TEXT,
                    updated_at TIMESTAMP DEFAULT NOW()
                )
                """
            )
            conn.commit()

ensure_hub_tables()

def normalize_phone(phone):
    digits = "".join([c for c in str(phone) if c.isdigit()])
    if digits.startswith("380") and len(digits) == 12:
        return "+" + digits
    if digits.startswith("0") and len(digits) == 10:
        return "+38" + digits
    return ""

def get_user_by_phone(phone):
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT u.id, u.telegram_id, u.name, u.phone_number, u.username, p.avatar_path
                FROM public.database_app_userdatatelegram u
                LEFT JOIN hub_user_profiles p ON p.user_id = u.id
                WHERE u.phone_number=%s
                LIMIT 1
                """,
                (phone,)
            )
            row = cur.fetchone()
            if not row:
                return None
            return {
                "id": row[0], "telegram_id": row[1], "name": row[2],
                "phone_number": row[3], "username": row[4],
                "role": "admin" if (row[4] or "").lower() == "admin" else "user",
                "avatar_path": row[5]
            }

def get_user_by_id(user_id):
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT u.id, u.telegram_id, u.name, u.phone_number, u.username, p.avatar_path
                FROM public.database_app_userdatatelegram u
                LEFT JOIN hub_user_profiles p ON p.user_id = u.id
                WHERE u.id=%s
                LIMIT 1
                """,
                (user_id,)
            )
            row = cur.fetchone()
            if not row:
                return None
            return {
                "id": row[0], "telegram_id": row[1], "name": row[2],
                "phone_number": row[3], "username": row[4],
                "role": "admin" if (row[4] or "").lower() == "admin" else "user",
                "avatar_path": row[5]
            }

def send_telegram_code(chat_id, code):
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    r = requests.post(url, json={"chat_id": chat_id, "text": f"Ваш код входу: {code}\nДійсний 5 хвилин."}, timeout=10)
    r.raise_for_status()

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

# ─────────────────────────────────────────
# СТОРІНКИ
# ─────────────────────────────────────────
@app.route("/", methods=["GET"])
def main():
    if not session.get("user_id"):
        return redirect("/login")
    return render_template("main.html")

@app.route("/login", methods=["GET"])
def login():
    if session.get("user_id"):
        return redirect("/")
    return render_template("index.html")

# ─────────────────────────────────────────
# АВТОРИЗАЦІЯ
# ─────────────────────────────────────────
@app.route("/api/auth/request-code", methods=["POST"])
def request_code():
    data = request.get_json()
    phone = normalize_phone(data.get("phone_number", ""))
    if not phone:
        return jsonify({"ok": False, "error": "Невірний формат телефону. Використовуйте +380XXXXXXXXX"}), 400
    user = get_user_by_phone(phone)
    if not user:
        return jsonify({"ok": False, "error": "Користувача не знайдено"}), 404
    if not user["telegram_id"]:
        return jsonify({"ok": False, "error": "Немає telegram_id"}), 400
    code = str(random.randint(100000, 999999))
    CODES[phone] = {"code": code, "expires_at": time.time() + CODE_TTL, "user_id": user["id"]}
    try:
        send_telegram_code(user["telegram_id"], code)
    except Exception as e:
        return jsonify({"ok": False, "error": f"Не вдалося надіслати код: {e}"}), 500
    return jsonify({"ok": True})

@app.route("/api/auth/verify", methods=["POST"])
def verify():
    data = request.get_json()
    phone = normalize_phone(data.get("phone_number", ""))
    if not phone:
        return jsonify({"ok": False, "error": "Невірний формат телефону. Використовуйте +380XXXXXXXXX"}), 400
    code = str(data.get("code", "")).strip()
    record = CODES.get(phone)
    if not record or time.time() > record["expires_at"]:
        return jsonify({"ok": False, "error": "Код протермінований або не запрошено"}), 400
    if code != record["code"]:
        return jsonify({"ok": False, "error": "Невірний код"}), 400
    user = get_user_by_id(record["user_id"])
    if not user:
        return jsonify({"ok": False, "error": "Користувача не знайдено"}), 404
    session["user_id"] = user["id"]
    session["role"] = user["role"]
    CODES.pop(phone, None)
    return jsonify({"ok": True, "user": user})

@app.route("/api/me", methods=["GET"])
def me():
    user_id = session.get("user_id")
    if not user_id:
        return jsonify({"ok": False}), 401
    user = get_user_by_id(user_id)
    if not user:
        session.clear()
        return jsonify({"ok": False}), 401
    return jsonify({"ok": True, "user": user})

@app.route("/api/logout", methods=["POST"])
def logout():
    session.clear()
    return jsonify({"ok": True})

# ─────────────────────────────────────────
# ПІДРЯДИ
# ─────────────────────────────────────────
@app.route("/api/contracts", methods=["GET"])
def get_contracts():
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT id, title, url, description, image_path, service_type FROM contracts ORDER BY id DESC")
            rows = cur.fetchall()
            contracts = [
                {"id": r[0], "name": r[1], "url": r[2], "description": r[3], "image": r[4], "service_type": r[5]}
                for r in rows
            ]
    return jsonify({"ok": True, "contracts": contracts})

@app.route("/api/contracts", methods=["POST"])
def add_contract():
    if session.get("role") != "admin":
        return jsonify({"ok": False, "error": "Доступ заборонено"}), 403
    name = request.form.get("name", "").strip()
    url = request.form.get("url", "").strip()
    description = request.form.get("description", "").strip()
    service_type = request.form.get("service_type", "site").strip()
    image = None
    file = request.files.get("image")
    if file and allowed_file(file.filename):
        filename = secure_filename(file.filename)
        file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
        image = filename
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO contracts (title, url, description, image_path, service_type) VALUES (%s, %s, %s, %s, %s) RETURNING id",
                (name, url, description, image, service_type)
            )
            contract_id = cur.fetchone()[0]
            conn.commit()
    return jsonify({"ok": True, "id": contract_id})

@app.route("/api/contracts/<int:contract_id>", methods=["PUT"])
def edit_contract(contract_id):
    if session.get("role") != "admin":
        return jsonify({"ok": False, "error": "Доступ заборонено"}), 403
    name = request.form.get("name", "").strip()
    url = request.form.get("url", "").strip()
    description = request.form.get("description", "").strip()
    service_type = request.form.get("service_type", "site").strip()
    image = None
    file = request.files.get("image")
    if file and allowed_file(file.filename):
        filename = secure_filename(file.filename)
        file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
        image = filename
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE contracts SET title=%s, url=%s, description=%s, image_path=COALESCE(%s, image_path), service_type=%s WHERE id=%s",
                (name, url, description, image, service_type, contract_id)
            )
            conn.commit()
    return jsonify({"ok": True})

@app.route("/api/contracts/<int:contract_id>", methods=["DELETE"])
def delete_contract(contract_id):
    if session.get("role") != "admin":
        return jsonify({"ok": False, "error": "Доступ заборонено"}), 403
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM contracts WHERE id=%s", (contract_id,))
            conn.commit()
    return jsonify({"ok": True})

@app.route("/uploads/<filename>")
def uploaded_file(filename):
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename)

@app.route('/favicon.ico')
def favicon():
    return send_from_directory(
        os.path.join(app.static_folder, 'branding'),
        'hub-favicon.png',
        mimetype='image/png'
    )


@app.route('/branding-logo')
def branding_logo():
    branding_dir = os.path.join(app.static_folder, 'branding')
    for name in ('hub-logo.png', 'hub-logo.PNG', 'hub-logo.jpg', 'hub-logo.jpeg', 'hub-logo.webp'):
        full_path = os.path.join(branding_dir, name)
        if os.path.exists(full_path):
            return send_from_directory(branding_dir, name)
    return ('', 404)

@app.route("/api/contracts/search", methods=["GET"])
def search_contracts():
    q = request.args.get("q", "").strip()
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT title FROM contracts WHERE title ILIKE %s LIMIT 5", (f"%{q}%",))
            rows = cur.fetchall()
            names = [r[0] for r in rows]
    return jsonify({"ok": True, "names": names})

@app.route("/api/contracts/<int:contract_id>/users", methods=["GET"])
def contract_users(contract_id):
    if session.get("role") != "admin":
        return jsonify({"ok": False, "error": "Доступ заборонено"}), 403
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT u.id, u.name, u.phone_number
                FROM user_services us
                JOIN public.database_app_userdatatelegram u ON u.id = us.user_id
                WHERE us.contract_id = %s
                ORDER BY u.name
                """,
                (contract_id,)
            )
            rows = cur.fetchall()
            users = [
                {"id": r[0], "name": r[1], "phone_number": r[2]}
                for r in rows
            ]
    return jsonify({"ok": True, "users": users, "count": len(users)})

# ─────────────────────────────────────────
# АДМІН СТОРІНКА
# ─────────────────────────────────────────
@app.route("/admin", methods=["GET"])
def admin():
    if session.get("role") != "admin":
        return redirect("/")
    return render_template("admin.html")

# ─────────────────────────────────────────
# КОРИСТУВАЧІ
# ─────────────────────────────────────────
@app.route("/api/users", methods=["GET"])
def get_users():
    if session.get("role") != "admin":
        return jsonify({"ok": False, "error": "Доступ заборонено"}), 403
    search = request.args.get("search", "").strip()
    sort = request.args.get("sort", "").strip()
    with get_db() as conn:
        with conn.cursor() as cur:
            query = "SELECT id, name, phone_number, username FROM public.database_app_userdatatelegram WHERE 1=1"
            params = []
            if search:
                query += " AND name ILIKE %s"
                params.append(f"%{search}%")
            if sort == "admin":
                query += " AND username ILIKE %s"
                params.append("admin")
            elif sort == "user":
                query += " AND (username NOT ILIKE %s OR username IS NULL)"
                params.append("admin")
            query += " ORDER BY name"
            cur.execute(query, params)
            rows = cur.fetchall()
            users = [
                {
                    "id": r[0],
                    "name": r[1],
                    "phone_number": r[2],
                    "username": r[3],
                    "role": "admin" if (r[3] or "").lower() == "admin" else "user"
                }
                for r in rows
            ]
    return jsonify({"ok": True, "users": users})

# ─────────────────────────────────────────
# USER SERVICES (логін/пароль до сервісів)
# ─────────────────────────────────────────
@app.route("/api/user-services", methods=["GET"])
def get_user_services():
    if session.get("role") != "admin":
        return jsonify({"ok": False, "error": "Доступ заборонено"}), 403
    user_id = request.args.get("user_id")
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT us.id, us.user_id, us.contract_id, us.login, us.password,
                       c.title, u.name
                FROM user_services us
                JOIN contracts c ON c.id = us.contract_id
                JOIN public.database_app_userdatatelegram u ON u.id = us.user_id
                WHERE us.user_id = %s
            """, (user_id,))
            rows = cur.fetchall()
            services = [
                {
                    "id": r[0], "user_id": r[1], "contract_id": r[2],
                    "login": r[3], "password": r[4],
                    "contract_title": r[5], "user_name": r[6]
                }
                for r in rows
            ]
    return jsonify({"ok": True, "services": services})

@app.route("/api/user-services", methods=["POST"])
def add_user_service():
    if session.get("role") != "admin":
        return jsonify({"ok": False, "error": "Доступ заборонено"}), 403
    data = request.get_json()
    user_id = data.get("user_id")
    contract_id = data.get("contract_id")
    login = data.get("login", "")
    password = data.get("password", "")
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO user_services (user_id, contract_id, login, password)
                VALUES (%s, %s, %s, %s)
                ON CONFLICT (user_id, contract_id) DO UPDATE
                SET login = EXCLUDED.login, password = EXCLUDED.password
                RETURNING id
            """, (user_id, contract_id, login, password))
            service_id = cur.fetchone()[0]
            conn.commit()
    return jsonify({"ok": True, "id": service_id})

@app.route("/api/user-services/<int:service_id>", methods=["DELETE"])
def delete_user_service(service_id):
    if session.get("role") != "admin":
        return jsonify({"ok": False, "error": "Доступ заборонено"}), 403
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM user_services WHERE id=%s", (service_id,))
            conn.commit()
    return jsonify({"ok": True})

# ─── МОЇ ДАНІ ДО СЕРВІСУ (для звичайного юзера) ───
@app.route("/api/my-service/<int:contract_id>", methods=["GET"])
def my_service(contract_id):
    user_id = session.get("user_id")
    if not user_id:
        return jsonify({"ok": False}), 401
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT login, password FROM user_services
                WHERE user_id=%s AND contract_id=%s
            """, (user_id, contract_id))
            row = cur.fetchone()
            if not row:
                return jsonify({"ok": False, "error": "Немає даних"}), 404
    return jsonify({"ok": True, "login": row[0], "password": row[1]})

@app.route("/profile", methods=["GET"])
def profile():
    if not session.get("user_id"):
        return redirect("/login")
    return render_template("profile.html")

@app.route("/workers", methods=["GET"])
def workers_page():
    if not session.get("user_id"):
        return redirect("/login")
    return render_template("workers.html")

@app.route("/api/profile", methods=["PUT"])
def update_profile():
    user_id = session.get("user_id")
    if not user_id:
        return jsonify({"ok": False}), 401
    data = request.get_json()
    name = data.get("name", "").strip()
    if not name:
        return jsonify({"ok": False, "error": "Ім'я не може бути порожнім"}), 400
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE public.database_app_userdatatelegram SET name=%s WHERE id=%s",
                (name, user_id)
            )
            conn.commit()
    return jsonify({"ok": True})

@app.route("/api/profile/avatar", methods=["PUT"])
def update_profile_avatar():
    user_id = session.get("user_id")
    if not user_id:
        return jsonify({"ok": False}), 401
    file = request.files.get("avatar")
    if not file or not file.filename:
        return jsonify({"ok": False, "error": "Файл не обрано"}), 400
    safe_name = secure_filename(file.filename or "")
    ext = ""
    if '.' in safe_name:
        ext = safe_name.rsplit('.', 1)[1].lower()

    if ext not in ALLOWED_EXTENSIONS:
        mime_to_ext = {
            "image/jpeg": "jpg",
            "image/jpg": "jpg",
            "image/png": "png",
            "image/gif": "gif",
            "image/webp": "jpg",
        }
        ext = mime_to_ext.get((file.mimetype or "").lower(), "")

    if ext not in ALLOWED_EXTENSIONS:
        return jsonify({"ok": False, "error": "Невірний формат файлу. Дозволено: PNG/JPG/JPEG/GIF"}), 400
    filename = f"avatar_{user_id}_{int(time.time())}.{ext}"
    file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))

    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO hub_user_profiles (user_id, avatar_path, updated_at)
                VALUES (%s, %s, NOW())
                ON CONFLICT (user_id) DO UPDATE
                SET avatar_path = EXCLUDED.avatar_path, updated_at = NOW()
                """,
                (user_id, filename)
            )
            conn.commit()

    return jsonify({"ok": True, "avatar_path": filename})

@app.route("/api/workers", methods=["GET"])
def get_workers():
    if not session.get("user_id"):
        return jsonify({"ok": False}), 401
    search = request.args.get("search", "").strip()
    position = request.args.get("position", "").strip()

    with get_db() as conn:
        with conn.cursor() as cur:
            query = """
                SELECT u.id, u.name, u.phone_number, u.username, p.avatar_path
                FROM public.database_app_userdatatelegram u
                LEFT JOIN hub_user_profiles p ON p.user_id = u.id
                WHERE 1=1
            """
            params = []

            if search:
                query += """
                    AND (
                        u.name ILIKE %s
                        OR u.phone_number ILIKE %s
                        OR u.username ILIKE %s
                    )
                """
                like = f"%{search}%"
                params.extend([like, like, like])

            if position:
                query += " AND u.username ILIKE %s"
                params.append(f"%{position}%")

            query += " ORDER BY u.name"
            cur.execute(
                query,
                params
            )
            rows = cur.fetchall()
            workers = [
                {
                    "id": r[0],
                    "name": r[1],
                    "phone_number": r[2],
                    "username": r[3],
                    "position": ("@" + r[3]) if r[3] else "Не вказано",
                    "is_admin": (r[3] or "").lower() == "admin",
                    "avatar_path": r[4],
                }
                for r in rows
            ]
    return jsonify({"ok": True, "workers": workers})

if __name__ == "__main__":
    app.run(debug=True, port=1234)