from flask import Flask, abort, request
from datetime import datetime
import html
import json
import logging
import os
import re
import threading
import time
from urllib.parse import urljoin, urlparse

from zoneinfo import ZoneInfo

from dotenv import load_dotenv
import psycopg2
import requests

app = Flask(__name__)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
)
logger = logging.getLogger("wiki_webhook")

load_dotenv()

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_WIKI_BOT_TOKEN", "")
BOOKSTACK_WEBHOOK_TOKEN = os.getenv("BOOKSTACK_WEBHOOK_TOKEN", "")
BOOKSTACK_API_TOKEN = os.getenv("BOOKSTACK_API_TOKEN", "")
BOOKSTACK_BASE_URL = os.getenv("BOOKSTACK_BASE_URL", "")
BOOKSTACK_TOKEN_ID = os.getenv("BOOKSTACK_TOKEN_ID", "")
BOOKSTACK_TOKEN_SECRET = os.getenv("BOOKSTACK_TOKEN_SECRET", "")
BS_URL = os.getenv("BS_URL", "")
CORPORATE_BOT_URL = os.getenv("CORPORATE_BOT_URL", "https://t.me/adaptationmimkbot")
TELEGRAM_UPDATE_MODE = os.getenv("TELEGRAM_UPDATE_MODE", "polling").strip().lower()

PG_CONN = {
    "host": os.getenv("PG_HOST"),
    "port": int(os.getenv("PG_PORT", "5432")),
    "dbname": os.getenv("PG_DBNAME"),
    "user": os.getenv("PG_USER"),
    "password": os.getenv("PG_PASSWORD"),
}
WIKI_COMMENT_FALLBACK_BROADCAST = os.getenv("WIKI_COMMENT_FALLBACK_BROADCAST", "0") == "1"


def get_db_connection():
    return psycopg2.connect(**PG_CONN)


def ensure_wiki_tables():
    conn = get_db_connection()
    cur = conn.cursor()
    try:
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS wiki_page_owners (
                page_id BIGINT PRIMARY KEY,
                page_name TEXT,
                page_url TEXT,
                owner_bookstack_id BIGINT,
                owner_name TEXT,
                owner_slug TEXT,
                last_editor_bookstack_id BIGINT,
                last_editor_name TEXT,
                last_event TEXT,
                last_seen_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
            """
        )
        cur.execute("ALTER TABLE wiki_page_owners ADD COLUMN IF NOT EXISTS owner_bookstack_id BIGINT")
        cur.execute("ALTER TABLE wiki_page_owners ADD COLUMN IF NOT EXISTS last_editor_bookstack_id BIGINT")
        cur.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_wiki_page_owners_owner_name
            ON wiki_page_owners(owner_name)
            """
        )
        conn.commit()
    finally:
        cur.close()
        conn.close()


def get_registered_user_ids():
    conn = get_db_connection()
    cur = conn.cursor()
    try:
        cur.execute(
            """
            SELECT DISTINCT telegram_id
            FROM database_app_userdatatelegram
            WHERE telegram_id IS NOT NULL
            """
        )
        return [int(row[0]) for row in cur.fetchall()]
    finally:
        cur.close()
        conn.close()


def broadcast_telegram_message(text):
    if not TELEGRAM_BOT_TOKEN:
        raise RuntimeError("TELEGRAM_WIKI_BOT_TOKEN не налаштований")

    recipients = get_registered_user_ids()
    for chat_id in recipients:
        send_telegram_message_to(chat_id, text)


def send_telegram_message_to(chat_id, text):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "HTML",
    }
    try:
        r = requests.post(url, json=payload, timeout=15)
        if r.status_code != 200:
            logger.warning("Telegram send failed for %s: %s %s", chat_id, r.status_code, r.text)
    except requests.RequestException as exc:
        logger.warning("Telegram send error for %s: %s", chat_id, exc)


