
from psycopg2.extras import execute_batch, execute_values
from oauth2client.service_account import ServiceAccountCredentials
from datetime import datetime
from dotenv import load_dotenv
import asyncio
import hashlib
import json
import re
import socket
import time
import gspread
import psycopg2
import os

load_dotenv()

# =========================
# Google Sheets configuration
# =========================
GOOGLE_SHEET_ID = os.environ.get("GOOGLE_SHEET_ID")
SHEET_NAME = "3D замір"
SHEET_NAME_DOP = "3D замір ДОП"

SECOND_GOOGLE_SHEET_ID = os.environ.get("SECOND_GOOGLE_SHEET_ID")
SECOND_SHEET_NAME = "Список замірів"

GOOGLE_SHEET_RZM_ID = '1llpmSz16AfGk_Bj27TybqalNGJ9tq5qrvAA-x40WWUQ'
GOOGLE_SHEET_RZM_ID_NAME = 'Матеріали'
GOOGLE_SHEET_RZM_ID_REGISTER = 'реєстр'
GOOGLE_SHEET_RZM_ID_REGISTER_CLOSED = 'Виконані'

PLAN_GOOGLE_SHEET_ID = os.environ.get(
    "PLAN_GOOGLE_SHEET_ID",
    "1I10uroNnT9yL6vcfsHi2WG3tBAc6tbGTxqUBbe7NLv8"
)
PLAN_SHEET_NAME = "data-plan"
PLAN_DATE_SHEET_NAME = "data-plan-date"
REC_SHEET_NAME = "data-rec"
USERS_SHEET_NAME = "users"
DESIGNER_SOURCE_SHEET_NAME = "Замовлення"
DESIGNER_CONSTR_SHEET_NAME = "Конструкторські"
PRODUCTION_SOURCE_SHEET_NAMES = [GOOGLE_SHEET_RZM_ID_REGISTER, GOOGLE_SHEET_RZM_ID_REGISTER_CLOSED]
METAL_SOURCE_SHEET_ID = os.environ.get(
    "METAL_SOURCE_SHEET_ID",
    "1lTfmirujbio8bNVdeazWGHZRk4T9lHifZ0sARSv3dlQ",
)
METAL_SOURCE_SHEET_NAME = "Метал"

JSON_KEY_FILE = os.environ.get('JSON_KEY_FILE')

APPEND_GOOGLE_SHEET_ID = os.environ.get(
    "APPEND_GOOGLE_SHEET_ID",
    "1RjioViixRUJ15R3bA0KdIxsPaUxD6HP04TG-UuVZ1H8",
)
APPEND_SHEET_MAIN_NAME = "main"
APPEND_SHEET_PARTS_NAME = "parts"


def resolve_service_account_path(path_value: str | None) -> str:
    if not path_value:
        return ""

    normalized = os.path.expanduser(path_value.strip().strip('"').strip("'"))
    if os.path.isabs(normalized):
        return normalized

    base_dir = os.path.dirname(os.path.abspath(__file__))
    return os.path.abspath(os.path.join(base_dir, normalized))

# =========================
# PostgreSQL configuration
# =========================
PG_CONN = {
    'host': os.environ.get("PG_HOST"),
    'port': int(os.environ.get("PG_PORT")),
    'dbname': os.environ.get("PG_DBNAME"),
    'user': os.environ.get("PG_USER"),
    'password': os.environ.get("PG_PASSWORD")
}

# =========================
# DB table names
# =========================
TABLE_NAME = 'sheet_data'
SECOND_TABLE_NAME = 'second_sheet_data'
RZM_TABLE_NAME = 'rzm_data'
REGISTER_TABLE_NAME = 'register_data'
TABLE_NAME_DOP = 'sheet_data_dop'
REGISTER_TABLE_NAME_CLOSED = 'register_data_closed'
DATA_PLAN_TABLE_NAME = 'data_plan'
DATA_PLAN_DATE_TABLE_NAME = 'data_plan_date'
DATA_REC_TABLE_NAME = 'data_rec'
USERS_TABLE_NAME = 'users'
DATA_DESIGNER_TABLE_NAME = 'data_designer'
DATA_PRODUCTION_TABLE_NAME = 'data_production'
DATA_METAL_TABLE_NAME = 'data_metal'
APPEND_MAIN_TABLE_NAME = 'sheet_append_main'
APPEND_PARTS_TABLE_NAME = 'sheet_append_parts'
APPEND_MAIN_VIEW_NAME = 'sheet_append_main_view'
APPEND_PARTS_VIEW_NAME = 'sheet_append_parts_view'

DESIGNER_HEADERS = [
    '▪️№ зам.',
    'частина',
    '▪️замовник',
    'всього частин',
    '▪️замовник',
    '▪️виріб',
    'менеджер',
    'технолог',
    '▪️тип зам.',
    'вартість зам.',
    '▪️конструктор',
    'кінець виконання конструктором',
    'кінець виконання адаптатором',
    '🟢малярний цех',
    '🟢метал',
    '🟢шпон',
    '🟢пластик HPL',
    '🟢столярний цех',
    "🟢м'який цех",
    '🟢штучний камінь',
    '🟢компакт-плита',
    '🟢cтільниця ДСП',
    'розсувні системи',
    'скло/дзеркало',
    'рамкові фасади',
    '🔴скло/дзеркало',
    '🔴розсувні системи',
    '🔴рамкові фасади',
    '🔴керамограніт',
    'дата підписання замовлення',
    'кінцева дата за договором',
    'кінцева дата за договором перенесена',
]

DESIGNER_CONSTR_HEADERS = [
    '🟢малярний цех', '🟢метал', '🟢шпон', '🟢пластик HPL', '🟢столярний цех',
    "🟢м'який цех", '🟢штучний камінь', '🟢компакт-плита', '🟢cтільниця ДСП',
    'розсувні системи', 'скло/дзеркало', 'рамкові фасади',
    '🔴скло/дзеркало', '🔴розсувні системи', '🔴рамкові фасади', '🔴керамограніт'
]

PRODUCTION_HEADERS = [
    'Номер замовлення',
    'Запуск',
    'Кількість запусків до частин',
    'Частина',
    'Всього частин',
    'Тип Номер Р',
    'Назва замовлення',
    'Тип матеріалу',
    'Статус',
    'Дата передачі на виробн.',
    'взяли в роботу',
    'Дата гот. виробництво',
]

