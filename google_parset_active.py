
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

JSON_KEY_FILE = os.environ.get('JSON_KEY_FILE')

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
    scope = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']
    credentials = ServiceAccountCredentials.from_json_keyfile_name(json_key_file, scope)
    client = gspread.authorize(credentials)
    return client


def fetch_data_from_sheet(sheet):
    return sheet.get_all_values()


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
            column24 TEXT
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
            column24 TEXT
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

    cols = ", ".join([f"column{i}" for i in range(1, 25)])

    rows_to_insert = []
    for row in data:
        # Ваша логіка: якщо більше 24 — видалити елемент з індексом 24
        if len(row) > 24:
            del row[24]

        row = row[:24]
        if len(row) < 24:
            row.extend([None] * (24 - len(row)))
        rows_to_insert.append(row)

    query = f"INSERT INTO {REGISTER_TABLE_NAME} ({cols}) VALUES ({', '.join(['%s'] * 24)})"
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

    cols = ", ".join([f"column{i}" for i in range(1, 25)])

    rows_to_insert = []
    for row in data:
        if len(row) > 24:
            del row[24]

        row = row[:24]
        if len(row) < 24:
            row.extend([None] * (24 - len(row)))
        rows_to_insert.append(row)

    query = f"INSERT INTO {REGISTER_TABLE_NAME_CLOSED} ({cols}) VALUES ({', '.join(['%s'] * 24)})"
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

        conn = get_pg_connection()
        cursor = conn.cursor()

        # Create tables
        create_table(cursor)
        create_second_table(cursor)
        create_rzm_table(cursor)
        create_register_table(cursor)
        create_table_dop(cursor)
        create_register_table_closed(cursor)
        conn.commit()

        while True:
            data = fetch_data_from_sheet(sheet)
            insert_data_into_db(cursor, data)
            conn.commit()
            print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] Inserted {len(data)} rows into {TABLE_NAME}.")

            second_data = fetch_data_from_sheet(second_sheet)
            insert_data_into_second_table(cursor, second_data)
            conn.commit()
            print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] Inserted {len(second_data)} rows into {SECOND_TABLE_NAME}.")

            rzm_data = fetch_data_from_sheet(rzm_sheet)
            insert_data_into_rzm_table(cursor, rzm_data)
            conn.commit()
            print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] Inserted rows into {RZM_TABLE_NAME} from row 4000+.")

            register_data = fetch_data_from_sheet(register_sheet)
            insert_data_into_register_table(cursor, register_data)
            conn.commit()
            print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] Inserted {len(register_data)} rows into {REGISTER_TABLE_NAME}.")

            sheet_data_dop = fetch_data_from_sheet(sheet_dop)
            insert_data_into_table_dop(cursor, sheet_data_dop)
            conn.commit()
            print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] Inserted {len(sheet_data_dop)} rows into {TABLE_NAME_DOP}.")

            register_data_closed = fetch_data_from_sheet(register_sheet_closed)
            insert_data_into_register_table_closed(cursor, register_data_closed)
            conn.commit()
            print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] Inserted {len(register_data_closed)} rows into {REGISTER_TABLE_NAME_CLOSED}.")

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