def _telegram_api_request(method, payload):
    if not TELEGRAM_BOT_TOKEN:
        raise RuntimeError("TELEGRAM_WIKI_BOT_TOKEN не налаштований")
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/{method}"
    try:
        response = requests.post(url, json=payload, timeout=15)
        if response.status_code != 200:
            logger.warning("Telegram API %s failed: %s %s", method, response.status_code, response.text)
            return None
        return response.json()
    except requests.RequestException as exc:
        logger.warning("Telegram API %s error: %s", method, exc)
        return None


def _is_registered_telegram_user(telegram_id):
    conn = get_db_connection()
    cur = conn.cursor()
    try:
        cur.execute(
            """
            SELECT COALESCE(name, '')
            FROM database_app_userdatatelegram
            WHERE telegram_id = %s
            LIMIT 1
            """,
            (int(telegram_id),),
        )
        row = cur.fetchone()
        if not row:
            return False, ""
        return True, row[0] or ""
    finally:
        cur.close()
        conn.close()


def _welcome_registered_text(full_name):
    display_name = _safe(full_name, "колего")
    return (
        f"✅ <b>Вітаємо, {display_name}!</b>\n\n"
        "Це корпоративний Wiki-бот MIM-K.\n"
        "Тут ви отримуватимете важливі сповіщення:\n"
        "• 💬 Коментарі на ваші статті\n"
        "• 🔄 Оновлення у ваших статтях\n"
        "• 🆕 Нові матеріали в Базі Знань\n"
        "• 👤 Системні події по вашому доступу\n\n"
        "Усі оновлення приходитимуть сюди автоматично."
    )


def _welcome_unregistered_text():
    return (
        "🚫 <b>Ваш Telegram ID не знайдено в базі користувачів.</b>\n\n"
        "Щоб отримувати сповіщення з Бази Знань, потрібно зареєструватись у корпоративному боті.\n\n"
        "1) Натисніть кнопку нижче\n"
        "2) Пройдіть реєстрацію\n"
        "3) Поверніться сюди та натисніть <b>Перевірити ще раз</b>"
    )


def _send_start_response(chat_id, telegram_user_id):
    is_registered, full_name = _is_registered_telegram_user(telegram_user_id)

    if is_registered:
        payload = {
            "chat_id": int(chat_id),
            "text": _welcome_registered_text(full_name),
            "parse_mode": "HTML",
        }
        _telegram_api_request("sendMessage", payload)
        return

    reply_markup = {
        "inline_keyboard": [
            [{"text": "Перейти до корпоративного бота", "url": CORPORATE_BOT_URL}],
            [{"text": "Перевірити ще раз", "callback_data": "check_registration"}],
        ]
    }
    payload = {
        "chat_id": int(chat_id),
        "text": _welcome_unregistered_text(),
        "parse_mode": "HTML",
        "reply_markup": reply_markup,
    }
    _telegram_api_request("sendMessage", payload)


@app.route('/telegram-webhook', methods=['POST'])
def handle_telegram_webhook():
    update = request.get_json(silent=True) or {}
    logger.info("Telegram update:\n%s", json.dumps(update, ensure_ascii=False, indent=2))

    _process_telegram_update(update)
    return {"ok": True}, 200


def _process_telegram_update(update):
    message = update.get("message") or {}
    callback_query = update.get("callback_query") or {}

    if message:
        text = (message.get("text") or "").strip()
        chat_id = (message.get("chat") or {}).get("id")
        user_id = (message.get("from") or {}).get("id")

        if text.lower() == "/start" and chat_id and user_id:
            _send_start_response(chat_id, user_id)

    elif callback_query:
        callback_data = callback_query.get("data") or ""
        callback_id = callback_query.get("id")
        user_id = (callback_query.get("from") or {}).get("id")
        chat_id = ((callback_query.get("message") or {}).get("chat") or {}).get("id")

        if callback_id:
            _telegram_api_request("answerCallbackQuery", {"callback_query_id": callback_id})

        if callback_data == "check_registration" and chat_id and user_id:
            _send_start_response(chat_id, user_id)