METAL_HEADERS = [
    'Номер замовлення',
    'Частина',
    'Дата опрацювання конструктором',
    'Дата переміщення в цех фарбування',
    'Дата отримання на склад ГП',
]

APPEND_PARTS_HEADERS = [
    "Номер замолення",
    "Виріб",
    "Статус",
    "Частина заміру",
    "Поміряно дата та час",
    "Завантажено на диск",
    "Замір зшито",
    "Назначено Адаптатора",
    "Адаптатор",
    "Початок виконання",
    "Завершено виконання",
    "Пауза адаптації",
    "Причина паузи",
]

APPEND_MAIN_HEADERS = [
    "Номер замолення",
    "Замовник",
    "Контакти до кого звертатись",
    "Частина заміру",
    "Тип замолення",
    "кількість виробів",
    "Вироби",
    "Менеджер",
    "Дата створення",
    "Тип будинку",
    "Адреса",
    "Додаткова інформація",
    "Примітка до адреси",
    "примітка до заміру",
    "Дата заміру",
    "час заміру",
    "замірник",
    "погоджено замір",
    "статус",
    "дата та час початку адатації",
    "Причина виїзду",
    "Днів до завершення адаптації",
    "Дата по договору",
    "Статус адаптація",
    "Фіксація виконаго заміру",
    "Пауза дата та час",
    "Причина паузи",
    "Кількість годин на паузі",
    "Кінцева дата подачі",
    "ТЗ на замір",
    "Причина не поміряних позицій",
    "Днів залишилось по подачі",
    "Днів залишилось по договору",
]

REGISTER_REQUIRED_HEADERS = [
    "Номер замовлення",
    "Запуск",
    "Кількість запусків до частин",
    "Частина",
    "Всього частин",
    "Тип Номер Р Назва замовлення",
    "Тип матеріалу",
    "Фюрер",
    "Кількість листів",
    "Статус",
    "Дата передачі на виробн.",
    "взяли в роботу",
    "Забез-ння сировиною",
    "Порізка метри",
    "Присадка кіл. отв. Порізка",
    "поклейка",
    "Присадка",
    "Криволі-нійна",
    "Формат-ник",
    "Стяжки",
    "Нестінг",
    "Дата гот. виробництво",
    "Дата по договору (монтаж)",
    "Куди передавати матеріал",
    "Примітки",
]

# =========================
# Utilities
# =========================
def is_internet_available():
    """Перевіряє наявність інтернет-з'єднання."""
    try:
        socket.create_connection(("8.8.8.8", 53), timeout=5)
        return True
    except OSError:
        return False

def is_work_time():
    now = datetime.now()
    # Понеділок = 0, ..., Субота = 5, Неділя = 6
    if now.weekday() > 5:  # Неділя
        return False
    if now.hour < 8 or now.hour >= 19:
        return False
    return True


def authenticate_google_sheets(json_key_file):
    candidate = json_key_file or os.environ.get("FIREBASE_SERVICE_ACCOUNT_FILE")
    resolved_path = resolve_service_account_path(candidate)

    if not resolved_path:
        raise ValueError("Не задано JSON_KEY_FILE або FIREBASE_SERVICE_ACCOUNT_FILE в .env")
    if not os.path.exists(resolved_path):
        raise FileNotFoundError(f"Не знайдено файл сервісного акаунта: {resolved_path}")

    scope = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']
    credentials = ServiceAccountCredentials.from_json_keyfile_name(resolved_path, scope)
    client = gspread.authorize(credentials)
    return client


def fetch_data_from_sheet(sheet):
    return sheet.get_all_values()


def normalize_header(value):
    return " ".join(str(value or "").replace("\xa0", " ").replace("\n", " ").strip().lower().split())


def strip_markers(value):
    if not value:
        return ""
    return re.sub(r"^[\s]*(?:▪️|🟢|🔴)\s*", "", str(value), flags=re.UNICODE).strip()


def normalize_marker_agnostic_name(value):
    return normalize_header(strip_markers(value))


def quote_ident(name: str) -> str:
    return '"' + str(name).replace('"', '""') + '"'


def sanitize_column_name(value: str, fallback_index: int) -> str:
    normalized = normalize_header(value)
    normalized = normalized.replace("%", " pct")
    normalized = re.sub(r"[^a-zA-Z0-9_]+", "_", normalized)
    normalized = re.sub(r"_+", "_", normalized).strip("_").lower()

    if not normalized:
        normalized = f"column_{fallback_index}"
    if normalized[0].isdigit():
        normalized = f"col_{normalized}"

    return normalized


def build_unique_columns(headers):
    columns = []
    seen = {}
    for idx, raw in enumerate(headers, start=1):
        base = sanitize_column_name(str(raw or ""), idx)
        count = seen.get(base, 0)
        seen[base] = count + 1
        columns.append(base if count == 0 else f"{base}_{count + 1}")
    return columns


def extract_rows_by_header_names(data, required_headers, header_row_index=1):
    if len(data) <= header_row_index:
        return []

    header_row = data[header_row_index]
    normalized_header_row = [normalize_header(h) for h in header_row]

    indices = []
    missing_headers = []
    for header_name in required_headers:
        normalized_target = normalize_header(header_name)
        if normalized_target in normalized_header_row:
            indices.append(normalized_header_row.index(normalized_target))
        else:
            indices.append(None)
            missing_headers.append(header_name)

    if missing_headers:
        print(
            f"Увага: не знайдено колонки в рядку {header_row_index + 1}: "
            + ", ".join(missing_headers)
        )

    rows_to_insert = []
    for row in data[header_row_index + 1:]:
        if all(cell is None or str(cell).strip() == "" for cell in row):
            continue

        extracted_row = []
        for idx in indices:
            if idx is None or idx >= len(row):
                extracted_row.append(None)
            else:
                extracted_row.append(row[idx])
        rows_to_insert.append(extracted_row)

    return rows_to_insert


def get_pg_connection():
    return psycopg2.connect(
        host=PG_CONN['host'],
        port=PG_CONN['port'],
        dbname=PG_CONN['dbname'],
        user=PG_CONN['user'],
        password=PG_CONN['password']
    )


