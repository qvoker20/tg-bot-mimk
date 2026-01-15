# MIM-K Telegram Bot System

## 📌 Опис проєкту

**MIM-K** — це внутрішня автоматизована система на базі **Telegram-бота**, призначена для:
- керування користувачами та ролями;
- роботи із замірами та адаптаціями;
- обробки виробничих процесів (перерізи, проблеми);
- інтеграції з Google Sheets та Google Apps Script;
- використання AI (OpenAI + ChromaDB) як внутрішньої бази знань;
- автоматичного резервного копіювання коду.

Система розрахована на використання в межах організації з чіткою рольовою моделлю доступів.

---

## 🧱 Архітектура

### Основні компоненти

- **Telegram-бот** — `teg_bot_mimk.py`
- **Адмін-панель (Flask)** — `app.py`, `templates/`
- **PostgreSQL** — основна база даних
- **Google Sheets Sync** — `google_parset_active.py`
- **Handlers** — `handlers/`
- **Utils** — `utils/`
- **AI** — OpenAI API + ChromaDB (локальне сховище)
- **JobQueue** — планувальник задач (python-telegram-bot)

---

## 🗂 Структура проєкту

tg-bot/
├── teg_bot_mimk.py
├── app.py
├── google_parset_active.py
├── handlers/
│ ├── zamiry_handlers.py
│ ├── production_handlers.py
│ ├── mimk_ai_handlers.py
│ ├── admin_handlers_custom.py
│ └── ...
├── utils/
│ ├── db_utils.py
│ └── ...
├── chroma_db/
├── docs/
│ └── functions.md
├── requirements.txt
└── README.md


---

## 🗄 База даних (PostgreSQL)

### Таблиця `database_app_userdatatelegram`

| Поле | Тип | Опис |
|----|----|----|
| id | SERIAL | Primary Key |
| telegram_id | BIGINT | Унікальний Telegram ID |
| name | TEXT | ПІБ користувача |
| phone_number | TEXT | Телефон |
| username | TEXT | Роль |
| date_registered | TIMESTAMP | Дата реєстрації |

---

### Таблиця `registration_requests`

| Поле | Тип |
|----|----|
| id | SERIAL |
| telegram_id | BIGINT |
| first_name | TEXT |
| last_name | TEXT |
| position | TEXT |
| phone_number | TEXT |
| date_submitted | TIMESTAMP |
| status | TEXT (`pending` / `registered`) |

---

## 👥 Ролі та доступи

| Роль | Доступ |
|----|------|
| admin | Повний доступ |
| adminpre | AI, Конструктор |
| конструктор | Конструктор |
| замірник | Заміри |
| менеджер / директор / user | Базові функції |

> Перевірка доступу здійснюється по полю `username`.

---

## 🔄 Основні процеси

### Реєстрація користувача
- Самостійна через Telegram-бот
- Через адмін-панель
- Ручна реєстрація адміністратором у боті

### Заміри
- Пошук по номеру замовлення
- Пошук конкретної позиції
- Подача запитів на адаптацію
- Сервісні запити в групу Telegram

### Виробництво
- Перерізи (інтеграція з Google Apps Script)
- Проблеми (інтеграція з Google Apps Script)
- Пошук закупівель і деталей
- Генерація PDF при великій кількості результатів

### AI MIM-K
- Відповіді на запити користувачів
- Додавання знань у базу
- Локальна ChromaDB (`./chroma_db`)

---

## ⏱ Планувальник задач (JobQueue)

| Завдання | Час |
|-------|----|
| Щоденні заміри | 08:30 |
| Перевірка змін | кожну хвилину |
| Перевірка порожніх значень | кожну хвилину |
| Резервне копіювання | 23:59 |

---

## 💾 Резервні копії

- Автоматичні щоденні ZIP-бекапи
- Ручна команда `/savefiletgbot`
- Архів надсилається адміну в Telegram

---

## ⚙️ Встановлення та запуск

### 1. Встановити залежності

```bash
pip install -r requirements.txt

3. Запуск
py teg_bot_mimk.py
py app.py
py google_parset_active.py