def _delete_telegram_webhook_for_polling():
    result = _telegram_api_request("deleteWebhook", {"drop_pending_updates": False})
    if result and result.get("ok"):
        logger.info("Telegram webhook disabled for polling mode")
    else:
        logger.warning("Could not disable Telegram webhook before polling")


def _telegram_polling_loop():
    logger.info("Telegram polling loop started")
    offset = None

    while True:
        payload = {
            "timeout": 25,
            "allowed_updates": ["message", "callback_query"],
        }
        if offset is not None:
            payload["offset"] = offset

        response = _telegram_api_request("getUpdates", payload)
        if not response or not response.get("ok"):
            time.sleep(2)
            continue

        updates = response.get("result") or []
        for upd in updates:
            try:
                _process_telegram_update(upd)
            except Exception:
                logger.exception("Failed to process telegram update")

            update_id = upd.get("update_id")
            if isinstance(update_id, int):
                offset = update_id + 1


def _start_telegram_updates_worker_if_needed():
    mode = TELEGRAM_UPDATE_MODE
    if mode not in {"webhook", "polling", "both"}:
        logger.warning("Unknown TELEGRAM_UPDATE_MODE='%s', fallback to polling", mode)
        mode = "polling"

    # Telegram API does not allow webhook and getUpdates simultaneously for one bot token.
    # 'both' here means BookStack webhook + Telegram polling in one process.
    if mode in {"polling", "both"}:
        _delete_telegram_webhook_for_polling()
        worker = threading.Thread(target=_telegram_polling_loop, daemon=True)
        worker.start()

    if mode == "webhook":
        logger.info("Telegram update mode: webhook")
    else:
        logger.info("Telegram update mode: polling")


def _normalize_name(value):
    if value is None:
        return ""
    return " ".join(str(value).strip().split())


def _extract_page_id(data, event):
    related = data.get("related_item") or {}
    current_revision = related.get("current_revision") or {}

    if event == "comment_create":
        return related.get("commentable_id")
    return related.get("id") or current_revision.get("page_id")


def _extract_owner_identity(data, event):
    related = data.get("related_item") or {}
    owned_by = related.get("owned_by") or {}
    created_by = related.get("created_by") or {}
    updated_by = related.get("updated_by") or {}
    triggered_by = data.get("triggered_by") or {}

    if event == "page_create":
        owner_id = _first_non_empty(owned_by.get("id"), created_by.get("id"), triggered_by.get("id"))
        owner_name = _normalize_name(
            _first_non_empty(owned_by.get("name"), created_by.get("name"), triggered_by.get("name"))
        )
        owner_slug = _normalize_name(
            _first_non_empty(owned_by.get("slug"), created_by.get("slug"), triggered_by.get("slug"))
        )
    else:
        owner_id = _first_non_empty(owned_by.get("id"))
        owner_name = _normalize_name(_first_non_empty(owned_by.get("name")))
        owner_slug = _normalize_name(_first_non_empty(owned_by.get("slug")))

    editor_id = _first_non_empty(triggered_by.get("id"), updated_by.get("id"), created_by.get("id"))
    editor_name = _normalize_name(
        _first_non_empty(triggered_by.get("name"), updated_by.get("name"), created_by.get("name"))
    )
    return owner_id or None, owner_name or None, owner_slug or None, editor_id or None, editor_name or None