# =========================
# Create tables (PostgreSQL)
# =========================
def create_table(cursor):
    cursor.execute(f'''
        CREATE TABLE IF NOT EXISTS {TABLE_NAME} (
            id SERIAL PRIMARY KEY,
            NGT TEXT,
            column2 TEXT,
            column3 TEXT,
            column4 TEXT,
            column5 TEXT,
            column6 TEXT,
            column7 TEXT,
            column8 TEXT,
            column9 TEXT,
            column10 TEXT,
            column11 TEXT,
            column12 TEXT,
            column13 TEXT,
            column14 TEXT,
            column15 TEXT,
            column16 TEXT,
            column17 TEXT,
            column18 TEXT,
            column19 TEXT,
            column20 TEXT,
            column21 TEXT,
            column22 TEXT,
            column23 TEXT,
            column24 TEXT,
            column25 TEXT,
            column26 TEXT,
            column27 TEXT,
            column28 TEXT
        );
    ''')


def create_second_table(cursor):
    cursor.execute(f'''
        CREATE TABLE IF NOT EXISTS {SECOND_TABLE_NAME} (
            id SERIAL PRIMARY KEY,
            column1 TEXT,
            column2 TEXT,
            column3 TEXT,
            column4 TEXT,
            column5 TEXT,
            column6 TEXT,
            column7 TEXT,
            column8 TEXT,
            column9 TEXT,
            column10 TEXT,
            column11 TEXT,
            column12 TEXT,
            column13 TEXT,
            column14 TEXT,
            column15 TEXT,
            column16 TEXT,
            column17 TEXT,
            column18 TEXT,
            column19 TEXT
        );
    ''')


def create_rzm_table(cursor):
    # Як у вашій логіці: оновлюємо структуру "з нуля"
    cursor.execute(f"DROP TABLE IF EXISTS {RZM_TABLE_NAME};")
    cursor.execute(f'''
        CREATE TABLE IF NOT EXISTS {RZM_TABLE_NAME} (
            id SERIAL PRIMARY KEY,
            columnA TEXT,
            columnB TEXT,
            columnC TEXT,
            columnD TEXT,
            columnE TEXT,
            columnF TEXT,
            columnG TEXT,
            columnH TEXT,
            columnI TEXT,
            columnJ TEXT,
            columnK TEXT,
            columnL TEXT,
            columnM TEXT,
            columnN TEXT
        );
    ''')


def create_register_table(cursor):
    cursor.execute(f'''
        CREATE TABLE IF NOT EXISTS {REGISTER_TABLE_NAME} (
            id SERIAL PRIMARY KEY,
            column1 TEXT,
            column2 TEXT,
            column3 TEXT,
            column4 TEXT,
            column5 TEXT,
            column6 TEXT,
            column7 TEXT,
            column8 TEXT,
            column9 TEXT,
            column10 TEXT,
            column11 TEXT,
            column12 TEXT,
            column13 TEXT,
            column14 TEXT,
            column15 TEXT,
            column16 TEXT,
            column17 TEXT,
            column18 TEXT,
            column19 TEXT,
            column20 TEXT,
            column21 TEXT,
            column22 TEXT,
            column23 TEXT,
            column24 TEXT,
            column25 TEXT
        );
    ''')


def create_table_dop(cursor):
    cursor.execute(f'''
        CREATE TABLE IF NOT EXISTS {TABLE_NAME_DOP} (
            id SERIAL PRIMARY KEY,
            column1 TEXT,
            column2 TEXT,
            column3 TEXT,
            column4 TEXT,
            column5 TEXT,
            column6 TEXT,
            column7 TEXT,
            column8 TEXT,
            column9 TEXT,
            column10 TEXT,
            column11 TEXT,
            column12 TEXT,
            column13 TEXT,
            column14 TEXT,
            column15 TEXT,
            column16 TEXT,
            column17 TEXT,
            column18 TEXT,
            column19 TEXT,
            column20 TEXT,
            column21 TEXT,
            column22 TEXT,
            column23 TEXT,
            column24 TEXT,
            column25 TEXT
        );
    ''')


def create_register_table_closed(cursor):
    cursor.execute(f'''
        CREATE TABLE IF NOT EXISTS {REGISTER_TABLE_NAME_CLOSED} (
            id SERIAL PRIMARY KEY,
            column1 TEXT,
            column2 TEXT,
            column3 TEXT,
            column4 TEXT,
            column5 TEXT,
            column6 TEXT,
            column7 TEXT,
            column8 TEXT,
            column9 TEXT,
            column10 TEXT,
            column11 TEXT,
            column12 TEXT,
            column13 TEXT,
            column14 TEXT,
            column15 TEXT,
            column16 TEXT,
            column17 TEXT,
            column18 TEXT,
            column19 TEXT,
            column20 TEXT,
            column21 TEXT,
            column22 TEXT,
            column23 TEXT,
            column24 TEXT,
            column25 TEXT
        );
    ''')


def create_append_only_table(cursor, table_name):
    cursor.execute(f'''
        CREATE TABLE IF NOT EXISTS {table_name} (
            id BIGSERIAL PRIMARY KEY,
            source_spreadsheet TEXT NOT NULL,
            source_sheet TEXT NOT NULL,
            source_row_index INTEGER NOT NULL,
            row_hash TEXT NOT NULL,
            row_data JSONB NOT NULL,
            parsed_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            UNIQUE (source_spreadsheet, source_sheet, row_hash)
        );
    ''')


def ensure_append_table_columns(cursor, table_name, column_names):
    for name in column_names:
        cursor.execute(
            f"ALTER TABLE {table_name} ADD COLUMN IF NOT EXISTS {quote_ident(name)} TEXT;"
        )


def ensure_append_table_schema_from_headers(cursor, table_name, headers):
    create_append_only_table(cursor, table_name)
    column_names = build_unique_columns(headers)
    ensure_append_table_columns(cursor, table_name, column_names)
    return column_names


def recreate_append_view(cursor, table_name, view_name, headers):
    column_names = build_unique_columns(headers)
    select_parts = [
        "id",
        "source_spreadsheet",
        "source_sheet",
        "source_row_index",
        "row_hash",
        "row_data",
        "parsed_at",
    ]

    for sql_col, display_name in zip(column_names, headers):
        alias = display_name.strip() if str(display_name or "").strip() else sql_col
        select_parts.append(f"{quote_ident(sql_col)} AS {quote_ident(alias)}")

    select_sql = ",\n            ".join(select_parts)
    cursor.execute(
        f'''
        CREATE OR REPLACE VIEW {view_name} AS
        SELECT
            {select_sql}
        FROM {table_name};
        '''
    )


def recreate_current_table_from_headers(cursor, table_name, headers):
    column_names = build_unique_columns(headers)
    cols_sql = ",\n            ".join(f"{quote_ident(name)} TEXT" for name in column_names)
    cursor.execute(f"DROP TABLE IF EXISTS {table_name};")
    cursor.execute(
        f'''
        CREATE TABLE {table_name} (
            id BIGSERIAL PRIMARY KEY,
            {cols_sql}
        );
        '''
    )
    return column_names


