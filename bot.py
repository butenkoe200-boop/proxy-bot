import sqlite3
import uuid
import asyncio
from datetime import datetime, timedelta
from aiogram import Bot, Dispatcher, types
from aiogram.utils import executor
from yookassa import Payment, Configuration
import os

API_TOKEN = os.getenv("API_TOKEN")
SHOP_ID = os.getenv("SHOP_ID")
SECRET_KEY = os.getenv("SECRET_KEY")
ADMIN_ID = 6542324565

Configuration.account_id = SHOP_ID
Configuration.secret_key = SECRET_KEY

bot = Bot(token=API_TOKEN)
dp = Dispatcher(bot)

# ===== БАЗА =====
conn = sqlite3.connect("db.sqlite")
cursor = conn.cursor()

cursor.execute("""
CREATE TABLE IF NOT EXISTS users (
    user_id INTEGER PRIMARY KEY,
    expire TEXT
)
""")

cursor.execute("""
CREATE TABLE IF NOT EXISTS payments (
    user_id INTEGER,
    amount INTEGER,
    date TEXT
)
""")

conn.commit()

# ===== ПРОКСИ (НОВЫЕ) =====
PROXIES = [
"https://t.me/proxy?server=213.165.42.119&port=443&secret=5c95fa91e3ba74956468698b3c3ae6ae",
"https://t.me/proxy?server=64.188.124.119&port=443&secret=0feeb7f54cbb7b09c6426c1f1cb984b8"
]

payments = {}

# ===== КНОПКИ =====
def main_kb():
    kb = types.InlineKeyboardMarkup()
    kb.add(types.InlineKeyboardButton("💳 Купить / Продлить", callback_data="buy"))
    kb.add(types.InlineKeyboardButton("🛠 Поддержка", url="https://t.me/suport_antibloktg"))
    return kb

def admin_kb():
    kb = types.InlineKeyboardMarkup()
    kb.add(types.InlineKeyboardButton("👥 Пользователи", callback_data="users"))
    kb.add(types.InlineKeyboardButton("💰 Статистика", callback_data="stats"))
    return kb

# ===== СТАРТ =====
@dp.message_handler(commands=['start'])
async def start(message: types.Message):
    cursor.execute("INSERT OR IGNORE INTO users (user_id, expire) VALUES (?, ?)", (message.from_user.id, "0"))
    conn.commit()

    await message.answer(
        "🚀 Telegram без блокировок\n\n"
        "— Работает на мобильном\n"
        "— Без лагов\n"
        "— Несколько серверов\n\n"
        "Нажми ниже 👇",
        reply_markup=main_kb()
    )

# ===== ПОКУПКА =====
def create_payment(user_id):
    payment = Payment.create({
        "amount": {"value": "149.00", "currency": "RUB"},
        "confirmation": {"type": "redirect", "return_url": "https://t.me/antibloktg_bot"},
        "capture": True,
        "description": str(user_id)
    }, uuid.uuid4())

    payments[payment.id] = user_id
    return payment.confirmation.confirmation_url

@dp.callback_query_handler(lambda c: c.data == "buy")
async def buy(callback: types.CallbackQuery):
    url = create_payment(callback.from_user.id)

    kb = types.InlineKeyboardMarkup()
    kb.add(types.InlineKeyboardButton("💳 Оплатить", url=url))

    await bot.send_message(callback.from_user.id, "Оплати доступ:", reply_markup=kb)

# ===== ВЫДАЧА ДОСТУПА =====
def get_proxies_text(expire):
    text = "✅ Доступ активирован\n\n"
    text += f"📅 До: {expire}\n\n"
    text += "🔑 Подключись:\n\n"

    for i, p in enumerate(PROXIES, start=1):
        text += f"{i}️⃣ {p}\n\n"

    text += "🛠 Поддержка: https://t.me/suport_antibloktg"
    return text

# ===== ПРОВЕРКА ОПЛАТ =====
async def check_payments():
    while True:
        for pid in list(payments.keys()):
            payment = Payment.find_one(pid)

            if payment.status == "succeeded":
                user_id = payments[pid]

                cursor.execute("SELECT expire FROM users WHERE user_id=?", (user_id,))
                row = cursor.fetchone()

                if row and row[0] != "0":
                    expire = datetime.fromisoformat(row[0])
                    new_expire = max(expire, datetime.now()) + timedelta(days=30)
                else:
                    new_expire = datetime.now() + timedelta(days=30)

                cursor.execute("UPDATE users SET expire=? WHERE user_id=?", (new_expire.isoformat(), user_id))

                cursor.execute("INSERT INTO payments VALUES (?, ?, ?)",
                               (user_id, 149, datetime.now().isoformat()))

                conn.commit()

                await bot.send_message(
                    user_id,
                    get_proxies_text(new_expire)
                )

                del payments[pid]

        await asyncio.sleep(10)

# ===== АДМИН =====
@dp.message_handler(commands=['admin'])
async def admin(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        return

    await message.answer("⚙️ Админ панель", reply_markup=admin_kb())

# ===== СПИСОК ПОЛЬЗОВАТЕЛЕЙ =====
@dp.callback_query_handler(lambda c: c.data == "users")
async def users(callback: types.CallbackQuery):
    if callback.from_user.id != ADMIN_ID:
        return

    cursor.execute("SELECT user_id, expire FROM users")
    data = cursor.fetchall()

    text = "👥 Пользователи:\n\n"

    for u in data[:20]:
        text += f"{u[0]} | {u[1]}\n"

    await bot.send_message(callback.from_user.id, text)

# ===== СТАТИСТИКА =====
@dp.callback_query_handler(lambda c: c.data == "stats")
async def stats(callback: types.CallbackQuery):
    if callback.from_user.id != ADMIN_ID:
        return

    cursor.execute("SELECT COUNT(*) FROM users")
    users_count = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(*), SUM(amount) FROM payments")
    p = cursor.fetchone()

    pays = p[0] if p[0] else 0
    money = p[1] if p[1] else 0

    text = (
        f"📊 Статистика\n\n"
        f"👥 Пользователей: {users_count}\n"
        f"💳 Оплат: {pays}\n"
        f"💰 Доход: {money} RUB"
    )

    await bot.send_message(callback.from_user.id, text)

# ===== ЗАПУСК =====
if __name__ == "__main__":
    loop = asyncio.get_event_loop()
    loop.create_task(check_payments())
    executor.start_polling(dp, skip_updates=True)