def upsert_page_owner(data, event, page_name, page_url):
    page_id = _extract_page_id(data, event)
    if not page_id:
        return

    owner_id, owner_name, owner_slug, editor_id, editor_name = _extract_owner_identity(data, event)
    clean_page_name = _normalize_name(page_name) or None
    clean_page_url = _normalize_name(page_url) or None

    conn = get_db_connection()
    cur = conn.cursor()
    try:
        cur.execute(
            """
            INSERT INTO wiki_page_owners (
                page_id,
                page_name,
                page_url,
                owner_bookstack_id,
                owner_name,
                owner_slug,
                last_editor_bookstack_id,
                last_editor_name,
                last_event,
                last_seen_at
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, NOW())
            ON CONFLICT (page_id) DO UPDATE
            SET
                page_name = COALESCE(EXCLUDED.page_name, wiki_page_owners.page_name),
                page_url = COALESCE(EXCLUDED.page_url, wiki_page_owners.page_url),
                owner_bookstack_id = COALESCE(EXCLUDED.owner_bookstack_id, wiki_page_owners.owner_bookstack_id),
                owner_name = COALESCE(EXCLUDED.owner_name, wiki_page_owners.owner_name),
                owner_slug = COALESCE(EXCLUDED.owner_slug, wiki_page_owners.owner_slug),
                last_editor_bookstack_id = COALESCE(EXCLUDED.last_editor_bookstack_id, wiki_page_owners.last_editor_bookstack_id),
                last_editor_name = COALESCE(EXCLUDED.last_editor_name, wiki_page_owners.last_editor_name),
                last_event = EXCLUDED.last_event,
                last_seen_at = NOW()
            """,
            (
                page_id,
                clean_page_name,
                clean_page_url,
                owner_id,
                owner_name,
                owner_slug,
                editor_id,
                editor_name,
                event,
            ),
        )
        conn.commit()
        logger.info(
            "Upsert wiki_page_owners: page_id=%s owner=%s editor=%s",
            page_id,
            owner_name,
            editor_name,
        )
    finally:
        cur.close()
        conn.close()


def get_page_owner_info(page_id):
    if not page_id:
        return None

    conn = get_db_connection()
    cur = conn.cursor()
    try:
        cur.execute(
            """
            SELECT owner_bookstack_id, owner_name, owner_slug, page_name, page_url
            FROM wiki_page_owners
            WHERE page_id = %s
            LIMIT 1
            """,
            (page_id,),
        )
        row = cur.fetchone()
        if not row:
            return None
        return {
            "owner_bookstack_id": row[0],
            "owner_name": _normalize_name(row[1]),
            "owner_slug": _normalize_name(row[2]),
            "page_name": row[3] or "",
            "page_url": row[4] or "",
        }
    finally:
        cur.close()
        conn.close()


def get_telegram_ids_by_user_name(name):
    normalized = _normalize_name(name)
    if not normalized:
        return []

    conn = get_db_connection()
    cur = conn.cursor()
    try:
        cur.execute(
            """
            SELECT DISTINCT telegram_id
            FROM database_app_userdatatelegram
            WHERE telegram_id IS NOT NULL
              AND LOWER(TRIM(COALESCE(name, ''))) = LOWER(TRIM(%s))
            """,
            (normalized,),
        )
        return [int(row[0]) for row in cur.fetchall()]
    finally:
        cur.close()
        conn.close()


def get_telegram_ids_by_username(username):
    normalized = _normalize_name(username)
    if not normalized:
        return []

    conn = get_db_connection()
    cur = conn.cursor()
    try:
        cur.execute(
            """
            SELECT DISTINCT telegram_id
            FROM database_app_userdatatelegram
            WHERE telegram_id IS NOT NULL
              AND LOWER(TRIM(COALESCE(username, ''))) = LOWER(TRIM(%s))
            """,
            (normalized,),
        )
        return [int(row[0]) for row in cur.fetchall()]
    finally:
        cur.close()
        conn.close()


def _extract_user_target(data):
    related = data.get("related_item") or {}
    event_text = _first_non_empty(data.get("text"), "")

    target_name = _normalize_name(
        _first_non_empty(
            related.get("name"),
            data.get("name"),
            _extract_quoted_title(event_text),
        )
    )
    target_username = _normalize_name(_first_non_empty(related.get("slug"), related.get("username")))
    target_email = _normalize_name(_first_non_empty(related.get("email"), related.get("mail")))

    return {
        "name": target_name,
        "username": target_username,
        "email": target_email,
        "raw": related,
    }


