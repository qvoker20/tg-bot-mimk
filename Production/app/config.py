import os

from dotenv import load_dotenv

load_dotenv()

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
TEMPLATES_DIR = os.path.join(BASE_DIR, "templates")
STATIC_DIR = os.path.join(BASE_DIR, "static")

SECRET_KEY = os.getenv("SECRET_KEY", "CHANGE_ME_SECRET_KEY")
PRODUCTION_PORT = int(os.getenv("PRODUCTION_PORT", "5001"))
CODE_TTL_SECONDS = int(os.getenv("PRODUCTION_CODE_TTL", "300"))

DEFAULT_ALLOWED_ROLES = "admin,adminpre"
ALLOWED_ROLES = {
    role.strip().lower()
    for role in os.getenv("PRODUCTION_ALLOWED_ROLES", DEFAULT_ALLOWED_ROLES).split(",")
    if role.strip()
}

PG_CONN = {
    "host": os.getenv("PG_HOST"),
    "port": int(os.getenv("PG_PORT", "5432")),
    "dbname": os.getenv("PG_DBNAME"),
    "user": os.getenv("PG_USER"),
    "password": os.getenv("PG_PASSWORD"),
}

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
