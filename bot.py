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
    username TEXT,
    first_name TEXT,
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

# ===== ПРОКСИ =====
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
    kb.add(types.InlineKeyboardButton("👥 Все пользователи", callback_data="all_users"))
    kb.add(types.InlineKeyboardButton("✅ Активные", callback_data="active"))
    kb.add(types.InlineKeyboardButton("❌ Неактивные", callback_data="expired"))
    kb.add(types.InlineKeyboardButton("💰 Статистика", callback_data="stats"))
    kb.add(types.InlineKeyboardButton("🔍 Найти пользователя", callback_data="find"))
    return kb

# ===== СТАРТ =====
@dp.message_handler(commands=['start'])
async def start(message: types.Message):

    cursor.execute("""
    INSERT OR REPLACE INTO users (user_id, username, first_name, expire)
    VALUES (?, ?, ?, COALESCE((SELECT expire FROM users WHERE user_id=?), '0'))
    """, (
        message.from_user.id,
        message.from_user.username,
        message.from_user.first_name,
        message.from_user.id
    ))

    conn.commit()

    await message.answer(
        "🚀 Telegram без блокировок\n\nНажми ниже 👇",
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

# ===== ВЫДАЧА =====
def get_proxies_text(expire):
    text = f"✅ Доступ до {expire}\n\n🔑 Подключись:\n\n"
    for p in PROXIES:
        text += p + "\n\n"
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
                cursor.execute("INSERT INTO payments VALUES (?, ?, ?)", (user_id, 149, datetime.now().isoformat()))

                conn.commit()

                await bot.send_message(user_id, get_proxies_text(new_expire))

                del payments[pid]

        await asyncio.sleep(10)

# ===== АДМИН =====
@dp.message_handler(commands=['admin'])
async def admin(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        return
    await message.answer("⚙️ Админ панель", reply_markup=admin_kb())

# ===== ВСЕ ПОЛЬЗОВАТЕЛИ =====
@dp.callback_query_handler(lambda c: c.data == "all_users")
async def all_users(callback: types.CallbackQuery):
    cursor.execute("SELECT user_id, username, expire FROM users")
    data = cursor.fetchall()

    text = "👥 Все пользователи:\n\n"
    for u in data[:30]:
        username = f"@{u[1]}" if u[1] else "нет"
        text += f"{u[0]} | {username} | {u[2]}\n"

    await bot.send_message(callback.from_user.id, text)

# ===== АКТИВНЫЕ =====
@dp.callback_query_handler(lambda c: c.data == "active")
async def active(callback: types.CallbackQuery):
    now = datetime.now().isoformat()

    cursor.execute("SELECT user_id, username, expire FROM users WHERE expire > ?", (now,))
    data = cursor.fetchall()

    text = "✅ Активные:\n\n"
    for u in data[:30]:
        username = f"@{u[1]}" if u[1] else "нет"
        text += f"{u[0]} | {username}\n"

    await bot.send_message(callback.from_user.id, text)

# ===== НЕАКТИВНЫЕ =====
@dp.callback_query_handler(lambda c: c.data == "expired")
async def expired(callback: types.CallbackQuery):
    now = datetime.now().isoformat()

    cursor.execute("SELECT user_id, username FROM users WHERE expire <= ?", (now,))
    data = cursor.fetchall()

    text = "❌ Неактивные:\n\n"
    for u in data[:30]:
        username = f"@{u[1]}" if u[1] else "нет"
        text += f"{u[0]} | {username}\n"

    await bot.send_message(callback.from_user.id, text)

# ===== СТАТИСТИКА =====
@dp.callback_query_handler(lambda c: c.data == "stats")
async def stats(callback: types.CallbackQuery):
    cursor.execute("SELECT COUNT(*) FROM users")
    users_count = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(*), SUM(amount) FROM payments")
    p = cursor.fetchone()

    pays = p[0] if p[0] else 0
    money = p[1] if p[1] else 0

    text = f"📊\nПользователей: {users_count}\nОплат: {pays}\nДоход: {money} RUB"

    await bot.send_message(callback.from_user.id, text)

# ===== ПОИСК =====
@dp.callback_query_handler(lambda c: c.data == "find")
async def find(callback: types.CallbackQuery):
    await bot.send_message(callback.from_user.id, "Введи ID пользователя")

@dp.message_handler(lambda m: m.text.isdigit())
async def find_user(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        return

    user_id = int(message.text)

    cursor.execute("SELECT user_id, username, expire FROM users WHERE user_id=?", (user_id,))
    u = cursor.fetchone()

    if not u:
        await message.answer("❌ Не найден")
        return

    username = f"@{u[1]}" if u[1] else "нет"
    await message.answer(f"👤 {u[0]}\n{username}\nДо: {u[2]}")

# ===== ЗАПУСК =====
if __name__ == "__main__":
    loop = asyncio.get_event_loop()
    loop.create_task(check_payments())
    executor.start_polling(dp, skip_updates=True)