def _extract_login_lines(target):
    raw = target.get("raw") or {}

    explicit_login = _safe(
        _first_non_empty(raw.get("login"), raw.get("username"), raw.get("user_login")),
        "",
    )
    explicit_email = _safe(
        _first_non_empty(raw.get("email"), raw.get("mail")),
        "",
    )

    password = _safe(
        _first_non_empty(
            raw.get("password"),
            raw.get("temporary_password"),
            raw.get("temp_password"),
            raw.get("generated_password"),
        ),
        "",
    )

    lines = []
    if explicit_login:
        lines.append(f"🔐 <b>Логін:</b> {explicit_login}")
    if explicit_email:
        lines.append(f"📧 <b>Email:</b> {explicit_email}")
    if password:
        lines.append(f"🔑 <b>Пароль:</b> <code>{password}</code>")
    return lines


def _build_user_lifecycle_message(event, target_name, triggered_by, event_datetime, login_lines):
    if event == "user_create":
        title = "✅ <b>Вас зареєстрували в Базі Знань</b>"
        actor_line = f"👤 <b>Хто зареєстрував:</b> {triggered_by}"
    elif event == "user_delete":
        title = "⛔ <b>Ваш доступ до Бази Знань видалено</b>"
        actor_line = f"👤 <b>Хто видалив:</b> {triggered_by}"
    else:
        title = "✏️ <b>Оновлено ваші дані в Базі Знань</b>"
        actor_line = f"👤 <b>Хто оновив:</b> {triggered_by}"

    details_block = ""
    if login_lines:
        details_block = "\n" + "\n".join(login_lines)

    return (
        f"{title}\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        f"🙍 <b>Користувач:</b> {target_name}\n"
        f"{actor_line}\n"
        f"🕒 <b>Коли:</b> {event_datetime}"
        f"{details_block}"
    )


def send_user_event_notification(data, event, triggered_by, event_datetime):
    target = _extract_user_target(data)
    target_name = _safe(_first_non_empty(target.get("name")), "")
    target_username = target.get("username")

    recipient_ids = get_telegram_ids_by_user_name(target_name)
    if not recipient_ids and target_username:
        recipient_ids = get_telegram_ids_by_username(target_username)

    if not recipient_ids:
        logger.warning(
            "User event '%s' target not found in telegram DB: name='%s', username='%s'",
            event,
            target_name,
            target_username,
        )
        return

    login_lines = _extract_login_lines(target)
    message = _build_user_lifecycle_message(
        event,
        target_name or "Користувач",
        triggered_by,
        event_datetime,
        login_lines,
    )
    for chat_id in recipient_ids:
        send_telegram_message_to(chat_id, message)
    logger.info(
        "User event '%s' routed to %s for name='%s' username='%s'",
        event,
        recipient_ids,
        target_name,
        target_username,
    )


def send_comment_to_page_owner(data, message, item_name, item_url):
    related = data.get("related_item") or {}
    page_id = related.get("commentable_id")

    owner_info = get_page_owner_info(page_id)
    if not owner_info:
        logger.warning("Owner mapping not found for page_id=%s", page_id)
        if WIKI_COMMENT_FALLBACK_BROADCAST:
            broadcast_telegram_message(message)
        return

    owner_name = owner_info.get("owner_name", "")
    owner_slug = owner_info.get("owner_slug", "")

    owner_telegram_ids = get_telegram_ids_by_user_name(owner_name)
    if not owner_telegram_ids and owner_slug:
        owner_telegram_ids = get_telegram_ids_by_username(owner_slug)

    if not owner_telegram_ids:
        logger.warning("Owner '%s' not found in database_app_userdatatelegram for page_id=%s", owner_name, page_id)
        if WIKI_COMMENT_FALLBACK_BROADCAST:
            broadcast_telegram_message(message)
        return

    logger.info(
        "Comment routed to owner '%s' for page_id=%s, page='%s', url='%s', recipients=%s",
        owner_name,
        page_id,
        item_name,
        item_url,
        owner_telegram_ids,
    )
    for chat_id in owner_telegram_ids:
        send_telegram_message_to(chat_id, message)


