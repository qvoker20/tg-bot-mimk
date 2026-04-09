
from psycopg2.extras import execute_batch
from oauth2client.service_account import ServiceAccountCredentials
from datetime import datetime
from dotenv import load_dotenv
import asyncio
import socket
import time
import gspread
import psycopg2
from psycopg2.extras import execute_batch
from oauth2client.service_account import ServiceAccountCredentials
from datetime import datetime
import os
from dotenv import load_dotenv

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

JSON_KEY_FILE = os.environ.get('JSON_KEY_FILE')


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

        conn = get_pg_connection()
        cursor = conn.cursor()

        # Create fixed-schema tables once
        create_table(cursor)
        create_second_table(cursor)
        create_rzm_table(cursor)
        create_table_dop(cursor)
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