def insert_rows_current_fixed_headers(cursor, table_name, data, headers, header_rows_to_skip=1):
    column_names = build_unique_columns(headers)
    width = len(column_names)

    cursor.execute(f"TRUNCATE TABLE {table_name} RESTART IDENTITY;")

    rows_to_insert = []
    for idx, row in enumerate(data):
        if idx < header_rows_to_skip:
            continue
        if all(v is None or str(v).strip() == "" for v in row):
            continue

        padded = list(row[:width])
        if len(padded) < width:
            padded.extend([None] * (width - len(padded)))
        rows_to_insert.append([None if v is None else str(v) for v in padded])

    if not rows_to_insert:
        return 0

    sql_columns = ", ".join(quote_ident(c) for c in column_names)
    template = "(" + ", ".join(["%s"] * width) + ")"
    query = f"INSERT INTO {table_name} ({sql_columns}) VALUES %s"

    execute_values(
        cursor,
        query,
        rows_to_insert,
        template=template,
        page_size=500,
    )
    return len(rows_to_insert)


def build_designer_rows(orders_data, constr_data):
    normalized_columns = [normalize_marker_agnostic_name(col) for col in DESIGNER_HEADERS]
    normalized_constr_columns = {normalize_marker_agnostic_name(col) for col in DESIGNER_CONSTR_HEADERS}
    header_to_write = [strip_markers(col) for col in DESIGNER_HEADERS]

    if not orders_data or len(orders_data) < 2:
        return header_to_write, []

    orders_header = orders_data[0]
    orders_rows = orders_data[1:]
    orders_index_map = {}
    for index, name in enumerate(orders_header):
        key = normalize_marker_agnostic_name(name)
        if key:
            orders_index_map[key] = index

    missing_base = [
        col for col in normalized_columns
        if col not in normalized_constr_columns and col not in orders_index_map
    ]
    if missing_base:
        raise ValueError(
            'У листі "Замовлення" не знайдені колонки: ' + ', '.join(missing_base)
        )

    constr_index_map = {}
    constr_lookup = {}
    if constr_data:
        constr_header = constr_data[0]
        for index, name in enumerate(constr_header):
            key = normalize_marker_agnostic_name(name)
            if key:
                constr_index_map[key] = index

        constr_order_idx = constr_index_map.get(normalize_marker_agnostic_name('▪️№ зам.'))
        constr_part_idx = constr_index_map.get(normalize_marker_agnostic_name('частина'))
        if constr_order_idx is None:
            raise ValueError('У листі "Конструкторські" не знайдено колонку "№ зам." для пошуку.')

        for row in constr_data[1:]:
            order_number = str(row[constr_order_idx] if constr_order_idx < len(row) else '').strip()
            if not order_number:
                continue

            part_number = ''
            if constr_part_idx is not None and constr_part_idx < len(row):
                part_number = str(row[constr_part_idx]).strip()

            lookup_key = order_number + (f'_{part_number}' if part_number else '')
            constr_lookup[lookup_key] = row
            constr_lookup.setdefault(order_number, row)

    order_number_idx = orders_index_map.get(normalize_marker_agnostic_name('▪️№ зам.'))
    part_number_idx = orders_index_map.get(normalize_marker_agnostic_name('частина'))

    output_rows = []
    for row in orders_rows:
        if all(value is None or str(value).strip() == '' for value in row):
            continue

        order_number = ''
        if order_number_idx is not None and order_number_idx < len(row):
            order_number = str(row[order_number_idx]).strip()
        if not order_number:
            continue

        part_number = ''
        if part_number_idx is not None and part_number_idx < len(row):
            part_number = str(row[part_number_idx]).strip()
        lookup_key = order_number + (f'_{part_number}' if part_number else '')
        constr_row = constr_lookup.get(lookup_key) or constr_lookup.get(order_number) or []

        new_row = []
        for col_name in normalized_columns:
            if col_name in normalized_constr_columns:
                constr_idx = constr_index_map.get(col_name)
                value = constr_row[constr_idx] if constr_idx is not None and constr_idx < len(constr_row) else ''
            else:
                order_idx = orders_index_map.get(col_name)
                value = row[order_idx] if order_idx is not None and order_idx < len(row) else ''
            new_row.append(value)
        output_rows.append(new_row)

    return header_to_write, output_rows


def build_production_rows(source_sheets_data, designer_rows):
    output_rows = []
    order_set = {
        str(row[0]).strip()
        for row in designer_rows
        if row and len(row) > 0 and str(row[0]).strip()
    }

    if not order_set:
        return PRODUCTION_HEADERS, []

    combined_header_name = normalize_header('Тип Номер Р Назва замовлення')

    for sheet_name, sheet_data in source_sheets_data:
        if not sheet_data or len(sheet_data) <= 2:
            continue

        header_row = sheet_data[1]
        normalized_header_row = [normalize_header(h) for h in header_row]
        index_map = {name: idx for idx, name in enumerate(normalized_header_row) if name}

        missing_headers = []
        for header_name in PRODUCTION_HEADERS:
            normalized_name = normalize_header(header_name)
            if normalized_name in ('тип номер р', 'назва замовлення'):
                if normalized_name not in index_map and combined_header_name not in index_map:
                    missing_headers.append(header_name)
            elif normalized_name not in index_map:
                missing_headers.append(header_name)

        if missing_headers:
            raise ValueError(
                f'У листі "{sheet_name}" не знайдені колонки: ' + ', '.join(missing_headers)
            )

        order_index = index_map[normalize_header('Номер замовлення')]
        combined_index = index_map.get(combined_header_name)

        for row in sheet_data[2:]:
            if all(cell is None or str(cell).strip() == '' for cell in row):
                continue

            order_number = str(row[order_index] if order_index < len(row) else '').strip()
            if not order_number or order_number not in order_set:
                continue

            prepared_row = []
            for header_name in PRODUCTION_HEADERS:
                normalized_name = normalize_header(header_name)
                value = ''

                if normalized_name == 'тип номер р' and combined_index is not None and combined_index < len(row):
                    combined_value = str(row[combined_index] or '').strip()
                    value = combined_value
                elif normalized_name == 'назва замовлення' and combined_index is not None and combined_index < len(row):
                    value = ''
                else:
                    col_index = index_map.get(normalized_name)
                    if col_index is not None and col_index < len(row):
                        value = row[col_index]

                prepared_row.append(value)

            output_rows.append(prepared_row)

    return PRODUCTION_HEADERS, output_rows


