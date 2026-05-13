import os
from pathlib import Path

from dotenv import load_dotenv


BASE_DIR = Path(__file__).resolve().parent
PROJECT_DIR = BASE_DIR.parent
ROOT_DIR = PROJECT_DIR.parent
ENV_PATH = ROOT_DIR / ".env"

load_dotenv(ENV_PATH)


def _parse_csv_env(name: str, default: str) -> list[str]:
    raw = os.getenv(name, default)
    return [value.strip() for value in raw.split(",") if value.strip()]

APP_HOST = os.getenv("COLLECTORS_HOST", "127.0.0.1")
APP_PORT = int(os.getenv("COLLECTORS_PORT", "9182"))
SECRET_KEY = os.getenv("SECRET_KEY", "CHANGE_ME_SECRET_KEY")
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
CODE_TTL_SECONDS = int(os.getenv("COLLECTORS_CODE_TTL_SECONDS", "300"))

SESSION_COOKIE_SECURE = os.getenv("SESSION_COOKIE_SECURE", "0") == "1"
SESSION_COOKIE_SAMESITE = os.getenv("SESSION_COOKIE_SAMESITE", "lax")
ALLOW_ALL_HOSTS = os.getenv("ALLOW_ALL_HOSTS", "0") == "1"
ALLOWED_HOSTS = ["*"] if ALLOW_ALL_HOSTS else _parse_csv_env(
    "ALLOWED_HOSTS",
    "127.0.0.1,localhost,::1,*.trycloudflare.com",
)
SECURITY_HEADERS_FORCE_HTTPS = os.getenv("SECURITY_HEADERS_FORCE_HTTPS", "0") == "1"

PG_CONN = {
    "host": os.getenv("PG_HOST"),
    "port": int(os.getenv("PG_PORT", "5432")),
    "dbname": os.getenv("PG_DBNAME"),
    "user": os.getenv("PG_USER"),
    "password": os.getenv("PG_PASSWORD"),
}

STATIC_DIR = PROJECT_DIR / "app" / "static"
TEMPLATES_DIR = PROJECT_DIR / "app" / "templates"