def _check_bookstack_token():
    if not BOOKSTACK_WEBHOOK_TOKEN:
        return
    header_token = request.headers.get("X-BookStack-Token", "") or request.headers.get("X-Webhook-Token", "")
    query_token = request.args.get("token", "")
    if header_token != BOOKSTACK_WEBHOOK_TOKEN and query_token != BOOKSTACK_WEBHOOK_TOKEN:
        abort(401, description="Invalid webhook token")


def _safe(value, fallback=""):
    if value is None:
        return fallback
    return html.escape(str(value))


def _first_non_empty(*values):
    for value in values:
        if value is None:
            continue
        text = str(value).strip()
        if text:
            return text
    return ""


def _extract_quoted_title(event_text):
    if not event_text:
        return ""
    text = str(event_text)
    match = re.search(r'"([^"]+)"', text)
    if match:
        return match.group(1).strip()
    match = re.search(r"«([^»]+)»", text)
    if match:
        return match.group(1).strip()
    match = re.search(r"“([^”]+)”", text)
    if match:
        return match.group(1).strip()
    return ""


def _extract_title_from_event_text(event_text):
    if not event_text:
        return ""

    text = str(event_text).strip()
    quoted = _extract_quoted_title(text)
    if quoted:
        return quoted

    patterns = [
        r"commented on\s+(.+)$",
        r"commented on page\s+(.+)$",
        r"updated page\s+(.+)$",
        r"created page\s+(.+)$",
        r"відредагував сторінку\s+(.+)$",
        r"створив сторінку\s+(.+)$",
        r"залишив коментар до сторінки\s+(.+)$",
    ]

    for pattern in patterns:
        match = re.search(pattern, text, flags=re.IGNORECASE)
        if match:
            title = match.group(1).strip().strip('"').strip("' ").strip(".")
            return title

    return ""


def _extract_title_from_url(item_url):
    if not item_url:
        return ""

    url = str(item_url).split("?", 1)[0].split("#", 1)[0].rstrip("/")
    if not url:
        return ""

    parts = [p for p in url.split("/") if p]
    if not parts:
        return ""

    slug = parts[-1]
    if slug in {"page", "chapter", "book", "shelf"} and len(parts) >= 2:
        slug = parts[-2]

    pretty = slug.replace("-", " ").replace("_", " ").strip()
    return pretty if pretty else ""


def _extract_item_name(data):
    event_text = data.get("text", "")
    quoted_name = _extract_quoted_title(event_text)

    related = data.get("related_item") or {}
    current_revision = related.get("current_revision") or {}
    related_page = related.get("page") or {}
    related_entity = related.get("entity") or {}
    related_subject = related.get("subject") or {}
    item_url = _extract_item_url(data)

    return _safe(
        _first_non_empty(
            quoted_name,
            related.get("name"),
            current_revision.get("name"),
            related_page.get("name"),
            related_entity.get("name"),
            related_subject.get("name"),
            data.get("name"),
            _extract_title_from_event_text(event_text),
            _extract_title_from_url(item_url),
        ),
        "Невідома сторінка",
    )


def _extract_item_url(data):
    related = data.get("related_item") or {}
    return _safe(_first_non_empty(data.get("url"), related.get("url")), "")


def _guess_bookstack_base_url(data):
    if BOOKSTACK_BASE_URL:
        return BOOKSTACK_BASE_URL.rstrip("/")

    profile_url = _first_non_empty(data.get("triggered_by_profile_url"))
    if not profile_url:
        return ""

    parsed = urlparse(profile_url)
    if not parsed.scheme or not parsed.netloc:
        return ""
    return f"{parsed.scheme}://{parsed.netloc}"


def _get_bookstack_auth_token():
    if BOOKSTACK_TOKEN_ID and BOOKSTACK_TOKEN_SECRET:
        return f"{BOOKSTACK_TOKEN_ID}:{BOOKSTACK_TOKEN_SECRET}"
    if BOOKSTACK_API_TOKEN:
        return BOOKSTACK_API_TOKEN
    return ""


def _get_bookstack_api_base_url(data):
    if BS_URL:
        return BS_URL.rstrip("/")

    if BOOKSTACK_BASE_URL:
        return f"{BOOKSTACK_BASE_URL.rstrip('/')}/api"

    guessed = _guess_bookstack_base_url(data)
    if guessed:
        return f"{guessed}/api"

    return ""