def build_metal_rows(source_data, designer_rows):
    order_set = {
        str(row[0]).strip()
        for row in designer_rows
        if row and len(row) > 0 and str(row[0]).strip()
    }

    if not order_set or not source_data or len(source_data) < 2:
        return METAL_HEADERS, []

    header_row = source_data[0]
    normalized_header_row = [normalize_header(h) for h in header_row]
    index_map = {name: idx for idx, name in enumerate(normalized_header_row) if name}

    missing_headers = [
        header_name for header_name in METAL_HEADERS
        if normalize_header(header_name) not in index_map
    ]
    if missing_headers:
        raise ValueError(
            f'У листі "{METAL_SOURCE_SHEET_NAME}" не знайдені колонки: ' + ', '.join(missing_headers)
        )

    order_index = index_map[normalize_header('Номер замовлення')]
    output_rows = []

    for row in source_data[1:]:
        if all(cell is None or str(cell).strip() == '' for cell in row):
            continue

        order_number = str(row[order_index] if order_index < len(row) else '').strip()
        if not order_number or order_number not in order_set:
            continue

        output_rows.append([
            row[index_map[normalize_header(header_name)]]
            if index_map[normalize_header(header_name)] < len(row)
            else ''
            for header_name in METAL_HEADERS
        ])

    return METAL_HEADERS, output_rows


# =========================
# Insert helpers (PostgreSQL)
# =========================
def insert_data_into_db(cursor, data):
    cursor.execute(f"TRUNCATE TABLE {TABLE_NAME} RESTART IDENTITY;")

    # Вставляємо 28 колонок без id
    cols = (
        "NGT, column2, column3, column4, column5, column6, column7, column8, column9, "
        "column10, column11, column12, column13, column14, column15, column16, column17, "
        "column18, column19, column20, column21, column22, column23, column24, column25, "
        "column26, column27, column28"
    )

    rows_to_insert = []
    for row in data:
        # Ваша логіка: видалити 5-й елемент (індекс 4)
        if len(row) > 4:
            del row[4]

        row = row[:28]
        if len(row) < 28:
            row.extend([None] * (28 - len(row)))
        rows_to_insert.append(row)

    query = f"INSERT INTO {TABLE_NAME} ({cols}) VALUES ({', '.join(['%s'] * 28)})"
    execute_batch(cursor, query, rows_to_insert, page_size=500)


def insert_data_into_second_table(cursor, data):
    cursor.execute(f"TRUNCATE TABLE {SECOND_TABLE_NAME} RESTART IDENTITY;")

    cols = (
        "column1, column2, column3, column4, column5, column6, column7, column8, column9, "
        "column10, column11, column12, column13, column14, column15, column16, column17, "
        "column18, column19"
    )

    rows_to_insert = []
    for index, row in enumerate(data):
        if index < 6:
            continue
        if all(v is None or str(v).strip() == '' for v in row):
            continue

        row = row[:19]
        if len(row) < 19:
            row.extend([None] * (19 - len(row)))
        rows_to_insert.append(row)

    query = f"INSERT INTO {SECOND_TABLE_NAME} ({cols}) VALUES ({', '.join(['%s'] * 19)})"
    execute_batch(cursor, query, rows_to_insert, page_size=500)


def insert_data_into_rzm_table(cursor, data):
    cursor.execute(f"TRUNCATE TABLE {RZM_TABLE_NAME} RESTART IDENTITY;")

    cols = (
        "columnA, columnB, columnC, columnD, columnE, columnF, columnG, columnH, "
        "columnI, columnJ, columnK, columnL, columnM, columnN"
    )

    last_order_number_1 = ''
    last_order_number_2 = ''
    last_order_number_3 = ''

    rows_to_insert = []
    for idx, row in enumerate(data):
        # Копіюємо тільки з рядка 4000 (індексація з 0, тому 3999)
        if idx < 3999:
            continue

        row = row[:14]
        if all(v is None or str(v).strip() == '' for v in row):
            continue

        # Пропускаємо рядки, де тільки columnI (індекс 8) заповнена, а інші порожні
        if (
            (row[8] is not None and str(row[8]).strip() != '') and
            all((cell is None or str(cell).strip() == '') for i, cell in enumerate(row) if i != 8)
        ):
            last_order_number_1 = ''
            last_order_number_2 = ''
            last_order_number_3 = ''
            continue

        if len(row) < 14:
            row.extend([None] * (14 - len(row)))

        # Розтягування для колонок 1,2,3 (A,B,C)
        if row[0] and str(row[0]).strip() != '':
            last_order_number_1 = row[0]
        else:
            row[0] = last_order_number_1

        if row[1] and str(row[1]).strip() != '':
            last_order_number_2 = row[1]
        else:
            row[1] = last_order_number_2

        if row[2] and str(row[2]).strip() != '':
            last_order_number_3 = row[2]
        else:
            row[2] = last_order_number_3

        if last_order_number_1 == '':
            row[0] = ''
        if last_order_number_2 == '':
            row[1] = ''
        if last_order_number_3 == '':
            row[2] = ''

        rows_to_insert.append(row)

    query = f"INSERT INTO {RZM_TABLE_NAME} ({cols}) VALUES ({', '.join(['%s'] * 14)})"
    execute_batch(cursor, query, rows_to_insert, page_size=500)


def insert_data_into_register_table(cursor, data):
    cursor.execute(f"TRUNCATE TABLE {REGISTER_TABLE_NAME} RESTART IDENTITY;")

    cols = ", ".join([f"column{i}" for i in range(1, 26)])
    rows_to_insert = extract_rows_by_header_names(
        data=data,
        required_headers=REGISTER_REQUIRED_HEADERS,
        header_row_index=1,
    )

    query = f"INSERT INTO {REGISTER_TABLE_NAME} ({cols}) VALUES ({', '.join(['%s'] * 25)})"
    execute_batch(cursor, query, rows_to_insert, page_size=500)


