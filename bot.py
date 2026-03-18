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
    expire TEXT,
    notified_2days INTEGER DEFAULT 0,
    notified_expired INTEGER DEFAULT 0
)
""")

cursor.execute("""
CREATE TABLE IF NOT EXISTS payments (
    payment_id TEXT PRIMARY KEY,
    user_id INTEGER,
    amount INTEGER,
    status TEXT,
    date TEXT
)
""")

conn.commit()

# ===== ПРОКСИ =====
PROXIES = [
"https://t.me/proxy?server=213.165.42.119&port=443&secret=5c95fa91e3ba74956468698b3c3ae6ae",
"https://t.me/proxy?server=64.188.124.119&port=443&secret=0feeb7f54cbb7b09c6426c1f1cb984b8"
]

# ===== КНОПКИ =====
def main_kb():
    kb = types.InlineKeyboardMarkup()
    kb.add(types.InlineKeyboardButton("💳 Купить / Продлить (149₽)", callback_data="buy"))
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

    await message.answer("🚀 Telegram без блокировок", reply_markup=main_kb())

# ===== ОПЛАТА =====
def create_payment(user_id):
    payment = Payment.create({
        "amount": {"value": "149.00", "currency": "RUB"},
        "confirmation": {"type": "redirect", "return_url": "https://t.me/antibloktg_bot"},
        "capture": True,
        "description": str(user_id)
    }, str(uuid.uuid4()))

    # сохраняем в БД
    cursor.execute("""
    INSERT INTO payments (payment_id, user_id, amount, status, date)
    VALUES (?, ?, ?, ?, ?)
    """, (payment.id, user_id, 149, "pending", datetime.now().isoformat()))
    conn.commit()

    return payment.confirmation.confirmation_url

@dp.callback_query_handler(lambda c: c.data == "buy")
async def buy(callback: types.CallbackQuery):
    url = create_payment(callback.from_user.id)

    kb = types.InlineKeyboardMarkup()
    kb.add(types.InlineKeyboardButton("💳 Оплатить", url=url))

    await bot.send_message(callback.from_user.id, "Оплати доступ:", reply_markup=kb)

# ===== ВЫДАЧА =====
def get_proxies_message(expire):
    text = f"✅ Доступ активирован\n\nДо: {expire}"
    kb = types.InlineKeyboardMarkup()
    kb.add(types.InlineKeyboardButton("🚀 Подключиться", url=PROXIES[0]))
    return text, kb

# ===== ПРОВЕРКА ОПЛАТ =====
async def check_payments():
    while True:
        cursor.execute("SELECT payment_id, user_id FROM payments WHERE status='pending'")
        rows = cursor.fetchall()

        for pid, user_id in rows:
            payment = Payment.find_one(pid)

            if payment.status == "succeeded":
                cursor.execute("UPDATE payments SET status='done' WHERE payment_id=?", (pid,))

                cursor.execute("SELECT expire FROM users WHERE user_id=?", (user_id,))
                row = cursor.fetchone()

                if row and row[0] != "0":
                    expire = datetime.fromisoformat(row[0])
                    new_expire = max(expire, datetime.now()) + timedelta(days=30)
                else:
                    new_expire = datetime.now() + timedelta(days=30)

                cursor.execute("""
                UPDATE users SET expire=? WHERE user_id=?
                """, (new_expire.isoformat(), user_id))

                conn.commit()

                text, kb = get_proxies_message(new_expire)
                await bot.send_message(user_id, text, reply_markup=kb)

        await asyncio.sleep(10)

# ===== СТАТИСТИКА =====
@dp.callback_query_handler(lambda c: c.data == "stats")
async def stats(callback):
    cursor.execute("SELECT COUNT(*) FROM users")
    users_count = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(*), SUM(amount) FROM payments WHERE status='done'")
    p = cursor.fetchone()

    pays = p[0] if p[0] else 0
    money = p[1] if p[1] else 0

    await bot.send_message(callback.from_user.id,
        f"📊\nПользователей: {users_count}\nОплат: {pays}\nДоход: {money} RUB")

# ===== ЗАПУСК =====
if __name__ == "__main__":
    loop = asyncio.get_event_loop()
    loop.create_task(check_payments())
    executor.start_polling(dp, skip_updates=True)