def _bookstack_api_get(data, endpoint):
    token = _get_bookstack_auth_token()
    if not token:
        return None

    api_base_url = _get_bookstack_api_base_url(data)
    if not api_base_url:
        return None

    url = f"{api_base_url}/{str(endpoint).lstrip('/')}"
    headers = {
        "Authorization": f"Token {token}",
        "Accept": "application/json",
    }

    try:
        response = requests.get(url, headers=headers, timeout=15)
        if response.status_code != 200:
            logger.warning("BookStack API GET failed: %s %s", response.status_code, response.text)
            return None
        return response.json()
    except requests.RequestException as exc:
        logger.warning("BookStack API request error: %s", exc)
        return None


def _enrich_comment_page_details(data, item_name, item_url):
    related = data.get("related_item") or {}
    commentable_type = str(related.get("commentable_type", "")).strip().lower()
    commentable_id = related.get("commentable_id")

    if commentable_type != "page" or not commentable_id:
        return item_name, item_url

    page_json = _bookstack_api_get(data, f"pages/{commentable_id}")
    if not page_json:
        return item_name, item_url

    api_name = _safe(page_json.get("name"), "")
    api_url = _safe(_first_non_empty(page_json.get("url"), page_json.get("slug")), "")

    base_url = _guess_bookstack_base_url(data)
    if api_url and base_url and api_url.startswith("/"):
        api_url = urljoin(base_url + "/", api_url.lstrip("/"))

    final_name = item_name
    if final_name == "Невідома сторінка" and api_name:
        final_name = api_name

    final_url = item_url or api_url
    return final_name, final_url


def get_page_info(data, page_id):
    if not page_id:
        return "", ""

    page_json = _bookstack_api_get(data, f"pages/{page_id}")
    if not page_json:
        return f"Сторінка #{page_id}", ""

    name = _safe(_first_non_empty(page_json.get("name")), f"Сторінка #{page_id}")

    raw_url = _first_non_empty(page_json.get("url"), page_json.get("slug"))
    if raw_url and str(raw_url).startswith("/"):
        base_url = _guess_bookstack_base_url(data)
        full_url = urljoin(base_url + "/", str(raw_url).lstrip("/")) if base_url else ""
    elif raw_url:
        full_url = str(raw_url)
    else:
        base_url = _guess_bookstack_base_url(data)
        full_url = f"{base_url}/link/{page_id}" if base_url else ""

    return name, _safe(full_url, "")


def get_comment_text(data, comment_id):
    if not comment_id:
        return ""

    comment_json = _bookstack_api_get(data, f"comments/{comment_id}")
    if not comment_json:
        return ""

    return _safe(
        _first_non_empty(
            comment_json.get("text"),
            comment_json.get("html"),
            comment_json.get("markdown"),
            comment_json.get("message"),
        ),
        "",
    )


def _extract_revision_summary(data):
    related = data.get("related_item") or {}
    current_revision = related.get("current_revision") or {}
    return _safe(_first_non_empty(current_revision.get("summary")), "")


def _extract_event_datetime(data):
    raw = _first_non_empty(data.get("triggered_at"), data.get("created_at"), data.get("updated_at"))
    if not raw:
        return "невідомо"

    try:
        dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        kyiv_dt = dt.astimezone(ZoneInfo("Europe/Kyiv"))
        return kyiv_dt.strftime("%d.%m.%Y %H:%M:%S")
    except Exception:
        return _safe(raw, "невідомо")


def _build_message(event_title, triggered_by, item_name, item_url, event_datetime, extra_line=""):
    link_line = f"🔗 <a href='{item_url}'>Відкрити статтю</a>" if item_url else "🔗 Посилання недоступне"
    extra = f"\n{extra_line}" if extra_line else ""
    return (
        f"<b>{event_title}</b>\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        f"👤 <b>Хто:</b> {triggered_by}\n"
        f"📄 <b>Стаття:</b> {item_name}\n"
        f"🕒 <b>Час:</b> {event_datetime}"
        f"{extra}\n"
        f"{link_line}"
    )