def insert_data_into_table_dop(cursor, data):
    cursor.execute(f"TRUNCATE TABLE {TABLE_NAME_DOP} RESTART IDENTITY;")

    cols = ", ".join([f"column{i}" for i in range(1, 26)])

    rows_to_insert = []
    for row in data:
        # Видаляємо спочатку більший індекс, потім менший!
        if len(row) > 20:
            del row[20]
        if len(row) > 14:
            del row[14]
        if len(row) > 15:
            del row[15]
        if len(row) > 4:
            del row[4]

        row = row[:25]
        if len(row) < 25:
            # У вашому коді було (26 - len(row)) — це було некоректно для 25 колонок.
            row.extend([None] * (25 - len(row)))

        rows_to_insert.append(row)

    query = f"INSERT INTO {TABLE_NAME_DOP} ({cols}) VALUES ({', '.join(['%s'] * 25)})"
    execute_batch(cursor, query, rows_to_insert, page_size=500)


def insert_data_into_register_table_closed(cursor, data):
    cursor.execute(f"TRUNCATE TABLE {REGISTER_TABLE_NAME_CLOSED} RESTART IDENTITY;")

    cols = ", ".join([f"column{i}" for i in range(1, 26)])
    rows_to_insert = extract_rows_by_header_names(
        data=data,
        required_headers=REGISTER_REQUIRED_HEADERS,
        header_row_index=1,
    )

    query = f"INSERT INTO {REGISTER_TABLE_NAME_CLOSED} ({cols}) VALUES ({', '.join(['%s'] * 25)})"
    execute_batch(cursor, query, rows_to_insert, page_size=500)


