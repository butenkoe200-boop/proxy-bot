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
    kb.add(types.InlineKeyboardButton("💳 Купить / Продлить (299₽)", callback_data="buy"))
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
        "🚀 Telegram без блокировок\n\n"
        "— Подключение за 30 секунд\n"
        "— Работает на мобильном\n"
        "— Без лагов\n\n"
        "Нажми ниже 👇",
        reply_markup=main_kb()
    )

# ===== ОПЛАТА =====
def create_payment(user_id):
    payment = Payment.create({
        "amount": {"value": "299.00", "currency": "RUB"},
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
def get_proxies_message(expire):
    text = (
        f"✅ Доступ активирован\n\n"
        f"📅 До: {expire}\n\n"
        f"👇 Выбери сервер:"
    )

    kb = types.InlineKeyboardMarkup()
    kb.add(types.InlineKeyboardButton("🚀 Основной сервер", url=PROXIES[0]))
    kb.add(types.InlineKeyboardButton("🛟 Резервный сервер", url=PROXIES[1]))
    kb.add(types.InlineKeyboardButton("🛠 Поддержка", url="https://t.me/suport_antibloktg"))

    return text, kb

# ===== ПРОВЕРКА ОПЛАТ =====
async def check_payments():
    while True:
        for pid in list(payments.keys()):
            payment = Payment.find_one(pid)

            if payment.status == "succeeded":
                user_id = payments[pid]

                cursor.
execute("SELECT expire FROM users WHERE user_id=?", (user_id,))
                row = cursor.fetchone()

                if row and row[0] != "0":
                    expire = datetime.fromisoformat(row[0])
                    new_expire = max(expire, datetime.now()) + timedelta(days=30)
                else:
                    new_expire = datetime.now() + timedelta(days=30)

                cursor.execute("""
                UPDATE users 
                SET expire=?, notified_2days=0, notified_expired=0 
                WHERE user_id=?
                """, (new_expire.isoformat(), user_id))

                cursor.execute("INSERT INTO payments VALUES (?, ?, ?)", (user_id, 299, datetime.now().isoformat()))

                conn.commit()

                text, kb = get_proxies_message(new_expire)

                await bot.send_message(user_id, text, reply_markup=kb)

                del payments[pid]

        await asyncio.sleep(10)

# ===== УВЕДОМЛЕНИЯ БЕЗ СПАМА =====
async def reminders():
    while True:
        cursor.execute("SELECT user_id, expire, notified_2days, notified_expired FROM users WHERE expire != '0'")
        users = cursor.fetchall()

        now = datetime.now()

        for u in users:
            user_id, exp, n2, ne = u
            expire = datetime.fromisoformat(exp)

            # за 2 дня
            if 0 < (expire - now).days <= 2 and n2 == 0:
                await bot.send_message(
                    user_id,
                    "⚠️ Осталось меньше 2 дней доступа\n\nПродли сейчас 👇",
                    reply_markup=types.InlineKeyboardMarkup().add(
                        types.InlineKeyboardButton("💳 Продлить (299₽)", callback_data="buy")
                    )
                )
                cursor.execute("UPDATE users SET notified_2days=1 WHERE user_id=?", (user_id,))
                conn.commit()

            # истек
            if expire < now and ne == 0:
                await bot.send_message(
                    user_id,
                    "❌ Доступ закончился\n\nПродли доступ 👇",
                    reply_markup=types.InlineKeyboardMarkup().add(
                        types.InlineKeyboardButton("💳 Продлить (299₽)", callback_data="buy")
                    )
                )
                cursor.execute("UPDATE users SET notified_expired=1 WHERE user_id=?", (user_id,))
                conn.commit()

        await asyncio.sleep(3600)

# ===== АДМИН =====
@dp.message_handler(commands=['admin'])
async def admin(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        return
    await message.answer("⚙️ Админ панель", reply_markup=admin_kb())

@dp.callback_query_handler(lambda c: c.data == "all_users")
async def all_users(callback: types.CallbackQuery):
    cursor.execute("SELECT user_id, username, expire FROM users")
    data = cursor.fetchall()

    text = "👥 Все пользователи:\n\n"
    for u in data[:30]:
        username = f"@{u[1]}" if u[1] else "нет"
        text += f"{u[0]} | {username} | {u[2]}\n"

    await bot.send_message(callback.from_user.id, text)

@dp.callback_query_handler(lambda c: c.data == "active")
async def active(callback):
    now = datetime.now().isoformat()
    cursor.execute("SELECT user_id, username FROM users WHERE expire > ?", (now,))
    data = cursor.fetchall()

    text = "✅ Активные:\n\n"
    for u in data[:30]:
        username = f"@{u[1]}" if u[1] else "нет"
        text += f"{u[0]} | {username}\n"

    await bot.send_message(callback.from_user.id, text)

@dp.callback_query_handler(lambda c: c.data == "expired")
async def expired(callback):
    now = datetime.now().isoformat()
    cursor.execute("SELECT user_id, username FROM users WHERE expire <= ?", (now,))
    data = cursor.fetchall()

    text = "❌ Неактивные:\n\n"
    for u in data[:30]:
        username = f"@{u[1]}" if u[1] else "нет"
        text += f"{u[0]} | {username}\n"

    await bot.send_message(callback.from_user.id, text)

@dp.callback_query_handler(lambda c: c.data == "stats")
async def stats(callback):
    cursor.execute("SELECT COUNT(*) FROM users")
users_count = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(*), SUM(amount) FROM payments")
    p = cursor.fetchone()

    pays = p[0] if p[0] else 0
    money = p[1] if p[1] else 0

    await bot.send_message(callback.from_user.id,
        f"📊\nПользователей: {users_count}\nОплат: {pays}\nДоход: {money} RUB")

@dp.callback_query_handler(lambda c: c.data == "find")
async def find(callback):
    await bot.send_message(callback.from_user.id, "Введи ID пользователя")

@dp.message_handler(lambda m: m.text.isdigit())
async def find_user(message):
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
if name == "__main__":
    loop = asyncio.get_event_loop()
    loop.create_task(check_payments())
    loop.create_task(reminders())
    executor.start_polling(dp, skip_updates=True)
