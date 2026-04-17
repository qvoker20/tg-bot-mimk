import os
import time
import random
import hmac
import psycopg2
import requests
from datetime import timedelta
from collections import defaultdict, deque
from threading import Lock
from flask import Flask, request, jsonify, session, render_template, redirect, send_from_directory
from werkzeug.utils import secure_filename
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__, template_folder="templates", static_folder="static")
app.secret_key = os.getenv("SECRET_KEY", "CHANGE_ME_SECRET_KEY")
app.config["SESSION_COOKIE_HTTPONLY"] = True
app.config["SESSION_COOKIE_SAMESITE"] = os.getenv("SESSION_COOKIE_SAMESITE", "Lax")
app.config["SESSION_COOKIE_SECURE"] = os.getenv("SESSION_COOKIE_SECURE", "0") == "1"
app.config["SESSION_REFRESH_EACH_REQUEST"] = True
app.config["PERMANENT_SESSION_LIFETIME"] = timedelta(days=int(os.getenv("SESSION_LIFETIME_DAYS", "14")))
app.config["MAX_CONTENT_LENGTH"] = int(os.getenv("MAX_CONTENT_LENGTH_MB", "8")) * 1024 * 1024

UPLOAD_FOLDER = os.path.join(os.path.dirname(__file__), 'uploads')
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif'}
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

CODES = {}
CODE_TTL = 300
HUB_PUBLIC_URL = os.getenv("HUB_PUBLIC_URL", "https://hub.mim-k.website")
ADMIN_ROLES = {"admin", "adminpre"}

RATE_LIMIT_WINDOW_SECONDS = int(os.getenv("RATE_LIMIT_WINDOW_SECONDS", "60"))
RATE_LIMIT_MAX_REQUESTS = int(os.getenv("RATE_LIMIT_MAX_REQUESTS", "120"))
AUTH_REQUEST_WINDOW_SECONDS = int(os.getenv("AUTH_REQUEST_WINDOW_SECONDS", "300"))
AUTH_REQUEST_CODE_LIMIT = int(os.getenv("AUTH_REQUEST_CODE_LIMIT", "5"))
AUTH_VERIFY_LIMIT = int(os.getenv("AUTH_VERIFY_LIMIT", "10"))

_request_limits = defaultdict(deque)
_auth_limits = defaultdict(deque)
_rate_lock = Lock()


def is_admin_role(value):
    return (value or "").strip().lower() in ADMIN_ROLES


def _client_ip():
    forwarded_for = request.headers.get("X-Forwarded-For", "").split(",")[0].strip()
    return forwarded_for or request.remote_addr or "unknown"


def _rate_limit_hit(storage, key, max_requests, window_seconds):
    now = time.time()
    with _rate_lock:
        bucket = storage[key]
        while bucket and now - bucket[0] > window_seconds:
            bucket.popleft()

        if len(bucket) >= max_requests:
            retry_after = max(1, int(window_seconds - (now - bucket[0])))
            return True, retry_after

        bucket.append(now)
        return False, 0


@app.before_request
def apply_security_guards():
    if session.get("user_id"):
        session.permanent = True

    if request.path.startswith("/static/"):
        return None

    if request.path.startswith("/api/"):
        route_key = request.endpoint or request.path
        blocked, retry_after = _rate_limit_hit(
            _request_limits,
            f"{_client_ip()}:{route_key}",
            RATE_LIMIT_MAX_REQUESTS,
            RATE_LIMIT_WINDOW_SECONDS,
        )
        if blocked:
            return jsonify({
                "ok": False,
                "error": "Забагато запитів. Спробуйте пізніше.",
                "retry_after": retry_after,
            }), 429

    return None


@app.after_request
def set_security_headers(response):
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["Permissions-Policy"] = "geolocation=(), microphone=(), camera=()"
    response.headers["Content-Security-Policy"] = (
        "default-src 'self'; "
        "img-src 'self' data: https:; "
        "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
        "font-src 'self' https://fonts.gstatic.com; "
        "script-src 'self'; "
        "connect-src 'self'; "
        "frame-ancestors 'none';"
    )
    if request.is_secure or app.config.get("SESSION_COOKIE_SECURE"):
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    return response

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
                "role": "admin" if is_admin_role(row[4]) else "user",
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
                "role": "admin" if is_admin_role(row[4]) else "user",
                "avatar_path": row[5]
            }

def send_telegram_code(chat_id, code):
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    r = requests.post(url, json={"chat_id": chat_id, "text": f"Ваш код входу: {code}\nДійсний 5 хвилин."}, timeout=10)
    r.raise_for_status()


