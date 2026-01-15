import sqlite3

USER_DATABASE_FILE = r'C:\Users\user\Desktop\tg-bot\google_sheet_data.db'

def get_user_data(telegram_id):
    conn = sqlite3.connect(USER_DATABASE_FILE)
    cursor = conn.cursor()
    try:
        cursor.execute('SELECT name, telegram_id, phone_number FROM database_app_userdatatelegram WHERE telegram_id = ?', (telegram_id,))
        user_data = cursor.fetchone()
    except Exception as e:
        user_data = None
    finally:
        cursor.close()
        conn.close()
    return user_data