def _build_new_page_message(item_name, triggered_by, event_datetime, item_url):
    link_line = f"🔗 <a href='{item_url}'>Відкрити сторінку</a>" if item_url else "🔗 Посилання недоступне"
    return (
        "🆕 <b>Нова сторінка в Базі Знань</b>\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        f"📄 <b>{item_name}</b>\n"
        f"👤 <b>Хто створив:</b> {triggered_by}\n"
        f"🕒 <b>Коли:</b> {event_datetime}\n"
        f"{link_line}"
    )


def _build_comment_owner_message(item_name, triggered_by, event_datetime, item_url):
    link_line = f"🔗 <a href='{item_url}'>Відкрити сторінку</a>" if item_url else "🔗 Посилання недоступне"
    return (
        "💬 <b>Додано коментар на вашу сторінку</b>\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        f"📄 <b>Сторінка:</b> {item_name}\n"
        f"👤 <b>Хто додав коментар:</b> {triggered_by}\n"
        f"🕒 <b>Коли:</b> {event_datetime}\n"
        f"{link_line}"
    )

@app.route('/bookstack-webhook', methods=['POST'])
def handle_webhook():
    raw_body = request.get_data(as_text=True)
    logger.info("BookStack webhook raw body: %s", raw_body)

    _check_bookstack_token()
    data = request.get_json(silent=True) or {}
    logger.info(
        "BookStack webhook parsed JSON:\n%s",
        json.dumps(data, ensure_ascii=False, indent=2),
    )

    event = data.get('event')
    triggered_by = _safe(data.get('triggered_by', {}).get('name'), 'Хтось')
    item_name = _extract_item_name(data)
    item_url = _extract_item_url(data)
    event_datetime = _extract_event_datetime(data)

    ensure_wiki_tables()

    if event == 'page_create':
        upsert_page_owner(data, event, item_name, item_url)
        message = _build_new_page_message(item_name, triggered_by, event_datetime, item_url)
        broadcast_telegram_message(message)

    elif event == 'page_update':
        upsert_page_owner(data, event, item_name, item_url)
        revision_summary = _extract_revision_summary(data)
        summary_line = f"📝 <b>Зміни:</b> <i>{revision_summary}</i>" if revision_summary else ""
        message = _build_message(
            "🔄 Оновлення інструкції",
            triggered_by,
            item_name,
            item_url,
            event_datetime,
            summary_line,
        )
        broadcast_telegram_message(message)

    elif event == 'comment_create':
        related = data.get('related_item') or {}
        page_id = related.get('commentable_id')

        mapped_owner = get_page_owner_info(page_id)
        if mapped_owner:
            mapped_page_name = mapped_owner.get('page_name')
            mapped_page_url = mapped_owner.get('page_url')
            if mapped_page_name:
                item_name = _safe(mapped_page_name, item_name)
            if mapped_page_url:
                item_url = _safe(mapped_page_url, item_url)

        api_item_name, api_item_url = get_page_info(data, page_id)
        if api_item_name and (not item_name or item_name == 'Невідома сторінка' or str(item_name).startswith('Сторінка #')):
            item_name = api_item_name
        if api_item_url and not item_url:
            item_url = api_item_url
        else:
            item_name, item_url = _enrich_comment_page_details(data, item_name, item_url)

        message = _build_comment_owner_message(item_name, triggered_by, event_datetime, item_url)
        send_comment_to_page_owner(data, message, item_name, item_url)

    elif event in ('user_create', 'user_update', 'user_delete'):
        send_user_event_notification(data, event, triggered_by, event_datetime)

    return {"ok": True}, 200

if __name__ == '__main__':
    ensure_wiki_tables()
    _start_telegram_updates_worker_if_needed()
    port = int(os.getenv("WIKI_WEBHOOK_PORT", "2001"))
    app.run(host='0.0.0.0', port=port)