# Production FastAPI

## Що зроблено

- Вхід по телефону у форматі `380XXXXXXXXX`
- У полі телефону префікс `380` стоїть одразу
- Відправка коду в Telegram через `TELEGRAM_BOT_TOKEN`
- У повідомленні в Telegram: `Вхід у виробництво!`
- Сторінки після авторизації: `Головна`, `Комплектування`, `Запуски`, `Реєстр`
- Базова перевірка ролей через `PRODUCTION_ALLOWED_ROLES`
- Модульна структура FastAPI (`app/config.py`, `app/db.py`, `app/services`, `app/routers`, `app/schemas`)

## Налаштування

Використовуються змінні з кореневого `.env`:

- `SECRET_KEY`
- `PG_HOST`, `PG_PORT`, `PG_DBNAME`, `PG_USER`, `PG_PASSWORD`
- `TELEGRAM_BOT_TOKEN`

Опційно:

- `PRODUCTION_CODE_TTL` (секунди, дефолт 300)
- `PRODUCTION_ALLOWED_ROLES` (через кому, дефолт: `admin,adminpre`)

## Запуск

```powershell
cd Production
pip install -r requirements.txt
python main.py
```

Після запуску відкрийте:

- `http://127.0.0.1:5001/login`