# =========================
# Main async updater
# =========================
async def update_google_sheets():
    try:
        client = authenticate_google_sheets(JSON_KEY_FILE)
        sheet = client.open_by_key(GOOGLE_SHEET_ID).worksheet(SHEET_NAME)
        second_sheet = client.open_by_key(SECOND_GOOGLE_SHEET_ID).worksheet(SECOND_SHEET_NAME)
        rzm_sheet = client.open_by_key(GOOGLE_SHEET_RZM_ID).worksheet(GOOGLE_SHEET_RZM_ID_NAME)
        register_sheet = client.open_by_key(GOOGLE_SHEET_RZM_ID).worksheet(GOOGLE_SHEET_RZM_ID_REGISTER)
        sheet_dop = client.open_by_key(GOOGLE_SHEET_ID).worksheet(SHEET_NAME_DOP)
        register_sheet_closed = client.open_by_key(GOOGLE_SHEET_RZM_ID).worksheet(GOOGLE_SHEET_RZM_ID_REGISTER_CLOSED)

        # plan sheets
        plan_sheet = client.open_by_key(PLAN_GOOGLE_SHEET_ID).worksheet(PLAN_SHEET_NAME)
        plan_date_sheet = client.open_by_key(PLAN_GOOGLE_SHEET_ID).worksheet(PLAN_DATE_SHEET_NAME)
        rec_sheet = client.open_by_key(PLAN_GOOGLE_SHEET_ID).worksheet(REC_SHEET_NAME)
        users_sheet = client.open_by_key(PLAN_GOOGLE_SHEET_ID).worksheet(USERS_SHEET_NAME)

        designer_orders_sheet = client.open_by_key(GOOGLE_SHEET_ID).worksheet(DESIGNER_SOURCE_SHEET_NAME)
        designer_constr_sheet = client.open_by_key(GOOGLE_SHEET_ID).worksheet(DESIGNER_CONSTR_SHEET_NAME)
        metal_source_sheet = client.open_by_key(METAL_SOURCE_SHEET_ID).worksheet(METAL_SOURCE_SHEET_NAME)
        production_source_sheets = [
            (sheet_name, client.open_by_key(GOOGLE_SHEET_RZM_ID).worksheet(sheet_name))
            for sheet_name in PRODUCTION_SOURCE_SHEET_NAMES
        ]

        append_main_sheet = client.open_by_key(APPEND_GOOGLE_SHEET_ID).worksheet(APPEND_SHEET_MAIN_NAME)
        append_parts_sheet = client.open_by_key(APPEND_GOOGLE_SHEET_ID).worksheet(APPEND_SHEET_PARTS_NAME)

        conn = get_pg_connection()
        cursor = conn.cursor()

        # Create fixed-schema tables once
        create_table(cursor)
        create_second_table(cursor)
        create_rzm_table(cursor)
        create_table_dop(cursor)
        recreate_current_table_from_headers(cursor, DATA_DESIGNER_TABLE_NAME, [strip_markers(col) for col in DESIGNER_HEADERS])
        recreate_current_table_from_headers(cursor, DATA_PRODUCTION_TABLE_NAME, PRODUCTION_HEADERS)
        recreate_current_table_from_headers(cursor, DATA_METAL_TABLE_NAME, METAL_HEADERS)
        recreate_current_table_from_headers(cursor, APPEND_MAIN_TABLE_NAME, APPEND_MAIN_HEADERS)
        recreate_current_table_from_headers(cursor, APPEND_PARTS_TABLE_NAME, APPEND_PARTS_HEADERS)
        cursor.execute(f"DROP VIEW IF EXISTS {APPEND_MAIN_VIEW_NAME};")
        cursor.execute(f"DROP VIEW IF EXISTS {APPEND_PARTS_VIEW_NAME};")
        conn.commit()

        while True:
            # 3D замір
            data = fetch_data_from_sheet(sheet)
            insert_data_into_db(cursor, data)
            conn.commit()
            print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] Inserted {len(data)} rows into {TABLE_NAME}.")

            # Список замірів
            second_data = fetch_data_from_sheet(second_sheet)
            insert_data_into_second_table(cursor, second_data)
            conn.commit()
            print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] Inserted {len(second_data)} rows into {SECOND_TABLE_NAME}.")

            # Матеріали (з 4000-го рядка)
            rzm_data = fetch_data_from_sheet(rzm_sheet)
            insert_data_into_rzm_table(cursor, rzm_data)
            conn.commit()
            print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] Inserted rows into {RZM_TABLE_NAME} from row 4000+.")

            # реєстр
            register_data = fetch_data_from_sheet(register_sheet)
            register_cols = get_max_columns(register_data)
            create_dynamic_table(cursor, REGISTER_TABLE_NAME, register_cols)
            insert_rows_dynamic(cursor, REGISTER_TABLE_NAME, register_data, register_cols)
            conn.commit()
            print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] Inserted {len(register_data)} rows into {REGISTER_TABLE_NAME} ({register_cols} cols).")

            # 3D замір ДОП
            sheet_data_dop = fetch_data_from_sheet(sheet_dop)
            insert_data_into_table_dop(cursor, sheet_data_dop)
            conn.commit()
            print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] Inserted {len(sheet_data_dop)} rows into {TABLE_NAME_DOP}.")

            # Виконані
            register_data_closed = fetch_data_from_sheet(register_sheet_closed)
            register_closed_cols = get_max_columns(register_data_closed)
            create_dynamic_table(cursor, REGISTER_TABLE_NAME_CLOSED, register_closed_cols)
            insert_rows_dynamic(cursor, REGISTER_TABLE_NAME_CLOSED, register_data_closed, register_closed_cols)
            conn.commit()
            print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] Inserted {len(register_data_closed)} rows into {REGISTER_TABLE_NAME_CLOSED} ({register_closed_cols} cols).")

            # data-plan (dynamic width)
            plan_data = fetch_data_from_sheet(plan_sheet)
            plan_cols = get_max_columns(plan_data)
            create_dynamic_table(cursor, DATA_PLAN_TABLE_NAME, plan_cols)
            insert_rows_dynamic(cursor, DATA_PLAN_TABLE_NAME, plan_data, plan_cols)
            conn.commit()
            print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] Inserted {len(plan_data)} rows into {DATA_PLAN_TABLE_NAME} ({plan_cols} cols).")

            # data-plan-date (dynamic width)
            plan_date_data = fetch_data_from_sheet(plan_date_sheet)
            plan_date_cols = get_max_columns(plan_date_data)
            create_dynamic_table(cursor, DATA_PLAN_DATE_TABLE_NAME, plan_date_cols)
            insert_rows_dynamic(cursor, DATA_PLAN_DATE_TABLE_NAME, plan_date_data, plan_date_cols)
            conn.commit()
            print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] Inserted {len(plan_date_data)} rows into {DATA_PLAN_DATE_TABLE_NAME} ({plan_date_cols} cols).")

            # data-rec (dynamic width)
            rec_data = fetch_data_from_sheet(rec_sheet)
            rec_cols = get_max_columns(rec_data)
            create_dynamic_table(cursor, DATA_REC_TABLE_NAME, rec_cols)
            insert_rows_dynamic(cursor, DATA_REC_TABLE_NAME, rec_data, rec_cols)
            conn.commit()
            print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] Inserted {len(rec_data)} rows into {DATA_REC_TABLE_NAME} ({rec_cols} cols).")

            # users (dynamic width)
            users_data = fetch_data_from_sheet(users_sheet)
            users_cols = get_max_columns(users_data)
            create_dynamic_table(cursor, USERS_TABLE_NAME, users_cols)
            insert_rows_dynamic(cursor, USERS_TABLE_NAME, users_data, users_cols)
            conn.commit()
            print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] Inserted {len(users_data)} rows into {USERS_TABLE_NAME} ({users_cols} cols).")

            # data-designer (Замовлення + Конструкторські, без фільтрації закритих)
            designer_orders_data = fetch_data_from_sheet(designer_orders_sheet)
            designer_constr_data = fetch_data_from_sheet(designer_constr_sheet)
            designer_headers, designer_rows = build_designer_rows(designer_orders_data, designer_constr_data)
            designer_inserted = insert_rows_current_fixed_headers(
                cursor,
                DATA_DESIGNER_TABLE_NAME,
                [designer_headers, *designer_rows],
                designer_headers,
                header_rows_to_skip=1,
            )
            conn.commit()
            print(
                f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] "
                f"Current sync {DATA_DESIGNER_TABLE_NAME}: {designer_inserted} рядків."
            )

            production_source_data = [
                (sheet_name, fetch_data_from_sheet(worksheet))
                for sheet_name, worksheet in production_source_sheets
            ]
            production_headers, production_rows = build_production_rows(production_source_data, designer_rows)
            production_inserted = insert_rows_current_fixed_headers(
                cursor,
                DATA_PRODUCTION_TABLE_NAME,
                [production_headers, *production_rows],
                production_headers,
                header_rows_to_skip=1,
            )
            conn.commit()
            print(
                f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] "
                f"Current sync {DATA_PRODUCTION_TABLE_NAME}: {production_inserted} рядків."
            )

            metal_source_data = fetch_data_from_sheet(metal_source_sheet)
            metal_headers, metal_rows = build_metal_rows(metal_source_data, designer_rows)
            metal_inserted = insert_rows_current_fixed_headers(
                cursor,
                DATA_METAL_TABLE_NAME,
                [metal_headers, *metal_rows],
                metal_headers,
                header_rows_to_skip=1,
            )
            conn.commit()
            print(
                f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] "
                f"Current sync {DATA_METAL_TABLE_NAME}: {metal_inserted} рядків."
            )

            # current snapshot: main (тільки актуальні дані)
            main_data = fetch_data_from_sheet(append_main_sheet)
            main_inserted = insert_rows_current_fixed_headers(cursor, APPEND_MAIN_TABLE_NAME, main_data, APPEND_MAIN_HEADERS, header_rows_to_skip=1)
            conn.commit()
            print(
                f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] "
                f"Current sync {APPEND_MAIN_TABLE_NAME}: {main_inserted} актуальних рядків."
            )

            # current snapshot: parts (тільки актуальні дані)
            parts_data = fetch_data_from_sheet(append_parts_sheet)
            parts_inserted = insert_rows_current_fixed_headers(cursor, APPEND_PARTS_TABLE_NAME, parts_data, APPEND_PARTS_HEADERS, header_rows_to_skip=1)
            conn.commit()
            print(
                f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] "
                f"Current sync {APPEND_PARTS_TABLE_NAME}: {parts_inserted} актуальних рядків."
            )

            await asyncio.sleep(180)
    except Exception as e:
        print(f"Помилка під час оновлення Google Sheets: {e}")
        raise
    finally:
        try:
            if 'cursor' in locals():
                cursor.close()
        except Exception:
            pass
        try:
            if 'conn' in locals():
                conn.close()
        except Exception:
            pass

def get_max_columns(data):
    return max((len(row) for row in data), default=1)


def create_dynamic_table(cursor, table_name, column_count):
    cursor.execute(f"DROP TABLE IF EXISTS {table_name};")
    cols_sql = ", ".join([f"column{i} TEXT" for i in range(1, column_count + 1)])
    cursor.execute(
        f"CREATE TABLE IF NOT EXISTS {table_name} (id SERIAL PRIMARY KEY, {cols_sql});"
    )


