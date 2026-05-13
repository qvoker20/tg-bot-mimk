# Collectors

FastAPI-модуль для керування збиральним цехом.

Поточний стан:
- логін по номеру телефону;
- код підтвердження надсилається в Telegram;
- сесійний доступ до головної сторінки;
- старт на `127.0.0.1:9182`.

## Запуск

1. Встановити залежності:
   `pip install -r requirements.txt`
2. Переконатися, що у кореневому `.env` заповнені:
   - `PG_HOST`
   - `PG_PORT`
   - `PG_DBNAME`
   - `PG_USER`
   - `PG_PASSWORD`
   - `SECRET_KEY`
   - `TELEGRAM_BOT_TOKEN`
3. Запустити:
   `python main.py`