def send_telegram_message(chat_id, text):
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    if not token or not chat_id:
        return False
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    try:
        r = requests.post(
            url,
            json={
                "chat_id": int(chat_id),
                "text": text,
                "parse_mode": "HTML",
                "disable_web_page_preview": True,
            },
            timeout=10,
        )
        r.raise_for_status()
        return True
    except Exception as e:
        app.logger.warning(f"Не вдалося надіслати Telegram повідомлення user={chat_id}: {e}")
        return False


def notify_user_service_connection(user_id, contract_id, updated=False):
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT u.telegram_id, COALESCE(u.name, ''), COALESCE(c.title, '')
                FROM public.database_app_userdatatelegram u
                JOIN contracts c ON c.id = %s
                WHERE u.id = %s
                LIMIT 1
                """,
                (contract_id, user_id),
            )
            row = cur.fetchone()

    if not row:
        return

    telegram_id, full_name, contract_title = row
    if not telegram_id:
        return

    title = "🔄 <b>Доступ до сервісу оновлено</b>" if updated else "✅ <b>Вас підключено до сервісу</b>"
    msg = (
        f"{title}\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        f"👤 <b>Користувач:</b> {full_name or 'Користувач'}\n"
        f"🔐 <b>Сервіс:</b> {contract_title or 'Сервіс'}\n"
        f"🌐 <b>MIM-K HUB:</b> <a href=\"{HUB_PUBLIC_URL}\">Перейти</a>\n\n"
        "Будь ласка, перейдіть на MIM-K HUB та отримайте доступ."
    )
    send_telegram_message(telegram_id, msg)

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

    blocked, retry_after = _rate_limit_hit(
        _auth_limits,
        f"reqcode:{_client_ip()}:{phone}",
        AUTH_REQUEST_CODE_LIMIT,
        AUTH_REQUEST_WINDOW_SECONDS,
    )
    if blocked:
        return jsonify({
            "ok": False,
            "error": "Забагато спроб запиту коду. Спробуйте пізніше.",
            "retry_after": retry_after,
        }), 429

    now = time.time()
    expired_phones = [k for k, v in CODES.items() if now > v.get("expires_at", 0)]
    for item in expired_phones:
        CODES.pop(item, None)

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

    blocked, retry_after = _rate_limit_hit(
        _auth_limits,
        f"verify:{_client_ip()}:{phone}",
        AUTH_VERIFY_LIMIT,
        AUTH_REQUEST_WINDOW_SECONDS,
    )
    if blocked:
        return jsonify({
            "ok": False,
            "error": "Забагато спроб підтвердження коду. Спробуйте пізніше.",
            "retry_after": retry_after,
        }), 429

    code = str(data.get("code", "")).strip()
    record = CODES.get(phone)
    if not record or time.time() > record["expires_at"]:
        return jsonify({"ok": False, "error": "Код протермінований або не запрошено"}), 400
    if not hmac.compare_digest(code, record["code"]):
        return jsonify({"ok": False, "error": "Невірний код"}), 400
    user = get_user_by_id(record["user_id"])
    if not user:
        return jsonify({"ok": False, "error": "Користувача не знайдено"}), 404
    session.clear()
    session["user_id"] = user["id"]
    session["role"] = user["role"]
    session.permanent = True
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
    if not session.get("user_id"):
        return jsonify({"ok": False}), 401
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
    if not is_admin_role(session.get("role")):
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
    if not is_admin_role(session.get("role")):
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
    if not is_admin_role(session.get("role")):
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
    if not is_admin_role(session.get("role")):
        return jsonify({"ok": False, "error": "Доступ заборонено"}), 403
    q = request.args.get("q", "").strip()
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT title FROM contracts WHERE title ILIKE %s LIMIT 5", (f"%{q}%",))
            rows = cur.fetchall()
            names = [r[0] for r in rows]
    return jsonify({"ok": True, "names": names})

@app.route("/api/contracts/<int:contract_id>/users", methods=["GET"])
def contract_users(contract_id):
    if not is_admin_role(session.get("role")):
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
    if not is_admin_role(session.get("role")):
        return redirect("/")
    return render_template("admin.html")

# ─────────────────────────────────────────
# КОРИСТУВАЧІ
# ─────────────────────────────────────────
@app.route("/api/users", methods=["GET"])
def get_users():
    if not is_admin_role(session.get("role")):
        return jsonify({"ok": False, "error": "Доступ заборонено"}), 403
    search = request.args.get("search", "").strip()
    role_filter = request.args.get("role", "").strip()
    sort = request.args.get("sort", "").strip()
    service_id_raw = request.args.get("service_id", "").strip()
    connection_status = request.args.get("connection_status", "all").strip().lower()

    service_id = None
    if service_id_raw:
        try:
            service_id = int(service_id_raw)
        except ValueError:
            return jsonify({"ok": False, "error": "Некоректний service_id"}), 400

    if connection_status not in {"all", "connected", "not_connected"}:
        return jsonify({"ok": False, "error": "Некоректний connection_status"}), 400

    # Backward compatibility for older frontend that sends `sort`.
    if not role_filter and sort:
        role_filter = sort

    with get_db() as conn:
        with conn.cursor() as cur:
            query = """
                SELECT
                    u.id,
                    u.name,
                    u.phone_number,
                    u.username,
                    COUNT(DISTINCT us.id) AS services_count,
                    COALESCE(BOOL_OR(us.contract_id = %s), FALSE) AS has_selected_service,
                    COALESCE(
                        json_agg(DISTINCT c.title) FILTER (WHERE c.title IS NOT NULL),
                        '[]'::json
                    ) AS connected_services
                FROM public.database_app_userdatatelegram u
                LEFT JOIN user_services us ON us.user_id = u.id
                LEFT JOIN contracts c ON c.id = us.contract_id
                WHERE 1=1
            """
            params = [service_id if service_id is not None else -1]

            if search:
                query += " AND name ILIKE %s"
                params.append(f"%{search}%")
            if role_filter:
                normalized_role = role_filter.lstrip("@").strip().lower()
                if normalized_role == "__empty__":
                    query += " AND (username IS NULL OR BTRIM(username) = '')"
                else:
                    query += " AND LOWER(BTRIM(COALESCE(username, ''))) = %s"
                    params.append(normalized_role)

            query += " GROUP BY u.id, u.name, u.phone_number, u.username"

            if service_id is not None:
                if connection_status == "connected":
                    query += " HAVING COALESCE(BOOL_OR(us.contract_id = %s), FALSE)"
                    params.append(service_id)
                elif connection_status == "not_connected":
                    query += " HAVING NOT COALESCE(BOOL_OR(us.contract_id = %s), FALSE)"
                    params.append(service_id)
            else:
                if connection_status == "connected":
                    query += " HAVING COUNT(DISTINCT us.id) > 0"
                elif connection_status == "not_connected":
                    query += " HAVING COUNT(DISTINCT us.id) = 0"

            query += " ORDER BY name"
            cur.execute(query, params)
            rows = cur.fetchall()
            users = [
                {
                    "id": r[0],
                    "name": r[1],
                    "phone_number": r[2],
                    "username": r[3],
                    "position": (r[3] or "").strip().lstrip("@"),
                    "role": (
                        "adminpre"
                        if (r[3] or "").strip().lower() == "adminpre"
                        else ("admin" if (r[3] or "").strip().lower() == "admin" else "user")
                    ),
                    "services_count": int(r[4] or 0),
                    "has_selected_service": bool(r[5]),
                    "connected_services": r[6] or [],
                }
                for r in rows
            ]

    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT DISTINCT BTRIM(username)
                FROM public.database_app_userdatatelegram
                WHERE username IS NOT NULL AND BTRIM(username) <> ''
                ORDER BY BTRIM(username)
                """
            )
            role_rows = cur.fetchall()
            available_roles = [str(r[0]).lstrip("@") for r in role_rows if r and r[0]]

    return jsonify({"ok": True, "users": users, "roles": available_roles})