def insert_rows_dynamic(cursor, table_name, data, column_count):
    cursor.execute(f"TRUNCATE TABLE {table_name} RESTART IDENTITY;")
    cols = ", ".join([f"column{i}" for i in range(1, column_count + 1)])
    placeholders = ", ".join(["%s"] * column_count)
    query = f"INSERT INTO {table_name} ({cols}) VALUES ({placeholders})"

    rows_to_insert = []
    for row in data:
        # skip fully empty rows
        if all(v is None or str(v).strip() == "" for v in row):
            continue
        # trim/pad
        row = row[:column_count]
        if len(row) < column_count:
            row.extend([None] * (column_count - len(row)))
        rows_to_insert.append(row)

    if rows_to_insert:
        execute_batch(cursor, query, rows_to_insert, page_size=500)


def _build_row_hash(sheet_name, row):
    row_payload = json.dumps(row, ensure_ascii=False)
    return hashlib.sha256(f"{sheet_name}|{row_payload}".encode("utf-8")).hexdigest()


def insert_rows_append_only(cursor, table_name, spreadsheet_id, sheet_name, data, header_rows_to_skip=1):
    rows_to_insert = []
    for idx, row in enumerate(data):
        if idx < header_rows_to_skip:
            continue
        if all(v is None or str(v).strip() == "" for v in row):
            continue

        row_payload = json.dumps(row, ensure_ascii=False)
        row_hash = _build_row_hash(sheet_name, row)
        rows_to_insert.append((spreadsheet_id, sheet_name, idx + 1, row_hash, row_payload))

    if not rows_to_insert:
        return 0

    query = f'''
        INSERT INTO {table_name} (
            source_spreadsheet,
            source_sheet,
            source_row_index,
            row_hash,
            row_data
        ) VALUES %s
        ON CONFLICT (source_spreadsheet, source_sheet, row_hash)
        DO NOTHING
        RETURNING 1;
    '''

    execute_values(
        cursor,
        query,
        rows_to_insert,
        template="(%s, %s, %s, %s, %s::jsonb)",
        page_size=500,
    )
    inserted = cursor.fetchall()
    return len(inserted)


def insert_rows_append_only_fixed_headers(
    cursor,
    table_name,
    spreadsheet_id,
    sheet_name,
    data,
    headers,
    header_rows_to_skip=1,
):
    column_names = ensure_append_table_schema_from_headers(cursor, table_name, headers)
    width = len(column_names)

    rows_to_insert = []
    for idx, row in enumerate(data):
        if idx < header_rows_to_skip:
            continue
        if all(v is None or str(v).strip() == "" for v in row):
            continue

        padded = list(row[:width])
        if len(padded) < width:
            padded.extend([None] * (width - len(padded)))

        row_map = {headers[i]: padded[i] for i in range(width)}
        row_payload = json.dumps(row_map, ensure_ascii=False)
        row_hash = hashlib.sha256(
            f"{sheet_name}|{json.dumps(padded, ensure_ascii=False)}".encode("utf-8")
        ).hexdigest()

        normalized_values = [None if v is None else str(v) for v in padded]
        rows_to_insert.append(
            (
                spreadsheet_id,
                sheet_name,
                idx + 1,
                row_hash,
                row_payload,
                *normalized_values,
            )
        )

    if not rows_to_insert:
        return 0

    fixed_columns = [
        "source_spreadsheet",
        "source_sheet",
        "source_row_index",
        "row_hash",
        "row_data",
    ]
    insert_columns = fixed_columns + column_names
    sql_columns = ", ".join(quote_ident(col) for col in insert_columns)

    placeholders = ["%s", "%s", "%s", "%s", "%s::jsonb"] + ["%s"] * width
    template = "(" + ", ".join(placeholders) + ")"

    query = f'''
        INSERT INTO {table_name} ({sql_columns}) VALUES %s
        ON CONFLICT (source_spreadsheet, source_sheet, row_hash)
        DO NOTHING
        RETURNING 1;
    '''

    execute_values(
        cursor,
        query,
        rows_to_insert,
        template=template,
        page_size=500,
    )
    inserted = cursor.fetchall()
    return len(inserted)


def insert_rows_append_only_structured(cursor, table_name, spreadsheet_id, sheet_name, data, header_rows_to_skip=1):
    header_row_index = max(header_rows_to_skip - 1, 0)
    if len(data) <= header_row_index:
        return 0

    headers = data[header_row_index]
    if not headers:
        return 0

    column_names = build_unique_columns(headers)
    ensure_append_table_columns(cursor, table_name, column_names)

    rows_to_insert = []
    for idx, row in enumerate(data):
        if idx <= header_row_index:
            continue
        if all(v is None or str(v).strip() == "" for v in row):
            continue

        padded = list(row[: len(column_names)])
        if len(padded) < len(column_names):
            padded.extend([None] * (len(column_names) - len(padded)))

        row_map = {column_names[i]: padded[i] for i in range(len(column_names))}
        row_payload = json.dumps(row_map, ensure_ascii=False)
        row_hash = hashlib.sha256(
            f"{sheet_name}|{json.dumps(padded, ensure_ascii=False)}".encode("utf-8")
        ).hexdigest()

        normalized_values = [None if v is None else str(v) for v in padded]
        rows_to_insert.append(
            (
                spreadsheet_id,
                sheet_name,
                idx + 1,
                row_hash,
                row_payload,
                *normalized_values,
            )
        )

    if not rows_to_insert:
        return 0

    fixed_columns = [
        "source_spreadsheet",
        "source_sheet",
        "source_row_index",
        "row_hash",
        "row_data",
    ]
    insert_columns = fixed_columns + column_names
    sql_columns = ", ".join(quote_ident(col) for col in insert_columns)

    placeholders = ["%s", "%s", "%s", "%s", "%s::jsonb"] + ["%s"] * len(column_names)
    template = "(" + ", ".join(placeholders) + ")"

    query = f'''
        INSERT INTO {table_name} ({sql_columns}) VALUES %s
        ON CONFLICT (source_spreadsheet, source_sheet, row_hash)
        DO NOTHING
        RETURNING 1;
    '''

    execute_values(
        cursor,
        query,
        rows_to_insert,
        template=template,
        page_size=500,
    )
    inserted = cursor.fetchall()
    return len(inserted)

# =========================
# Entrypoint
# =========================
if __name__ == '__main__':
    while True:
        if not is_work_time():
            print("Не робочий час. Очікування...")
            time.sleep(60)
            continue

        if is_internet_available():
            try:
                asyncio.run(update_google_sheets())
            except Exception as e:
                print(f"Скрипт перезапускається через помилку: {e}")
                time.sleep(5)
        else:
            print("Інтернет недоступний. Очікування з'єднання...")
            time.sleep(5)
