import logging
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import CallbackContext
import chromadb
from openai import OpenAI
import psycopg2

PG_CONN = {
    'host': 'localhost',
    'port': 5433,  # ваш порт
    'dbname': 'parset_google_mimk',
    'user': 'postgres',
    'password': '123789456'
}

def get_pg_connection():
    return psycopg2.connect(**PG_CONN)

USER_DATABASE_FILE = r'C:\Users\user\Desktop\tg-bot\google_sheet_data.db'

def get_user_data(user_id):
    conn = get_pg_connection()
    cursor = conn.cursor()
    try:
        cursor.execute(
            "SELECT name, telegram_id, phone_number FROM database_app_userdatatelegram WHERE telegram_id = %s",
            (user_id,)
        )
        row = cursor.fetchone()
        return row if row else None
    finally:
        cursor.close()
        conn.close()

async def show_mimk_ai(update, context):
    keyboard = [
        [InlineKeyboardButton("Продажі", callback_data='ai_sales')],
        [InlineKeyboardButton("Технічні рішення", callback_data='ai_tech')],
        [InlineKeyboardButton("Додати знання", callback_data='ai_work')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    if update.callback_query:
        await update.callback_query.edit_message_text(
            "🤖 Оберіть напрямок для AI MIM-K:", reply_markup=reply_markup
        )
    else:
        await update.message.reply_text(
            "🤖 Оберіть напрямок для AI MIM-K:",
            reply_markup=reply_markup
        )

async def mimk_ai_button_handler(update: Update, context: CallbackContext):
    query = update.callback_query
    await query.answer()
    if query.data == 'ai_sales':
        await query.edit_message_text("Введіть питання для AI по продажах: \n\n⚠️для скасування запиту введіть 'відміна'⚠️")
        context.user_data["ai_mode"] = "sales"
    elif query.data == 'ai_tech':
        await query.edit_message_text("🛠у розробці🛠")
        context.user_data["ai_mode"] = "tech"
    elif query.data == 'ai_work':
        await query.edit_message_text("Введіть текст знання, яке потрібно додати:")
        context.user_data["ai_mode"] = "add_knowledge"

async def handle_mimk_ai_text(update: Update, context: CallbackContext, openai_client):
    user_id = update.message.from_user.id
    text = update.message.text.strip()
    user_data = get_user_data(user_id)

    if context.user_data.get("ai_mode") == "sales":
        if text.lower() == "відміна":
            context.user_data["ai_mode"] = None
            await update.message.reply_text("🤖AI-запит скасовано✅")
            return

        context.user_data["ai_mode"] = None
        await update.message.reply_text("🤖AI (Продажі) думає над відповіддю... 🌀")

        client = chromadb.PersistentClient(path="./chroma_db")
        collection = client.get_or_create_collection(name="knowledge")
        results = collection.query(query_texts=[text], n_results=3)
        context_knowledge = ""
        if results and results.get("documents"):
            docs = results["documents"][0]
            if docs:
                context_knowledge = "\n".join([f"- {d}" for d in docs if d])

        prompt = (
            "Ти — експерт з продажу меблів! "
            "Тобі пише менеджер, який описує ситуацію з клієнтом. "
            "Відповідай лише в межах описаної ситуації, та ігноруй попередні діалоги. кожне нове повідомлення це новий запит!"
            "Використовуй, якщо доречно, наступні знання з бази:\n"
            f"{context_knowledge}\n\n"
            "Опис ситуації від менеджера:\n"
            f"{text}"
        )

        try:
            response = openai_client.chat.completions.create(
                model="gpt-4.1",
                messages=[
                    {"role": "system", "content": "Ти — експерт з продажу меблів, допомагаєш менеджерам закривати угоди."},
                    {"role": "user", "content": prompt}
                ],
                max_tokens=2000,
                temperature=0.7,
            )
            answer = response.choices[0].message.content.strip()
            await update.message.reply_text(f"🤖 AI відповідь:\n{answer}")
        except Exception as e:
            await update.message.reply_text("⚠️ Сталася помилка при зверненні до AI.")
            logging.error(f"OpenAI error: {e}")
        return

    if context.user_data.get("ai_mode") == "add_knowledge":
        text_to_add = update.message.text.strip()
        if text_to_add.lower() == "відміна":
            context.user_data["ai_mode"] = None
            await update.message.reply_text("Додавання знання скасовано.")
            return

        client = chromadb.PersistentClient(path="./chroma_db")
        collection = client.get_or_create_collection(name="knowledge")
        import time
        doc_id = f"knowledge_{int(time.time())}"
        collection.add(documents=[text_to_add], ids=[doc_id])

        context.user_data["ai_mode"] = None
        await update.message.reply_text("Знання успішно додано до бази!")
        return