# ─────────────────────────────────────────
# USER SERVICES (логін/пароль до сервісів)
# ─────────────────────────────────────────
@app.route("/api/user-services", methods=["GET"])
def get_user_services():
    if not is_admin_role(session.get("role")):
        return jsonify({"ok": False, "error": "Доступ заборонено"}), 403
    user_id = request.args.get("user_id")
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT us.id, us.user_id, us.contract_id, us.login,
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
                    "login": r[3],
                    "contract_title": r[4], "user_name": r[5]
                }
                for r in rows
            ]
    return jsonify({"ok": True, "services": services})

@app.route("/api/user-services", methods=["POST"])
def add_user_service():
    if not is_admin_role(session.get("role")):
        return jsonify({"ok": False, "error": "Доступ заборонено"}), 403
    data = request.get_json()
    user_id = data.get("user_id")
    contract_id = data.get("contract_id")
    login = data.get("login", "")
    password = data.get("password", "")

    if not user_id or not contract_id:
        return jsonify({"ok": False, "error": "user_id і contract_id обов'язкові"}), 400

    login = str(login).strip()[:255]
    password = str(password).strip()[:255]

    if not login or not password:
        return jsonify({"ok": False, "error": "Логін і пароль обов'язкові"}), 400

    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO user_services (user_id, contract_id, login, password)
                VALUES (%s, %s, %s, %s)
                ON CONFLICT (user_id, contract_id) DO UPDATE
                SET login = EXCLUDED.login, password = EXCLUDED.password
                RETURNING id, (xmax = 0) AS inserted
            """, (user_id, contract_id, login, password))
            fetched = cur.fetchone()
            service_id = fetched[0]
            inserted = bool(fetched[1])
            conn.commit()

    notify_user_service_connection(user_id, contract_id, updated=not inserted)
    return jsonify({"ok": True, "id": service_id})

@app.route("/api/user-services/<int:service_id>", methods=["DELETE"])
def delete_user_service(service_id):
    if not is_admin_role(session.get("role")):
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
    service_id_raw = request.args.get("service_id", "").strip()
    connection_status = request.args.get("connection_status", "all").strip().lower()

    service_id = None
    if service_id_raw:
        try:
            service_id = int(service_id_raw)
        except ValueError:
            return jsonify({"ok": False, "error": "Некоректний service_id"}), 400

    if connection_status not in {"all", "connected", "not_connected"}:
        return jsonify({"ok": False, "error": "Некоректний connection_status"}), 400

    try:
        with get_db() as conn:
            with conn.cursor() as cur:
                query = """
                    SELECT
                        u.id,
                        u.name,
                        u.phone_number,
                        u.username,
                        p.avatar_path,
                        COALESCE(
                            json_agg(
                                DISTINCT jsonb_build_object(
                                    'id', c.id,
                                    'title', c.title,
                                    'service_type', c.service_type
                                )
                            ) FILTER (WHERE c.id IS NOT NULL),
                            '[]'::json
                        ) AS services,
                        COUNT(DISTINCT us.id) AS services_count,
                        COALESCE(BOOL_OR(us.contract_id = %s), FALSE) AS has_selected_service
                    FROM public.database_app_userdatatelegram u
                    LEFT JOIN hub_user_profiles p ON p.user_id = u.id
                    LEFT JOIN user_services us ON us.user_id = u.id
                    LEFT JOIN contracts c ON c.id = us.contract_id
                    WHERE 1=1
                """
                params = [service_id if service_id is not None else -1]

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

                query += " GROUP BY u.id, u.name, u.phone_number, u.username, p.avatar_path"

                if service_id is not None:
                    if connection_status == "connected":
                        query += " HAVING COALESCE(BOOL_OR(us.contract_id = %s), FALSE)"
                        params.append(service_id)
                    elif connection_status == "not_connected":
                        query += " HAVING NOT COALESCE(BOOL_OR(us.contract_id = %s), FALSE)"
                        params.append(service_id)
                else:
                    if connection_status == "connected":
                        query += " HAVING COUNT(DISTINCT us.id) > 0"
                    elif connection_status == "not_connected":
                        query += " HAVING COUNT(DISTINCT us.id) = 0"

                query += " ORDER BY u.name"
                cur.execute(query, params)
                rows = cur.fetchall()
                workers = [
                    {
                        "id": r[0],
                        "name": r[1],
                        "phone_number": r[2],
                        "username": r[3],
                        "position": ("@" + r[3]) if r[3] else "Не вказано",
                        "is_admin": is_admin_role(r[3]),
                        "avatar_path": r[4],
                        "services": r[5] or [],
                        "services_count": r[6] or 0,
                        "has_selected_service": bool(r[7]),
                    }
                    for r in rows
                ]
        return jsonify({"ok": True, "workers": workers})
    except Exception:
        app.logger.exception("Primary /api/workers query failed. Falling back to basic workers list.")

    try:
        with get_db() as conn:
            with conn.cursor() as cur:
                fallback_query = """
                    SELECT
                        u.id,
                        u.name,
                        u.phone_number,
                        u.username,
                        p.avatar_path
                    FROM public.database_app_userdatatelegram u
                    LEFT JOIN hub_user_profiles p ON p.user_id = u.id
                    WHERE 1=1
                """
                fallback_params = []

                if search:
                    fallback_query += """
                        AND (
                            u.name ILIKE %s
                            OR u.phone_number ILIKE %s
                            OR u.username ILIKE %s
                        )
                    """
                    like = f"%{search}%"
                    fallback_params.extend([like, like, like])

                if position:
                    fallback_query += " AND u.username ILIKE %s"
                    fallback_params.append(f"%{position}%")

                fallback_query += " ORDER BY u.name"
                cur.execute(fallback_query, fallback_params)
                rows = cur.fetchall()
                workers = [
                    {
                        "id": r[0],
                        "name": r[1],
                        "phone_number": r[2],
                        "username": r[3],
                        "position": ("@" + r[3]) if r[3] else "Не вказано",
                        "is_admin": is_admin_role(r[3]),
                        "avatar_path": r[4],
                        "services": [],
                        "services_count": 0,
                        "has_selected_service": False,
                    }
                    for r in rows
                ]
        return jsonify({"ok": True, "workers": workers, "fallback": True})
    except Exception as e:
        app.logger.exception("Fallback /api/workers query also failed.")
        return jsonify({"ok": False, "error": f"Не вдалося завантажити робітників: {e}"}), 500

if __name__ == "__main__":
    app.run(debug=True, port=1234)